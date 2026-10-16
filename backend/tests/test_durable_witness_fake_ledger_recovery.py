"""Local synthetic control-fixture/fake-ledger recovery drills.

The control store here is SQLite, not the application's PostgreSQL database.
"""
import hashlib
import shutil
import sqlite3
from uuid import uuid4

import pytest

from durable_local_recovery_witness import (DurableLocalRecoveryWitness,
    WitnessDenied, request_mac, verify_response)
from synthetic_write_ledger import SyntheticWriteLedger
from workforce.synthetic_write_contract import (SyntheticWriteIntent, WriteScope,
    intent_digest, verify_write_receipt)

CALLER = 'restore-drill'
CALLER_KEY = b'd' * 32
STATE_KEY = b'w' * 32
LEDGER_KEY = b'l' * 32
CONTENT = b'fixture-only record body'


def create_intent():
    return SyntheticWriteIntent(version=1, action='synthetic.record.replace',
        scope=WriteScope(project_id=uuid4(), agent_id=uuid4(), root_id=uuid4(),
            invocation_id=uuid4()), ledger_id=uuid4(), record_id=uuid4(),
        expected_revision=0, content_sha256=hashlib.sha256(CONTENT).hexdigest(),
        content_size=len(CONTENT), approval_payload_sha256='a'*64,
        policy_snapshot_sha256='b'*64)


def authenticated(method, request, *, caller=CALLER, key=CALLER_KEY):
    response = method(caller_id=caller, request=request,
        mac=request_mac(key, caller, request))
    return verify_response(key, response)


def reserve_and_consume(witness, intent):
    invocation = str(intent.scope.invocation_id)
    reserve = {'operation': 'reserve', 'request_id': invocation,
        'ledger_id': str(intent.ledger_id), 'invocation_id': invocation,
        'intent_sha256': intent_digest(intent)}
    permit = authenticated(witness.reserve, reserve)
    consume = {'operation': 'consume', **{key: permit[key] for key in
        ('request_id','ledger_id','invocation_id','intent_sha256','generation',
         'state_key_id','nonce')},
        'ticket_mac': permit['ticket_mac']}
    authenticated(witness.consume, consume)


def setup(tmp_path):
    intent = create_intent()
    # Distinct fixture roots model separate restore scopes on one local host.
    control_path = tmp_path/'control-fixture'/'control.sqlite3'
    control_path.parent.mkdir(mode=0o700)
    with sqlite3.connect(control_path) as db:
        db.execute('CREATE TABLE admission (invocation_id TEXT PRIMARY KEY, status TEXT NOT NULL)')
    ledger_dir = tmp_path/'ledger-fixture'
    ledger_dir.mkdir(mode=0o700)
    ledger = SyntheticWriteLedger(ledger_dir, ledger_id=intent.ledger_id,
        key=LEDGER_KEY, experiment_enabled=True)
    snapshots = tmp_path/'snapshots'
    snapshots.mkdir(mode=0o700)
    shutil.copy2(control_path, snapshots/'control.sqlite3')
    shutil.copy2(ledger.path, snapshots/'ledger.sqlite3')
    witness_path = tmp_path/'witness-fixture'/'witness.sqlite3'
    witness = DurableLocalRecoveryWitness(witness_path,
        caller_keys={CALLER: CALLER_KEY}, state_key=STATE_KEY, initialize=True)
    return intent, control_path, ledger_dir, ledger.path, snapshots, witness_path, witness


def apply_through_fixture(witness, intent, control_path, ledger_dir):
    reserve_and_consume(witness, intent)
    invocation = str(intent.scope.invocation_id)
    with sqlite3.connect(control_path) as db:
        db.execute('INSERT INTO admission VALUES (?,?)', (invocation, 'unknown'))
    ledger = SyntheticWriteLedger(ledger_dir, ledger_id=intent.ledger_id,
        key=LEDGER_KEY, experiment_enabled=True)
    return ledger.apply(intent, CONTENT)


@pytest.mark.parametrize('rollback', ['control', 'ledger', 'both'])
def test_durable_witness_blocks_actual_fake_ledger_after_fixture_restore(tmp_path, rollback):
    intent, control, ledger_dir, ledger_path, snapshots, witness_path, witness = setup(tmp_path)
    receipt = verify_write_receipt(apply_through_fixture(witness, intent, control,
        ledger_dir), intent, key=LEDGER_KEY)
    assert receipt.result_revision == 1
    # Simulate a process restart before restoring one or both local fixtures.
    witness = DurableLocalRecoveryWitness(witness_path,
        caller_keys={CALLER: CALLER_KEY}, state_key=STATE_KEY)
    if rollback in ('control', 'both'):
        shutil.copy2(snapshots/'control.sqlite3', control)
    if rollback in ('ledger', 'both'):
        shutil.copy2(snapshots/'ledger.sqlite3', ledger_path)

    with pytest.raises(WitnessDenied, match='consumed'):
        apply_through_fixture(witness, intent, control, ledger_dir)
    with sqlite3.connect(control) as db:
        assert db.execute('SELECT count(*) FROM admission').fetchone()[0] == (
            0 if rollback in ('control','both') else 1)
    ledger = SyntheticWriteLedger(ledger_dir, ledger_id=intent.ledger_id,
        key=LEDGER_KEY, experiment_enabled=True)
    with sqlite3.connect(ledger.path) as db:
        expected = 0 if rollback in ('ledger','both') else 1
        assert db.execute('SELECT count(*) FROM records').fetchone()[0] == expected
        assert db.execute('SELECT count(*) FROM attempts').fetchone()[0] == expected


def test_lost_consume_reply_burns_invocation_before_control_or_fake_ledger(tmp_path):
    intent, control, ledger_dir, ledger_path, _, witness_path, witness = setup(tmp_path)
    invocation = str(intent.scope.invocation_id)
    reserve = {'operation': 'reserve', 'request_id': invocation,
        'ledger_id': str(intent.ledger_id), 'invocation_id': invocation,
        'intent_sha256': intent_digest(intent)}
    permit = authenticated(witness.reserve, reserve)
    consume = {'operation': 'consume', **{key: permit[key] for key in
        ('request_id','ledger_id','invocation_id','intent_sha256','generation',
         'state_key_id','nonce')},
        'ticket_mac': permit['ticket_mac']}
    witness.consume(caller_id=CALLER, request=consume,
        mac=request_mac(CALLER_KEY, CALLER, consume))  # lose reply after durable commit
    restarted = DurableLocalRecoveryWitness(witness_path,
        caller_keys={CALLER: CALLER_KEY}, state_key=STATE_KEY)
    with pytest.raises(WitnessDenied, match='consumed'):
        apply_through_fixture(restarted, intent, control, ledger_dir)
    with sqlite3.connect(control) as db:
        assert db.execute('SELECT count(*) FROM admission').fetchone()[0] == 0
    with sqlite3.connect(ledger_path) as db:
        assert db.execute('SELECT count(*) FROM records').fetchone()[0] == 0
        assert db.execute('SELECT count(*) FROM attempts').fetchone()[0] == 0


def test_empty_replacement_ledger_and_conflicting_request_do_not_reopen_witness(tmp_path):
    intent, control, ledger_dir, ledger_path, _, witness_path, witness = setup(tmp_path)
    apply_through_fixture(witness, intent, control, ledger_dir)
    ledger_path.unlink()
    replacement = SyntheticWriteLedger(ledger_dir, ledger_id=intent.ledger_id,
        key=LEDGER_KEY, experiment_enabled=True)
    with sqlite3.connect(replacement.path) as db:
        assert db.execute('SELECT count(*) FROM records').fetchone()[0] == 0
    restarted = DurableLocalRecoveryWitness(witness_path,
        caller_keys={CALLER: CALLER_KEY}, state_key=STATE_KEY)
    with pytest.raises(WitnessDenied, match='consumed'):
        apply_through_fixture(restarted, intent, control, ledger_dir)


def test_consolidated_rollback_restart_overlap_and_lost_consume_reply(tmp_path):
    intent, control, ledger_dir, ledger_path, snapshots, witness_path, witness = setup(tmp_path)
    invocation = str(intent.scope.invocation_id)
    reserve = {'operation': 'reserve', 'request_id': invocation,
        'ledger_id': str(intent.ledger_id), 'invocation_id': invocation,
        'intent_sha256': intent_digest(intent)}

    # A retry after an unknown reservation reply returns the same durable ticket.
    first = authenticated(witness.reserve, reserve)
    retry = authenticated(witness.reserve, reserve)
    assert retry == first
    assert first['generation'] == 1

    consume = {'operation': 'consume', **{key: first[key] for key in
        ('request_id','ledger_id','invocation_id','intent_sha256','generation',
         'state_key_id','nonce')}, 'ticket_mac': first['ticket_mac']}
    witness.consume(caller_id=CALLER, request=consume,
        mac=request_mac(CALLER_KEY, CALLER, consume))  # reply is deliberately lost

    # Simulate coordinated control and ledger restore; witness is intentionally retained.
    shutil.copy2(snapshots/'control.sqlite3', control)
    shutil.copy2(snapshots/'ledger.sqlite3', ledger_path)
    restarted = DurableLocalRecoveryWitness(witness_path,
        caller_keys={CALLER: {'caller-v1': CALLER_KEY, 'caller-v2': b'e' * 32}},
        state_keys={'state-v1': STATE_KEY, 'state-v2': b'x' * 32},
        current_state_key_id='state-v2')

    with pytest.raises(WitnessDenied, match='consumed'):
        authenticated(restarted.reserve, reserve, key=CALLER_KEY)
    with pytest.raises(WitnessDenied, match='consumed'):
        authenticated(restarted.consume, consume, key=CALLER_KEY)
    generation = authenticated(restarted.generation,
        {'operation': 'generation'}, key=CALLER_KEY)
    assert generation['generation'] == 1
    with sqlite3.connect(control) as db:
        assert db.execute('SELECT count(*) FROM admission').fetchone()[0] == 0
    with sqlite3.connect(ledger_path) as db:
        assert db.execute('SELECT count(*) FROM records').fetchone()[0] == 0
        assert db.execute('SELECT count(*) FROM attempts').fetchone()[0] == 0
    with sqlite3.connect(witness_path) as db:
        assert db.execute('SELECT count(*) FROM reservations WHERE consumed=1').fetchone()[0] == 1
        assert db.execute("SELECT count(*) FROM witness_events WHERE event='reserved'").fetchone()[0] == 1
        assert db.execute("SELECT count(*) FROM witness_events WHERE event='consumed'").fetchone()[0] == 1


def test_witness_outage_blocks_fake_ledger_and_restored_state_stays_spent(tmp_path):
    intent, control, ledger_dir, ledger_path, _, witness_path, witness = setup(tmp_path)
    reserve_and_consume(witness, intent)
    unavailable_path = witness_path.with_suffix('.unavailable')
    witness_path.rename(unavailable_path)

    with pytest.raises(WitnessDenied, match='state unavailable'):
        apply_through_fixture(witness, intent, control, ledger_dir)
    with sqlite3.connect(control) as db:
        assert db.execute('SELECT count(*) FROM admission').fetchone()[0] == 0
    with sqlite3.connect(ledger_path) as db:
        assert db.execute('SELECT count(*) FROM records').fetchone()[0] == 0
        assert db.execute('SELECT count(*) FROM attempts').fetchone()[0] == 0

    # A missing-state startup does not bootstrap a replacement witness database.
    with pytest.raises(WitnessDenied, match='state unavailable'):
        DurableLocalRecoveryWitness(witness_path,
            caller_keys={CALLER: CALLER_KEY}, state_key=STATE_KEY)
    unavailable_path.rename(witness_path)
    restored = DurableLocalRecoveryWitness(witness_path,
        caller_keys={CALLER: CALLER_KEY}, state_key=STATE_KEY)
    with pytest.raises(WitnessDenied, match='consumed'):
        apply_through_fixture(restored, intent, control, ledger_dir)
    with sqlite3.connect(witness_path) as db:
        assert db.execute('SELECT count(*) FROM reservations WHERE consumed=1').fetchone()[0] == 1

