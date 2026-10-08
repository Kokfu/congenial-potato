from concurrent.futures import ThreadPoolExecutor
from fastapi.testclient import TestClient
from sqlalchemy import select

from workforce.activity import record_activity
from workforce.db import session_factory
from workforce.models import ProjectActivity, ProjectActivityCursor
from workforce.main import app
from workforce.tool_effects import apply_admitted_tools

from test_tool_approval import proposed_write, decide
from test_runtime_collaboration import source_fixture


def test_project_activity_is_scoped_and_commit_ordered(authenticated):
    headers = {'Origin': 'http://localhost:8080',
               'X-CSRF-Token': authenticated.cookies['workforce_csrf']}
    first = authenticated.post('/api/projects', json={'name': 'Activity A'},
                               headers=headers).json()
    second = authenticated.post('/api/projects', json={'name': 'Activity B'},
                                headers=headers).json()
    task = authenticated.post('/api/tasks', json={
        'project_id': first['id'], 'title': 'Scoped task'}, headers=headers)
    assert task.status_code == 201
    path = f"/api/projects/{first['id']}/activity"
    rows = authenticated.get(path).json()
    assert [(row['sequence'], row['action']) for row in rows] == [
        (1, 'project.create'), (2, 'task.create')]
    assert authenticated.get(path, params={'after': 1}).json() == rows[1:]
    assert len(authenticated.get(f"/api/projects/{second['id']}/activity").json()) == 1
    assert authenticated.get(path, params={'after': -1}).status_code == 422
    with TestClient(app, base_url='http://localhost:8080') as stranger:
        assert stranger.get(path).status_code == 401

    def append(_: int):
        with session_factory()() as db:
            record_activity(db, project_id=first['id'], actor='fixture',
                            action='fixture.concurrent', resource=task.json()['id'],
                            outcome='allowed')
            db.commit()
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(append, range(2)))
    with session_factory()() as db:
        assert db.get(ProjectActivityCursor, first['id']).sequence == 4
        assert [row.sequence for row in db.scalars(select(ProjectActivity).where(
            ProjectActivity.project_id == first['id']).order_by(
            ProjectActivity.sequence)).all()] == [1, 2, 3, 4]


def test_tool_and_collaboration_milestones_are_scoped_metadata(authenticated):
    project, _, _, invocation = proposed_write(authenticated)
    assert decide(authenticated, invocation).status_code == 200
    assert apply_admitted_tools() == 1
    tool_events = authenticated.get(f"/api/projects/{project['id']}/activity").json()
    assert [(row['action'], row['outcome']) for row in tool_events if
            row['action'].startswith('tool.')] == [
        ('tool.approval.create', 'pending'),
        ('tool.propose', 'awaiting_approval'),
        ('tool.approval', 'approved'), ('tool.apply', 'reconciled')]
    assert 'Exact synthetic payload' not in str(tool_events)

    candidate = {'kind': 'message', 'task_id': 'TASK_ID',
                 'recipient_agent_id': 'TARGET_ID',
                 'correlation_key': 'activity-note', 'content': 'Private synthetic note'}
    headers, other, _, _, _, _ = source_fixture(authenticated, candidate)
    row = authenticated.get('/api/collaboration-proposals', params={
        'project_id': other['id']}).json()[0]
    response = authenticated.post(f"/api/collaboration-proposals/{row['id']}/decision",
        json={'approved': True, 'payload_hash': row['payload_hash']}, headers=headers)
    assert response.status_code == 200, response.text
    events = authenticated.get(f"/api/projects/{other['id']}/activity").json()
    assert [(item['action'], item['outcome']) for item in events if
            item['action'].startswith('collaboration.')] == [
        ('collaboration.propose', 'pending'),
        ('collaboration.decision', 'admitted')]
    assert 'Private synthetic note' not in str(events)
    assert not any(item['resource'] == invocation['id'] for item in events)
