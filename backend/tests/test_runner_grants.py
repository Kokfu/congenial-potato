from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Barrier
from uuid import uuid4
import hashlib

import pytest
from sqlalchemy import select

from workforce.db import session_factory
from workforce.models import Agent, AgentProjectGrant, AuditEvent, Owner, RunnerProfileGrant
from workforce.runner_grants import (
    REVIEWED_JOB_SHA256, RunnerBinding, RunnerGrantDenied, RunnerGrantInput,
    active_runner_grant_record, set_runner_grant,
)


@pytest.fixture
def scope(authenticated):
    headers = {'Origin': 'http://localhost:8080',
               'X-CSRF-Token': authenticated.cookies['workforce_csrf']}
    project = authenticated.post('/api/projects', json={'name': 'Runner grant'}, headers=headers).json()
    agent = authenticated.post('/api/agents', json={
        'name': 'Runner', 'role': 'specialist', 'instructions': 'Synthetic',
        'provider_connection': 'fixture', 'model_id': 'fake-v1'}, headers=headers).json()
    pins = authenticated.get('/api/runner-profile').json()
    payload = {**pins, 'project_id': project['id'], 'agent_id': agent['id'],
        'image_id': 'sha256:' + 'a'*64, 'enabled': True, 'expected_revision': 0,
        'expires_at': (datetime.now(timezone.utc)+timedelta(hours=1)).isoformat()}
    return authenticated, headers, payload


def binding(payload):
    return RunnerBinding.model_validate({k: payload[k] for k in (
        'profile_id', 'profile_revision', 'profile_sha256', 'job_sha256', 'image_id')})


def execute_grant(client, headers, payload, allowed=True):
    response = client.post(f"/api/agents/{payload['agent_id']}/grants", json={
        'project_id': payload['project_id'], 'action': 'project.execute', 'allowed': allowed},
        headers=headers)
    assert response.status_code == 201


def lookup(db, payload):
    return active_runner_grant_record(db, project_id=payload['project_id'],
        agent_id=payload['agent_id'], binding=binding(payload))


def test_owner_metadata_scope_revision_and_revocation(scope):
    client, headers, payload = scope
    assert client.post('/api/runner-profile-grants', json=payload).status_code == 403
    with session_factory()() as db, pytest.raises(RunnerGrantDenied):
        lookup(db, payload)
    response = client.post('/api/runner-profile-grants', json=payload, headers=headers)
    assert response.status_code == 201, response.text
    row = response.json()
    assert row['revision'] == 1
    assert set(row) == set(payload)-{'expected_revision'} | {'id', 'revision'}
    with session_factory()() as db, pytest.raises(RunnerGrantDenied):
        lookup(db, payload)
    execute_grant(client, headers, payload)
    with session_factory()() as db:
        assert lookup(db, payload).id == row['id']
    other = client.post('/api/projects', json={'name': 'Other'}, headers=headers).json()['id']
    for changed in ({'project_id': other}, {'agent_id': str(uuid4())},
                    {'image_id': 'sha256:'+'b'*64}):
        with session_factory()() as db, pytest.raises(RunnerGrantDenied):
            lookup(db, payload | changed)
    assert client.get('/api/runner-profile-grants', params={'project_id': other}).json() == []
    listed = client.get('/api/runner-profile-grants', params={'project_id': payload['project_id']})
    assert listed.status_code == 200 and listed.json() == [row]
    changed = payload | {'expected_revision': 1, 'image_id': 'sha256:'+'b'*64}
    updated = client.post('/api/runner-profile-grants', json=changed, headers=headers)
    assert updated.status_code == 201 and updated.json()['revision'] == 2
    assert updated.json()['id'] == row['id']
    assert client.post('/api/runner-profile-grants', json=changed, headers=headers).status_code == 422
    with session_factory()() as db, pytest.raises(RunnerGrantDenied):
        lookup(db, payload)
    expired = (datetime.now(timezone.utc)-timedelta(seconds=1)).isoformat()
    revoked = client.post('/api/runner-profile-grants', json=changed | {
        'expected_revision': 2, 'enabled': False, 'expires_at': expired}, headers=headers)
    assert revoked.status_code == 201 and revoked.json()['revision'] == 3
    with session_factory()() as db:
        assert len(db.scalars(select(RunnerProfileGrant)).all()) == 1
        assert len(db.scalars(select(AuditEvent).where(AuditEvent.action == 'runner.grant.set')).all()) == 3
        with pytest.raises(RunnerGrantDenied):
            lookup(db, changed)
    client.post('/api/auth/logout', headers=headers)
    assert client.get('/api/runner-profile').status_code == 401
    assert client.get('/api/runner-profile-grants', params={'project_id': payload['project_id']}).status_code == 401


@pytest.mark.parametrize('change', [
    {'profile_id': 'arbitrary.shell'}, {'profile_revision': 2}, {'profile_revision': True},
    {'profile_sha256': 'b'*64}, {'job_sha256': 'b'*64},
    {'image_id': 'workforce:latest'}, {'image_id': 'repository@sha256:'+'a'*64},
    {'image_id': 'sha256:'+'A'*64}, {'image_id': 'sha256:'+'a'*63},
    {'enabled': 'true'}, {'expected_revision': True}, {'expected_revision': -1},
    {'command': 'sh'}, {'env': {}}, {'mounts': []}, {'input': {'text': 'not metadata'}},
    {'expires_at': '2026-10-15T00:00:00'},
    {'expires_at': '2000-01-01T00:00:00Z'}, {'expires_at': '2999-01-01T00:00:00Z'},
    {'project_id': str(uuid4())}, {'agent_id': str(uuid4())},
])
def test_invalid_runner_grants_are_inert(scope, change):
    client, headers, payload = scope
    response = client.post('/api/runner-profile-grants', json=payload | change, headers=headers)
    assert response.status_code == 422, response.text
    with session_factory()() as db:
        assert db.scalar(select(RunnerProfileGrant)) is None
        assert db.scalar(select(AuditEvent).where(AuditEvent.action == 'runner.grant.set')) is None


def test_lookup_rechecks_project_agent_expiry_and_cached_rows(scope):
    client, headers, payload = scope
    assert client.post('/api/runner-profile-grants', json=payload, headers=headers).status_code == 201
    execute_grant(client, headers, payload)
    with session_factory()() as cached:
        row = lookup(cached, payload)
        grant_id = row.id
        cached_project_grant = cached.scalar(select(AgentProjectGrant).where(
            AgentProjectGrant.agent_id == payload['agent_id']))
        cached.commit()
        execute_grant(client, headers, payload, allowed=False)
        with pytest.raises(RunnerGrantDenied):
            lookup(cached, payload)
        assert cached_project_grant.allowed is False
        cached.rollback()
        execute_grant(client, headers, payload)
        with session_factory()() as db:
            db.get(Agent, payload['agent_id']).status = 'paused'
            db.commit()
        with pytest.raises(RunnerGrantDenied):
            lookup(cached, payload)
        cached.rollback()
        with session_factory()() as db:
            db.get(Agent, payload['agent_id']).status = 'active'
            db.get(RunnerProfileGrant, grant_id).expires_at = datetime.now(timezone.utc)-timedelta(seconds=1)
            db.commit()
        with pytest.raises(RunnerGrantDenied):
            lookup(cached, payload)
        cached.rollback()
        with session_factory()() as db:
            grant = db.get(RunnerProfileGrant, grant_id)
            grant.expires_at = datetime.now(timezone.utc)+timedelta(hours=1)
            grant.profile_sha256 = 'b'*64
            db.commit()
        with pytest.raises(RunnerGrantDenied):
            lookup(cached, payload)


def test_concurrent_first_grants_reject_stale_owner_update(scope):
    _, _, payload = scope
    barrier = Barrier(2)
    data = RunnerGrantInput.model_validate(payload)
    def write():
        with session_factory()() as db:
            owner_id = db.scalar(select(Owner.id))
            barrier.wait(timeout=10)
            try:
                row = set_runner_grant(db, data=data, owner_id=owner_id)
                db.commit()
                return row.revision
            except RunnerGrantDenied:
                db.rollback()
                return 'stale'
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(lambda _: write(), range(2)), key=str) == [1, 'stale']
    with session_factory()() as db:
        assert len(db.scalars(select(RunnerProfileGrant)).all()) == 1
        assert len(db.scalars(select(AuditEvent).where(AuditEvent.action == 'runner.grant.set')).all()) == 1


def test_copied_binding_and_input_cannot_bypass_validation(scope):
    _, _, payload = scope
    data = RunnerGrantInput.model_validate(payload).model_copy(update={'job_sha256': 'b'*64})
    with session_factory()() as db, pytest.raises(RunnerGrantDenied):
        set_runner_grant(db, data=data, owner_id=db.scalar(select(Owner.id)))
    with session_factory()() as db, pytest.raises(RunnerGrantDenied):
        active_runner_grant_record(db, project_id=payload['project_id'], agent_id=payload['agent_id'],
            binding=binding(payload).model_copy(update={'image_id': 'latest'}))


def test_reviewed_job_pin_matches_source_without_product_import():
    source = Path(__file__).parents[1]/'src/workforce/runner_fixture_job.py'
    assert hashlib.sha256(source.read_bytes()).hexdigest() == REVIEWED_JOB_SHA256
