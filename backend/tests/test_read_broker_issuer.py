from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
import hashlib
import json
import secrets

import pytest
from sqlalchemy import select

from workforce.db import session_factory
from workforce.local_read_experiment import ReadDenied
from workforce.models import (Approval, AuditEvent, Execution, ExternalReadObservation,
    ReadDestinationGrant, ReadEffectAttempt, ToolInvocation, now)
from workforce.read_broker_contract import BrokerOutcomeUnknown, verify_ticket
from workforce.read_broker_issuer import begin_broker_attempt, issue_broker_ticket
from workforce.read_effect_experiment import run_read_effect_experiment
from workforce.tool_approval import _digest, exact_payload
from test_local_read_experiment import local_server
from test_network_policy import answers
from test_read_effect_experiment import approved_read, change, run


def begin(invocation_id):
    return begin_broker_attempt(invocation_id, resolver=answers('8.8.8.8'),
                                 experiment_enabled=True)


def issue(invocation_id, capability, prepared, key, **kwargs):
    return issue_broker_ticket(invocation_id, capability=capability, prepared=prepared,
        key=key, resolver=kwargs.pop('resolver', answers('8.8.8.8')),
        experiment_enabled=True, **kwargs)


def test_issuer_derives_and_commits_exact_authority_without_dispatch(authenticated):
    invocation_id, source_id, project_id = approved_read(authenticated)
    with pytest.raises(ReadDenied, match='disabled'):
        begin_broker_attempt(invocation_id, resolver=answers('8.8.8.8'))
    capability, prepared = begin(invocation_id)
    with session_factory()() as db:
        attempt = db.get(ReadEffectAttempt, invocation_id)
        assert attempt.status == 'unknown' and attempt.broker_ticket_hash is None
        assert attempt.broker_capability_hash == hashlib.sha256(capability).hexdigest()
    key = secrets.token_bytes(32)
    envelope = issue(invocation_id, capability, prepared, key)
    ticket = verify_ticket(envelope, key=key)
    with session_factory()() as db:
        attempt = db.get(ReadEffectAttempt, invocation_id)
        invocation = db.get(ToolInvocation, invocation_id)
        source = db.get(Execution, source_id)
        approval = db.scalar(select(Approval).where(Approval.tool_invocation_id == invocation_id))
        grant = db.scalar(select(ReadDestinationGrant))
        assert str(ticket.attempt_id) == invocation.id
        assert str(ticket.project_id) == project_id
        assert str(ticket.agent_id) == source.agent_id and str(ticket.root_id) == source.root_id
        assert str(ticket.approval_id) == approval.id and ticket.payload_hash == approval.payload_hash
        assert ticket.payload_hash == attempt.payload_hash == _digest(exact_payload(invocation))
        assert ticket.policy_hash == _digest(invocation.policy_snapshot)
        assert ticket.schema_hash == invocation.schema_hash
        assert str(ticket.grant_id) == grant.id and ticket.grant_revision == grant.revision
        assert ticket.grant_expires_at == grant.expires_at
        assert ticket.url == invocation.arguments['url'] and ticket.addresses == prepared.addresses
        assert ticket.max_bytes == invocation.arguments['max_bytes']
        assert ticket.expires_at <= min(approval.expires_at, grant.expires_at)
        assert attempt.broker_ticket_hash == hashlib.sha256(envelope.encode()).hexdigest()
        assert attempt.broker_issued_at == ticket.issued_at
        assert attempt.status == 'unknown' and invocation.status == 'approved_staged'
        assert db.scalar(select(ExternalReadObservation)) is None
        details = json.dumps([r.detail for r in db.scalars(select(AuditEvent).where(
            AuditEvent.action.in_(['read.broker.prepare','read.broker.issue'])))])
        assert capability.hex() not in details and key.hex() not in details
        assert envelope not in details and 'signature' not in details
    with pytest.raises(BrokerOutcomeUnknown):
        issue(invocation_id, capability, prepared, secrets.token_bytes(32))
    with pytest.raises(BrokerOutcomeUnknown):
        begin(invocation_id)


@pytest.mark.parametrize('kind', ['cancel', 'grant', 'grant_expiry', 'policy', 'scope',
                                 'budget', 'approval', 'expiry', 'arguments'])
@pytest.mark.parametrize('phase', ['prepare', 'issue'])
def test_issuer_rechecks_each_authority(authenticated, kind, phase):
    invocation_id, source_id, _ = approved_read(authenticated)
    if phase == 'issue':
        capability, prepared = begin(invocation_id)
    change(authenticated, invocation_id, source_id, kind)
    with pytest.raises(ReadDenied):
        if phase == 'prepare':
            begin(invocation_id)
        else:
            issue(invocation_id, capability, prepared, secrets.token_bytes(32))
    with session_factory()() as db:
        attempt = db.get(ReadEffectAttempt, invocation_id)
        if phase == 'prepare':
            assert attempt is None
        else:
            assert attempt.status == 'discarded' and attempt.broker_ticket_hash is None
        assert db.scalar(select(ExternalReadObservation)) is None


def test_wrong_or_lost_capability_cannot_issue(authenticated):
    invocation_id, _, _ = approved_read(authenticated)
    capability, prepared = begin(invocation_id)
    key = secrets.token_bytes(32)
    for wrong in (None, b'short', secrets.token_bytes(32)):
        with pytest.raises(ReadDenied, match='capability'):
            issue(invocation_id, wrong, prepared, key)
    assert verify_ticket(issue(invocation_id, capability, prepared, key), key=key)


def test_old_unknown_local_fetch_cannot_be_reissued_via_broker(authenticated):
    invocation_id, _, _ = approved_read(authenticated)
    def crash():
        raise RuntimeError('lost local response')
    with local_server() as (port, seen):
        with pytest.raises(RuntimeError):
            run(invocation_id, port, after_fetch=crash)
        with pytest.raises(BrokerOutcomeUnknown):
            begin(invocation_id)
        from workforce.network_policy import PinnedDestination
        prepared = PinnedDestination('example.test', 443, ('8.8.8.8',))
        with pytest.raises(ReadDenied, match='capability'):
            issue(invocation_id, secrets.token_bytes(32), prepared, secrets.token_bytes(32))
        assert run(invocation_id, port) == 'unknown' and seen == ['/source']


def test_broker_unknown_cannot_fall_back_to_local_transport(authenticated):
    invocation_id, _, _ = approved_read(authenticated)
    begin(invocation_id)
    with local_server() as (port, seen):
        assert run(invocation_id, port) == 'unknown' and seen == []


def test_concurrent_ticket_issuance_is_once(authenticated):
    invocation_id, _, _ = approved_read(authenticated)
    capability, prepared = begin(invocation_id)
    key = secrets.token_bytes(32)
    def attempt(_):
        try:
            issue(invocation_id, capability, prepared, key)
            return 'issued'
        except BrokerOutcomeUnknown:
            return 'unknown'
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(attempt, range(2))) == ['issued', 'unknown']
    with session_factory()() as db:
        rows = db.scalars(select(AuditEvent).where(AuditEvent.action == 'read.broker.issue')).all()
        assert len(rows) == 1


@pytest.mark.parametrize('address', ['169.254.169.254', '127.0.0.1', '1.1.1.1'])
def test_changed_dns_cannot_get_an_issued_ticket(authenticated, address):
    invocation_id, _, _ = approved_read(authenticated)
    capability, prepared = begin(invocation_id)
    with pytest.raises(ReadDenied):
        issue(invocation_id, capability, prepared, secrets.token_bytes(32), resolver=answers(address))
    with session_factory()() as db:
        attempt = db.get(ReadEffectAttempt, invocation_id)
        assert attempt.status == 'unknown' and attempt.broker_ticket_hash is None


def test_ticket_expiry_cannot_outlive_approval_or_grant(authenticated):
    invocation_id, _, _ = approved_read(authenticated)
    with session_factory()() as db:
        approval = db.scalar(select(Approval))
        grant = db.scalar(select(ReadDestinationGrant))
        approval.expires_at = now()+timedelta(seconds=19)
        grant.expires_at = now()+timedelta(seconds=21)
        db.commit()
        expires = approval.expires_at
    capability, prepared = begin(invocation_id)
    key = secrets.token_bytes(32)
    assert verify_ticket(issue(invocation_id, capability, prepared, key), key=key).expires_at == expires


@pytest.mark.parametrize('phase', ['prepare', 'issue'])
def test_lost_process_cannot_recover_dispatch_capability(authenticated, tmp_path, phase):
    import subprocess
    import sys
    invocation_id, _, _ = approved_read(authenticated)
    key_path = tmp_path / 'broker-key'
    key_path.write_bytes(secrets.token_bytes(32))
    key_path.chmod(0o600)
    program = '''
import os, socket, sys
from pathlib import Path
from workforce.read_broker_issuer import begin_broker_attempt, issue_broker_ticket

def resolve(host, port, *, type):
    return [(socket.AF_INET,socket.SOCK_STREAM,6,'',('8.8.8.8',port))]
capability, prepared = begin_broker_attempt(sys.argv[1], resolver=resolve, experiment_enabled=True)
if sys.argv[3] == 'issue':
    issue_broker_ticket(sys.argv[1],capability=capability,prepared=prepared,
        key=Path(sys.argv[2]).read_bytes(),resolver=resolve,experiment_enabled=True)
os._exit(73)
'''
    result = subprocess.run([sys.executable, '-c', program, invocation_id, str(key_path), phase],
                            capture_output=True, text=True, timeout=15)
    assert result.returncode == 73, result.stderr
    with pytest.raises(BrokerOutcomeUnknown):
        begin(invocation_id)
    from workforce.network_policy import PinnedDestination
    with pytest.raises(ReadDenied, match='capability'):
        issue(invocation_id, secrets.token_bytes(32),
              PinnedDestination('example.test',443,('8.8.8.8',)), key_path.read_bytes())
    with session_factory()() as db:
        attempt = db.get(ReadEffectAttempt, invocation_id)
        assert attempt.status == 'unknown' and attempt.broker_capability_hash is not None
        assert (attempt.broker_ticket_hash is not None) == (phase == 'issue')
        assert db.scalar(select(ExternalReadObservation)) is None
