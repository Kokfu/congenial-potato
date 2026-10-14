from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import json
import os
import secrets
from threading import Event
from uuid import uuid4

import pytest

from workforce.local_read_experiment import ReadDenied
from workforce.read_broker_contract import (BrokerOutcomeUnknown, BrokerReadTicket,
    consume_ticket, execute_broker_read, sign_ticket, verify_ticket)
from test_local_read_experiment import local_server
from test_network_policy import answers
from test_read_effect_experiment import transport


@pytest.fixture
def journal(tmp_path):
    path = tmp_path / 'broker-journal'
    path.mkdir(mode=0o700)
    return path


def ticket(**changes):
    at = datetime.now(timezone.utc)
    data = dict(version=1, attempt_id=uuid4(), approval_id=uuid4(), project_id=uuid4(),
        agent_id=uuid4(), root_id=uuid4(), payload_hash='a'*64, policy_hash='b'*64,
        schema_hash='c'*64, grant_id=uuid4(), grant_revision=1,
        grant_expires_at=at+timedelta(hours=1), issued_at=at,
        expires_at=at+timedelta(seconds=30), url='https://example.test/source',
        max_bytes=64, timeout_seconds=1., addresses=('8.8.8.8',))
    return BrokerReadTicket(**(data | changes))


def run(envelope, key, journal, port, **kwargs):
    return execute_broker_read(envelope, key=key, journal=journal,
        resolver=kwargs.pop('resolver', answers('8.8.8.8')),
        connection_factory=transport(port), experiment_enabled=True, **kwargs)


def test_exact_ticket_and_durable_fence_precede_one_request(journal):
    key = secrets.token_bytes(32)
    expected = ticket()
    envelope = sign_ticket(expected, key=key)
    assert verify_ticket(envelope, key=key) == expected
    with local_server() as (port, seen):
        with pytest.raises(ReadDenied, match='disabled'):
            execute_broker_read(envelope, key=key, journal=journal,
                resolver=answers('8.8.8.8'), connection_factory=transport(port))
        def checkpoint():
            paths = list(journal.iterdir())
            assert len(paths) == 1 and paths[0].stat().st_mode & 0o077 == 0
            assert len(paths[0].read_bytes()) == 65
            assert 'source' not in paths[0].read_text() and seen == []
        result = run(envelope, key, journal, port, after_fence=checkpoint)
        assert result.trust_origin == 'external_claim' and result.text == 'A synthetic source claim'
        with pytest.raises(BrokerOutcomeUnknown):
            run(envelope, key, journal, port)
        assert seen == ['/source']


@pytest.mark.parametrize('field,value', [
    ('url', 'https://attacker.test/collect'), ('version', 2), ('max_bytes', 65),
    *[(field, (datetime.now(timezone.utc)+timedelta(seconds=10)).isoformat())
      for field in ('issued_at', 'expires_at', 'grant_expires_at')],
    ('timeout_seconds', 2), ('addresses', ['1.1.1.1']), ('grant_revision', 2),
    ('payload_hash', 'd'*64), ('policy_hash', 'd'*64), ('schema_hash', 'd'*64),
    *[(field, str(uuid4())) for field in ('attempt_id', 'approval_id', 'project_id',
                                        'agent_id', 'root_id', 'grant_id')],
])
def test_any_bound_field_change_without_signature_is_denied(journal, field, value):
    key = secrets.token_bytes(32)
    envelope = json.loads(sign_ticket(ticket(), key=key))
    envelope['ticket'][field] = value
    with pytest.raises(ReadDenied):
        verify_ticket(json.dumps(envelope), key=key)
    assert list(journal.iterdir()) == []


def test_wrong_key_duplicate_fields_extra_fields_and_oversize_rejected():
    key = secrets.token_bytes(32)
    envelope = sign_ticket(ticket(), key=key)
    for changed in [envelope[:-1]+',"signature":"'+'0'*64+'"}', envelope+' '*16385,
                    envelope[:-1]+',"approved":true}', '{"ticket":{}}']:
        with pytest.raises(ReadDenied):
            verify_ticket(changed, key=key)
    with pytest.raises(ReadDenied):
        verify_ticket(envelope, key=secrets.token_bytes(32))
    with pytest.raises(ReadDenied):
        verify_ticket(envelope, key=b'weak')


@pytest.mark.parametrize('changes', [
    {'url': 'http://example.test/source'}, {'url': 'https://example.test:0/source'},
    {'url': 'https://user@example.test/source'}, {'url': 'https://example.test/source#x'},
    {'addresses': ('169.254.169.254',)}, {'addresses': ('8.8.8.8', '127.0.0.1')},
    {'addresses': ('::ffff:169.254.169.254',)}, {'addresses': ('8.8.8.8', '1.1.1.1')},
    {'addresses': ('8.8.8.8', '8.8.8.8')}, {'max_bytes': 65537},
    {'timeout_seconds': 6.}, {'grant_revision': True}, {'version': True},
])
def test_invalid_broker_contract_is_rejected(changes):
    with pytest.raises(ValueError):
        ticket(**changes)


def test_expired_future_and_overlong_tickets_fail_closed():
    key = secrets.token_bytes(32)
    at = datetime.now(timezone.utc)
    for changes in [
        {'issued_at': at-timedelta(seconds=10), 'expires_at': at-timedelta(seconds=1)},
        {'issued_at': at+timedelta(seconds=1), 'expires_at': at+timedelta(seconds=5)},
        {'expires_at': at+timedelta(seconds=40)},
        {'grant_expires_at': at+timedelta(seconds=1)},
        {'issued_at': at.replace(tzinfo=None)},
    ]:
        with pytest.raises(ValueError):
            sign_ticket(ticket(**changes), key=key)


def test_concurrent_duplicate_cannot_dispatch_twice(journal):
    key = secrets.token_bytes(32)
    envelope = sign_ticket(ticket(), key=key)
    ready, release = Event(), Event()
    def pause():
        ready.set()
        assert release.wait(10)
    with local_server() as (port, seen), ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(run, envelope, key, journal, port, after_fence=pause)
        try:
            assert ready.wait(10)
            duplicate = pool.submit(run, envelope, key, journal, port)
            with pytest.raises(BrokerOutcomeUnknown):
                duplicate.result(timeout=5)
        finally:
            release.set()
        assert first.result(timeout=10).text == 'A synthetic source claim'
        assert seen == ['/source']


def test_crash_after_fence_and_changed_replay_remain_unknown(journal):
    key = secrets.token_bytes(32)
    expected = ticket()
    envelope = sign_ticket(expected, key=key)
    def crash():
        raise RuntimeError('simulated broker loss')
    with local_server() as (port, seen):
        with pytest.raises(RuntimeError):
            run(envelope, key, journal, port, after_fence=crash)
        for replay in (envelope, sign_ticket(expected.model_copy(update={'max_bytes': 32}), key=key)):
            with pytest.raises(BrokerOutcomeUnknown):
                run(replay, key, journal, port)
        assert seen == []


def test_journal_symlink_permissions_and_fsync_failure_deny_fetch(tmp_path, monkeypatch):
    key = secrets.token_bytes(32)
    expected = ticket()
    journal = tmp_path / 'journal'
    journal.mkdir(mode=0o700)
    alias = tmp_path / 'alias'
    alias.symlink_to(journal, target_is_directory=True)
    with pytest.raises(ReadDenied):
        consume_ticket(expected, journal=alias)
    journal.chmod(0o755)
    with pytest.raises(ReadDenied):
        consume_ticket(expected, journal=journal)
    journal.chmod(0o700)
    def fail(_fd):
        raise OSError('synthetic fsync failure')
    monkeypatch.setattr(os, 'fsync', fail)
    with local_server() as (port, seen):
        with pytest.raises(ReadDenied, match='persisted'):
            run(sign_ticket(expected, key=key), key, journal, port)
        with pytest.raises(BrokerOutcomeUnknown):
            run(sign_ticket(expected, key=key), key, journal, port)
        assert seen == []


@pytest.mark.parametrize('address', ['169.254.169.254', '127.0.0.1', '1.1.1.1'])
def test_broker_reresolves_and_never_retries_changed_dns(journal, address):
    key = secrets.token_bytes(32)
    envelope = sign_ticket(ticket(), key=key)
    with local_server() as (port, seen):
        with pytest.raises(ReadDenied):
            run(envelope, key, journal, port, resolver=answers(address))
        with pytest.raises(BrokerOutcomeUnknown):
            run(envelope, key, journal, port)
        assert seen == []


def test_expiry_after_fence_never_dispatches(journal):
    import time
    key = secrets.token_bytes(32)
    at = datetime.now(timezone.utc)
    expected = ticket(issued_at=at, expires_at=at+timedelta(seconds=.2))
    with local_server() as (port, seen):
        with pytest.raises(ReadDenied, match='expired'):
            run(sign_ticket(expected, key=key), key, journal, port,
                after_fence=lambda: time.sleep(.25))
        assert seen == [] and len(list(journal.iterdir())) == 1


@pytest.mark.parametrize('phase', ['fence', 'fetch'])
def test_process_crash_and_fresh_broker_never_repeat(journal, tmp_path, phase):
    import subprocess
    import sys
    key_path, envelope_path = tmp_path / 'broker-key', tmp_path / 'envelope'
    key = secrets.token_bytes(32)
    key_path.write_bytes(key)
    key_path.chmod(0o600)
    envelope_path.write_text(sign_ticket(ticket(), key=key))
    program = '''
import os, socket, sys
from pathlib import Path
from workforce.network_policy import PinnedHTTPConnection
from workforce.read_broker_contract import execute_broker_read, BrokerOutcomeUnknown

def resolve(host, port, *, type):
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('8.8.8.8', port))]
def factory(host, port, ip, *, timeout):
    assert (host, port, ip) == ('example.test',443,'8.8.8.8')
    return PinnedHTTPConnection(host,int(sys.argv[4]),'127.0.0.1',timeout=timeout)
try:
    execute_broker_read(Path(sys.argv[3]).read_text(), key=Path(sys.argv[2]).read_bytes(),
        journal=Path(sys.argv[1]), resolver=resolve, connection_factory=factory,
        experiment_enabled=True,
        after_fence=(lambda: os._exit(73)) if sys.argv[5]=='fence' else None)
    os._exit(73)
except BrokerOutcomeUnknown:
    print('unknown; no retry')
'''
    with local_server() as (port, seen):
        args = [sys.executable, '-c', program, str(journal), str(key_path), str(envelope_path), str(port)]
        crashed = subprocess.run(args+[phase], capture_output=True, text=True, timeout=15)
        assert crashed.returncode == 73, crashed.stderr
        restarted = subprocess.run(args+['restart'], capture_output=True, text=True, timeout=15)
        assert restarted.returncode == 0, restarted.stderr
        assert restarted.stdout.strip() == 'unknown; no retry'
        assert seen == ([] if phase == 'fence' else ['/source'])
