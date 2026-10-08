from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from workforce.db import session_factory
from workforce.local_read_experiment import ReadDenied, ReadRequest
from workforce.models import ReadDestinationGrant
from workforce.network_policy import canonical_public_url, prepare_public_destination
from workforce.read_grants import active_read_grant


def test_exact_persistent_destination_grant_and_revocation(authenticated):
    headers = {'Origin': 'http://localhost:8080',
               'X-CSRF-Token': authenticated.cookies['workforce_csrf']}
    project = authenticated.post('/api/projects', json={'name': 'Read grant'},
                                 headers=headers).json()
    other = authenticated.post('/api/projects', json={'name': 'Other grant'},
                               headers=headers).json()
    agent = authenticated.post('/api/agents', json={
        'name': 'Reader', 'role': 'specialist', 'instructions': 'Fixture',
        'provider_connection': 'fixture', 'model_id': 'fake-v1'}, headers=headers).json()
    expiry = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
    payload = {'project_id': project['id'], 'agent_id': agent['id'],
               'host': 'example.test', 'expires_at': expiry, 'enabled': True}
    with session_factory()() as db:
        with pytest.raises(ReadDenied):
            active_read_grant(db, project_id=project['id'],
                              agent_id=agent['id'], host='example.test')
    assert authenticated.post('/api/read-destination-grants', json=payload).status_code == 403
    created = authenticated.post('/api/read-destination-grants', json=payload,
                                 headers=headers)
    assert created.status_code == 201, created.text
    assert created.json()['revision'] == 1
    with session_factory()() as db:
        with pytest.raises(ReadDenied):
            active_read_grant(db, project_id=project['id'],
                              agent_id=agent['id'], host='example.test')
    grant = authenticated.post(f"/api/agents/{agent['id']}/grants", json={
        'project_id': project['id'], 'action': 'project.execute', 'allowed': True},
        headers=headers)
    assert grant.status_code == 201
    with session_factory()() as db:
        active = active_read_grant(db, project_id=project['id'],
                                   agent_id=agent['id'], host='example.test')
        request = ReadRequest(project_id=project['id'], agent_id=agent['id'],
                              url='https://example.test/evidence')
        prepared = prepare_public_destination(request, active,
            resolver=lambda _host, port, *, type: [(2, type, 6, '', ('8.8.8.8', port))])
        assert prepared.host == 'example.test'
        for wrong_project, wrong_host in ((other['id'], 'example.test'),
                                          (project['id'], 'other.test')):
            with pytest.raises(ReadDenied):
                active_read_grant(db, project_id=wrong_project,
                                  agent_id=agent['id'], host=wrong_host)
    listed = authenticated.get('/api/read-destination-grants',
                               params={'project_id': project['id']})
    assert listed.status_code == 200 and len(listed.json()) == 1
    assert authenticated.get('/api/read-destination-grants',
        params={'project_id': other['id']}).json() == []
    revoked = authenticated.post('/api/read-destination-grants',
        json={**payload, 'enabled': False}, headers=headers)
    assert revoked.status_code == 201 and revoked.json()['revision'] == 2
    with session_factory()() as db:
        assert len(db.scalars(select(ReadDestinationGrant)).all()) == 1
        with pytest.raises(ReadDenied):
            active_read_grant(db, project_id=project['id'],
                              agent_id=agent['id'], host='example.test')


def test_grant_input_and_url_authority_tricks_fail_closed(authenticated):
    headers = {'Origin': 'http://localhost:8080',
               'X-CSRF-Token': authenticated.cookies['workforce_csrf']}
    project = authenticated.post('/api/projects', json={'name': 'Host checks'},
                                 headers=headers).json()
    agent = authenticated.post('/api/agents', json={
        'name': 'Reader', 'role': 'specialist', 'instructions': 'Fixture',
        'provider_connection': 'fixture', 'model_id': 'fake-v1'}, headers=headers).json()
    payload = {'project_id': project['id'], 'agent_id': agent['id'],
               'host': 'example.test', 'enabled': True,
               'expires_at': (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()}
    for host in ('LOCALHOST', 'localhost', '127.0.0.1', 'example.test.',
                 'example.test:443', 'example..test', 'example_test'):
        response = authenticated.post('/api/read-destination-grants',
            json={**payload, 'host': host}, headers=headers)
        assert response.status_code == 422, (host, response.text)
    for url in ('https://example.test', 'http://example.test/a',
                'https://example.test:0/a', 'https://user@example.test/a',
                'https://example.test/a#x', 'https://example.test./a',
                ' https://example.test/a', 'https://example.test\\@other.test/a'):
        with pytest.raises(ReadDenied):
            canonical_public_url(url)
