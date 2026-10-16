"""Control-database admission and authority checks for the local fake writer."""
import hashlib
import json
import os
import sqlite3
import socket
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from tempfile import TemporaryDirectory
from datetime import datetime, timezone
from threading import Barrier, Event
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select

from workforce.db import session_factory
from workforce.models import (AgentProjectGrant, Approval, AuditEvent, BudgetAccount,
    Execution, PolicyRule, SyntheticWriteAdmission, SyntheticWriteLedgerControl,
    ToolInvocation)
from synthetic_write_admission import (SyntheticWriteAdmissionDenied,
    SyntheticWriteAdmissionUnknown, execute_governed_fake_write)
from workforce.synthetic_write_contract import (SyntheticWriteIntent,
    ReconciliationQuery, WriteContractError, intent_digest, parse_write_intent,
    verify_reconciliation_result, verify_write_receipt)
from synthetic_write_ledger import SyntheticWriteLedger
from workforce.tool_approval import _digest
from test_tool_approval import decide, proposed_write
from durable_local_recovery_witness import (DurableLocalRecoveryWitness,
    WitnessDenied, request_mac, verify_response)

from durable_local_witness_transport import (LocalWitnessUnixServer,
    UnixWitnessClient, WitnessTransportDenied)

KEY = b'w' * 32
LEDGER_ID = UUID('5f94d899-9e2c-4f4e-9d2f-62b62102ae51')


def prepared(authenticated, tmp_path, *, artifact_id=None):
    _, _, artifact_id, row = proposed_write(authenticated, artifact_id=artifact_id)
    assert decide(authenticated, row).status_code == 200
    ledger_dir = tmp_path/'private-ledger'
    ledger_dir.mkdir(mode=0o700, parents=True)
    with session_factory()() as db:
        invocation = db.get(ToolInvocation, row['id'])
        source = db.get(Execution, invocation.execution_id)
        approval = db.scalar(select(Approval).where(
            Approval.tool_invocation_id == invocation.id))
        raw = {'version': 1, 'action': 'synthetic.record.replace',
            'scope': {'project_id': invocation.project_id, 'agent_id': source.agent_id,
                'root_id': source.root_id, 'invocation_id': invocation.id},
            'ledger_id': str(LEDGER_ID), 'record_id': artifact_id,
            'expected_revision': 0,
            'content_sha256': hashlib.sha256(invocation.arguments['content'].encode()).hexdigest(),
            'content_size': len(invocation.arguments['content'].encode()),
            'approval_payload_sha256': approval.payload_hash,
            'policy_snapshot_sha256': _digest(invocation.policy_snapshot)}
    intent = parse_write_intent(json.dumps(raw))
    return row['id'], intent, ledger_dir


def run(invocation_id, intent, directory, **kwargs):
    return execute_governed_fake_write(invocation_id, intent,
        ledger_directory=directory, ledger_id=LEDGER_ID, ledger_key=KEY,
        experiment_enabled=True, **kwargs)


def test_commit_independent_fence_before_ledger_and_return_fixture_receipt(authenticated, tmp_path):
    invocation_id, intent, directory = prepared(authenticated, tmp_path)
    def committed():
        with session_factory()() as db:
            row = db.get(SyntheticWriteAdmission, invocation_id)
            assert row.status == 'unknown' and row.intent_sha256 == intent_digest(intent)
            assert db.get(SyntheticWriteLedgerControl, 1).ledger_id == str(intent.ledger_id)
            assert not (directory/'ledger.sqlite3').exists()
    signed = run(invocation_id, intent, directory, after_admission_commit=committed)
    receipt = verify_write_receipt(signed, intent, key=KEY)
    assert receipt.result_revision == 1
    ledger = SyntheticWriteLedger(directory, ledger_id=intent.ledger_id,
        key=KEY, experiment_enabled=True)
    query = ReconciliationQuery(version=1, intent_sha256=intent_digest(intent),
        nonce=uuid4(), issued_at=datetime.now(timezone.utc))
    reply = ledger.reconcile(intent, query.model_dump_json())
    assert verify_reconciliation_result(reply, query, intent, key=KEY).outcome == 'applied'
    with session_factory()() as db:
        row = db.get(SyntheticWriteAdmission, invocation_id)
        assert row.status == 'unknown'
        assert row.approval_payload_sha256 == intent.approval_payload_sha256
        assert row.policy_snapshot_sha256 == intent.policy_snapshot_sha256
        assert len(db.scalars(select(AuditEvent).where(
            AuditEvent.action == 'synthetic.write.admission')).all()) == 1


@pytest.mark.parametrize('change', ['policy', 'grant', 'budget', 'cancel',
                                    'approval', 'arguments', 'agent'])
def test_current_authority_is_required_before_database_fence(authenticated, tmp_path, change):
    invocation_id, intent, directory = prepared(authenticated, tmp_path)
    with session_factory()() as db:
        invocation = db.get(ToolInvocation, invocation_id)
        source = db.get(Execution, invocation.execution_id)
        if change == 'policy':
            rule = db.scalar(select(PolicyRule).where(
                PolicyRule.subject == f'agent:{source.agent_id}',
                PolicyRule.action == 'project.artifact.write'))
            rule.effect = 'deny'
        elif change == 'grant':
            grant = db.scalar(select(AgentProjectGrant).where(
                AgentProjectGrant.agent_id == source.agent_id,
                AgentProjectGrant.project_id == invocation.project_id))
            grant.allowed = False
        elif change == 'budget':
            db.get(BudgetAccount, source.root_id).cap = 0
        elif change == 'cancel':
            source.cancelled = True
        elif change == 'approval':
            db.scalar(select(Approval).where(
                Approval.tool_invocation_id == invocation_id)).decision_payload_hash = '0'*64
        elif change == 'arguments':
            invocation.arguments = invocation.arguments | {'content': 'substituted'}
        elif change == 'agent':
            from workforce.models import Agent
            db.get(Agent, source.agent_id).status = 'paused'
        db.commit()
    with pytest.raises(SyntheticWriteAdmissionDenied):
        run(invocation_id, intent, directory)
    assert not (directory/'ledger.sqlite3').exists()
    with session_factory()() as db:
        assert db.get(SyntheticWriteAdmission, invocation_id) is None


def test_authority_change_after_fence_keeps_unknown_and_never_opens_ledger(authenticated, tmp_path):
    invocation_id, intent, directory = prepared(authenticated, tmp_path)
    def revoke():
        with session_factory()() as db:
            rule = db.scalar(select(PolicyRule).where(
                PolicyRule.subject.like('agent:%'),
                PolicyRule.action == 'project.artifact.write'))
            rule.effect = 'deny'
            db.commit()
    with pytest.raises(SyntheticWriteAdmissionDenied):
        run(invocation_id, intent, directory, after_admission_commit=revoke)
    assert not (directory/'ledger.sqlite3').exists()
    with session_factory()() as db:
        assert db.get(SyntheticWriteAdmission, invocation_id).status == 'unknown'
    with pytest.raises(SyntheticWriteAdmissionUnknown): run(invocation_id, intent, directory)
    assert not (directory/'ledger.sqlite3').exists()


def test_consumed_fence_blocks_missing_or_replaced_ledger_before_open(authenticated, tmp_path):
    invocation_id, intent, directory = prepared(authenticated, tmp_path)
    with pytest.raises(RuntimeError, match='simulated loss before ledger open'):
        run(invocation_id, intent, directory, after_admission_commit=lambda: (_ for _ in ()).throw(
            RuntimeError('simulated loss before ledger open')))
    ledger_path = directory/'ledger.sqlite3'
    assert not ledger_path.exists()
    with pytest.raises(SyntheticWriteAdmissionUnknown): run(invocation_id, intent, directory)
    assert not ledger_path.exists()
    # An exact original invocation also remains fenced after a successful write
    # and deletion of its entire private ledger file.
    other_id, other_intent, other_dir = prepared(authenticated, tmp_path/'second')
    other_intent = other_intent.model_copy(update={'ledger_id': intent.ledger_id})
    run(other_id, other_intent, other_dir)
    (other_dir/'ledger.sqlite3').unlink()
    replacement = SyntheticWriteLedger(other_dir, ledger_id=LEDGER_ID,
        key=KEY, experiment_enabled=True)
    with sqlite3.connect(replacement.path) as db:
        assert db.execute('SELECT count(*) FROM records').fetchone()[0] == 0
    with pytest.raises(SyntheticWriteAdmissionUnknown): run(other_id, other_intent, other_dir)
    with sqlite3.connect(replacement.path) as db:
        assert db.execute('SELECT count(*) FROM records').fetchone()[0] == 0
        assert db.execute('SELECT count(*) FROM attempts').fetchone()[0] == 0


def test_actual_process_exit_after_control_commit_is_unknown_in_fresh_interpreter(authenticated, tmp_path):
    invocation_id, intent, directory = prepared(authenticated, tmp_path)
    config = tmp_path/'private-admission.json'
    config.write_text(json.dumps({'invocation_id': invocation_id,
        'intent': intent.model_dump(mode='json'), 'directory': str(directory),
        'key': KEY.hex(), 'ledger_id': str(LEDGER_ID)}))
    config.chmod(0o600)
    program = '''
import json, os, sys
from pathlib import Path
from uuid import UUID
from synthetic_write_admission import execute_governed_fake_write
from workforce.synthetic_write_contract import parse_write_intent
p=json.loads(Path(sys.argv[1]).read_text())
i=parse_write_intent(json.dumps(p['intent']))
execute_governed_fake_write(p['invocation_id'], i, ledger_directory=p['directory'],
    ledger_id=UUID(p['ledger_id']), ledger_key=bytes.fromhex(p['key']), experiment_enabled=True,
    after_admission_commit=lambda:os._exit(79))
'''
    lost = subprocess.run([sys.executable, '-c', program, str(config)],
        capture_output=True, text=True, timeout=20)
    assert lost.returncode == 79, lost.stderr
    with pytest.raises(SyntheticWriteAdmissionUnknown): run(invocation_id, intent, directory)
    assert not (directory/'ledger.sqlite3').exists()
    with session_factory()() as db:
        assert db.get(SyntheticWriteAdmission, invocation_id).status == 'unknown'


@pytest.mark.parametrize('field', ['project_id', 'agent_id', 'root_id', 'invocation_id',
    'ledger_id', 'record_id', 'expected_revision', 'content_sha256', 'content_size',
    'approval_payload_sha256', 'policy_snapshot_sha256'])
def test_intent_substitution_is_rejected_without_fence_or_ledger(authenticated, tmp_path, field):
    invocation_id, intent, directory = prepared(authenticated, tmp_path)
    if field in ('project_id', 'agent_id', 'root_id', 'invocation_id'):
        altered = intent.model_copy(update={'scope': intent.scope.model_copy(
            update={field: uuid4()})})
    elif field.endswith('_id'):
        altered = intent.model_copy(update={field: uuid4()})
    else:
        values = {'expected_revision': 1, 'content_sha256': 'b'*64,
            'content_size': 1, 'approval_payload_sha256': 'a'*64,
            'policy_snapshot_sha256': 'c'*64}
        altered = intent.model_copy(update={field: values[field]})
    with pytest.raises(SyntheticWriteAdmissionDenied): run(invocation_id, altered, directory)
    with session_factory()() as db:
        assert db.get(SyntheticWriteAdmission, invocation_id) is None
        assert db.get(SyntheticWriteLedgerControl, 1) is None
    assert not (directory/'ledger.sqlite3').exists()


def test_concurrent_delivery_consumes_one_control_fence_and_one_fake_effect(authenticated, tmp_path):
    invocation_id, intent, directory = prepared(authenticated, tmp_path)
    barrier = Barrier(2)
    def attempt():
        barrier.wait(timeout=5)
        try:
            return ('applied', run(invocation_id, intent, directory))
        except SyntheticWriteAdmissionUnknown:
            return ('unknown', None)
    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(lambda _: attempt(), range(2)))
    assert sorted(label for label, _ in outcomes) == ['applied', 'unknown']
    ledger_path = directory/'ledger.sqlite3'
    with sqlite3.connect(ledger_path) as db:
        assert db.execute('SELECT count(*) FROM records').fetchone()[0] == 1
        assert db.execute('SELECT count(*) FROM attempts').fetchone()[0] == 1
    with session_factory()() as db:
        assert len(db.scalars(select(SyntheticWriteAdmission)).all()) == 1


def test_one_ledger_identity_is_pinned_and_target_revision_is_single_use(authenticated, tmp_path):
    invocation_id, intent, directory = prepared(authenticated, tmp_path)
    run(invocation_id, intent, directory)
    replacement_id, replacement_intent, replacement_dir = prepared(authenticated,
        tmp_path/'replacement', artifact_id=str(intent.record_id))
    replacement_intent = replacement_intent.model_copy(update={'ledger_id': intent.ledger_id})
    with pytest.raises(SyntheticWriteAdmissionUnknown, match='target revision'):
        run(replacement_id, replacement_intent, replacement_dir)
    assert not (replacement_dir/'ledger.sqlite3').exists()


def test_downgrade_cannot_erase_consumed_admission_or_ledger_identity(authenticated, tmp_path):
    invocation_id, intent, directory = prepared(authenticated, tmp_path)
    with pytest.raises(RuntimeError, match='simulated loss before ledger open'):
        run(invocation_id, intent, directory, after_admission_commit=lambda: (_ for _ in ()).throw(
            RuntimeError('simulated loss before ledger open')))
    backend = Path(__file__).resolve().parents[1]
    result = subprocess.run([sys.executable, '-m', 'alembic', 'downgrade', 'ca53e6f90274'],
        cwd=backend, capture_output=True, text=True, timeout=20)
    assert result.returncode != 0
    assert 'Cannot erase consumed synthetic write admission or ledger identity' in result.stderr
    with pytest.raises(SyntheticWriteAdmissionUnknown): run(invocation_id, intent, directory)
    assert not (directory/'ledger.sqlite3').exists()


def test_empty_admission_schema_downgrade_upgrade_round_trip():
    backend = Path(__file__).resolve().parents[1]
    for arguments in (('downgrade', 'ca53e6f90274'), ('upgrade', 'head')):
        result = subprocess.run([sys.executable, '-m', 'alembic', *arguments],
            cwd=backend, capture_output=True, text=True, timeout=20)
        assert result.returncode == 0, result.stderr


def test_disabled_before_database_or_ledger_access(authenticated, tmp_path):
    invocation_id, intent, directory = prepared(authenticated, tmp_path)
    with pytest.raises(WriteContractError, match='disabled'):
        execute_governed_fake_write(invocation_id, intent,
            ledger_directory=directory, ledger_id=LEDGER_ID, ledger_key=KEY,
            experiment_enabled=False)
    assert not (directory/'ledger.sqlite3').exists()
    with session_factory()() as db:
        assert db.get(SyntheticWriteAdmission, invocation_id) is None


def test_joint_control_and_ledger_restore_exposes_reexecution_gap(authenticated, tmp_path):
    """A rollback of both stores erases the current replay fence."""
    invocation_id, intent, directory = prepared(authenticated, tmp_path)
    first = verify_write_receipt(run(invocation_id, intent, directory), intent, key=KEY)
    # Model restoring a pre-admission control snapshot and its matching empty
    # ledger snapshot. This destructive operation touches disposable fixture state only.
    with session_factory()() as db:
        db.delete(db.get(SyntheticWriteAdmission, invocation_id))
        db.delete(db.get(SyntheticWriteLedgerControl, 1))
        db.commit()
    (directory/'ledger.sqlite3').unlink()
    second = verify_write_receipt(run(invocation_id, intent, directory), intent, key=KEY)
    assert second.event_id != first.event_id
    with sqlite3.connect(directory/'ledger.sqlite3') as db:
        assert db.execute('SELECT revision FROM records').fetchone()[0] == 1
        assert db.execute('SELECT count(*) FROM attempts').fetchone()[0] == 1


@pytest.mark.parametrize('transport', ['direct', pytest.param('unix',
    marks=pytest.mark.skipif(not hasattr(socket, 'SO_PEERCRED'),
        reason='local peer credential transport requires Linux SO_PEERCRED'))])
@pytest.mark.parametrize('rollback', ['control', 'ledger', 'both'])
def test_live_witness_blocks_single_or_joint_store_rollback(authenticated, tmp_path, rollback, transport):
    invocation_id, intent, directory = prepared(authenticated, tmp_path)
    witness_path = tmp_path/'separate-witness-fixture'/'witness.sqlite3'
    witness = DurableLocalRecoveryWitness(witness_path,
        caller_keys={'synthetic-write-fixture': b'c'*32}, state_key=b'r'*32,
        initialize=True)

    @contextmanager
    def connected(witness):
        if transport == 'unix':
            # Keep AF_UNIX paths below the kernel limit even for long pytest IDs.
            with TemporaryDirectory(prefix='witness-pg-') as private:
                path = Path(private)/'w.sock'
                with LocalWitnessUnixServer(witness, path):
                    client = UnixWitnessClient(path,
                        caller_id='synthetic-write-fixture', key=b'c'*32)
                    yield client.request
        else:
            def authenticated_call(request):
                caller_id = 'synthetic-write-fixture'
                mac = request_mac(b'c'*32, caller_id, request)
                method = getattr(witness, request['operation'])
                envelope = method(caller_id=caller_id, request=request, mac=mac)
                return verify_response(b'c'*32, envelope,
                    expected_request_mac=mac, expected_request=request)
            yield authenticated_call

    def witnessed_effect(call):
        binding = {'operation': 'reserve', 'request_id': invocation_id,
            'ledger_id': str(intent.ledger_id), 'invocation_id': invocation_id,
            'intent_sha256': intent_digest(intent)}
        permit = call(binding)
        consume = {'operation': 'consume', **{key: permit[key] for key in
            ('request_id','ledger_id','invocation_id','intent_sha256','generation',
             'state_key_id','nonce')},
            'ticket_mac': permit['ticket_mac']}
        call(consume)
        return run(invocation_id, intent, directory)

    with connected(witness) as call:
        witnessed_effect(call)
    # Reopen the witness and, for Unix transport, start a new server instance.
    witness = DurableLocalRecoveryWitness(witness_path,
        caller_keys={'synthetic-write-fixture': b'c'*32}, state_key=b'r'*32)
    if rollback in ('control', 'both'):
        with session_factory()() as db:
            db.delete(db.get(SyntheticWriteAdmission, invocation_id))
            db.delete(db.get(SyntheticWriteLedgerControl, 1))
            db.commit()
    if rollback in ('ledger', 'both'):
        (directory/'ledger.sqlite3').unlink()

    denial = WitnessTransportDenied if transport == 'unix' else WitnessDenied
    reason = 'denied or response unavailable' if transport == 'unix' else 'consumed'
    with connected(witness) as call:
        # Prove restarted transport/authentication are healthy before replay denial.
        assert call({'operation': 'generation'})['generation'] == 1
        with pytest.raises(denial, match=reason):
            witnessed_effect(call)
    if rollback in ('control', 'both'):
        with session_factory()() as db:
            assert db.get(SyntheticWriteAdmission, invocation_id) is None
            assert db.get(SyntheticWriteLedgerControl, 1) is None
    else:
        with session_factory()() as db:
            assert db.get(SyntheticWriteAdmission, invocation_id).status == 'unknown'
    if rollback in ('ledger', 'both'):
        assert not (directory/'ledger.sqlite3').exists()
    else:
        with sqlite3.connect(directory/'ledger.sqlite3') as db:
            assert db.execute('SELECT count(*) FROM records').fetchone()[0] == 1
            assert db.execute('SELECT count(*) FROM attempts').fetchone()[0] == 1


@pytest.mark.skipif(not hasattr(socket, 'SO_PEERCRED'),
    reason='local peer credential transport requires Linux SO_PEERCRED')
def test_lost_rpc_consume_reply_keeps_postgres_and_fake_ledger_empty(authenticated,
        tmp_path, monkeypatch):
    invocation_id, intent, directory = prepared(authenticated, tmp_path)
    witness_path = tmp_path/'separate-witness-fixture'/'witness.sqlite3'
    caller, key = 'synthetic-write-fixture', b'c'*32
    witness = DurableLocalRecoveryWitness(witness_path,
        caller_keys={caller: key}, state_key=b'r'*32, initialize=True)
    binding = {'operation': 'reserve', 'request_id': invocation_id,
        'ledger_id': str(intent.ledger_id), 'invocation_id': invocation_id,
        'intent_sha256': intent_digest(intent)}
    committed = Event()
    original_consume = witness.consume

    def observed_consume(**kwargs):
        reply = original_consume(**kwargs)
        committed.set()  # Observe the real commit, without changing its result.
        return reply

    monkeypatch.setattr(witness, 'consume', observed_consume)
    with TemporaryDirectory(prefix='witness-pg-') as private:
        path = Path(private)/'w.sock'
        with LocalWitnessUnixServer(witness, path):
            client = UnixWitnessClient(path, caller_id=caller, key=key)
            permit = client.request(binding)
            consume = {'operation': 'consume', **{name: permit[name] for name in
                ('request_id', 'ledger_id', 'invocation_id', 'intent_sha256',
                 'generation', 'state_key_id', 'nonce', 'ticket_mac')}}
            exchange_nonce = str(uuid4())
            frame = {'caller_id': caller, 'caller_key_id': 'caller-v1',
                'request': consume, 'exchange_nonce': exchange_nonce,
                'mac': request_mac(key, caller, consume,
                    exchange_nonce=exchange_nonce)}
            # Send a valid consume frame and close without reading any reply.
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
                connection.settimeout(2)
                connection.connect(str(path))
                connection.sendall(json.dumps(frame).encode('ascii') + b'\n')
            assert committed.wait(2), 'consume did not commit before the deadline'

        witness = DurableLocalRecoveryWitness(witness_path,
            caller_keys={caller: key}, state_key=b'r'*32)
        with LocalWitnessUnixServer(witness, path):
            client = UnixWitnessClient(path, caller_id=caller, key=key)
            assert client.request({'operation': 'generation'})['generation'] == 1
            with pytest.raises(WitnessTransportDenied):
                client.request(binding)
            with pytest.raises(WitnessTransportDenied):
                client.request(consume)
                run(invocation_id, intent, directory)

    # Uncertain consumption burns this invocation; no effect is guessed/retried.
    with session_factory()() as db:
        assert db.get(SyntheticWriteAdmission, invocation_id) is None
        assert db.get(SyntheticWriteLedgerControl, 1) is None
        assert not db.scalars(select(AuditEvent).where(
            AuditEvent.action == 'synthetic.write.admission')).all()
    assert not (directory/'ledger.sqlite3').exists()
    with sqlite3.connect(witness_path) as db:
        assert db.execute('SELECT count(*) FROM reservations WHERE consumed=1').fetchone()[0] == 1
        assert db.execute('SELECT event FROM witness_events ORDER BY sequence').fetchall() == [
            ('reserved',), ('consumed',)]
