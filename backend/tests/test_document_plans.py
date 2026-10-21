import json
from hashlib import sha256
import pytest
from sqlalchemy import func, select

from workforce.db import session_factory
from workforce.models import (AgentProjectGrant, CollaborationProposal, DocumentPlanTask,
    Execution, ExecutionBriefContext, Outbox, PlanProposal, Task)
from test_runtime_collaboration import source_fixture


def candidate():
    return {'kind': 'plan', 'proposal_key': 'document-plan', 'expected_revision': 1,
        'tasks': [
            {'work_key': 'draft', 'title': 'Prepare a cited fixture draft', 'assignee_id': 'TARGET_ID', 'depends_on': []},
            {'work_key': 'review', 'title': 'Review citations and unknowns', 'assignee_id': 'TARGET_ID', 'depends_on': ['draft']}]}


def recorded(client, raw=None, objective='Source notes for a document plan 🌱'):
    result = source_fixture(client, raw or candidate(), objective=objective)
    headers, project, target, _, _, execution = result
    rows = client.get('/api/collaboration-proposals', params={'project_id': project['id']}).json()
    return headers, project, target, execution, rows


def decide(client, row, headers, approved=True):
    return client.post(f"/api/collaboration-proposals/{row['id']}/decision", json={
        'approved': approved, 'payload_hash': row['payload_hash']}, headers=headers)


def test_project_edit_rejects_stale_plan_without_partial_tasks_but_owner_can_reject(authenticated):
    headers, project, _, _, rows = recorded(authenticated)
    assert authenticated.put(f"/api/projects/{project['id']}/brief", json={
        'expected_revision': 1, 'content': 'New source version'}, headers=headers).status_code == 200
    response = decide(authenticated, rows[0], headers)
    assert response.status_code == 409 and 'source_brief_changed' in response.text
    with session_factory()() as db:
        assert db.scalar(select(func.count()).select_from(DocumentPlanTask)) == 0
        assert db.scalar(select(func.count()).select_from(PlanProposal)) == 0
        assert db.get(CollaborationProposal, rows[0]['id']).status == 'pending'
    assert decide(authenticated, rows[0], headers, False).json()['status'] == 'rejected'


@pytest.mark.parametrize('fault', ['cycle', 'assignee_scope', 'grant_revoked'])
def test_source_binding_keeps_existing_graph_and_grant_admission_rules(authenticated, fault):
    raw = candidate()
    if fault == 'cycle':
        raw['tasks'][0]['depends_on'] = ['review']
    if fault == 'assignee_scope':
        raw['tasks'][0]['assignee_id'] = 'missing-agent'
    headers, _, target, _, rows = recorded(authenticated, raw)
    if fault == 'grant_revoked':
        with session_factory()() as db:
            db.scalar(select(AgentProjectGrant).where(AgentProjectGrant.agent_id == target['id'])).allowed = False
            db.commit()
    response = decide(authenticated, rows[0], headers)
    assert response.status_code in (403, 409)
    with session_factory()() as db:
        assert db.scalar(select(func.count()).select_from(DocumentPlanTask)) == 0


def test_model_cannot_supply_server_source_binding(authenticated):
    raw = candidate()
    raw['document_source'] = {'brief_revision': 99}
    _, _, _, _, rows = recorded(authenticated, raw)
    assert rows == []


def test_changed_prepared_context_blocks_admission_even_with_a_new_hash(authenticated):
    headers, _, _, execution, rows = recorded(authenticated)
    with session_factory()() as db:
        row = db.get(ExecutionBriefContext, execution)
        payload = json.loads(row.message)
        payload['content'] = 'Changed source'
        row.message = json.dumps(payload)
        row.digest = sha256(row.message.encode()).hexdigest()
        db.commit()
    response = decide(authenticated, rows[0], headers)
    assert response.status_code == 409 and 'source_context_unavailable' in response.text


def test_direct_plan_api_derives_binding_and_rejects_forged_or_wrong_project_source(authenticated):
    headers, project, target, execution, rows = recorded(authenticated)
    body = {'source_execution_id': execution, 'proposal_key': 'owner-plan', 'expected_revision': 1,
        'tasks': [{'work_key': 'owner-draft', 'title': 'Owner fixture draft',
                   'assignee_id': target['id'], 'depends_on': []}]}
    path = f"/api/projects/{project['id']}/plan-proposals"
    forged = {**rows[0]['payload']['document_source'], 'context_digest': '0' * 64}
    assert authenticated.post(path, json={**body, 'document_source': forged}, headers=headers).status_code == 409
    other = authenticated.post('/api/projects', json={'name': 'Other project'}, headers=headers).json()
    assert authenticated.post(f"/api/projects/{other['id']}/plan-proposals", json=body, headers=headers).status_code == 409
    response = authenticated.post(path, json=body, headers=headers)
    assert response.status_code == 201, response.text
    assert authenticated.post(path, json=body, headers=headers).json()['id'] == response.json()['id']
    assert authenticated.get(path).json()[0]['payload']['document_source'] == rows[0]['payload']['document_source']


def test_truncated_source_binding_reports_the_prepared_prefix(authenticated):
    _, _, _, execution, rows = recorded(authenticated, objective='Source notes ' * 1500)
    source = authenticated.get(f'/api/executions/{execution}/brief').json()
    binding = rows[0]['payload']['document_source']
    assert binding['truncated'] and binding['included_characters'] < binding['total_characters']
    assert binding['context_digest'] == source['context']['message_digest']


def test_legacy_pending_plan_is_not_silently_rebound_at_decision(authenticated):
    headers, _, _, _, rows = recorded(authenticated)
    from workforce.collaboration import proposal_hash
    with session_factory()() as db:
        row = db.get(CollaborationProposal, rows[0]['id'])
        payload = dict(row.payload)
        payload.pop('document_source')
        row.payload = payload
        row.payload_hash = proposal_hash(payload)
        db.commit()
        legacy = {'id': row.id, 'payload_hash': row.payload_hash}
    response = decide(authenticated, legacy, headers)
    assert response.status_code == 409 and 'source_binding_changed' in response.text


def test_runtime_document_plan_binds_exact_source_and_only_admits_gated_backlog_tasks(authenticated):
    headers, project, target, execution, rows = recorded(authenticated)
    assert len(rows) == 1
    row = rows[0]
    source = authenticated.get(f'/api/executions/{execution}/brief').json()
    binding = row['payload']['document_source']
    assert binding['project_id'] == project['id'] and binding['brief_revision'] == 1
    assert binding['brief_digest'] == source['digest']
    assert binding['context_digest'] == source['context']['message_digest']
    assert binding['included_characters'] == len(source['content']) and not binding['truncated']
    assert row['status'] == 'pending'
    with session_factory()() as db:
        assert db.scalar(select(func.count()).select_from(DocumentPlanTask)) == 0
        before_runs = db.scalar(select(func.count()).select_from(Execution))
        before_outbox = db.scalar(select(func.count()).select_from(Outbox))
    assert authenticated.post(f"/api/collaboration-proposals/{row['id']}/decision", json={
        'approved': True, 'payload_hash': '0' * 64}, headers=headers).status_code == 409
    response = decide(authenticated, row, headers)
    assert response.status_code == 200, response.text
    assert decide(authenticated, row, headers).json() == response.json()
    tasks = authenticated.get('/api/tasks', params={'project_id': project['id']}).json()
    admitted = [t for t in tasks if t['document_plan_id']]
    assert len(admitted) == 2 and all(t['status'] == 'backlog' for t in admitted)
    for task in admitted:
        result = authenticated.post(f"/api/tasks/{task['id']}/dispatch", json={
            'agent_id': target['id'], 'root_cap': '1.0'}, headers=headers)
        assert result.status_code == 409 and 'not enabled' in result.text
    with session_factory()() as db:
        plan = db.get(PlanProposal, response.json()['admitted_ref'])
        assert plan.payload['document_source'] == binding
        assert db.scalar(select(func.count()).select_from(Execution)) == before_runs
        assert db.scalar(select(func.count()).select_from(Outbox)) == before_outbox
        assert db.scalar(select(func.count()).select_from(DocumentPlanTask)) == 2

