from concurrent.futures import ThreadPoolExecutor
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import func, select

from workforce.db import session_factory
from workforce.main import app
from workforce.models import (AgentConfigVersion, AgentProjectGrant, Approval, ArtifactVersion,
    DocumentDraftRun, Execution, ExecutionBriefContext, Outbox, PlanProposal, Task)
from workforce.worker import generate_step, complete_step
from workforce.artifacts import apply_approved_artifacts
from workforce import providers
from test_document_plans import recorded, decide


def admitted(client):
    headers, project, target, source, rows = recorded(client)
    response = decide(client, rows[0], headers)
    assert response.status_code == 200, response.text
    tasks = client.get('/api/tasks', params={'project_id': project['id']}).json()
    draft = next(t for t in tasks if t['title'] == 'Prepare a cited fixture draft')
    review = next(t for t in tasks if t['title'] == 'Review citations and unknowns')
    return headers, project, target, source, draft, review


def run(client, task, headers, digest=None):
    return client.post(f"/api/tasks/{task['id']}/draft-fixture", json={
        'plan_payload_hash': digest or task['document_plan_hash'], 'root_cap': '1.0'}, headers=headers)


def proposed(client, headers, task):
    response = run(client, task, headers)
    assert response.status_code == 202, response.text
    execution = response.json()['execution_id']
    result = generate_step.__wrapped__(execution)
    assert 'error' not in result, result
    assert complete_step.__wrapped__(execution, result) == 'succeeded'
    approval = next(row for row in client.get('/api/approvals').json() if row['execution_id'] == execution)
    return execution, result, approval


def approve(client, headers, row):
    return client.post(f"/api/approvals/{row['id']}/decision", json={
        'approved': True, 'payload_hash': row['payload_hash']}, headers=headers)


def test_concurrent_explicit_requests_admit_one_bound_draft(authenticated):
    headers, _, _, _, draft, _ = admitted(authenticated)
    cookies = dict(authenticated.cookies)
    def dispatch(_):
        with TestClient(app, base_url='http://localhost:8080') as client:
            client.cookies.update(cookies)
            return run(client, draft, headers)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(dispatch, range(2)))
    assert sorted(r.status_code for r in results) == [202, 409]
    with session_factory()() as db:
        assert db.scalar(select(func.count()).select_from(DocumentDraftRun)) == 1
        assert db.scalar(select(func.count()).select_from(Execution)) == 2  # Manager plus draft.


@pytest.mark.parametrize('fault', ['hash', 'source_cancelled', 'grant', 'config', 'context'])
def test_denial_does_not_queue_partial_draft(authenticated, fault):
    headers, _, target, source, draft, _ = admitted(authenticated)
    with session_factory()() as db:
        if fault == 'source_cancelled':
            db.get(Execution, source).cancelled = True
        elif fault == 'grant':
            db.scalar(select(AgentProjectGrant).where(AgentProjectGrant.agent_id == target['id'])).allowed = False
        elif fault == 'config':
            config = db.scalar(select(AgentConfigVersion).where(AgentConfigVersion.agent_id == target['id']))
            config.provider_connection = 'fixture-collaboration'
        elif fault == 'context':
            db.get(ExecutionBriefContext, source).digest = '0' * 64
        db.commit()
        count = db.scalar(select(func.count()).select_from(Outbox))
    response = run(authenticated, draft, headers, '0' * 64 if fault == 'hash' else None)
    assert response.status_code in (403, 409), response.text
    with session_factory()() as db:
        assert db.scalar(select(func.count()).select_from(DocumentDraftRun)) == 0
        assert db.get(Task, draft['id']).status == 'backlog'
        assert db.scalar(select(func.count()).select_from(Outbox)) == count


def test_changed_adapter_result_cannot_become_an_approval(authenticated):
    headers, _, _, _, draft, _ = admitted(authenticated)
    execution = run(authenticated, draft, headers).json()['execution_id']
    result = generate_step.__wrapped__(execution)
    result['content'] = 'Invented citations and unsupported facts'
    assert complete_step.__wrapped__(execution, result) == 'denied'
    with session_factory()() as db:
        assert db.scalar(select(func.count()).select_from(Approval)) == 0


def test_plan_change_invalidates_pending_draft_approval(authenticated):
    headers, _, _, _, draft, _ = admitted(authenticated)
    _, _, approval = proposed(authenticated, headers, draft)
    with session_factory()() as db:
        plan = db.get(PlanProposal, draft['document_plan_id'])
        plan.payload = {**plan.payload, 'proposal_key': 'changed-after-generation'}
        db.commit()
    assert approve(authenticated, headers, approval).status_code == 409
    assert apply_approved_artifacts() == 0


def test_grant_revocation_after_approval_blocks_persistence(authenticated):
    headers, _, target, _, draft, _ = admitted(authenticated)
    _, _, approval = proposed(authenticated, headers, draft)
    assert approve(authenticated, headers, approval).status_code == 200
    with session_factory()() as db:
        db.scalar(select(AgentProjectGrant).where(AgentProjectGrant.agent_id == target['id'])).allowed = False
        db.commit()
    assert apply_approved_artifacts() == 0
    with session_factory()() as db:
        assert db.get(Approval, approval['id']).status == 'invalidated'
        assert db.scalar(select(func.count()).select_from(ArtifactVersion)) == 0


def test_explicit_route_keeps_owner_auth_and_csrf_requirements(authenticated):
    headers, _, _, _, draft, _ = admitted(authenticated)
    with TestClient(app, base_url='http://localhost:8080') as stranger:
        assert run(stranger, draft, {'Origin': 'http://localhost:8080'}).status_code == 401
    assert run(authenticated, draft, {'Origin': 'http://localhost:8080'}).status_code == 403


@pytest.mark.parametrize('fault', ['source_cancelled', 'run_hash', 'copied_context'])
def test_changed_authority_after_dispatch_prevents_fixture_call(authenticated, monkeypatch, fault):
    headers, _, _, source, draft, _ = admitted(authenticated)
    execution = run(authenticated, draft, headers).json()['execution_id']
    with session_factory()() as db:
        if fault == 'source_cancelled':
            db.get(Execution, source).cancelled = True
        elif fault == 'run_hash':
            db.get(DocumentDraftRun, execution).plan_digest = '0' * 64
        else:
            db.get(ExecutionBriefContext, execution).digest = '0' * 64
        db.commit()
    def forbidden(_):
        pytest.fail('Changed draft authority reached the fixture adapter')
    monkeypatch.setattr(providers.registry.get('fixture'), 'generate', forbidden)
    assert generate_step.__wrapped__(execution)['error'] == 'policy_denied'


def test_rejected_document_output_cannot_complete_task_or_release_dependencies(authenticated):
    headers, project, _, _, draft, review = admitted(authenticated)
    _, _, approval = proposed(authenticated, headers, draft)
    response = authenticated.post(f"/api/approvals/{approval['id']}/decision", json={
        'approved': False, 'payload_hash': approval['payload_hash']}, headers=headers)
    assert response.status_code == 200
    current = next(t for t in authenticated.get('/api/tasks', params={'project_id': project['id']}).json() if t['id'] == draft['id'])
    assert authenticated.post(f"/api/tasks/{draft['id']}/accept", json={
        'expected_revision': current['revision']}, headers=headers).status_code == 409
    assert run(authenticated, review, headers).status_code == 409


def test_reviewed_draft_keeps_old_source_and_requires_exact_approval_before_saved_output(authenticated):
    headers, project, target, source, draft, review = admitted(authenticated)
    assert authenticated.put(f"/api/projects/{project['id']}/brief", json={
        'expected_revision': 1, 'content': 'LATER NOTES MUST NOT REPLACE REVIEWED SOURCE'}, headers=headers).status_code == 200
    execution, result, approval = proposed(authenticated, headers, draft)
    content = result['content']
    assert '# Synthetic document draft' in content and '[S1]' in content
    assert 'Source notes for a document plan' in content
    assert 'LATER NOTES' not in content
    assert draft['document_plan_hash'] in content and 'remain unknown' in content
    assert len(content) <= 1800
    with session_factory()() as db:
        assert db.get(ExecutionBriefContext, execution).message == db.get(ExecutionBriefContext, source).message
        assert db.get(DocumentDraftRun, execution).plan_digest == draft['document_plan_hash']
        assert db.get(Approval, approval['id']).status == 'pending'
    assert apply_approved_artifacts() == 0
    assert run(authenticated, review, headers).status_code == 409
    current = next(t for t in authenticated.get('/api/tasks', params={'project_id': project['id']}).json() if t['id'] == draft['id'])
    assert authenticated.post(f"/api/tasks/{draft['id']}/accept", json={
        'expected_revision': current['revision']}, headers=headers).status_code == 409
    assert authenticated.post(f"/api/approvals/{approval['id']}/decision", json={
        'approved': True, 'payload_hash': '0' * 64}, headers=headers).status_code == 409
    assert approve(authenticated, headers, approval).status_code == 200
    assert apply_approved_artifacts() == 1 and apply_approved_artifacts() == 0
    versions = authenticated.get('/api/artifacts', params={'project_id': project['id']}).json()
    assert len(versions) == 1
    path = f"/api/artifacts/versions/{versions[0]['id']}"
    assert authenticated.get(path).json()['content'] == content
    assert authenticated.post(f"/api/tasks/{draft['id']}/accept", json={
        'expected_revision': current['revision']}, headers=headers).status_code == 200
    with session_factory()() as db:
        assert db.get(Task, draft['id']).status == 'completed'
        grant = db.scalar(select(AgentProjectGrant).where(AgentProjectGrant.agent_id == target['id']))
        grant.allowed = False
        db.commit()
    # Accepted history is readable by the owner after a grant is revoked.
    assert authenticated.get(path).status_code == 200
    assert run(authenticated, review, headers).status_code == 403
