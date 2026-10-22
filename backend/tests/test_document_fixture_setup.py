from fastapi.testclient import TestClient
from sqlalchemy import select, func
from workforce.db import session_factory
from workforce.main import app
from workforce.models import (Project, ProjectBriefVersion, Agent, AgentConfigVersion,
    AgentProjectGrant, Task, Execution, Outbox, Approval)


def headers(client):
    return {'Origin': 'http://localhost:8080', 'X-CSRF-Token': client.cookies['workforce_csrf']}


def test_setup_creates_only_fixed_local_configuration(authenticated):
    notes = 'Meeting notes 🌱\nExact trailing  '
    response = authenticated.post('/api/document-fixtures', json={'name': 'Walkthrough', 'notes': notes},
                                  headers=headers(authenticated))
    assert response.status_code == 201, response.text
    ids = response.json()
    with session_factory()() as db:
        project = db.get(Project, ids['project_id'])
        assert project.objective == notes and project.brief_revision == 1
        assert db.scalar(select(ProjectBriefVersion)).content == notes
        assert db.scalar(select(func.count()).select_from(Agent)) == 2
        configs = db.scalars(select(AgentConfigVersion)).all()
        assert {c.provider_connection for c in configs} == {'fixture', 'fixture-collaboration'}
        assert all(not c.config.get('price_envelope') for c in configs)
        manager = next(c for c in configs if c.agent_id == ids['manager_id'])
        assert ids['draft_agent_id'] in manager.instructions
        grants = db.scalars(select(AgentProjectGrant)).all()
        assert len(grants) == 2 and all(g.project_id == project.id and g.allowed and g.action == 'project.execute' for g in grants)
        task = db.get(Task, ids['task_id'])
        assert task.status == 'backlog' and task.project_id == project.id
        for model in (Execution, Outbox, Approval):
            assert db.scalar(select(func.count()).select_from(model)) == 0


def test_setup_auth_csrf_and_strict_input(authenticated):
    data = {'name': 'Walkthrough', 'notes': 'Sample'}
    assert TestClient(app, base_url="http://localhost:8080").post('/api/document-fixtures', json=data, headers={'Origin': 'http://localhost:8080'}).status_code == 401
    assert authenticated.post('/api/document-fixtures', json=data).status_code == 403
    assert authenticated.post('/api/document-fixtures', json=data, headers={'Origin': 'http://localhost:8080'}).status_code == 403
    for invalid in ({**data, 'provider_connection': 'live'}, {**data, 'notes': '  '}, {**data, 'name': 'x'*121}):
        assert authenticated.post('/api/document-fixtures', json=invalid, headers=headers(authenticated)).status_code == 422
    with session_factory()() as db:
        assert db.scalar(select(func.count()).select_from(Project)) == 0


def test_setup_rolls_back_every_created_record(authenticated, monkeypatch):
    def fail(*args, **kwargs):
        raise RuntimeError('Synthetic setup failure')
    monkeypatch.setattr('workforce.document_fixture_setup.record_activity', fail)
    with TestClient(app, base_url="http://localhost:8080", raise_server_exceptions=False) as client:
        client.cookies.update(authenticated.cookies)
        response = client.post('/api/document-fixtures', json={'name': 'Rollback', 'notes': 'Sample'}, headers=headers(client))
    assert response.status_code == 500
    with session_factory()() as db:
        for model in (Project, ProjectBriefVersion, Agent, AgentConfigVersion, AgentProjectGrant, Task):
            assert db.scalar(select(func.count()).select_from(model)) == 0
