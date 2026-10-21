from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
from fastapi.testclient import TestClient
from sqlalchemy import func, select
import pytest

from workforce.db import session_factory
from workforce.main import app
from workforce.models import AuditEvent, Project, ProjectActivity, ProjectBriefVersion


def fixture_project(client, content='Original notes 🌱\nKeep exact spacing.  '):
    headers = {'Origin': 'http://localhost:8080',
               'X-CSRF-Token': client.cookies['workforce_csrf']}
    response = client.post('/api/projects', json={'name': 'Brief', 'objective': content}, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()['id'], headers


def test_history_preserves_exact_content_scope_and_metadata(authenticated):
    content = 'Original notes 🌱\nKeep exact spacing.  '
    project, headers = fixture_project(authenticated, content)
    other, _ = fixture_project(authenticated, '')
    path = f'/api/projects/{project}'
    first = authenticated.get(path + '/briefs/1').json()
    assert first['content'] == content
    assert first['digest'] == sha256(content.encode()).hexdigest()
    assert first['project_id'] == project
    assert first['actor'] != 'migration:existing-objective'
    revised = authenticated.put(path + '/brief', json={
        'expected_revision': 1, 'content': '<script>untrusted</script>'}, headers=headers)
    assert revised.status_code == 200, revised.text
    assert revised.json()['revision'] == 2
    assert authenticated.get(path + '/briefs/1').json() == first
    rows = authenticated.get(path + '/briefs').json()
    assert [row['revision'] for row in rows] == [2, 1]
    assert all('content' not in row for row in rows)
    assert authenticated.get(f'/api/projects/{other}/briefs/2').status_code == 404
    assert authenticated.get(path + '/briefs/99').status_code == 404
    projects = authenticated.get('/api/projects').json()
    assert next(p for p in projects if p['id'] == project)['objective'] == '<script>untrusted</script>'
    assert next(p for p in projects if p['id'] == project)['brief_revision'] == 2
    with session_factory()() as db:
        events = db.scalars(select(ProjectActivity).where(ProjectActivity.project_id == project)).all()
        assert [e.action for e in events] == ['project.create', 'project.brief.revise']
        assert '<script>' not in str([(e.action, e.resource) for e in events])
        assert db.scalar(select(func.count()).select_from(AuditEvent).where(
            AuditEvent.action == 'project.brief.revise')) == 1


def test_concurrent_edits_have_one_winner_and_retry_cannot_overwrite(authenticated):
    project, headers = fixture_project(authenticated)
    cookies = dict(authenticated.cookies)
    def edit(content):
        with TestClient(app, base_url='http://localhost:8080') as client:
            client.cookies.update(cookies)
            return client.put(f'/api/projects/{project}/brief', json={
                'expected_revision': 1, 'content': content}, headers=headers)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(edit, ['Concurrent A', 'Concurrent B']))
    assert sorted(r.status_code for r in results) == [200, 409]
    winner = next(r.json()['content'] for r in results if r.status_code == 200)
    assert edit('Lost reply retry').status_code == 409
    assert authenticated.get(f'/api/projects/{project}/briefs/2').json()['content'] == winner
    assert len(authenticated.get(f'/api/projects/{project}/briefs').json()) == 2


def test_empty_revision_and_bounded_history_pagination(authenticated):
    project, headers = fixture_project(authenticated, 'Start')
    for revision in range(1, 53):
        response = authenticated.put(f'/api/projects/{project}/brief', json={
            'expected_revision': revision, 'content': '' if revision == 52 else str(revision)}, headers=headers)
        assert response.status_code == 200, response.text
    path = f'/api/projects/{project}/briefs'
    newest = authenticated.get(path).json()
    assert [r['revision'] for r in newest] == list(range(53, 3, -1))
    assert [r['revision'] for r in authenticated.get(path, params={'before': 4}).json()] == [3, 2, 1]
    empty = authenticated.get(path + '/53').json()
    assert empty['content'] == ''
    assert empty['digest'] == sha256(b'').hexdigest()


@pytest.mark.parametrize('payload', [
    {'expected_revision': True, 'content': 'x'},
    {'expected_revision': 0, 'content': 'x'},
    {'expected_revision': '1', 'content': 'x'},
    {'expected_revision': 1, 'content': 'x' * 20001},
    {'expected_revision': 1, 'content': 'x', 'allow_external': True},
])
def test_invalid_updates_do_not_mutate(authenticated, payload):
    project, headers = fixture_project(authenticated)
    assert authenticated.put(f'/api/projects/{project}/brief', json=payload, headers=headers).status_code == 422
    with session_factory()() as db:
        assert db.get(Project, project).brief_revision == 1
        assert db.scalar(select(func.count()).select_from(ProjectBriefVersion)) == 1


def test_brief_auth_csrf_and_missing_scope(authenticated):
    project, headers = fixture_project(authenticated)
    path = f'/api/projects/{project}'
    with TestClient(app, base_url='http://localhost:8080') as stranger:
        assert stranger.get(path + '/briefs').status_code == 401
        assert stranger.get(path + '/briefs/1').status_code == 401
        assert stranger.put(path + '/brief', json={'expected_revision': 1, 'content': 'x'},
                            headers={'Origin': 'http://localhost:8080'}).status_code == 401
    assert authenticated.put(path + '/brief', json={'expected_revision': 1, 'content': 'x'},
                             headers={'Origin': 'http://localhost:8080'}).status_code == 403
    assert authenticated.get('/api/projects/missing/briefs').status_code == 404
    assert authenticated.put('/api/projects/missing/brief', json={
        'expected_revision': 1, 'content': 'x'}, headers=headers).status_code == 404
    assert authenticated.get(path + '/briefs?before=0').status_code == 422
