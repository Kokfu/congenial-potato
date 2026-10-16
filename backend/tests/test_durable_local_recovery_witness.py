"""Durability and authentication contract tests for the local-only prototype."""
import shutil
import json
import hmac
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


@pytest.mark.parametrize('exchange_nonce', [None, str(uuid4())], ids=['direct', 'exchange'])
def test_caller_and_key_id_boundaries_cannot_relabel_a_request_mac(tmp_path, exchange_nonce):
    # The fixture deliberately reuses key bytes to isolate message encoding.
    key = b'k' * 32
    ordinary, ordinary_key_id = 'a\0b', 'c'
    admin, admin_key_id = 'a', 'b\0c'
    path = tmp_path/'state.sqlite3'
    witness = DurableLocalRecoveryWitness(path,
        caller_keys={ordinary: {ordinary_key_id: key}, admin: {admin_key_id: key}},
        current_caller_key_ids={ordinary: ordinary_key_id, admin: admin_key_id},
        state_key=STATE_KEY, advance_callers={admin}, initialize=True)
    request = {'operation': 'advance', 'request_id': str(uuid4())}
    ordinary_mac = request_mac(key, ordinary, request, ordinary_key_id,
        exchange_nonce=exchange_nonce)
    with pytest.raises(WitnessDenied, match='caller authentication'):
        witness.advance_generation(caller_id=admin, caller_key_id=admin_key_id,
            request=request, mac=ordinary_mac, exchange_nonce=exchange_nonce)
    with sqlite3.connect(path) as db:
        assert db.execute('SELECT generation FROM witness_state').fetchone()[0] == 1
        assert db.execute('SELECT count(*) FROM witness_events').fetchone()[0] == 0
        assert db.execute('SELECT count(*) FROM generation_operations').fetchone()[0] == 0

    # The old delimiter format must not remain available as a fallback.
    old_domain = b'workforce.synthetic.write.witness.request.v1\0'
    old_body = request
    if exchange_nonce is not None:
        old_domain = b'workforce.synthetic.write.witness.exchange.request.v1\0'
        old_body = {'exchange_nonce': exchange_nonce, 'request': request}
    old_mac = hmac.digest(key, old_domain + admin.encode() + b'\0' +
        admin_key_id.encode() + b'\0' + json.dumps(old_body,
            sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode('ascii'), 'sha256').hex()
    with pytest.raises(WitnessDenied, match='caller authentication'):
        witness.advance_generation(caller_id=admin, caller_key_id=admin_key_id,
            request=request, mac=old_mac, exchange_nonce=exchange_nonce)

    admin_mac = request_mac(key, admin, request, admin_key_id,
        exchange_nonce=exchange_nonce)
    assert ordinary_mac != admin_mac
    reply = witness.advance_generation(caller_id=admin, caller_key_id=admin_key_id,
        request=request, mac=admin_mac, exchange_nonce=exchange_nonce)
    assert verify_response(key, reply, admin_key_id, expected_request_mac=admin_mac,
        expected_request=request)['generation'] == 2
    with sqlite3.connect(path) as db:
        assert db.execute('SELECT caller_id, caller_key_id FROM witness_events').fetchall() == [(admin, admin_key_id)]


def call(witness, request, *, key=CALLER_KEY, caller=CALLER, key_id='caller-v1'):
    envelope = dispatch(witness, request, caller=caller, key=key, key_id=key_id)
    return verify_response(key, envelope, key_id,
        expected_request_mac=request_mac(key, caller, request, key_id), expected_request=request)


@pytest.mark.parametrize('bad', ['\ud800', '\udfff'], ids=['high-surrogate', 'low-surrogate'])
@pytest.mark.parametrize('field', ['caller', 'caller_key', 'state_key'])
def test_invalid_unicode_identity_config_denies_before_creating_state(tmp_path, bad, field):
    config = {'caller_keys': {CALLER: {'caller-v1': CALLER_KEY}},
        'current_caller_key_ids': {CALLER: 'caller-v1'},
        'state_keys': {'state-v1': STATE_KEY}, 'current_state_key_id': 'state-v1'}
    if field == 'caller':
        config['caller_keys'] = {bad: {'caller-v1': CALLER_KEY}}
        config['current_caller_key_ids'] = {bad: 'caller-v1'}
    elif field == 'caller_key':
        config['caller_keys'] = {CALLER: {bad: CALLER_KEY}}
        config['current_caller_key_ids'] = {CALLER: bad}
    else:
        config['state_keys'] = {bad: STATE_KEY}
        config['current_state_key_id'] = bad
    path = tmp_path/'new-state'/'witness.sqlite3'
    with pytest.raises(WitnessDenied, match='key configuration'):
        DurableLocalRecoveryWitness(path, **config, initialize=True)
    assert not path.parent.exists()


@pytest.mark.parametrize('caller,key_id,state_id', [
    ('管理者', '呼出鍵', '状態鍵'), ('caller-😀', 'caller-key-🚀', 'state-key-🔐'),
])
def test_valid_unicode_identities_preserve_protocol_and_audit(tmp_path, caller, key_id, state_id):
    path = tmp_path/'state.sqlite3'
    witness = DurableLocalRecoveryWitness(path, caller_keys={caller: {key_id: CALLER_KEY}},
        current_caller_key_ids={caller: key_id}, state_keys={state_id: STATE_KEY},
        current_state_key_id=state_id, advance_callers={caller}, initialize=True)
    ticket = call(witness, reserve_request(), caller=caller, key_id=key_id)
    assert ticket['state_key_id'] == state_id
    assert call(witness, consume_request(ticket), caller=caller, key_id=key_id)['status'] == 'spent'
    assert call(witness, {'operation': 'advance', 'request_id': str(uuid4())},
        caller=caller, key_id=key_id)['generation'] == 2
    with sqlite3.connect(path) as db:
        assert db.execute('SELECT caller_id, caller_key_id, state_key_id FROM witness_events ORDER BY sequence').fetchall() == [
            (caller, key_id, state_id), (caller, key_id, state_id), (caller, key_id, None)]


def dispatch(witness, request, *, caller=CALLER, key=CALLER_KEY, key_id='caller-v1'):
    mac = request_mac(key, caller, request, key_id)
    if request['operation'] == 'reserve':
        return witness.reserve(caller_id=caller, request=request, mac=mac, caller_key_id=key_id)
    if request['operation'] == 'consume':
        return witness.consume(caller_id=caller, request=request, mac=mac, caller_key_id=key_id)
    if request['operation'] == 'advance':
        return witness.advance_generation(caller_id=caller, request=request, mac=mac, caller_key_id=key_id)
    return witness.generation(caller_id=caller, request=request, mac=mac, caller_key_id=key_id)


def reserve_request(*, request_id=None, invocation_id=None, ledger_id=LEDGER, intent=INTENT):
    return {'operation': 'reserve', 'request_id': request_id or str(uuid4()),
            'ledger_id': ledger_id, 'invocation_id': invocation_id or str(uuid4()),
            'intent_sha256': intent}


def consume_request(reservation):
    return {'operation': 'consume', **{key: reservation[key] for key in
            ('request_id','ledger_id','invocation_id','intent_sha256','generation',
             'state_key_id','nonce')},
            'ticket_mac': reservation['ticket_mac']}


def create(path):
    return DurableLocalRecoveryWitness(path, caller_keys={CALLER: CALLER_KEY},
        state_key=STATE_KEY, advance_callers={CALLER}, initialize=True)


def reopen(path):
    return DurableLocalRecoveryWitness(path, caller_keys={CALLER: CALLER_KEY},
        state_key=STATE_KEY, advance_callers={CALLER})


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


def test_old_and_new_caller_keys_racing_to_consume_have_one_durable_winner(tmp_path):
    path = tmp_path/'witness.sqlite3'
    old_key, new_key = CALLER_KEY, b'q'*32
    initial = DurableLocalRecoveryWitness(path, caller_keys={CALLER:old_key},
        state_key=STATE_KEY, initialize=True)
    reservation = call(initial, reserve_request())
    overlap = DurableLocalRecoveryWitness(path,
        caller_keys={CALLER:{'caller-v1':old_key,'caller-v2':new_key}},
        current_caller_key_ids={CALLER:'caller-v2'}, state_key=STATE_KEY)
    request = consume_request(reservation)
    barrier = Barrier(2)
    def attempt(key, key_id):
        barrier.wait(timeout=3)
        try:
            call(overlap, request, key=key, key_id=key_id)
            return key_id, 'spent'
        except WitnessDenied:
            return key_id, 'denied'
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda pair: attempt(*pair),
            [(old_key,'caller-v1'),(new_key,'caller-v2')]))
    assert [result for _, result in results].count('spent') == 1
    assert [result for _, result in results].count('denied') == 1
    with sqlite3.connect(path) as db:
        consumed = db.execute("SELECT caller_key_id FROM witness_events "
            "WHERE event='consumed'").fetchall()
    assert len(consumed) == 1
    assert consumed[0][0] in {'caller-v1','caller-v2'}


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
        state_key=STATE_KEY, advance_callers={CALLER, 'other-caller'}, initialize=True)
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


def test_overlapping_admin_keys_racing_same_advance_are_idempotent(tmp_path):
    path = tmp_path/'witness.sqlite3'
    old_key, new_key = CALLER_KEY, b'r'*32
    DurableLocalRecoveryWitness(path, caller_keys={CALLER:old_key},
        state_key=STATE_KEY, advance_callers={CALLER}, initialize=True)
    overlap = DurableLocalRecoveryWitness(path,
        caller_keys={CALLER:{'caller-v1':old_key,'caller-v2':new_key}},
        current_caller_key_ids={CALLER:'caller-v2'}, state_key=STATE_KEY,
        advance_callers={CALLER})
    request = {'operation':'advance','request_id':str(uuid4())}
    barrier = Barrier(2)
    def attempt(key, key_id):
        barrier.wait(timeout=3)
        return call(overlap, request, key=key, key_id=key_id)
    with ThreadPoolExecutor(max_workers=2) as pool:
        replies = list(pool.map(lambda pair: attempt(*pair),
            [(old_key,'caller-v1'),(new_key,'caller-v2')]))
    assert replies == [{'generation':2,'request_id':request['request_id'],
        'status':'advanced'}]*2
    assert call(reopen(path), {'operation':'generation'})['generation'] == 2
    with sqlite3.connect(path) as db:
        assert db.execute('SELECT count(*) FROM generation_operations').fetchone()[0] == 1
        events = db.execute("SELECT caller_key_id FROM witness_events "
            "WHERE event='generation_advanced'").fetchall()
    assert len(events) == 1 and events[0][0] in {'caller-v1','caller-v2'}


def test_authenticated_non_admin_caller_cannot_advance_generation(tmp_path):
    witness = DurableLocalRecoveryWitness(tmp_path/'witness.sqlite3',
        caller_keys={CALLER: CALLER_KEY, 'ordinary-caller': b'o'*32},
        state_key=STATE_KEY, advance_callers={CALLER}, initialize=True)
    request = {'operation': 'advance', 'request_id': str(uuid4())}
    with pytest.raises(WitnessDenied, match='administrator'):
        dispatch(witness, request, caller='ordinary-caller', key=b'o'*32)
    assert call(witness, {'operation': 'generation'})['generation'] == 1
    with sqlite3.connect(witness.path) as db:
        assert db.execute('SELECT count(*) FROM generation_operations').fetchone()[0] == 0


def test_state_key_rotation_keeps_old_reservations_during_overlap(tmp_path):
    path = tmp_path/'witness.sqlite3'
    old_key, new_key = b'1'*32, b'2'*32
    witness = DurableLocalRecoveryWitness(path, caller_keys={CALLER: CALLER_KEY},
        state_key=old_key, advance_callers={CALLER}, initialize=True)
    old_request = reserve_request()
    old_ticket = call(witness, old_request)
    rotated = DurableLocalRecoveryWitness(path, caller_keys={CALLER: CALLER_KEY},
        state_keys={'state-v1': old_key, 'state-v2': new_key},
        current_state_key_id='state-v2', advance_callers={CALLER})
    assert call(rotated, old_request) == old_ticket
    new_request = reserve_request()
    new_ticket = call(rotated, new_request)
    assert old_ticket['state_key_id'] == 'state-v1'
    assert new_ticket['state_key_id'] == 'state-v2'
    assert call(rotated, consume_request(old_ticket))['status'] == 'spent'
    assert call(rotated, consume_request(new_ticket))['status'] == 'spent'


def test_retiring_state_key_with_pending_reservation_fails_closed_until_restored(tmp_path):
    path = tmp_path/'witness.sqlite3'
    old_key, new_key = b'3'*32, b'4'*32
    witness = DurableLocalRecoveryWitness(path, caller_keys={CALLER: CALLER_KEY},
        state_key=old_key, advance_callers={CALLER}, initialize=True)
    reservation = call(witness, reserve_request())
    premature_retirement = DurableLocalRecoveryWitness(path,
        caller_keys={CALLER: CALLER_KEY}, state_keys={'state-v2': new_key},
        current_state_key_id='state-v2', advance_callers={CALLER})
    consume = consume_request(reservation)
    with pytest.raises(WitnessDenied, match='state key unavailable'):
        call(premature_retirement, consume)
    overlap = DurableLocalRecoveryWitness(path, caller_keys={CALLER: CALLER_KEY},
        state_keys={'state-v1': old_key, 'state-v2': new_key},
        current_state_key_id='state-v2', advance_callers={CALLER})
    assert call(overlap, consume)['status'] == 'spent'


def test_retired_key_is_not_needed_to_keep_consumed_identity_spent(tmp_path):
    path = tmp_path/'witness.sqlite3'
    old_key, new_key = b'5'*32, b'6'*32
    witness = DurableLocalRecoveryWitness(path, caller_keys={CALLER: CALLER_KEY},
        state_key=old_key, advance_callers={CALLER}, initialize=True)
    reservation = call(witness, reserve_request())
    call(witness, consume_request(reservation))
    retired = DurableLocalRecoveryWitness(path, caller_keys={CALLER: CALLER_KEY},
        state_keys={'state-v2': new_key}, current_state_key_id='state-v2',
        advance_callers={CALLER})
    with pytest.raises(WitnessDenied, match='already consumed'):
        call(retired, reserve_request(invocation_id=reservation['invocation_id']))


def test_caller_key_rotation_overlap_and_retirement_preserve_stable_admin_identity(tmp_path):
    path = tmp_path/'witness.sqlite3'
    old_key, new_key = b'a'*32, b'b'*32
    initial = DurableLocalRecoveryWitness(path, caller_keys={CALLER: old_key},
        state_key=STATE_KEY, advance_callers={CALLER}, initialize=True)
    reservation_request = reserve_request()
    reservation = call(initial, reservation_request, key=old_key)
    rotated = DurableLocalRecoveryWitness(path,
        caller_keys={CALLER: {'caller-v1': old_key, 'caller-v2': new_key}},
        current_caller_key_ids={CALLER: 'caller-v2'}, state_key=STATE_KEY,
        advance_callers={CALLER})
    assert call(rotated, reservation_request, key=old_key, key_id='caller-v1') == reservation
    assert call(rotated, reservation_request, key=new_key, key_id='caller-v2') == reservation
    assert call(rotated, consume_request(reservation), key=new_key,
        key_id='caller-v2')['status'] == 'spent'
    advance = {'operation':'advance','request_id':str(uuid4())}
    assert call(rotated, advance, key=new_key, key_id='caller-v2')['generation'] == 2
    retired = DurableLocalRecoveryWitness(path,
        caller_keys={CALLER: {'caller-v2': new_key}},
        current_caller_key_ids={CALLER: 'caller-v2'}, state_key=STATE_KEY,
        advance_callers={CALLER})
    with pytest.raises(WitnessDenied, match='caller authentication failed'):
        call(retired, {'operation':'generation'}, key=old_key, key_id='caller-v1')
    assert call(retired, {'operation':'generation'}, key=new_key,
        key_id='caller-v2')['generation'] == 2
    with sqlite3.connect(path) as db:
        audit = db.execute('SELECT event,caller_id,caller_key_id,state_key_id '
            'FROM witness_events ORDER BY sequence').fetchall()
    assert audit == [
        ('reserved', CALLER, 'caller-v1', 'state-v1'),
        ('consumed', CALLER, 'caller-v2', 'state-v1'),
        ('generation_advanced', CALLER, 'caller-v2', None),
    ]


def test_startup_rejects_symlink_and_non_private_witness_state(tmp_path):
    path = tmp_path/'witness.sqlite3'
    witness = create(path)
    alias = tmp_path/'witness-alias.sqlite3'
    alias.symlink_to(path)
    with pytest.raises(WitnessDenied, match='private witness state file'):
        reopen(alias)
    path.chmod(0o644)
    with pytest.raises(WitnessDenied, match='private witness state file'):
        reopen(path)
    path.chmod(0o600)
    path.parent.chmod(0o750)
    with pytest.raises(WitnessDenied, match='private witness state directory'):
        reopen(path)
    path.parent.chmod(0o700)
    assert call(witness, {'operation':'generation'})['generation'] == 1


def test_startup_rejects_malformed_or_incomplete_witness_schema(tmp_path):
    path = tmp_path/'incomplete.sqlite3'
    path.touch(mode=0o600)
    with sqlite3.connect(path) as db:
        db.execute('CREATE TABLE witness_state(singleton INTEGER, generation INTEGER)')
        db.execute('INSERT INTO witness_state VALUES(1,1)')
    path.chmod(0o600)
    with pytest.raises(WitnessDenied, match='witness state unavailable'):
        reopen(path)


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


def test_witness_database_replacement_rewinds_generation(tmp_path):
    """Generation is monotonic only while this replaceable local file is retained."""
    path = tmp_path/'witness.sqlite3'
    witness = create(path)
    old_copy = tmp_path/'old-generation.sqlite3'
    shutil.copy2(path, old_copy)

    first = call(witness, {'operation': 'advance', 'request_id': str(uuid4())})
    second = call(witness, {'operation': 'advance', 'request_id': str(uuid4())})
    assert (first['generation'], second['generation']) == (2, 3)

    # Replacing the database with a prior copy rolls the durable generation back.
    shutil.copy2(old_copy, path)
    restored = reopen(path)
    assert call(restored, {'operation': 'generation'})['generation'] == 1



@pytest.mark.parametrize('operation', ['generation', 'reserve', 'consume', 'advance'])
@pytest.mark.parametrize('caller,key_id', [
    ('unknown-caller', 'caller-v1'), (CALLER, 'unknown-key'),
    ('unknown-caller', 'unknown-key')])
def test_empty_mac_and_missing_key_deny_before_state_changes(tmp_path, operation, caller, key_id):
    path = tmp_path/'witness.sqlite3'
    witness = create(path)
    permit = call(witness, reserve_request())
    requests = {'generation': {'operation': 'generation'},
        'reserve': reserve_request(), 'consume': consume_request(permit),
        'advance': {'operation': 'advance', 'request_id': str(uuid4())}}
    method = witness.advance_generation if operation == 'advance' else getattr(witness, operation)
    before = path.read_bytes()
    with pytest.raises(WitnessDenied, match='caller authentication'):
        method(caller_id=caller, caller_key_id=key_id,
            request=requests[operation], mac='')
    assert path.read_bytes() == before
    assert call(witness, {'operation': 'generation'})['generation'] == 1
    assert call(witness, consume_request(permit))['status'] == 'spent'


@pytest.mark.parametrize('operation', ['generation', 'reserve', 'consume', 'advance'])
def test_malformed_mac_denies_with_protocol_error_before_mutation(tmp_path, operation):
    path = tmp_path/'witness.sqlite3'
    witness = create(path)
    permit = call(witness, reserve_request())
    requests = {'generation': {'operation': 'generation'},
        'reserve': reserve_request(), 'consume': consume_request(permit),
        'advance': {'operation': 'advance', 'request_id': str(uuid4())}}
    method = witness.advance_generation if operation == 'advance' else getattr(witness, operation)
    before = path.read_bytes()
    for bad in ('é'*64, '\ud800'*64, '', '0'*63, '0'*65, 'g'*64, None, b'', []):
        with pytest.raises(WitnessDenied, match='caller authentication'):
            method(caller_id=CALLER, request=requests[operation], mac=bad)
        assert path.read_bytes() == before
    assert call(witness, consume_request(permit))['status'] == 'spent'
