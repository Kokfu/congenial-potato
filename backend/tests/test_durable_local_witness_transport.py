"""Process-boundary checks for authenticated local Unix-socket witness RPC."""
import hashlib
import errno
import json
import os
import shutil
import socket
import sqlite3
import subprocess
import sys
import time
import threading
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from uuid import uuid4

import pytest

from durable_local_recovery_witness import (DurableLocalRecoveryWitness,
    WitnessDenied, request_mac)
from synthetic_write_ledger import SyntheticWriteLedger
import durable_local_witness_transport as transport_module
from durable_local_witness_transport import (LocalWitnessUnixServer,
    UnixWitnessClient, WitnessTransportDenied)
from workforce.synthetic_write_contract import (SyntheticWriteIntent, WriteScope,
    intent_digest, verify_write_receipt)

CALLER = 'socket-fixture-caller'
CALLER_KEY = b'u' * 32
STATE_KEY = b'v' * 32


def test_malformed_ticket_mac_rpc_preserves_pending_ticket_and_service(tmp_path):
    state = tmp_path/'witness.sqlite3'
    witness = DurableLocalRecoveryWitness(state, caller_keys={CALLER: CALLER_KEY},
        state_key=STATE_KEY, initialize=True)
    server = LocalWitnessUnixServer(witness, tmp_path/'witness.sock').start()
    client = UnixWitnessClient(tmp_path/'witness.sock', caller_id=CALLER, key=CALLER_KEY)
    try:
        ticket = client.request({'operation': 'reserve', 'request_id': str(uuid4()),
            'ledger_id': str(uuid4()), 'invocation_id': str(uuid4()), 'intent_sha256': 'a'*64})
        consume = {'operation': 'consume', **{key: value for key, value in ticket.items()
            if key != 'status'}}
        before = state.read_bytes()
        for bad in ('é'*64, '\ud800'*64, '', 'a'*63, 'a'*65, 'g'*64,
                    'A'*64, None, 0, [], {}):
            with pytest.raises(WitnessTransportDenied):
                client.request({**consume, 'ticket_mac': bad})
            assert state.read_bytes() == before
            assert client.request({'operation': 'generation'})['generation'] == 1
        assert client.request(consume)['status'] == 'spent'
        with pytest.raises(WitnessTransportDenied):
            client.request(consume)
        with sqlite3.connect(state) as db:
            assert db.execute('SELECT consumed FROM reservations').fetchall() == [(1,)]
            assert db.execute('SELECT event FROM witness_events ORDER BY sequence').fetchall() == [
                ('reserved',), ('consumed',)]
    finally:
        server.close()


def start_server(config_path):
    source_dir = Path(transport_module.__file__).parent
    server_script = source_dir/'run_durable_local_witness_server.py'
    env = dict(os.environ)
    env['PYTHONPATH'] = str(source_dir) + os.pathsep + env.get('PYTHONPATH', '')
    config = json.loads(config_path.read_text())
    socket_path = config['socket_path']
    if 'caller_keyrings' in config:
        keys = {key_id: bytes.fromhex(value) for key_id, value in config['caller_keyrings'][CALLER].items()}
        current_key_id = config['current_caller_key_ids'][CALLER]
    else:
        keys = {'caller-v1': bytes.fromhex(config['caller_keys'][CALLER])}
        current_key_id = 'caller-v1'
    readiness = UnixWitnessClient(socket_path, caller_id=CALLER, keys=keys,
        current_key_id=current_key_id, timeout=0.1)
    process = subprocess.Popen([sys.executable, str(server_script), str(config_path)],
        env=env, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        if process.poll() is not None:
            _, error = process.communicate(timeout=2)
            raise AssertionError(f'local witness server exited during startup: {error}')
        if Path(socket_path).exists():
            try:
                readiness.request({'operation': 'generation'})
            except WitnessTransportDenied:
                pass
            else:
                return process
        time.sleep(0.01)
    process.terminate()
    process.wait(timeout=2)
    raise AssertionError('local witness socket did not start')


def stop_server(process):
    process.terminate()
    process.wait(timeout=5)


def client_program():
    return '''
import json, os, sys, time
import socket
from pathlib import Path
from durable_local_witness_transport import UnixWitnessClient
from uuid import uuid4
from durable_local_recovery_witness import WitnessDenied, request_mac
from durable_local_witness_transport import WitnessTransportDenied
config=json.load(open(sys.argv[1]))
if 'client_keyrings' in config:
    keys={key_id:bytes.fromhex(value) for key_id,value in config['client_keyrings'].items()}
    client=UnixWitnessClient(config['socket_path'], caller_id='socket-fixture-caller',
        keys=keys, current_key_id=config['client_key_id'])
else:
    client=UnixWitnessClient(config['socket_path'], caller_id='socket-fixture-caller', key=b'u'*32)
invocation, ledger, digest, mode=sys.argv[2:]
if mode == 'reserve-consume':
    request={'operation':'reserve','request_id':invocation,'ledger_id':ledger,
        'invocation_id':invocation,'intent_sha256':digest}
    first=client.request(request)
    retry=client.request(request)
    assert first == retry
    consume={'operation':'consume',**{key:first[key] for key in
        ('request_id','ledger_id','invocation_id','intent_sha256','generation','state_key_id','nonce')},
        'ticket_mac':first['ticket_mac']}
    result=client.request(consume)
    print(json.dumps({'first':first,'retry':retry,'consumed':result},sort_keys=True))
elif mode == 'reserve-only':
    request={'operation':'reserve','request_id':invocation,'ledger_id':ledger,
        'invocation_id':invocation,'intent_sha256':digest}
    print(json.dumps(client.request(request),sort_keys=True))
elif mode in ('consume-ticket','consume-race'):
    if mode == 'consume-race':
        ready=Path(config['ready_dir'])/str(os.getpid())
        ready.touch(mode=0o600)
        while not Path(config['start_file']).exists():
            time.sleep(0.005)
    ticket=json.load(open(config['ticket_path']))
    consume={'operation':'consume',**{key:ticket[key] for key in
        ('request_id','ledger_id','invocation_id','intent_sha256','generation','state_key_id','nonce')},
        'ticket_mac':ticket['ticket_mac']}
    try:
        print(client.request(consume)['status'])
    except WitnessTransportDenied:
        print('denied')
elif mode == 'drop-consume-reply':
    ticket=json.load(open(config['ticket_path']))
    consume={'operation':'consume',**{key:ticket[key] for key in
        ('request_id','ledger_id','invocation_id','intent_sha256','generation','state_key_id','nonce')},
        'ticket_mac':ticket['ticket_mac']}
    exchange_nonce=str(uuid4())
    frame={'caller_id':'socket-fixture-caller','caller_key_id':'caller-v1',
        'request':consume,'exchange_nonce':exchange_nonce,
        'mac':request_mac(b'u'*32,'socket-fixture-caller',consume,'caller-v1',exchange_nonce=exchange_nonce)}
    payload=json.dumps(frame,sort_keys=True,separators=(',',':')).encode('ascii')+b'\\n'
    connection=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)
    connection.connect(config['socket_path'])
    connection.sendall(payload)
    connection.shutdown(socket.SHUT_RD)
    connection.close()
    print('reply intentionally abandoned')
elif mode == 'retry-consumed':
    request={'operation':'reserve','request_id':invocation,'ledger_id':ledger,
        'invocation_id':invocation,'intent_sha256':digest}
    try:
        client.request(request)
    except WitnessTransportDenied:
        print('denied')
    else:
        raise AssertionError('consumed identity reopened after restart')
elif mode == 'wrong-key':
    client=UnixWitnessClient(config['socket_path'], caller_id='socket-fixture-caller', key=b'x'*32)
    try:
        client.request({'operation':'generation'})
    except WitnessTransportDenied:
        print('denied')
    else:
        raise AssertionError('wrong caller key was accepted')
elif mode == 'old-key':
    client=UnixWitnessClient(config['socket_path'], caller_id='socket-fixture-caller',
        key=bytes.fromhex(config['client_keyrings']['caller-v1']))
    try:
        client.request({'operation':'generation'})
    except WitnessTransportDenied:
        print('denied')
    else:
        print('accepted')
elif mode == 'advance-race':
    ready=Path(config['ready_dir'])/str(os.getpid())
    ready.touch(mode=0o600)
    while not Path(config['start_file']).exists():
        time.sleep(0.005)
    print(json.dumps(client.request({'operation':'advance','request_id':invocation}),
        sort_keys=True))
elif mode == 'advance-denied':
    try:
        client.request({'operation':'advance','request_id':invocation})
    except WitnessTransportDenied:
        print('denied')
    else:
        raise AssertionError('caller without recovery-admin role advanced generation')
'''


@pytest.mark.skipif(not hasattr(__import__('socket'), 'SO_PEERCRED'),
    reason='local peer credential transport requires Linux SO_PEERCRED')
def test_separate_server_and_client_processes_authenticate_and_recover(tmp_path):
    socket_dir = tmp_path/'private-socket'
    socket_dir.mkdir(mode=0o700)
    state_dir = tmp_path/'witness-state'
    state_dir.mkdir(mode=0o700)
    state_path = state_dir/'witness.sqlite3'
    DurableLocalRecoveryWitness(state_path,
        caller_keys={CALLER: CALLER_KEY}, state_key=STATE_KEY, initialize=True)
    old_key, new_key = CALLER_KEY, b'n'*32
    config = {'socket_path': str(socket_dir/'witness.sock'),
        'state_path': str(state_path),
        'caller_keyrings': {CALLER: {'caller-v1': old_key.hex(), 'caller-v2': new_key.hex()}},
        'current_caller_key_ids': {CALLER: 'caller-v2'},
        'state_key': STATE_KEY.hex()}
    config_path = tmp_path/'server-config.json'
    config_path.write_text(json.dumps(config))
    config_path.chmod(0o600)
    client_config_path = tmp_path/'client-config.json'
    client_config = {'socket_path': config['socket_path'],
        'client_keyrings': {'caller-v1': old_key.hex(), 'caller-v2': new_key.hex()},
        'client_key_id': 'caller-v2'}
    client_config_path.write_text(json.dumps(client_config))
    client_config_path.chmod(0o600)
    config_path.parent.chmod(0o700)
    invocation, ledger, digest = str(uuid4()), str(uuid4()), 'd'*64
    args = [sys.executable, '-c', client_program(), str(client_config_path),
        invocation, ledger, digest]
    client_env = dict(os.environ)
    client_env['PYTHONPATH'] = str(Path(transport_module.__file__).parent) + os.pathsep + client_env.get('PYTHONPATH', '')

    server = start_server(config_path)
    try:
        first = subprocess.run(args+['reserve-consume'], capture_output=True,
            text=True, env=client_env, timeout=10)
        assert first.returncode == 0, first.stderr
        first_result = json.loads(first.stdout)
        assert first_result['first'] == first_result['retry']
        assert first_result['consumed']['status'] == 'spent'
        overlap = subprocess.run(args+['old-key'], capture_output=True,
            text=True, env=client_env, timeout=10)
        assert overlap.returncode == 0, overlap.stderr
        assert overlap.stdout.strip() == 'accepted'
        wrong_key = subprocess.run(args+['wrong-key'], capture_output=True,
            text=True, env=client_env, timeout=10)
        assert wrong_key.returncode == 0, wrong_key.stderr
        assert wrong_key.stdout.strip() == 'denied'
        advance = subprocess.run(args+['advance-denied'], capture_output=True,
            text=True, env=client_env, timeout=10)
        assert advance.returncode == 0, advance.stderr
        assert advance.stdout.strip() == 'denied'
    finally:
        stop_server(server)

    unavailable = UnixWitnessClient(config['socket_path'], caller_id=CALLER,
        key=CALLER_KEY, timeout=0.1)
    with pytest.raises(WitnessTransportDenied, match='unavailable'):
        unavailable.request({'operation':'generation'})

    config['caller_keyrings'] = {CALLER: {'caller-v2': new_key.hex()}}
    config['current_caller_key_ids'] = {CALLER: 'caller-v2'}
    config_path.write_text(json.dumps(config))
    config_path.chmod(0o600)
    restarted = start_server(config_path)
    try:
        retry = subprocess.run(args+['retry-consumed'], capture_output=True,
            text=True, env=client_env, timeout=10)
        assert retry.returncode == 0, retry.stderr
        assert retry.stdout.strip() == 'denied'
        retired = subprocess.run(args+['old-key'], capture_output=True,
            text=True, env=client_env, timeout=10)
        assert retired.returncode == 0, retired.stderr
        assert retired.stdout.strip() == 'denied'
    finally:
        stop_server(restarted)


@pytest.mark.skipif(not hasattr(__import__('socket'), 'SO_PEERCRED'),
    reason='local peer credential transport requires Linux SO_PEERCRED')
def test_state_key_rotation_survives_server_restart_and_fails_closed_during_retirement(tmp_path):
    socket_dir = tmp_path/'private-socket'
    socket_dir.mkdir(mode=0o700)
    state_dir = tmp_path/'witness-state'
    state_dir.mkdir(mode=0o700)
    state_path = state_dir/'witness.sqlite3'
    DurableLocalRecoveryWitness(state_path,
        caller_keys={CALLER: CALLER_KEY}, state_key=STATE_KEY, initialize=True)
    config = {'socket_path':str(socket_dir/'witness.sock'),
        'state_path':str(state_path), 'caller_keys':{CALLER:CALLER_KEY.hex()},
        'state_key':STATE_KEY.hex()}
    config_path = tmp_path/'server-config.json'
    client_config_path = tmp_path/'client-config.json'
    ticket_path = tmp_path/'pending-ticket.json'
    client_config = {'socket_path':config['socket_path'], 'ticket_path':str(ticket_path)}
    config_path.write_text(json.dumps(config))
    config_path.chmod(0o600)
    client_config_path.write_text(json.dumps(client_config))
    client_config_path.chmod(0o600)
    args = [sys.executable, '-c', client_program(), str(client_config_path)]
    client_env = dict(os.environ)
    client_env['PYTHONPATH'] = str(Path(transport_module.__file__).parent) + os.pathsep + client_env.get('PYTHONPATH', '')
    content = b'state rotation process fixture'
    ledger_id = uuid4()
    intent = SyntheticWriteIntent(version=1, action='synthetic.record.replace',
        scope=WriteScope(project_id=uuid4(), agent_id=uuid4(), root_id=uuid4(),
            invocation_id=uuid4()), ledger_id=ledger_id, record_id=uuid4(),
        expected_revision=0, content_sha256=hashlib.sha256(content).hexdigest(),
        content_size=len(content), approval_payload_sha256='a'*64,
        policy_snapshot_sha256='b'*64)
    invocation, ledger, digest = str(intent.scope.invocation_id), str(ledger_id), intent_digest(intent)
    server = start_server(config_path)
    try:
        reserve = subprocess.run(args+[invocation,ledger,digest,'reserve-only'],
            capture_output=True,text=True,env=client_env,timeout=10)
        assert reserve.returncode == 0, reserve.stderr
        ticket = json.loads(reserve.stdout)
        assert ticket['state_key_id'] == 'state-v1'
        ticket_path.write_text(json.dumps(ticket))
        ticket_path.chmod(0o600)
    finally:
        stop_server(server)

    new_state_key = b'z'*32
    config.pop('state_key')
    config['state_keys'] = {'state-v2':new_state_key.hex()}
    config['current_state_key_id'] = 'state-v2'
    config_path.write_text(json.dumps(config))
    config_path.chmod(0o600)
    retired_too_early = start_server(config_path)
    try:
        consume = subprocess.run(args+[invocation,ledger,digest,'consume-ticket'],
            capture_output=True,text=True,env=client_env,timeout=10)
        assert consume.returncode == 0, consume.stderr
        assert consume.stdout.strip() == 'denied'
        ledger_dir = tmp_path/'ledger-fixture'
        ledger_dir.mkdir(mode=0o700)
        fake_ledger = SyntheticWriteLedger(ledger_dir, ledger_id=ledger_id,
            key=b'l'*32, experiment_enabled=True)
        with sqlite3.connect(fake_ledger.path) as db:
            assert db.execute('SELECT count(*) FROM records').fetchone()[0] == 0
            assert db.execute('SELECT count(*) FROM attempts').fetchone()[0] == 0
    finally:
        stop_server(retired_too_early)

    config['state_keys'] = {'state-v1':STATE_KEY.hex(), 'state-v2':new_state_key.hex()}
    config_path.write_text(json.dumps(config))
    config_path.chmod(0o600)
    overlap = start_server(config_path)
    try:
        new_invocation, new_ledger = str(uuid4()), str(uuid4())
        new_reserve = subprocess.run(args+[new_invocation,new_ledger,digest,'reserve-only'],
            capture_output=True,text=True,env=client_env,timeout=10)
        assert new_reserve.returncode == 0, new_reserve.stderr
        assert json.loads(new_reserve.stdout)['state_key_id'] == 'state-v2'
        consume = subprocess.run(args+[invocation,ledger,digest,'consume-ticket'],
            capture_output=True,text=True,env=client_env,timeout=10)
        assert consume.returncode == 0, consume.stderr
        assert consume.stdout.strip() == 'spent'
        receipt = verify_write_receipt(fake_ledger.apply(intent, content), intent,
            key=b'l'*32)
        assert receipt.result_revision == 1
    finally:
        stop_server(overlap)

    config['state_keys'] = {'state-v2':new_state_key.hex()}
    config_path.write_text(json.dumps(config))
    config_path.chmod(0o600)
    retired_after_consume = start_server(config_path)
    try:
        retry = subprocess.run(args+[invocation,ledger,digest,'retry-consumed'],
            capture_output=True,text=True,env=client_env,timeout=10)
        assert retry.returncode == 0, retry.stderr
        assert retry.stdout.strip() == 'denied'
        with sqlite3.connect(fake_ledger.path) as db:
            assert db.execute('SELECT count(*) FROM records').fetchone()[0] == 1
            assert db.execute('SELECT count(*) FROM attempts').fetchone()[0] == 1
    finally:
        stop_server(retired_after_consume)


@pytest.mark.skipif(not hasattr(__import__('socket'), 'SO_PEERCRED'),
    reason='local peer credential transport requires Linux SO_PEERCRED')
def test_separate_client_processes_racing_consume_commit_once(tmp_path):
    socket_dir = tmp_path/'private-socket'
    socket_dir.mkdir(mode=0o700)
    state_dir = tmp_path/'witness-state'
    state_dir.mkdir(mode=0o700)
    state_path = state_dir/'witness.sqlite3'
    replacement_key = b'w' * 32
    DurableLocalRecoveryWitness(state_path,
        caller_keys={CALLER:{'caller-v1':CALLER_KEY,'caller-v2':replacement_key}},
        current_caller_key_ids={CALLER:'caller-v2'}, state_key=STATE_KEY, initialize=True)
    config = {'socket_path':str(socket_dir/'witness.sock'),
        'state_path':str(state_path),
        'caller_keyrings':{CALLER:{'caller-v1':CALLER_KEY.hex(),
            'caller-v2':replacement_key.hex()}},
        'current_caller_key_ids':{CALLER:'caller-v2'},'state_key':STATE_KEY.hex()}
    config_path = tmp_path/'server-config.json'
    config_path.write_text(json.dumps(config))
    config_path.chmod(0o600)
    start_signal = tmp_path/'start-consume-race'
    ready_dir = tmp_path/'ready-clients'
    ready_dir.mkdir(mode=0o700)
    ticket_path = tmp_path/'pending-ticket.json'
    client_keyring = {'caller-v1':CALLER_KEY.hex(),'caller-v2':replacement_key.hex()}
    client_args = {}
    for key_id in ('caller-v1','caller-v2'):
        client_config_path = tmp_path/f'client-{key_id}.json'
        client_config = {'socket_path':config['socket_path'],
            'client_keyrings':client_keyring,'client_key_id':key_id,
            'ticket_path':str(ticket_path),'start_file':str(start_signal),
            'ready_dir':str(ready_dir)}
        client_config_path.write_text(json.dumps(client_config))
        client_config_path.chmod(0o600)
        client_args[key_id] = [sys.executable,'-c',client_program(),str(client_config_path)]
    client_env = dict(os.environ)
    client_env['PYTHONPATH'] = str(Path(transport_module.__file__).parent) + os.pathsep + client_env.get('PYTHONPATH','')
    content = b'process-race fixture record'
    ledger_id = uuid4()
    intent = SyntheticWriteIntent(version=1, action='synthetic.record.replace',
        scope=WriteScope(project_id=uuid4(), agent_id=uuid4(), root_id=uuid4(),
            invocation_id=uuid4()), ledger_id=ledger_id, record_id=uuid4(),
        expected_revision=0, content_sha256=hashlib.sha256(content).hexdigest(),
        content_size=len(content), approval_payload_sha256='a'*64,
        policy_snapshot_sha256='b'*64)
    invocation, ledger, digest = str(intent.scope.invocation_id), str(ledger_id), intent_digest(intent)
    control_dir = tmp_path/'control-fixture'
    control_dir.mkdir(mode=0o700)
    control_path = control_dir/'control.sqlite3'
    with sqlite3.connect(control_path) as db:
        db.execute('CREATE TABLE admission (invocation_id TEXT PRIMARY KEY, status TEXT NOT NULL)')
    ledger_dir = tmp_path/'ledger-fixture'
    ledger_dir.mkdir(mode=0o700)
    fake_ledger = SyntheticWriteLedger(ledger_dir, ledger_id=ledger_id,
        key=b'l'*32, experiment_enabled=True)
    snapshots = tmp_path/'snapshots'
    snapshots.mkdir(mode=0o700)
    shutil.copy2(control_path, snapshots/'control.sqlite3')
    shutil.copy2(fake_ledger.path, snapshots/'ledger.sqlite3')
    server = start_server(config_path)
    clients = []
    try:
        reserve = subprocess.run(client_args['caller-v2']+[invocation,ledger,digest,'reserve-only'],
            capture_output=True,text=True,env=client_env,timeout=10)
        assert reserve.returncode == 0, reserve.stderr
        ticket_path.write_text(reserve.stdout)
        ticket_path.chmod(0o600)
        clients = [subprocess.Popen(client_args[key_id]+[invocation,ledger,digest,'consume-race'],
            stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,env=client_env)
            for key_id in ('caller-v1','caller-v2')]
        deadline = time.monotonic() + 5
        while len(list(ready_dir.iterdir())) < 2 and time.monotonic() < deadline:
            time.sleep(0.01)
        assert len(list(ready_dir.iterdir())) == 2, 'client processes did not reach the consume barrier'
        start_signal.touch(mode=0o600)
        results = [client.communicate(timeout=10) for client in clients]
        assert [client.returncode for client in clients] == [0,0]
        replies = [stdout.strip() for stdout, _ in results]
        assert replies.count('spent') == 1
        assert replies.count('denied') == 1
        receipt = verify_write_receipt(fake_ledger.apply(intent, content), intent,
            key=b'l'*32)
        assert receipt.result_revision == 1
        with sqlite3.connect(fake_ledger.path) as db:
            assert db.execute('SELECT count(*) FROM records').fetchone()[0] == 1
            assert db.execute('SELECT count(*) FROM attempts').fetchone()[0] == 1
        with sqlite3.connect(state_path) as db:
            assert db.execute("SELECT count(*) FROM witness_events "
                "WHERE event='consumed'").fetchone()[0] == 1
        with sqlite3.connect(control_path) as db:
            db.execute('INSERT INTO admission VALUES (?,?)', (invocation, 'unknown'))

        # Restore both effect-side fixtures, but retain and restart the witness state.
        stop_server(server)
        server = None
        shutil.copy2(snapshots/'control.sqlite3', control_path)
        shutil.copy2(snapshots/'ledger.sqlite3', fake_ledger.path)
        server = start_server(config_path)
        replay = subprocess.run(client_args['caller-v2']+[invocation,ledger,digest,'retry-consumed'],
            capture_output=True,text=True,env=client_env,timeout=10)
        assert replay.returncode == 0, replay.stderr
        assert replay.stdout.strip() == 'denied'
        with sqlite3.connect(control_path) as db:
            assert db.execute('SELECT count(*) FROM admission').fetchone()[0] == 0
        with sqlite3.connect(fake_ledger.path) as db:
            assert db.execute('SELECT count(*) FROM records').fetchone()[0] == 0
            assert db.execute('SELECT count(*) FROM attempts').fetchone()[0] == 0
        with sqlite3.connect(state_path) as db:
            assert db.execute('SELECT consumed FROM reservations WHERE invocation_id=?',
                (invocation,)).fetchone()[0] == 1
            assert db.execute("SELECT count(*) FROM witness_events "
                "WHERE event='consumed'").fetchone()[0] == 1
    finally:
        for client in clients:
            if client.poll() is None:
                client.terminate()
                client.wait(timeout=2)
        if server is not None:
            stop_server(server)


@pytest.mark.skipif(not hasattr(__import__('socket'), 'SO_PEERCRED'),
    reason='local peer credential transport requires Linux SO_PEERCRED')
def test_separate_admin_processes_retry_generation_advance_once(tmp_path):
    socket_dir = tmp_path/'private-socket'
    socket_dir.mkdir(mode=0o700)
    state_dir = tmp_path/'witness-state'
    state_dir.mkdir(mode=0o700)
    state_path = state_dir/'witness.sqlite3'
    DurableLocalRecoveryWitness(state_path, caller_keys={CALLER:CALLER_KEY},
        state_key=STATE_KEY, advance_callers={CALLER}, initialize=True)
    config = {'socket_path':str(socket_dir/'witness.sock'),
        'state_path':str(state_path), 'caller_keys':{CALLER:CALLER_KEY.hex()},
        'state_key':STATE_KEY.hex(), 'advance_callers':[CALLER]}
    config_path = tmp_path/'server-config.json'
    config_path.write_text(json.dumps(config))
    config_path.chmod(0o600)
    start_signal = tmp_path/'start-advance-race'
    ready_dir = tmp_path/'ready-clients'
    ready_dir.mkdir(mode=0o700)
    client_config_path = tmp_path/'client-config.json'
    client_config = {'socket_path':config['socket_path'],
        'start_file':str(start_signal),'ready_dir':str(ready_dir)}
    client_config_path.write_text(json.dumps(client_config))
    client_config_path.chmod(0o600)
    args = [sys.executable,'-c',client_program(),str(client_config_path)]
    client_env = dict(os.environ)
    client_env['PYTHONPATH'] = str(Path(transport_module.__file__).parent) + os.pathsep + client_env.get('PYTHONPATH','')
    request_id = str(uuid4())
    server = start_server(config_path)
    clients = []
    try:
        clients = [subprocess.Popen(args+[request_id,str(uuid4()),'a'*64,'advance-race'],
            stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,env=client_env)
            for _ in range(2)]
        deadline = time.monotonic() + 5
        while len(list(ready_dir.iterdir())) < 2 and time.monotonic() < deadline:
            time.sleep(0.01)
        assert len(list(ready_dir.iterdir())) == 2, 'admin processes did not reach the advance barrier'
        start_signal.touch(mode=0o600)
        results = [client.communicate(timeout=10) for client in clients]
        assert [client.returncode for client in clients] == [0,0]
        replies = [json.loads(stdout) for stdout, _ in results]
        assert replies == [{'generation':2,'request_id':request_id,'status':'advanced'}]*2
        with sqlite3.connect(state_path) as db:
            assert db.execute('SELECT generation FROM witness_state').fetchone()[0] == 2
            assert db.execute('SELECT count(*) FROM generation_operations').fetchone()[0] == 1
            assert db.execute("SELECT count(*) FROM witness_events "
                "WHERE event='generation_advanced'").fetchone()[0] == 1
    finally:
        for client in clients:
            if client.poll() is None:
                client.terminate()
                client.wait(timeout=2)
        stop_server(server)


@pytest.mark.skipif(not hasattr(__import__('socket'), 'SO_PEERCRED'),
    reason='local peer credential transport requires Linux SO_PEERCRED')
def test_lost_consume_reply_remains_spent_after_server_restart(tmp_path):
    socket_dir = tmp_path/'private-socket'
    socket_dir.mkdir(mode=0o700)
    state_dir = tmp_path/'witness-state'
    state_dir.mkdir(mode=0o700)
    state_path = state_dir/'witness.sqlite3'
    DurableLocalRecoveryWitness(state_path,
        caller_keys={CALLER:CALLER_KEY}, state_key=STATE_KEY, initialize=True)
    config = {'socket_path':str(socket_dir/'witness.sock'),
        'state_path':str(state_path), 'caller_keys':{CALLER:CALLER_KEY.hex()},
        'state_key':STATE_KEY.hex()}
    config_path = tmp_path/'server-config.json'
    config_path.write_text(json.dumps(config))
    config_path.chmod(0o600)
    ticket_path = tmp_path/'pending-ticket.json'
    client_config_path = tmp_path/'client-config.json'
    client_config_path.write_text(json.dumps({'socket_path':config['socket_path'],
        'ticket_path':str(ticket_path)}))
    client_config_path.chmod(0o600)
    args = [sys.executable,'-c',client_program(),str(client_config_path)]
    client_env = dict(os.environ)
    client_env['PYTHONPATH'] = str(Path(transport_module.__file__).parent) + os.pathsep + client_env.get('PYTHONPATH','')
    content = b'lost reply fixture body'
    ledger_id = uuid4()
    intent = SyntheticWriteIntent(version=1, action='synthetic.record.replace',
        scope=WriteScope(project_id=uuid4(), agent_id=uuid4(), root_id=uuid4(),
            invocation_id=uuid4()), ledger_id=ledger_id, record_id=uuid4(),
        expected_revision=0, content_sha256=hashlib.sha256(content).hexdigest(),
        content_size=len(content), approval_payload_sha256='a'*64,
        policy_snapshot_sha256='b'*64)
    invocation, ledger, digest = str(intent.scope.invocation_id), str(ledger_id), intent_digest(intent)
    server = start_server(config_path)
    try:
        reserve = subprocess.run(args+[invocation,ledger,digest,'reserve-only'],
            capture_output=True,text=True,env=client_env,timeout=10)
        assert reserve.returncode == 0, reserve.stderr
        ticket_path.write_text(reserve.stdout)
        ticket_path.chmod(0o600)
        dropped = subprocess.run(args+[invocation,ledger,digest,'drop-consume-reply'],
            capture_output=True,text=True,env=client_env,timeout=10)
        assert dropped.returncode == 0, dropped.stderr
        assert dropped.stdout.strip() == 'reply intentionally abandoned'
        deadline = time.monotonic() + 5
        consumed = 0
        while time.monotonic() < deadline:
            with sqlite3.connect(state_path) as db:
                consumed = db.execute("SELECT count(*) FROM witness_events "
                    "WHERE event='consumed'").fetchone()[0]
            if consumed:
                break
            time.sleep(0.01)
        assert consumed == 1, 'server did not durably consume before the client abandoned the reply'
    finally:
        stop_server(server)

    restarted = start_server(config_path)
    try:
        retry = subprocess.run(args+[invocation,ledger,digest,'retry-consumed'],
            capture_output=True,text=True,env=client_env,timeout=10)
        assert retry.returncode == 0, retry.stderr
        assert retry.stdout.strip() == 'denied'
        with sqlite3.connect(state_path) as db:
            assert db.execute('SELECT consumed FROM reservations WHERE invocation_id=?',
                (invocation,)).fetchone()[0] == 1
            assert db.execute("SELECT count(*) FROM witness_events "
                "WHERE event='consumed'").fetchone()[0] == 1
        # A lost consume reply leaves the caller uncertain, so this harness does not enter the effect.
        ledger_dir = tmp_path/'ledger-fixture'
        ledger_dir.mkdir(mode=0o700)
        fake_ledger = SyntheticWriteLedger(ledger_dir, ledger_id=ledger_id,
            key=b'l'*32, experiment_enabled=True)
        with sqlite3.connect(fake_ledger.path) as db:
            assert db.execute('SELECT count(*) FROM records').fetchone()[0] == 0
            assert db.execute('SELECT count(*) FROM attempts').fetchone()[0] == 0
    finally:
        stop_server(restarted)


def test_server_rejects_non_private_socket_directory(tmp_path):
    directory = tmp_path/'not-private'
    directory.mkdir(mode=0o755)
    directory.chmod(0o755)
    state = tmp_path/'state.sqlite3'
    witness = DurableLocalRecoveryWitness(state,
        caller_keys={CALLER: CALLER_KEY}, state_key=STATE_KEY, initialize=True)
    server = LocalWitnessUnixServer(witness, directory/'witness.sock')
    with pytest.raises(WitnessTransportDenied, match='private'):
        server.start()


def test_client_rejects_oversized_request_before_connect(tmp_path):
    client = UnixWitnessClient(tmp_path/'absent.sock', caller_id=CALLER, key=CALLER_KEY)
    with pytest.raises(WitnessTransportDenied, match='frame'):
        client.request({'operation':'reserve', 'payload':'x'*20000})


def test_client_rejects_unbounded_or_invalid_timeout_before_socket_creation(tmp_path, monkeypatch):
    def unexpected_socket(*args, **kwargs):
        pytest.fail('invalid client timeout reached socket creation')

    monkeypatch.setattr(transport_module.socket, 'socket', unexpected_socket)
    for bad in (None, True, False, 0, -1, float('nan'), float('inf'),
                float('-inf'), '1', [], 3, 10**1000):
        with pytest.raises(WitnessTransportDenied, match='timeout'):
            UnixWitnessClient(tmp_path/'absent.sock', caller_id=CALLER,
                key=CALLER_KEY, timeout=bad)


@pytest.mark.parametrize('delays,accepted,committed', [
    ((0.2, 0.2, 0.2), True, True), ((0.6, 0.2, 0.3), False, True),
    ((1.1, 0, 0), False, False), ((0.6, 0.6, 0), False, False),
], ids=['within-budget', 'reply-after-shared-budget', 'connect-budget', 'send-budget'])
def test_client_shares_transport_budget_and_preserves_unknown_consume(tmp_path, monkeypatch, delays, accepted, committed):
    witness = DurableLocalRecoveryWitness(tmp_path/'state.sqlite3',
        caller_keys={CALLER: CALLER_KEY}, state_key=STATE_KEY, initialize=True)
    reserve = {'operation': 'reserve', 'request_id': str(uuid4()),
        'ledger_id': str(uuid4()), 'invocation_id': str(uuid4()), 'intent_sha256': 'a'*64}
    ticket = witness.reserve(caller_id=CALLER, request=reserve,
        mac=request_mac(CALLER_KEY, CALLER, reserve))['body']
    consume = {'operation': 'consume', **{k: v for k, v in ticket.items() if k != 'status'}}
    clock = SimpleNamespace(now=0.0)
    monkeypatch.setattr(transport_module, 'time', SimpleNamespace(monotonic=lambda: clock.now))

    class DelayedPeer:
        timeout = None
        closed = False

        def __enter__(self):
            return self

        def __exit__(self, *args):
            self.closed = True

        def settimeout(self, value):
            self.timeout = value

        def gettimeout(self):
            return self.timeout

        def elapse(self, delay):
            if self.timeout is not None and delay > self.timeout:
                clock.now += self.timeout
                raise TimeoutError('controlled peer exceeded socket budget')
            clock.now += delay

        def connect(self, path):
            self.elapse(delays[0])

        def sendall(self, payload):
            self.elapse(delays[1])
            frame = json.loads(payload)
            self.reply = witness.consume(caller_id=frame['caller_id'],
                caller_key_id=frame['caller_key_id'], request=frame['request'],
                mac=frame['mac'], exchange_nonce=frame['exchange_nonce'])

        def recv(self, size):
            self.elapse(delays[2])
            return json.dumps(self.reply).encode('ascii') + b'\n'

    peer = DelayedPeer()
    monkeypatch.setattr(transport_module.socket, 'socket', lambda *args: peer)
    client = UnixWitnessClient(tmp_path/'controlled.sock', caller_id=CALLER,
        key=CALLER_KEY, timeout=1)
    if accepted:
        assert client.request(consume)['status'] == 'spent'
    else:
        with pytest.raises(WitnessTransportDenied):
            client.request(consume)
    assert peer.closed
    assert clock.now <= 1.0
    # A response deadline never revokes a consume already committed by the peer.
    with sqlite3.connect(witness.path) as db:
        assert db.execute('SELECT consumed FROM reservations').fetchall() == [(int(committed),)]
        events = [('reserved',), ('consumed',)] if committed else [('reserved',)]
        assert db.execute('SELECT event FROM witness_events ORDER BY sequence').fetchall() == events
    if committed:
        with pytest.raises(WitnessDenied, match='already consumed'):
            witness.consume(caller_id=CALLER, request=consume,
                mac=request_mac(CALLER_KEY, CALLER, consume))


def test_server_config_rejects_duplicate_and_unexpected_fields(tmp_path):
    config_path = tmp_path/'server-config.json'
    duplicate = '{"socket_path":"first","socket_path":"second"}'
    config_path.write_text(duplicate)
    config_path.chmod(0o600)
    with pytest.raises(WitnessTransportDenied, match='config unavailable'):
        transport_module.serve_config(config_path)
    config = {'socket_path':'/tmp/witness.sock', 'state_path':'/tmp/witness.sqlite3',
        'caller_keys':{CALLER:CALLER_KEY.hex()}, 'state_key':STATE_KEY.hex(),
        'client_keyrings':{'client-v1':CALLER_KEY.hex()}}
    config_path.write_text(json.dumps(config))
    config_path.chmod(0o600)
    with pytest.raises(WitnessTransportDenied, match='config fields unavailable'):
        transport_module.serve_config(config_path)


def test_server_config_maps_excessive_json_nesting_to_denial(tmp_path, monkeypatch):
    depth = 6000
    path = tmp_path/'config.json'
    path.write_text('[' * depth + '0' + ']' * depth)
    path.chmod(0o600)

    def unexpected_server(*args, **kwargs):
        pytest.fail('deep configuration reached server construction')

    monkeypatch.setattr(transport_module, 'LocalWitnessUnixServer', unexpected_server)
    with pytest.raises(WitnessTransportDenied):
        transport_module.serve_config(path)


@pytest.mark.parametrize('field', ['caller', 'caller_key', 'state_key'])
def test_server_config_rejects_invalid_unicode_identity_before_start(tmp_path, monkeypatch, field):
    state = tmp_path/'state.sqlite3'
    DurableLocalRecoveryWitness(state, caller_keys={CALLER: CALLER_KEY},
        state_key=STATE_KEY, initialize=True)
    config = {'socket_path': str(tmp_path/'witness.sock'), 'state_path': str(state),
        'caller_keyrings': {CALLER: {'caller-v1': CALLER_KEY.hex()}},
        'current_caller_key_ids': {CALLER: 'caller-v1'},
        'state_keys': {'state-v1': STATE_KEY.hex()}, 'current_state_key_id': 'state-v1'}
    bad = '\ud800'
    if field == 'caller':
        config['caller_keyrings'] = {bad: {'caller-v1': CALLER_KEY.hex()}}
        config['current_caller_key_ids'] = {bad: 'caller-v1'}
    elif field == 'caller_key':
        config['caller_keyrings'] = {CALLER: {bad: CALLER_KEY.hex()}}
        config['current_caller_key_ids'] = {CALLER: bad}
    else:
        config['state_keys'] = {bad: STATE_KEY.hex()}
        config['current_state_key_id'] = bad
    path = tmp_path/'config.json'
    path.write_text(json.dumps(config))
    path.chmod(0o600)
    before = state.read_bytes()

    def unexpected_server(*args, **kwargs):
        pytest.fail('invalid Unicode identity reached server construction')

    monkeypatch.setattr(transport_module, 'LocalWitnessUnixServer', unexpected_server)
    with pytest.raises(WitnessTransportDenied):
        transport_module.serve_config(path)
    assert state.read_bytes() == before
    assert not (tmp_path/'witness.sock').exists()


@pytest.mark.parametrize('allowlist', [
    'ab', {'a': True, 'b': False}, None, True, 1,
    [1], [''], ['a', 'a'], ['unknown'],
])
def test_server_config_rejects_malformed_admin_allowlist_before_server_start(tmp_path, monkeypatch, allowlist):
    state = tmp_path/'state.sqlite3'
    DurableLocalRecoveryWitness(state, caller_keys={'a': b'a'*32, 'b': b'b'*32},
        state_key=STATE_KEY, initialize=True)
    config = {'socket_path': str(tmp_path/'witness.sock'), 'state_path': str(state),
        'caller_keys': {'a': (b'a'*32).hex(), 'b': (b'b'*32).hex()},
        'state_key': STATE_KEY.hex(), 'advance_callers': allowlist}
    path = tmp_path/'config.json'
    path.write_text(json.dumps(config))
    path.chmod(0o600)
    before = state.read_bytes()

    def unexpected_server(*args, **kwargs):
        pytest.fail('malformed recovery-admin config reached server construction')

    monkeypatch.setattr(transport_module, 'LocalWitnessUnixServer', unexpected_server)
    with pytest.raises(WitnessTransportDenied):
        transport_module.serve_config(path)
    assert state.read_bytes() == before
    assert not (tmp_path/'witness.sock').exists()


@pytest.mark.parametrize('allowlist', [None, [], ['a'], ['a', 'b']])
def test_server_config_admin_allowlist_preserves_explicit_caller_membership(tmp_path, monkeypatch, allowlist):
    state = tmp_path/'state.sqlite3'
    keys = {'a': b'a'*32, 'b': b'b'*32}
    DurableLocalRecoveryWitness(state, caller_keys=keys, state_key=STATE_KEY, initialize=True)
    config = {'socket_path': str(tmp_path/'witness.sock'), 'state_path': str(state),
        'caller_keys': {caller: key.hex() for caller, key in keys.items()},
        'state_key': STATE_KEY.hex()}
    if allowlist is not None:
        config['advance_callers'] = allowlist
    path = tmp_path/'config.json'
    path.write_text(json.dumps(config))
    path.chmod(0o600)
    loaded = []

    class ConfigLoaded(Exception):
        pass

    def capture(witness, socket_path):
        loaded.append(witness)
        raise ConfigLoaded

    monkeypatch.setattr(transport_module, 'LocalWitnessUnixServer', capture)
    with pytest.raises(ConfigLoaded):
        transport_module.serve_config(path)
    for caller, key in keys.items():
        request = {'operation': 'advance', 'request_id': str(uuid4())}
        if caller in (allowlist or []):
            reply = loaded[0].advance_generation(caller_id=caller, request=request,
                mac=request_mac(key, caller, request))
            assert reply['body']['status'] == 'advanced'
        else:
            with pytest.raises(WitnessDenied, match='recovery administrator'):
                loaded[0].advance_generation(caller_id=caller, request=request,
                    mac=request_mac(key, caller, request))
    with sqlite3.connect(state) as db:
        assert db.execute('SELECT generation FROM witness_state').fetchone()[0] == 1 + len(allowlist or [])
        assert [row[0] for row in db.execute('SELECT caller_id FROM witness_events ORDER BY sequence')] == (allowlist or [])


@pytest.mark.skipif(not hasattr(socket, 'SO_PEERCRED'),
    reason='local peer credential transport requires Linux SO_PEERCRED')
def test_server_rejects_duplicate_rpc_fields_before_reservation(tmp_path):
    socket_dir = tmp_path/'private-socket'
    socket_dir.mkdir(mode=0o700)
    path = tmp_path/'state.sqlite3'
    witness = DurableLocalRecoveryWitness(path,
        caller_keys={CALLER:CALLER_KEY}, state_key=STATE_KEY, initialize=True)
    request = {'operation':'reserve','request_id':str(uuid4()),
        'ledger_id':str(uuid4()),'invocation_id':str(uuid4()),
        'intent_sha256':'c'*64}
    nonce = str(uuid4())
    mac = request_mac(CALLER_KEY, CALLER, request, exchange_nonce=nonce)
    valid = json.dumps({'caller_id': CALLER, 'caller_key_id': 'caller-v1',
        'request': request, 'exchange_nonce': nonce, 'mac': mac})
    frame = ('{"caller_id":'+json.dumps(CALLER)+','+valid[1:]+'\n').encode()
    with LocalWitnessUnixServer(witness, socket_dir/'witness.sock'):
        with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as connection:
            connection.settimeout(2)
            connection.connect(str(socket_dir/'witness.sock'))
            connection.sendall(frame)
            response = json.loads(transport_module._read_frame(connection).decode())
    assert response == {'error':'denied'}
    with sqlite3.connect(path) as db:
        assert db.execute('SELECT count(*) FROM reservations').fetchone()[0] == 0


@pytest.mark.skipif(not hasattr(socket, 'SO_PEERCRED'),
    reason='local peer credential transport requires Linux SO_PEERCRED')
def test_server_rejects_oversized_inbound_frame_before_reservation(tmp_path):
    socket_dir = tmp_path/'private-socket'
    socket_dir.mkdir(mode=0o700)
    path = tmp_path/'state.sqlite3'
    witness = DurableLocalRecoveryWitness(path,
        caller_keys={CALLER:CALLER_KEY}, state_key=STATE_KEY, initialize=True)
    with LocalWitnessUnixServer(witness, socket_dir/'witness.sock'):
        with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as connection:
            connection.settimeout(2)
            connection.connect(str(socket_dir/'witness.sock'))
            connection.sendall(b'x'*(transport_module._MAX_FRAME+1))
            connection.shutdown(socket.SHUT_WR)
            response = json.loads(transport_module._read_frame(connection).decode())
    assert response == {'error':'denied'}
    with sqlite3.connect(path) as db:
        assert db.execute('SELECT count(*) FROM reservations').fetchone()[0] == 0


@pytest.mark.skipif(not hasattr(socket, 'SO_PEERCRED'),
    reason='local peer credential transport requires Linux SO_PEERCRED')
def test_server_replaces_owned_stale_socket_path_only(tmp_path):
    directory = tmp_path/'private'
    directory.mkdir(mode=0o700)
    path = directory/'witness.sock'
    stale = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    stale.bind(str(path))
    stale.close()
    witness = DurableLocalRecoveryWitness(tmp_path/'state.sqlite3',
        caller_keys={CALLER: CALLER_KEY}, state_key=STATE_KEY, initialize=True)
    with LocalWitnessUnixServer(witness, path):
        client = UnixWitnessClient(path, caller_id=CALLER, key=CALLER_KEY)
        assert client.request({'operation':'generation'})['generation'] == 1


def test_server_refuses_to_replace_an_active_owned_socket(tmp_path):
    directory = tmp_path/'private'
    directory.mkdir(mode=0o700)
    path = directory/'witness.sock'
    first = DurableLocalRecoveryWitness(tmp_path/'first.sqlite3',
        caller_keys={CALLER: CALLER_KEY}, state_key=STATE_KEY, initialize=True)
    other = DurableLocalRecoveryWitness(tmp_path/'other.sqlite3',
        caller_keys={CALLER: CALLER_KEY}, state_key=STATE_KEY, initialize=True)
    with LocalWitnessUnixServer(first, path):
        original = path.lstat()
        before = (first.path.read_bytes(), other.path.read_bytes())
        second = LocalWitnessUnixServer(other, path)
        try:
            with pytest.raises(WitnessTransportDenied, match='active'):
                second.start()
        finally:
            second.close()
        current = path.lstat()
        assert (current.st_dev, current.st_ino) == (original.st_dev, original.st_ino)
        client = UnixWitnessClient(path, caller_id=CALLER, key=CALLER_KEY)
        assert client.request({'operation': 'generation'})['generation'] == 1
        assert (first.path.read_bytes(), other.path.read_bytes()) == before


@pytest.mark.parametrize('probe_error', [TimeoutError(), PermissionError(errno.EACCES, 'fixture denied')])
def test_server_does_not_unlink_socket_when_liveness_is_unknown(tmp_path, monkeypatch, probe_error):
    directory = tmp_path/'private'
    directory.mkdir(mode=0o700)
    path = directory/'witness.sock'
    witness = DurableLocalRecoveryWitness(tmp_path/'state.sqlite3',
        caller_keys={CALLER: CALLER_KEY}, state_key=STATE_KEY, initialize=True)
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as stale:
        stale.bind(str(path))
        before = path.lstat()

        class Probe:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                pass

            def settimeout(self, timeout):
                pass

            def connect(self, address):
                raise probe_error

        monkeypatch.setattr(transport_module.socket, 'socket', lambda *args: Probe())
        with pytest.raises(WitnessTransportDenied):
            LocalWitnessUnixServer(witness, path).start()
        after = path.lstat()
        assert (after.st_dev, after.st_ino) == (before.st_dev, before.st_ino)


def test_server_does_not_unlink_a_replacement_socket_after_stale_probe(tmp_path, monkeypatch):
    directory = tmp_path/'private'
    directory.mkdir(mode=0o700)
    path = directory/'witness.sock'
    witness = DurableLocalRecoveryWitness(tmp_path/'state.sqlite3',
        caller_keys={CALLER: CALLER_KEY}, state_key=STATE_KEY, initialize=True)
    real_socket = socket.socket
    with real_socket(socket.AF_UNIX, socket.SOCK_STREAM) as old:
        old.bind(str(path))
        before = path.lstat()
        with real_socket(socket.AF_UNIX, socket.SOCK_STREAM) as replacement:
            class Probe:
                def __enter__(self):
                    return self

                def __exit__(self, *args):
                    pass

                def settimeout(self, timeout):
                    pass

                def connect(self, address):
                    path.unlink()
                    replacement.bind(str(path))
                    raise ConnectionRefusedError(errno.ECONNREFUSED, 'fixture stale endpoint')

            monkeypatch.setattr(transport_module.socket, 'socket', lambda *args: Probe())
            with pytest.raises(WitnessTransportDenied):
                LocalWitnessUnixServer(witness, path).start()
            after = path.lstat()
            assert (after.st_dev, after.st_ino) != (before.st_dev, before.st_ino)
            assert path.exists()


def test_frame_receive_budget_does_not_restart_for_each_chunk(monkeypatch):
    clock = SimpleNamespace(now=0.0)
    monkeypatch.setattr(transport_module, 'time', SimpleNamespace(monotonic=lambda: clock.now), raising=False)

    class SlowStream:
        timeout = 1.0

        def __init__(self):
            self.chunks = iter([b'{"', b'status":', b'"current"}\n'])

        def gettimeout(self):
            return self.timeout

        def settimeout(self, value):
            self.timeout = value

        def recv(self, size):
            if self.timeout < 0.4:
                clock.now += self.timeout
                raise TimeoutError('fixture receive budget expired')
            clock.now += 0.4
            return next(self.chunks)

    with pytest.raises((WitnessTransportDenied, TimeoutError)):
        transport_module._read_frame(SlowStream())
    assert clock.now <= 1.0


def test_server_expires_partial_frame_without_mutation_and_serves_next_client(tmp_path, monkeypatch):
    monkeypatch.setattr(transport_module, '_FRAME_TIMEOUT', 0.05, raising=False)
    directory = tmp_path/'private'
    directory.mkdir(mode=0o700)
    path = directory/'witness.sock'
    witness = DurableLocalRecoveryWitness(tmp_path/'state.sqlite3',
        caller_keys={CALLER: CALLER_KEY}, state_key=STATE_KEY, initialize=True)
    with LocalWitnessUnixServer(witness, path):
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
            connection.settimeout(2)
            connection.connect(str(path))
            connection.sendall(b'{')
            assert json.loads(transport_module._read_frame(connection)) == {'error': 'denied'}
        client = UnixWitnessClient(path, caller_id=CALLER, key=CALLER_KEY)
        assert client.request({'operation': 'generation'})['generation'] == 1
        with sqlite3.connect(witness.path) as db:
            assert db.execute('SELECT count(*) FROM reservations').fetchone()[0] == 0
            assert db.execute('SELECT count(*) FROM witness_events').fetchone()[0] == 0


def test_connection_capacity_rejects_excess_and_recovers_after_handler_finishes(tmp_path, monkeypatch):
    monkeypatch.setattr(transport_module, '_MAX_CONNECTIONS', 1, raising=False)
    monkeypatch.setattr(transport_module, '_FRAME_TIMEOUT', 5.0)
    started, finished = threading.Event(), threading.Event()
    original_handle = LocalWitnessUnixServer._handle

    def observed_handle(self, connection):
        started.set()
        try:
            original_handle(self, connection)
        finally:
            finished.set()

    monkeypatch.setattr(LocalWitnessUnixServer, '_handle', observed_handle)
    directory = tmp_path/'private'
    directory.mkdir(mode=0o700)
    path = directory/'witness.sock'
    witness = DurableLocalRecoveryWitness(tmp_path/'state.sqlite3',
        caller_keys={CALLER: CALLER_KEY}, state_key=STATE_KEY, initialize=True)
    before = witness.path.read_bytes()
    with LocalWitnessUnixServer(witness, path):
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as first:
            first.settimeout(2)
            first.connect(str(path))
            first.sendall(b'{')
            assert started.wait(timeout=2), 'first connection did not enter the handler'
            client = UnixWitnessClient(path, caller_id=CALLER, key=CALLER_KEY)
            with pytest.raises(WitnessTransportDenied):
                client.request({'operation': 'generation'})
            first.sendall(b'}\n')
            assert json.loads(transport_module._read_frame(first)) == {'error': 'denied'}
            assert finished.wait(timeout=2), 'first handler did not release capacity'
        assert client.request({'operation': 'generation'})['generation'] == 1
    assert witness.path.read_bytes() == before


def test_failed_handler_thread_start_releases_connection_capacity(tmp_path, monkeypatch):
    monkeypatch.setattr(transport_module, '_MAX_CONNECTIONS', 1)
    directory = tmp_path/'private'
    directory.mkdir(mode=0o700)
    path = directory/'witness.sock'
    witness = DurableLocalRecoveryWitness(tmp_path/'state.sqlite3',
        caller_keys={CALLER: CALLER_KEY}, state_key=STATE_KEY, initialize=True)
    before = witness.path.read_bytes()
    real_thread = threading.Thread
    fail_next = True

    class FailedStart:
        def start(self):
            raise RuntimeError('fixture cannot start a handler thread')

    def create_thread(*args, **kwargs):
        nonlocal fail_next
        if fail_next:
            fail_next = False
            return FailedStart()
        return real_thread(*args, **kwargs)

    with LocalWitnessUnixServer(witness, path):
        monkeypatch.setattr(transport_module.threading, 'Thread', create_thread)
        client = UnixWitnessClient(path, caller_id=CALLER, key=CALLER_KEY)
        with pytest.raises(WitnessTransportDenied):
            client.request({'operation': 'generation'})
        assert client.request({'operation': 'generation'})['generation'] == 1
    assert witness.path.read_bytes() == before


def test_request_completed_after_server_close_does_not_create_a_reservation(tmp_path, monkeypatch):
    entered, finished = threading.Event(), threading.Event()
    original_handle = LocalWitnessUnixServer._handle

    def observed_handle(self, connection):
        entered.set()
        try:
            original_handle(self, connection)
        finally:
            finished.set()

    monkeypatch.setattr(LocalWitnessUnixServer, '_handle', observed_handle)
    directory = tmp_path/'private'
    directory.mkdir(mode=0o700)
    path = directory/'witness.sock'
    witness = DurableLocalRecoveryWitness(tmp_path/'state.sqlite3',
        caller_keys={CALLER: CALLER_KEY}, state_key=STATE_KEY, initialize=True)
    request = {'operation': 'reserve', 'request_id': str(uuid4()),
        'ledger_id': str(uuid4()), 'invocation_id': str(uuid4()),
        'intent_sha256': 'a' * 64}
    nonce = str(uuid4())
    frame = {'caller_id': CALLER, 'caller_key_id': 'caller-v1', 'request': request,
        'exchange_nonce': nonce,
        'mac': request_mac(CALLER_KEY, CALLER, request, exchange_nonce=nonce)}
    payload = json.dumps(frame).encode('ascii') + b'\n'
    before = witness.path.read_bytes()
    server = LocalWitnessUnixServer(witness, path).start()
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
            connection.settimeout(2)
            connection.connect(str(path))
            connection.sendall(payload[:1])
            assert entered.wait(timeout=2), 'connection was not accepted before close'
            server.close()
            assert not path.exists()
            connection.sendall(payload[1:])
            assert json.loads(transport_module._read_frame(connection)) == {'error': 'denied'}
            assert finished.wait(timeout=2), 'handler did not finish after denial'
    finally:
        server.close()
    assert witness.path.read_bytes() == before


@pytest.mark.parametrize('mode', ['wait', 'timeout'])
def test_close_waits_for_admitted_dispatch_or_reports_unknown(tmp_path, monkeypatch, mode):
    monkeypatch.setattr(transport_module, '_DRAIN_TIMEOUT', 0.05 if mode == 'timeout' else 2.0, raising=False)
    entered, release, closed = threading.Event(), threading.Event(), threading.Event()
    directory = tmp_path/'private'
    directory.mkdir(mode=0o700)
    path = directory/'witness.sock'
    witness = DurableLocalRecoveryWitness(tmp_path/'state.sqlite3',
        caller_keys={CALLER: CALLER_KEY}, state_key=STATE_KEY,
        advance_callers={CALLER}, initialize=True)
    original_advance = witness.advance_generation

    def paused_advance(**kwargs):
        entered.set()
        assert release.wait(timeout=5), 'fixture dispatch was not released'
        return original_advance(**kwargs)

    monkeypatch.setattr(witness, 'advance_generation', paused_advance)
    server = LocalWitnessUnixServer(witness, path).start()
    replies, errors = [], []

    def call():
        try:
            replies.append(UnixWitnessClient(path, caller_id=CALLER, key=CALLER_KEY).request(
                {'operation': 'advance', 'request_id': str(uuid4())}))
        except Exception as error:
            errors.append(error)

    def close():
        try:
            server.close()
        except Exception as error:
            errors.append(error)
        finally:
            closed.set()

    caller = threading.Thread(target=call, daemon=True)
    closer = None
    caller.start()
    try:
        assert entered.wait(timeout=2), 'request was not admitted'
        if mode == 'timeout':
            with pytest.raises(WitnessTransportDenied, match='in-flight'):
                server.close()
        else:
            closer = threading.Thread(target=close, daemon=True)
            closer.start()
            assert server._stop.wait(timeout=2)
            assert not closed.wait(timeout=0.5), 'close returned before admitted dispatch completed'
        with sqlite3.connect(witness.path) as db:
            assert db.execute('SELECT generation FROM witness_state').fetchone()[0] == 1
        release.set()
        caller.join(timeout=2)
        if closer is not None:
            closer.join(timeout=2)
            assert closed.is_set()
        assert not caller.is_alive()
        assert errors == []
        assert len(replies) == 1 and replies[0]['generation'] == 2
    finally:
        release.set()
        caller.join(timeout=2)
        if closer is not None:
            closer.join(timeout=2)
        server.close()
    with sqlite3.connect(witness.path) as db:
        assert db.execute('SELECT generation FROM witness_state').fetchone()[0] == 2
        assert db.execute('SELECT count(*) FROM generation_operations').fetchone()[0] == 1
        assert db.execute('SELECT count(*) FROM witness_events').fetchone()[0] == 1


def test_shutdown_rejects_dispatch_that_passed_the_early_stop_check(tmp_path):
    lookup, release = threading.Event(), threading.Event()
    directory = tmp_path/'private'
    directory.mkdir(mode=0o700)
    path = directory/'witness.sock'
    witness = DurableLocalRecoveryWitness(tmp_path/'state.sqlite3',
        caller_keys={CALLER: CALLER_KEY}, state_key=STATE_KEY,
        advance_callers={CALLER}, initialize=True)

    class PausedLookup:
        def __getattr__(self, name):
            if name == 'advance_generation':
                lookup.set()
                assert release.wait(timeout=5), 'fixture method lookup was not released'
            return getattr(witness, name)

    server = LocalWitnessUnixServer(PausedLookup(), path).start()
    outcomes = []

    def call():
        try:
            result = UnixWitnessClient(path, caller_id=CALLER, key=CALLER_KEY).request(
                {'operation': 'advance', 'request_id': str(uuid4())})
            outcomes.append(result)
        except WitnessTransportDenied:
            outcomes.append('denied')

    before = witness.path.read_bytes()
    caller = threading.Thread(target=call, daemon=True)
    caller.start()
    try:
        assert lookup.wait(timeout=2), 'handler did not pass the early stop check'
        server.close()
        release.set()
        caller.join(timeout=2)
        assert not caller.is_alive()
        assert outcomes == ['denied']
        assert witness.path.read_bytes() == before
    finally:
        release.set()
        caller.join(timeout=2)
        server.close()


@pytest.mark.skipif(not hasattr(socket, 'SO_PEERCRED'),
    reason='local peer credential transport requires Linux SO_PEERCRED')
@pytest.mark.parametrize('operation', ['reserve', 'consume', 'advance'])
def test_empty_mac_unknown_key_rpc_denies_before_commit(tmp_path, operation):
    path = tmp_path/'state.sqlite3'
    witness = DurableLocalRecoveryWitness(path, caller_keys={CALLER: CALLER_KEY},
        state_key=STATE_KEY, advance_callers={CALLER}, initialize=True)
    with TemporaryDirectory(prefix='witness-auth-') as private:
        socket_path = Path(private)/'w.sock'
        with LocalWitnessUnixServer(witness, socket_path):
            client = UnixWitnessClient(socket_path, caller_id=CALLER, key=CALLER_KEY)
            reserve = {'operation': 'reserve', 'request_id': str(uuid4()),
                'ledger_id': str(uuid4()), 'invocation_id': str(uuid4()),
                'intent_sha256': 'a'*64}
            permit = client.request(reserve)
            consume = {'operation': 'consume', **{name: permit[name] for name in
                ('request_id', 'ledger_id', 'invocation_id', 'intent_sha256',
                 'generation', 'state_key_id', 'nonce', 'ticket_mac')}}
            request = {'reserve': {**reserve, 'request_id': str(uuid4()),
                    'invocation_id': str(uuid4())}, 'consume': consume,
                'advance': {'operation': 'advance', 'request_id': str(uuid4())}}[operation]
            before = path.read_bytes()
            frame = {'caller_id': CALLER, 'caller_key_id': 'unknown-key',
                'request': request, 'exchange_nonce': str(uuid4()), 'mac': ''}
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
                connection.settimeout(2)
                connection.connect(str(socket_path))
                connection.sendall(json.dumps(frame).encode('ascii') + b'\n')
                assert json.loads(transport_module._read_frame(connection)) == {'error': 'denied'}
            assert path.read_bytes() == before
            assert client.request({'operation': 'generation'})['generation'] == 1
            assert client.request(consume)['status'] == 'spent'
    with sqlite3.connect(path) as db:
        assert db.execute('SELECT count(*) FROM reservations').fetchone()[0] == 1
        assert db.execute('SELECT event FROM witness_events ORDER BY sequence').fetchall() == [
            ('reserved',), ('consumed',)]


@pytest.mark.skipif(not hasattr(socket, 'SO_PEERCRED'),
    reason='local peer credential transport requires Linux SO_PEERCRED')
@pytest.mark.parametrize('operation', ['reserve', 'consume', 'advance'])
def test_retired_caller_key_empty_mac_cannot_mutate_after_process_restart(operation):
    with TemporaryDirectory(prefix='witness-retired-') as private:
        root = Path(private)
        state_path = root/'state'/'witness.sqlite3'
        old_key, new_key = CALLER_KEY, b'n'*32
        DurableLocalRecoveryWitness(state_path,
            caller_keys={CALLER: {'caller-v1': old_key, 'caller-v2': new_key}},
            current_caller_key_ids={CALLER: 'caller-v2'}, state_key=STATE_KEY,
            advance_callers={CALLER}, initialize=True)
        config = {'socket_path': str(root/'w.sock'), 'state_path': str(state_path),
            'caller_keyrings': {CALLER: {'caller-v1': old_key.hex(), 'caller-v2': new_key.hex()}},
            'current_caller_key_ids': {CALLER: 'caller-v2'},
            'advance_callers': [CALLER], 'state_key': STATE_KEY.hex()}
        config_path = root/'config.json'
        config_path.write_text(json.dumps(config)); config_path.chmod(0o600)
        old = UnixWitnessClient(config['socket_path'], caller_id=CALLER, key=old_key)
        reserve = {'operation': 'reserve', 'request_id': str(uuid4()),
            'ledger_id': str(uuid4()), 'invocation_id': str(uuid4()),
            'intent_sha256': 'b'*64}
        server = start_server(config_path)
        try:
            assert old.request({'operation': 'advance', 'request_id': str(uuid4())})['generation'] == 2
            permit = old.request(reserve)
        finally:
            stop_server(server)
        consume = {'operation': 'consume', **{name: permit[name] for name in
            ('request_id', 'ledger_id', 'invocation_id', 'intent_sha256',
             'generation', 'state_key_id', 'nonce', 'ticket_mac')}}
        config['caller_keyrings'] = {CALLER: {'caller-v2': new_key.hex()}}
        config_path.write_text(json.dumps(config)); config_path.chmod(0o600)
        server = start_server(config_path)
        try:
            before = state_path.read_bytes()
            with pytest.raises(WitnessTransportDenied):
                old.request({'operation': 'generation'})
            request = {'reserve': {**reserve, 'request_id': str(uuid4()),
                    'invocation_id': str(uuid4())}, 'consume': consume,
                'advance': {'operation': 'advance', 'request_id': str(uuid4())}}[operation]
            frame = {'caller_id': CALLER, 'caller_key_id': 'caller-v1',
                'request': request, 'exchange_nonce': str(uuid4()), 'mac': ''}
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
                connection.settimeout(2)
                connection.connect(config['socket_path'])
                connection.sendall(json.dumps(frame).encode('ascii') + b'\n')
                assert json.loads(transport_module._read_frame(connection)) == {'error': 'denied'}
            assert state_path.read_bytes() == before
            replacement = UnixWitnessClient(config['socket_path'], caller_id=CALLER,
                keys={'caller-v2': new_key}, current_key_id='caller-v2')
            assert replacement.request({'operation': 'generation'})['generation'] == 2
            assert replacement.request(consume)['status'] == 'spent'
        finally:
            stop_server(server)
        with sqlite3.connect(state_path) as db:
            assert db.execute('SELECT count(*) FROM reservations').fetchone()[0] == 1
            assert db.execute('SELECT generation FROM witness_state').fetchone()[0] == 2
            assert db.execute('SELECT event,caller_key_id FROM witness_events ORDER BY sequence').fetchall() == [
                ('generation_advanced', 'caller-v1'), ('reserved', 'caller-v1'),
                ('consumed', 'caller-v2')]
