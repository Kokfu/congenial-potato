from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from uuid import uuid4
import pytest
from sqlalchemy import select
from workforce.db import session_factory
from workforce.models import Agent, AgentProjectGrant, BudgetAccount, BudgetReservation, Project
from workforce.services import AccessDenied, authorize_agent_project, reserve_budget

ORIGIN = {'Origin': 'http://localhost:8080'}


def test_owner_login_session_csrf_and_audit(client):
    assert client.get('/api/projects').status_code == 401
    assert client.post('/api/auth/login', json={'password': 'wrong'}, headers=ORIGIN).status_code == 401
    assert client.post('/api/auth/login', json={'password': 'synthetic-strong-password-123'}).status_code == 403
    assert client.post('/api/auth/login', json={'password': 'synthetic-strong-password-123'}, headers=ORIGIN).status_code == 200
    assert client.get('/api/auth/me').json()['username'] == 'owner'
    assert client.post('/api/projects', json={'name': 'A'}, headers=ORIGIN).status_code == 403
    csrf = client.cookies['workforce_csrf']
    created = client.post('/api/projects', json={'name': 'A'}, headers={**ORIGIN, 'X-CSRF-Token': csrf})
    assert created.status_code == 201, created.text
    assert len(client.get('/api/projects').json()) == 1
    assert client.post('/api/auth/logout', headers={**ORIGIN, 'X-CSRF-Token': csrf}).status_code == 200
    assert client.get('/api/projects').status_code == 401


def test_login_throttle(client):
    for _ in range(5):
        assert client.post('/api/auth/login', json={'password': 'wrong'}, headers=ORIGIN).status_code == 401
    assert client.post('/api/auth/login', json={'password': 'synthetic-strong-password-123'}, headers=ORIGIN).status_code == 429


def test_project_grants_default_deny_and_explicit_deny():
    with session_factory()() as db:
        a = Agent(name='A', role='worker')
        p = Project(name='P')
        db.add_all([a, p])
        db.flush()
        agent_id, project_id = a.id, p.id
        db.commit()
    with session_factory()() as db:
        try:
            authorize_agent_project(db, agent_id, project_id, 'project.read')
            assert False, 'empty grants must deny'
        except AccessDenied:
            pass
        db.add(AgentProjectGrant(agent_id=agent_id, project_id=project_id, action='project.read', allowed=True))
        db.commit()
    with session_factory()() as db:
        authorize_agent_project(db, agent_id, project_id, 'project.read')
        try:
            authorize_agent_project(db, agent_id, project_id, 'artifact.read')
            assert False, 'different action must deny'
        except AccessDenied:
            pass
        db.scalar(select(AgentProjectGrant)).allowed = False
        db.commit()
    with session_factory()() as db:
        try:
            authorize_agent_project(db, agent_id, project_id, 'project.read')
            assert False, 'explicit denial must win'
        except AccessDenied:
            pass


def test_concurrent_reservations_share_root_cap():
    root = str(uuid4())
    with session_factory()() as db:
        db.add(BudgetAccount(root_id=root, cap=Decimal('1.000000'), reserved=Decimal('0'), spent=Decimal('0')))
        db.commit()

    def attempt(key):
        with session_factory()() as db:
            try:
                reserve_budget(db, root, key, Decimal('0.700000'))
                db.commit()
                return 'reserved'
            except AccessDenied:
                db.rollback()
                return 'denied'

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(attempt, ['child-a', 'child-b']))
    assert sorted(results) == ['denied', 'reserved']
    with session_factory()() as db:
        assert db.get(BudgetAccount, root).reserved == Decimal('0.700000')
        assert len(db.scalars(select(BudgetReservation)).all()) == 1
        winner = next(key for key, result in zip(['child-a', 'child-b'], results) if result == 'reserved')
        assert reserve_budget(db, root, winner, Decimal('0.700000')).amount == Decimal('0.700000')


def test_fixture_dispatch_is_outside_http_and_deduplicates(authenticated):
    from dbos import DBOS
    from workforce.models import AuditEvent, Execution, ModelCall, Outbox, Task
    from workforce.worker import dispatch_once
    csrf = authenticated.cookies['workforce_csrf']
    headers = {**ORIGIN, 'X-CSRF-Token': csrf}
    project = authenticated.post('/api/projects', json={'name': 'Fixture project'}, headers=headers).json()
    agent = authenticated.post('/api/agents', json={'name': 'Fixture worker', 'role': 'specialist', 'instructions': 'Return fixed fixture', 'provider_connection': 'fixture', 'model_id': 'fake-v1'}, headers=headers).json()
    task = authenticated.post('/api/tasks', json={'project_id': project['id'], 'title': 'Fixture task'}, headers=headers).json()
    denied = authenticated.post(f"/api/tasks/{task['id']}/dispatch", json={'agent_id': agent['id'], 'root_cap': '1.0'}, headers=headers)
    assert denied.status_code == 403
    authenticated.post(f"/api/agents/{agent['id']}/grants", json={'project_id': project['id'], 'action': 'project.execute', 'allowed': True}, headers=headers)
    submitted = authenticated.post(f"/api/tasks/{task['id']}/dispatch", json={'agent_id': agent['id'], 'root_cap': '1.0'}, headers=headers)
    assert submitted.status_code == 202, submitted.text
    execution_id = submitted.json()['execution_id']
    assert authenticated.get(f'/api/executions/{execution_id}').json()['status'] == 'queued'
    DBOS(config={'name': 'workforce-test', 'system_database_url': 'postgresql://postgres:phase1fixture@127.0.0.1:55433/workforce_dbos_test', 'application_version': 'provider-boundary-v1'})
    DBOS.launch()
    try:
        assert dispatch_once() == 1
        assert DBOS.retrieve_workflow(f'execution:{execution_id}').get_result() == 'succeeded'
        with session_factory()() as db:
            outbox = db.scalar(select(Outbox).where(Outbox.idempotency_key == f'execution:{execution_id}'))
            outbox.delivered_at = None
            db.commit()
        assert dispatch_once() == 1
        assert DBOS.retrieve_workflow(f'execution:{execution_id}').get_result() == 'succeeded'
        cancelled_task = authenticated.post('/api/tasks', json={'project_id': project['id'], 'title': 'Cancel pending'}, headers=headers).json()
        cancelled_run = authenticated.post(f"/api/tasks/{cancelled_task['id']}/dispatch", json={'agent_id': agent['id'], 'root_cap': '1.0'}, headers=headers).json()['execution_id']
        assert authenticated.post(f'/api/executions/{cancelled_run}/cancel', headers=headers).status_code == 200
        assert dispatch_once() == 1
        assert DBOS.retrieve_workflow(f'execution:{cancelled_run}').get_result() == 'cancelled'
        revoked_task = authenticated.post('/api/tasks', json={'project_id': project['id'], 'title': 'Revoke pending'}, headers=headers).json()
        revoked_run = authenticated.post(f"/api/tasks/{revoked_task['id']}/dispatch", json={'agent_id': agent['id'], 'root_cap': '1.0'}, headers=headers).json()['execution_id']
        authenticated.post(f"/api/agents/{agent['id']}/grants", json={'project_id': project['id'], 'action': 'project.execute', 'allowed': False}, headers=headers)
        assert dispatch_once() == 1
        assert DBOS.retrieve_workflow(f'execution:{revoked_run}').get_result() == 'denied'
    finally:
        DBOS.destroy()
    with session_factory()() as db:
        assert db.get(Execution, execution_id).status == 'succeeded'
        assert db.get(Task, task['id']).status == 'review'
        assert len(db.scalars(select(ModelCall).where(ModelCall.execution_id == execution_id)).all()) == 1
        assert len(db.scalars(select(AuditEvent).where(AuditEvent.effect_key == f'fixture:{execution_id}')).all()) == 1
        assert db.get(Task, cancelled_task['id']).status == 'cancelled'
        assert db.get(Task, revoked_task['id']).status == 'failed'
        assert db.scalar(select(ModelCall.id).where(ModelCall.execution_id.in_([cancelled_run, revoked_run]))) is None


def test_concurrent_same_reservation_key_is_idempotent():
    root = str(uuid4())
    with session_factory()() as db:
        db.add(BudgetAccount(root_id=root, cap=Decimal('1.000000'), reserved=Decimal('0'), spent=Decimal('0')))
        db.commit()

    def reserve():
        with session_factory()() as db:
            result = reserve_budget(db, root, 'one-logical-call', Decimal('0.700000'))
            db.commit()
            return result.id

    with ThreadPoolExecutor(max_workers=2) as pool:
        ids = list(pool.map(lambda _: reserve(), range(2)))
    assert ids[0] == ids[1]
    with session_factory()() as db:
        assert db.get(BudgetAccount, root).reserved == Decimal('0.700000')


def test_exact_artifact_approval_and_stale_replacement(authenticated):
    from datetime import timedelta
    from workforce.artifacts import SCHEMA_HASH, apply_approved_artifacts, payload_hash, propose_fixture_artifact
    from workforce.models import AgentConfigVersion, Approval, ArtifactVersion, AuditEvent, Execution, ModelCall, Task, now
    with session_factory()() as db:
        project = Project(name='Artifact project')
        agent = Agent(name='Artifact agent', role='specialist')
        db.add_all([project, agent])
        db.flush()
        config = AgentConfigVersion(agent_id=agent.id, version=1, instructions='Fixture', provider_connection='fixture', model_id='fake-v1')
        task = Task(project_id=project.id, title='Write fixture', status='review')
        db.add_all([config, task, AgentProjectGrant(agent_id=agent.id, project_id=project.id, action='project.execute', allowed=True)])
        db.flush()
        execution = Execution(task_id=task.id, agent_id=agent.id, config_version_id=config.id, root_id='root', workflow_id=f'fixture:{uuid4()}', status='succeeded')
        db.add(execution)
        db.flush()
        db.add(ModelCall(execution_id=execution.id, provider='fixture', model_id='fake-v1', result='Synthetic artifact one'))
        proposal = propose_fixture_artifact(db, execution, 'Synthetic artifact one')
        db.flush()
        proposal_id, artifact_id, project_id, execution_id, agent_id = proposal.id, proposal.resource, project.id, execution.id, agent.id
        db.commit()

    headers = {**ORIGIN, 'X-CSRF-Token': authenticated.cookies['workforce_csrf']}
    listed = authenticated.get('/api/approvals').json()
    assert listed[0]['id'] == proposal_id
    assert authenticated.post(f'/api/approvals/{proposal_id}/decision', json={'approved': True, 'payload_hash': '0' * 64}, headers=headers).status_code == 409
    assert authenticated.post(f'/api/approvals/{proposal_id}/decision', json={'approved': True, 'payload_hash': listed[0]['payload_hash']}, headers=headers).status_code == 200
    with pytest.raises(RuntimeError, match='checkpoint lost'):
        apply_approved_artifacts(after_file_write=lambda: (_ for _ in ()).throw(RuntimeError('checkpoint lost')))
    with session_factory()() as db:
        assert db.get(Approval, proposal_id).status == 'approved'
        assert db.scalar(select(ArtifactVersion.id).where(ArtifactVersion.artifact_id == artifact_id)) is None
    assert apply_approved_artifacts() == 1
    assert apply_approved_artifacts() == 0
    assert authenticated.post(f'/api/approvals/{proposal_id}/decision', json={'approved': True, 'payload_hash': listed[0]['payload_hash']}, headers=headers).status_code == 409
    versions = authenticated.get(f'/api/artifacts?project_id={project_id}').json()
    assert len(versions) == 1 and versions[0]['version'] == 1
    assert authenticated.get(f"/api/artifacts/versions/{versions[0]['id']}").json()['content'] == 'Synthetic artifact one'

    def replacement(db, content, key, expected_parent=versions[0]['id']):
        payload = {'artifact_id': artifact_id, 'project_id': project_id, 'content': content,
                   'mime_type': 'text/markdown', 'expected_parent': expected_parent}
        row = Approval(execution_id=execution_id, invocation_key=key, payload=payload,
                       payload_hash=payload_hash(payload), schema_hash=SCHEMA_HASH,
                       resource=artifact_id, target_version=expected_parent, status='pending',
                       expires_at=now() + timedelta(days=1))
        db.add(row)
        db.flush()
        return row.id, row.payload_hash

    with session_factory()() as db:
        good_id, good_hash = replacement(db, 'Synthetic artifact two', 'artifact:replace-good')
        stale_id, stale_hash = replacement(db, 'Stale replacement', 'artifact:replace-stale')
        tampered_id, tampered_hash = replacement(db, 'Original proposal', 'artifact:replace-tampered')
        db.commit()
    assert authenticated.post(f'/api/approvals/{good_id}/decision', json={'approved': True, 'payload_hash': good_hash}, headers=headers).status_code == 200
    assert apply_approved_artifacts() == 1
    for approval_id, digest in ((stale_id, stale_hash), (tampered_id, tampered_hash)):
        assert authenticated.post(f'/api/approvals/{approval_id}/decision', json={'approved': True, 'payload_hash': digest}, headers=headers).status_code == 200
    with session_factory()() as db:
        tampered = db.get(Approval, tampered_id)
        tampered.payload = {**tampered.payload, 'content': 'Changed after approval'}
        tampered.payload_hash = payload_hash(tampered.payload)
        db.commit()
    assert apply_approved_artifacts() == 0
    with session_factory()() as db:
        assert db.get(Approval, good_id).status == 'applied'
        assert db.get(Approval, stale_id).status == 'invalidated'
        assert db.get(Approval, tampered_id).status == 'invalidated'
        assert len(db.scalars(select(ArtifactVersion).where(ArtifactVersion.artifact_id == artifact_id)).all()) == 2
        assert len(db.scalars(select(AuditEvent).where(AuditEvent.effect_key == 'artifact:replace-good')).all()) == 1
    second_version = authenticated.get(f'/api/artifacts?project_id={project_id}').json()[1]
    with session_factory()() as db:
        schema_id, schema_hash = replacement(db, 'Wrong schema', 'artifact:replace-schema', second_version['id'])
        db.get(Approval, schema_id).schema_hash = '0' * 64
        db.commit()
    assert authenticated.post(f'/api/approvals/{schema_id}/decision', json={'approved': True, 'payload_hash': schema_hash}, headers=headers).status_code == 409
    with session_factory()() as db:
        assert db.get(Approval, schema_id).status == 'invalidated'

    with session_factory()() as db:
        revoked_id, revoked_hash = replacement(db, 'Revoked replacement', 'artifact:replace-revoked', second_version['id'])
        db.commit()
    assert authenticated.post(f'/api/approvals/{revoked_id}/decision', json={'approved': True, 'payload_hash': revoked_hash}, headers=headers).status_code == 200
    grant_path = f'/api/agents/{agent_id}/grants'
    assert authenticated.post(grant_path, json={'project_id': project_id, 'action': 'project.execute', 'allowed': False}, headers=headers).status_code == 201
    assert apply_approved_artifacts() == 0
    with session_factory()() as db:
        assert db.get(Approval, revoked_id).status == 'invalidated'
    assert authenticated.post(grant_path, json={'project_id': project_id, 'action': 'project.execute', 'allowed': True}, headers=headers).status_code == 201

    with session_factory()() as db:
        cancel_id, cancel_hash = replacement(db, 'Cancelled replacement', 'artifact:replace-cancelled', second_version['id'])
        db.commit()
    assert authenticated.post(f'/api/approvals/{cancel_id}/decision', json={'approved': True, 'payload_hash': cancel_hash}, headers=headers).status_code == 200
    assert authenticated.post(f'/api/executions/{execution_id}/cancel', headers=headers).status_code == 200
    assert apply_approved_artifacts() == 0
    with session_factory()() as db:
        assert db.get(Approval, cancel_id).status == 'invalidated'
        assert len(db.scalars(select(ArtifactVersion).where(ArtifactVersion.artifact_id == artifact_id)).all()) == 2
