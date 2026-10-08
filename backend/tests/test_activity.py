from concurrent.futures import ThreadPoolExecutor
from fastapi.testclient import TestClient
from sqlalchemy import select

from workforce.activity import record_activity
from workforce.db import session_factory
from workforce.models import Project, ProjectActivity
from workforce.main import app


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
        assert db.get(Project, first['id']).activity_seq == 4
        assert [row.sequence for row in db.scalars(select(ProjectActivity).where(
            ProjectActivity.project_id == first['id']).order_by(
            ProjectActivity.sequence)).all()] == [1, 2, 3, 4]
