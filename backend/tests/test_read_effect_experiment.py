from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
import hashlib
import json
from threading import Event

import pytest
from sqlalchemy import select

from workforce.db import session_factory
from workforce.local_read_experiment import ReadDenied
from workforce.models import (AgentProjectGrant, Approval, BudgetAccount, Execution,
    ExternalReadObservation, PolicyRule, ReadDestinationGrant, ReadEffectAttempt,
    ToolInvocation, now)
from workforce.network_policy import PinnedHTTPConnection
from workforce.read_effect_experiment import run_read_effect_experiment
from workforce.tool_effects import apply_admitted_tools
from test_local_read_experiment import local_server
from test_network_policy import answers
from test_tool_gateway import fixture_run, headers


def approved_read(client, path='/source', max_bytes=64):
    output = json.dumps({'version': 1, 'action': 'project.web.read',
        'arguments': {'project_id': 'PROJECT_ID',
                      'url': f'https://example.test{path}',
                      'max_bytes': max_bytes, 'timeout_seconds': 1}})
    project, _, execution_id = fixture_run(client, output, web_grant=True)
    row = client.get('/api/tool-invocations', params={'project_id': project['id']}).json()[0]
    staged = client.post(f"/api/tool-invocations/{row['id']}/stage-web-read-approval",
                         headers=headers(client))
    assert staged.status_code == 200, staged.text
    decision = client.post(f"/api/tool-invocations/{row['id']}/decision",
        json={'approved': True, 'payload_hash': staged.json()['payload_hash']},
        headers=headers(client))
    assert decision.status_code == 200, decision.text
    return row['id'], execution_id, project['id']


def transport(port):
    def factory(host, public_port, ip, *, timeout):
        assert (host, public_port, ip) == ('example.test', 443, '8.8.8.8')
        return PinnedHTTPConnection(host, port, '127.0.0.1', timeout=timeout)
    return factory


def run(invocation_id, port, **kwargs):
    return run_read_effect_experiment(invocation_id, experiment_enabled=True,
        resolver=kwargs.pop('resolver', answers('8.8.8.8')),
        connection_factory=transport(port), **kwargs)


def change(client, invocation_id, execution_id, kind):
    if kind == 'cancel':
        assert client.post(f'/api/executions/{execution_id}/cancel',
                           headers=headers(client)).status_code == 200
        return
    with session_factory()() as db:
        invocation = db.get(ToolInvocation, invocation_id)
        source = db.get(Execution, execution_id)
        if kind in ('grant', 'grant_expiry'):
            grant = db.scalar(select(ReadDestinationGrant))
            if kind == 'grant':
                grant.revision += 1
            else:
                grant.expires_at = now() - timedelta(seconds=1)
        elif kind == 'policy':
            db.scalar(select(PolicyRule).where(PolicyRule.action == 'project.web.read')).effect = 'deny'
        elif kind == 'scope':
            db.scalar(select(AgentProjectGrant)).allowed = False
        elif kind == 'budget':
            account = db.get(BudgetAccount, source.root_id)
            account.reserved = account.cap - account.spent
        elif kind == 'approval':
            db.scalar(select(Approval)).decision_payload_hash = '0' * 64
        elif kind == 'expiry':
            db.scalar(select(Approval)).expires_at = now() - timedelta(seconds=1)
        elif kind == 'arguments':
            invocation.arguments = {**invocation.arguments, 'url': 'https://example.test/changed'}
        db.commit()


def test_durable_attempt_and_one_cited_observation(authenticated):
    invocation_id, _, project_id = approved_read(authenticated)
    with local_server() as (port, seen):
        with pytest.raises(ReadDenied, match='disabled'):
            run_read_effect_experiment(invocation_id, resolver=answers('8.8.8.8'),
                                       connection_factory=transport(port))
        def checkpoint():
            with session_factory()() as db:
                row = db.get(ReadEffectAttempt, invocation_id)
                assert row.status == 'unknown' and row.observation_id is None
            assert seen == []
            assert run(invocation_id, port) == 'unknown'
        assert run(invocation_id, port, after_attempt_commit=checkpoint) == 'succeeded'
        assert run(invocation_id, port) == 'succeeded'
        assert seen == ['/source']
    assert apply_admitted_tools() == 0
    with session_factory()() as db:
        attempt = db.get(ReadEffectAttempt, invocation_id)
        observation = db.get(ExternalReadObservation, attempt.observation_id)
        assert observation.invocation_key == f'read-effect:{invocation_id}'
        assert observation.trust_origin == 'external_claim'
        assert observation.source_url == 'https://example.test/source'
        assert observation.digest == hashlib.sha256(observation.content.encode()).hexdigest()
        assert len(db.scalars(select(ExternalReadObservation)).all()) == 1
    assert authenticated.get(f'/api/projects/{project_id}/read-observations').json()[0]['id'] == attempt.observation_id


@pytest.mark.parametrize('kind', ['cancel', 'grant', 'grant_expiry', 'policy', 'scope',
                                 'budget', 'approval', 'expiry', 'arguments'])
@pytest.mark.parametrize('checkpoint', ['before', 'after'])
def test_authority_changes_discard_without_provenance(authenticated, kind, checkpoint):
    invocation_id, execution_id, _ = approved_read(authenticated)
    with local_server() as (port, seen):
        hook = lambda: change(authenticated, invocation_id, execution_id, kind)
        assert run(invocation_id, port, **{
            'after_attempt_commit' if checkpoint == 'before' else 'after_fetch': hook}) == 'discarded'
        assert seen == ([] if checkpoint == 'before' else ['/source'])
        assert run(invocation_id, port) == 'discarded'
    with session_factory()() as db:
        assert db.scalar(select(ExternalReadObservation)) is None
        assert db.get(ToolInvocation, invocation_id).status == 'invalidated'


@pytest.mark.parametrize('checkpoint', ['after_attempt_commit', 'after_fetch'])
def test_crash_and_restart_never_repeat_unknown_outcome(authenticated, checkpoint):
    invocation_id, _, _ = approved_read(authenticated)
    def crash():
        raise RuntimeError('simulated process loss')
    with local_server() as (port, seen):
        with pytest.raises(RuntimeError, match='process loss'):
            run(invocation_id, port, **{checkpoint: crash})
        assert run(invocation_id, port) == 'unknown'
        assert seen == ([] if checkpoint == 'after_attempt_commit' else ['/source'])
    with session_factory()() as db:
        assert db.get(ReadEffectAttempt, invocation_id).status == 'unknown'
        assert db.scalar(select(ExternalReadObservation)) is None


def test_concurrent_duplicate_does_not_dispatch_again(authenticated):
    invocation_id, _, _ = approved_read(authenticated)
    ready, release = Event(), Event()
    def pause():
        ready.set()
        assert release.wait(10)
    with local_server() as (port, seen), ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(run, invocation_id, port, after_fetch=pause)
        try:
            assert ready.wait(10)
            assert pool.submit(run, invocation_id, port).result(timeout=5) == 'unknown'
        finally:
            release.set()
        assert first.result(timeout=10) == 'succeeded'
        assert seen == ['/source']


@pytest.mark.parametrize('ip', ['169.254.169.254', '127.0.0.1', '10.0.0.1',
                              '::ffff:169.254.169.254', '1.1.1.1'])
def test_rebinding_denies_before_connection(authenticated, ip):
    invocation_id, _, _ = approved_read(authenticated)
    calls = 0
    def resolver(host, port, *, type):
        nonlocal calls
        calls += 1
        return answers('8.8.8.8' if calls == 1 else ip)(host, port, type=type)
    with local_server() as (port, seen):
        with pytest.raises(ReadDenied):
            run(invocation_id, port, resolver=resolver)
        assert run(invocation_id, port) == 'unknown'
        assert seen == []


@pytest.mark.parametrize('path', ['/redirect', '/big'])
def test_redirect_and_oversize_never_create_observation(authenticated, path):
    invocation_id, _, _ = approved_read(authenticated, path)
    with local_server() as (port, seen):
        with pytest.raises(ReadDenied):
            run(invocation_id, port)
        assert run(invocation_id, port) == 'unknown'
        assert seen == [path]
    with session_factory()() as db:
        assert db.scalar(select(ExternalReadObservation)) is None


@pytest.mark.parametrize('kind', ['cancel', 'grant', 'policy', 'budget', 'approval'])
def test_initial_authority_denial_never_creates_attempt(authenticated, kind):
    invocation_id, execution_id, _ = approved_read(authenticated)
    change(authenticated, invocation_id, execution_id, kind)
    with local_server() as (port, seen):
        assert run(invocation_id, port) == 'denied'
        assert seen == []
    with session_factory()() as db:
        assert db.scalar(select(ReadEffectAttempt)) is None
