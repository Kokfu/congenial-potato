from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from uuid import uuid4
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
    DBOS(config={'name': 'workforce-test', 'system_database_url': 'postgresql://postgres:phase1fixture@127.0.0.1:55433/workforce_dbos_test', 'application_version': 'foundation-v1'})
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
