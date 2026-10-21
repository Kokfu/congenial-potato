from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from workforce.db import session_factory
from workforce.main import app
from workforce.models import Execution, ExecutionBriefSource, Outbox, ProjectBriefVersion, Schedule, ScheduleOccurrence, Task
from workforce.schedule_dispatch import schedule_due_once
from test_schedule_dispatch import _schedule


def setup(client):
    headers = {'Origin': 'http://localhost:8080', 'X-CSRF-Token': client.cookies['workforce_csrf']}
    project = client.post('/api/projects', json={'name': 'Run source', 'objective': 'Original source 🌱'}, headers=headers).json()['id']
    agent = client.post('/api/agents', json={'name': 'Source manager', 'role': 'Manager',
        'instructions': 'Fixture only', 'provider_connection': 'fixture', 'model_id': 'fake-v1'}, headers=headers).json()['id']
    assert client.post(f'/api/agents/{agent}/grants', json={'project_id': project,
        'action': 'project.execute', 'allowed': True}, headers=headers).status_code == 201
    task = client.post('/api/tasks', json={'project_id': project, 'title': 'Source test'}, headers=headers).json()['id']
    return project, agent, task, headers


def dispatch(client, task, agent, headers, **extra):
    return client.post(f'/api/tasks/{task}/dispatch', json={
        'agent_id': agent, 'root_cap': '1.0', **extra}, headers=headers)


def test_queued_run_keeps_exact_source_through_edits_and_duplicate_dispatch(authenticated):
    project, agent, task, headers = setup(authenticated)
    response = dispatch(authenticated, task, agent, headers, expected_brief_revision=1)
    assert response.status_code == 202, response.text
    execution = response.json()['execution_id']
    source = authenticated.get(f'/api/executions/{execution}/brief').json()
    assert source == {'status': 'pinned', 'project_id': project, 'revision': 1,
        'digest': sha256('Original source 🌱'.encode()).hexdigest(),
        'content': 'Original source 🌱', 'used_in_model_context': False}
    assert authenticated.put(f'/api/projects/{project}/brief', json={
        'expected_revision': 1, 'content': 'New source'}, headers=headers).status_code == 200
    assert dispatch(authenticated, task, agent, headers).status_code == 409
    assert authenticated.get(f'/api/executions/{execution}/brief').json() == source
    with session_factory()() as db:
        assert db.get(Task, task).status == 'queued'
        assert db.scalar(select(func.count()).select_from(ExecutionBriefSource)) == 1
        assert db.scalar(select(func.count()).select_from(Outbox)) == 1


def test_stale_expected_source_denies_admission_without_partial_state(authenticated):
    project, agent, task, headers = setup(authenticated)
    assert authenticated.put(f'/api/projects/{project}/brief', json={
        'expected_revision': 1, 'content': ''}, headers=headers).status_code == 200
    assert dispatch(authenticated, task, agent, headers, expected_brief_revision=1).status_code == 409
    with session_factory()() as db:
        assert db.get(Task, task).status == 'backlog'
        assert db.scalar(select(func.count()).select_from(Execution)) == 0
    response = dispatch(authenticated, task, agent, headers, expected_brief_revision=2)
    assert response.status_code == 202
    source = authenticated.get(f"/api/executions/{response.json()['execution_id']}/brief").json()
    assert source['revision'] == 2 and source['content'] == ''


def test_concurrent_edit_and_dispatch_capture_one_coherent_revision(authenticated):
    project, agent, task, headers = setup(authenticated)
    cookies = dict(authenticated.cookies)
    def action(kind):
        with TestClient(app, base_url='http://localhost:8080') as client:
            client.cookies.update(cookies)
            if kind == 'edit':
                return client.put(f'/api/projects/{project}/brief', json={
                    'expected_revision': 1, 'content': 'Concurrent new source'}, headers=headers)
            return dispatch(client, task, agent, headers)
    with ThreadPoolExecutor(max_workers=2) as pool:
        edited, admitted = list(pool.map(action, ['edit', 'dispatch']))
    assert edited.status_code == 200 and admitted.status_code == 202
    source = authenticated.get(f"/api/executions/{admitted.json()['execution_id']}/brief").json()
    assert (source['revision'], source['content']) in [(1, 'Original source 🌱'), (2, 'Concurrent new source')]
    assert source['digest'] == sha256(source['content'].encode()).hexdigest()


def test_delegated_runs_inherit_source_and_retries_never_recapture(authenticated):
    project, agent, task, headers = setup(authenticated)
    root = dispatch(authenticated, task, agent, headers).json()['execution_id']
    with session_factory()() as db:
        db.get(Execution, root).status = 'running'
        db.commit()
    assert authenticated.put(f'/api/projects/{project}/brief', json={
        'expected_revision': 1, 'content': 'Later source'}, headers=headers).status_code == 200
    payload = {'request_key': 'source-child', 'work_key': 'source-child', 'title': 'Inherited source', 'agent_id': agent}
    response = authenticated.post(f'/api/executions/{root}/delegate', json=payload, headers=headers)
    assert response.status_code == 202, response.text
    child = response.json()['id']
    assert authenticated.get(f'/api/executions/{child}/brief').json() == authenticated.get(f'/api/executions/{root}/brief').json()
    assert authenticated.post(f'/api/executions/{root}/delegate', json=payload, headers=headers).json()['id'] == child


def test_concurrent_duplicate_dispatch_cannot_create_a_second_source(authenticated):
    _, agent, task, headers = setup(authenticated)
    cookies = dict(authenticated.cookies)
    def admit(_):
        with TestClient(app, base_url='http://localhost:8080') as client:
            client.cookies.update(cookies)
            return dispatch(client, task, agent, headers)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(admit, range(2)))
    assert sorted(r.status_code for r in results) == [202, 409]
    with session_factory()() as db:
        assert db.scalar(select(func.count()).select_from(Execution)) == 1
        assert db.scalar(select(func.count()).select_from(ExecutionBriefSource)) == 1


def test_missing_current_history_denies_admission_without_guessing_a_source(authenticated):
    project, agent, task, headers = setup(authenticated)
    with session_factory()() as db:
        db.delete(db.get(ProjectBriefVersion, (project, 1)))
        db.commit()
    assert dispatch(authenticated, task, agent, headers).status_code == 409
    with session_factory()() as db:
        assert db.get(Task, task).status == 'backlog'
        assert db.scalar(select(func.count()).select_from(Outbox)) == 0


def test_scheduled_source_is_pinned_once_at_occurrence_admission(authenticated):
    project, _, schedule, headers = _schedule(authenticated)
    at = datetime(2030, 1, 2, 12, tzinfo=timezone.utc)
    with session_factory()() as db:
        db.get(Schedule, schedule).last_checked_at = at - timedelta(days=2)
        db.commit()
    assert schedule_due_once(at=at) == 1
    assert authenticated.put(f"/api/projects/{project['id']}/brief", json={
        'expected_revision': 1, 'content': 'After scheduled admission'}, headers=headers).status_code == 200
    assert schedule_due_once(at=at) == 0
    with session_factory()() as db:
        execution = db.scalar(select(ScheduleOccurrence.execution_id))
    source = authenticated.get(f'/api/executions/{execution}/brief').json()
    assert source['revision'] == 1 and source['content'] == ''


def test_legacy_runs_stay_unpinned_including_delegated_children(authenticated):
    _, agent, task, headers = setup(authenticated)
    root = dispatch(authenticated, task, agent, headers).json()['execution_id']
    with session_factory()() as db:
        # Simulate a pre-migration run; new migrations do not backfill source rows.
        db.delete(db.get(ExecutionBriefSource, root))
        db.get(Execution, root).status = 'running'
        db.commit()
    response = authenticated.post(f'/api/executions/{root}/delegate', json={
        'request_key': 'legacy-child', 'work_key': 'legacy-child', 'title': 'Legacy', 'agent_id': agent}, headers=headers)
    assert response.status_code == 202, response.text
    assert authenticated.get(f'/api/executions/{root}/brief').json() == {'status': 'unpinned'}
    assert authenticated.get(f"/api/executions/{response.json()['id']}/brief").json() == {'status': 'unpinned'}


def test_source_read_rejects_changed_bytes_digest_scope_and_unauthenticated_reads(authenticated):
    project, agent, task, headers = setup(authenticated)
    execution = dispatch(authenticated, task, agent, headers).json()['execution_id']
    path = f'/api/executions/{execution}/brief'
    with TestClient(app, base_url='http://localhost:8080') as stranger:
        assert stranger.get(path).status_code == 401
    assert authenticated.get('/api/executions/missing/brief').status_code == 404
    with session_factory()() as db:
        version = db.get(ProjectBriefVersion, (project, 1))
        version.content = 'Tampered database text'
        db.commit()
    assert authenticated.get(path).status_code == 409
    with session_factory()() as db:
        version = db.get(ProjectBriefVersion, (project, 1))
        version.digest = sha256(version.content.encode()).hexdigest()
        db.commit()
    assert authenticated.get(path).status_code == 409
    other = authenticated.post('/api/projects', json={'name': 'Other source'}, headers=headers).json()['id']
    with session_factory()() as db:
        db.get(ExecutionBriefSource, execution).project_id = other
        db.commit()
    assert authenticated.get(path).status_code == 409
