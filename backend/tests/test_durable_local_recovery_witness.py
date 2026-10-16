"""Durability and authentication contract tests for the local-only prototype."""
import shutil
import json
import sqlite3
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier
from uuid import uuid4

import pytest

from durable_local_recovery_witness import (DurableLocalRecoveryWitness,
    WitnessDenied, request_mac, verify_response)

CALLER = 'fixture-caller'
CALLER_KEY = b'c' * 32
STATE_KEY = b's' * 32
LEDGER = str(uuid4())
INTENT = 'a' * 64


def call(witness, request, *, key=CALLER_KEY, caller=CALLER):
    envelope = dispatch(witness, request, caller=caller, key=key)
    return verify_response(key, envelope)


def dispatch(witness, request, *, caller=CALLER, key=CALLER_KEY):
    mac = request_mac(key, caller, request)
    if request['operation'] == 'reserve':
        return witness.reserve(caller_id=caller, request=request, mac=mac)
    if request['operation'] == 'consume':
        return witness.consume(caller_id=caller, request=request, mac=mac)
    if request['operation'] == 'advance':
        return witness.advance_generation(caller_id=caller, request=request, mac=mac)
    return witness.generation(caller_id=caller, request=request, mac=mac)


def reserve_request(*, request_id=None, invocation_id=None, ledger_id=LEDGER, intent=INTENT):
    return {'operation': 'reserve', 'request_id': request_id or str(uuid4()),
            'ledger_id': ledger_id, 'invocation_id': invocation_id or str(uuid4()),
            'intent_sha256': intent}


def consume_request(reservation):
    return {'operation': 'consume', **{key: reservation[key] for key in
            ('request_id','ledger_id','invocation_id','intent_sha256','generation','nonce')},
            'ticket_mac': reservation['ticket_mac']}


def create(path):
    return DurableLocalRecoveryWitness(path, caller_keys={CALLER: CALLER_KEY},
        state_key=STATE_KEY, initialize=True)


def reopen(path):
    return DurableLocalRecoveryWitness(path, caller_keys={CALLER: CALLER_KEY},
        state_key=STATE_KEY)


def test_reservation_retry_is_idempotent_and_exact_binding_is_required(tmp_path):
    witness = create(tmp_path/'witness.sqlite3')
    request = reserve_request()
    first = call(witness, request)
    retry = call(witness, request)
    assert retry == first
    changed = {**request, 'intent_sha256': 'b' * 64}
    with pytest.raises(WitnessDenied, match='conflict'):
        call(witness, changed)
    with pytest.raises(WitnessDenied, match='already reserved'):
        call(witness, reserve_request(invocation_id=request['invocation_id']))


def test_restart_preserves_generation_reservation_and_consumed_state(tmp_path):
    path = tmp_path/'witness.sqlite3'
    witness = create(path)
    reservation = call(witness, reserve_request())
    assert call(witness, {'operation': 'consume', **consume_request(reservation)})['status'] == 'spent'
    advanced = call(witness, {'operation': 'advance', 'request_id': str(uuid4())})
    assert advanced['generation'] == 2
    restarted = reopen(path)
    assert call(restarted, {'operation': 'generation'})['generation'] == 2
    with pytest.raises(WitnessDenied, match='already consumed'):
        call(restarted, reserve_request(invocation_id=reservation['invocation_id']))
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT count(*) FROM witness_events WHERE event='consumed'").fetchone()[0] == 1


def test_fresh_interpreter_restart_preserves_consumed_identity(tmp_path):
    path = tmp_path/'witness.sqlite3'
    witness = create(path)
    reservation = call(witness, reserve_request())
    request = consume_request(reservation)
    program = '''
import json, sys
from durable_local_recovery_witness import DurableLocalRecoveryWitness, request_mac
path, request_json = sys.argv[1:]
caller, caller_key, state_key = 'fixture-caller', b'c'*32, b's'*32
witness = DurableLocalRecoveryWitness(path, caller_keys={caller: caller_key}, state_key=state_key)
request = json.loads(request_json)
witness.consume(caller_id=caller, request=request, mac=request_mac(caller_key, caller, request))
'''
    import os
    env = dict(os.environ)
    env['PYTHONPATH'] = str(Path(__file__).parent) + os.pathsep + env.get('PYTHONPATH', '')
    result = subprocess.run([sys.executable, '-c', program, str(path),
        json.dumps(request)], capture_output=True, text=True, env=env, timeout=10)
    assert result.returncode == 0, result.stderr
    with pytest.raises(WitnessDenied, match='already consumed'):
        call(reopen(path), request)


def test_lost_reserve_reply_retries_same_reservation_and_lost_consume_reply_burns_identity(tmp_path):
    witness = create(tmp_path/'witness.sqlite3')
    request = reserve_request()
    lost_reserve = witness.reserve(caller_id=CALLER, request=request,
                                   mac=request_mac(CALLER_KEY, CALLER, request))
    retry = call(witness, request)
    assert verify_response(CALLER_KEY, lost_reserve) == retry
    consume = consume_request(retry)
    witness.consume(caller_id=CALLER, request=consume,
                    mac=request_mac(CALLER_KEY, CALLER, consume))  # response lost
    restarted = reopen(tmp_path/'witness.sqlite3')
    with pytest.raises(WitnessDenied, match='already consumed'):
        call(restarted, consume)
    with pytest.raises(WitnessDenied, match='consumed'):
        call(restarted, reserve_request(invocation_id=request['invocation_id']))


def test_concurrent_consume_has_one_durable_winner(tmp_path):
    witness = create(tmp_path/'witness.sqlite3')
    reservation = call(witness, reserve_request())
    request = consume_request(reservation)
    barrier = Barrier(8)
    def attempt(_):
        barrier.wait(timeout=3)
        try:
            call(witness, request)
            return 'spent'
        except WitnessDenied:
            return 'denied'
    with ThreadPoolExecutor(max_workers=8) as pool:
        result = list(pool.map(attempt, range(8)))
    assert result.count('spent') == 1
    assert result.count('denied') == 7


def test_authentication_response_tampering_and_outage_fail_closed(tmp_path):
    witness = create(tmp_path/'witness.sqlite3')
    request = {'operation': 'generation'}
    with pytest.raises(WitnessDenied, match='caller authentication'):
        witness.generation(caller_id=CALLER, request=request, mac='0'*64)
    with pytest.raises(WitnessDenied, match='caller authentication'):
        dispatch(witness, request, caller='unknown')
    envelope = dispatch(witness, request)
    envelope['body']['generation'] = 99
    with pytest.raises(WitnessDenied, match='response authentication'):
        verify_response(CALLER_KEY, envelope)
    witness.set_available(False)
    with pytest.raises(WitnessDenied, match='unavailable'):
        dispatch(witness, request)
    witness.set_available(True)
    assert call(witness, request)['generation'] == 1


def test_missing_corrupt_or_replaced_state_fails_closed_without_bootstrap(tmp_path):
    path = tmp_path/'witness.sqlite3'
    with pytest.raises(WitnessDenied, match='state unavailable'):
        reopen(path)
    witness = create(path)
    path.write_bytes(b'not a sqlite database')
    with pytest.raises(WitnessDenied, match='state unavailable'):
        dispatch(witness, {'operation': 'generation'})
    with pytest.raises(WitnessDenied, match='state unavailable'):
        reopen(path)


def test_generation_advance_stales_unconsumed_ticket_and_never_rewinds(tmp_path):
    path = tmp_path/'witness.sqlite3'
    witness = create(path)
    reservation = call(witness, reserve_request())
    call(witness, {'operation': 'advance', 'request_id': str(uuid4())})
    with pytest.raises(WitnessDenied, match='ticket binding'):
        call(witness, consume_request(reservation))
    assert call(reopen(path), {'operation': 'generation'})['generation'] == 2


def test_generation_advance_retry_is_idempotent_after_lost_reply_and_restart(tmp_path):
    path = tmp_path/'witness.sqlite3'
    witness = create(path)
    request = {'operation': 'advance', 'request_id': str(uuid4())}
    lost = dispatch(witness, request)  # response is dropped after durable commit
    retry = call(reopen(path), request)
    assert verify_response(CALLER_KEY, lost) == retry
    assert retry['generation'] == 2
    second = call(reopen(path), {'operation': 'advance', 'request_id': str(uuid4())})
    assert second['generation'] == 3
    assert call(reopen(path), request) == retry
    with sqlite3.connect(path) as db:
        assert db.execute('SELECT count(*) FROM generation_operations').fetchone()[0] == 2


def test_generation_advance_rejects_request_identity_reuse_by_other_caller(tmp_path):
    path = tmp_path/'witness.sqlite3'
    witness = DurableLocalRecoveryWitness(path,
        caller_keys={CALLER: CALLER_KEY, 'other-caller': b'o'*32},
        state_key=STATE_KEY, initialize=True)
    request = {'operation': 'advance', 'request_id': str(uuid4())}
    assert call(witness, request)['generation'] == 2
    with pytest.raises(WitnessDenied, match='operation conflict'):
        dispatch(witness, request, caller='other-caller', key=b'o'*32)
    assert call(witness, {'operation': 'generation'})['generation'] == 2


def test_concurrent_duplicate_generation_advance_increments_once(tmp_path):
    path = tmp_path/'witness.sqlite3'
    witness = create(path)
    request = {'operation': 'advance', 'request_id': str(uuid4())}
    barrier = Barrier(8)
    def attempt(_):
        barrier.wait(timeout=3)
        return call(witness, request)
    with ThreadPoolExecutor(max_workers=8) as pool:
        replies = list(pool.map(attempt, range(8)))
    assert len(set(tuple(sorted(reply.items())) for reply in replies)) == 1
    assert replies[0]['generation'] == 2
    assert call(reopen(path), {'operation': 'generation'})['generation'] == 2


def test_restoring_app_and_fake_ledger_fixtures_does_not_restore_separate_witness_file(tmp_path):
    """Synthetic fixture copies model coordinated restore; not backup/power-loss proof."""
    witness_path = tmp_path/'outside-fixture-restore-domains'/'witness.sqlite3'
    witness = create(witness_path)
    reservation = call(witness, reserve_request())
    call(witness, consume_request(reservation))
    control = tmp_path/'control.sqlite3'
    ledger = tmp_path/'ledger.sqlite3'
    control.write_text('post-admission fixture state')
    ledger.write_text('post-effect fixture state')
    snapshots = tmp_path/'old-snapshots'
    snapshots.mkdir()
    shutil.copy2(control, snapshots/'control.sqlite3')
    shutil.copy2(ledger, snapshots/'ledger.sqlite3')
    control.write_text('restored pre-admission fixture state')
    ledger.write_text('restored empty fixture state')
    assert control.read_text().startswith('restored')
    assert ledger.read_text().startswith('restored')
    restarted = reopen(witness_path)
    with pytest.raises(WitnessDenied, match='already consumed'):
        call(restarted, reserve_request(invocation_id=reservation['invocation_id']))


def test_witness_database_replacement_is_a_known_unprotected_boundary(tmp_path):
    """Explicitly shows the local file itself is not protected against rollback."""
    path = tmp_path/'witness.sqlite3'
    witness = create(path)
    old_copy = tmp_path/'old-copy.sqlite3'
    shutil.copy2(path, old_copy)
    used = reserve_request()
    call(witness, used)
    call(witness, consume_request(call(witness, used)))
    shutil.copy2(old_copy, path)
    replacement = reopen(path)
    # Rollback of witness state reopens the invocation: production safety is not proven.
    assert call(replacement, {**used, 'request_id': str(uuid4())})['status'] == 'reserved'

