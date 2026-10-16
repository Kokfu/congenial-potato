"""Process-boundary checks for authenticated local Unix-socket witness RPC."""
import json
import os
import socket
import sqlite3
import subprocess
import sys
import time
from pathlib import Path
from uuid import uuid4

import pytest

from durable_local_recovery_witness import (DurableLocalRecoveryWitness,
    request_mac)
import durable_local_witness_transport as transport_module
from durable_local_witness_transport import (LocalWitnessUnixServer,
    UnixWitnessClient, WitnessTransportDenied)

CALLER = 'socket-fixture-caller'
CALLER_KEY = b'u' * 32
STATE_KEY = b'v' * 32


def start_server(config_path):
    source_dir = Path(transport_module.__file__).parent
    server_script = source_dir/'run_durable_local_witness_server.py'
    env = dict(os.environ)
    env['PYTHONPATH'] = str(source_dir) + os.pathsep + env.get('PYTHONPATH', '')
    socket_path = json.loads(config_path.read_text())['socket_path']
    try:
        old_socket = Path(socket_path).lstat()
    except FileNotFoundError:
        old_socket = None
    if old_socket is not None:
        import stat
        if not stat.S_ISSOCK(old_socket.st_mode) or old_socket.st_uid != os.getuid():
            raise AssertionError('unexpected stale witness socket type or owner')
        Path(socket_path).unlink()
    process = subprocess.Popen([sys.executable, str(server_script), str(config_path)],
        env=env, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        if process.poll() is not None:
            _, error = process.communicate(timeout=2)
            raise AssertionError(f'local witness server exited during startup: {error}')
        if Path(socket_path).exists():
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
from pathlib import Path
from durable_local_witness_transport import UnixWitnessClient
from durable_local_recovery_witness import WitnessDenied
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
    invocation, ledger, digest = str(uuid4()), str(uuid4()), 'e'*64
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
    DurableLocalRecoveryWitness(state_path,
        caller_keys={CALLER:CALLER_KEY}, state_key=STATE_KEY, initialize=True)
    config = {'socket_path':str(socket_dir/'witness.sock'),
        'state_path':str(state_path), 'caller_keys':{CALLER:CALLER_KEY.hex()},
        'state_key':STATE_KEY.hex()}
    config_path = tmp_path/'server-config.json'
    config_path.write_text(json.dumps(config))
    config_path.chmod(0o600)
    start_signal = tmp_path/'start-consume-race'
    ready_dir = tmp_path/'ready-clients'
    ready_dir.mkdir(mode=0o700)
    ticket_path = tmp_path/'pending-ticket.json'
    client_config_path = tmp_path/'client-config.json'
    client_config = {'socket_path':config['socket_path'],
        'ticket_path':str(ticket_path),'start_file':str(start_signal),
        'ready_dir':str(ready_dir)}
    client_config_path.write_text(json.dumps(client_config))
    client_config_path.chmod(0o600)
    args = [sys.executable,'-c',client_program(),str(client_config_path)]
    client_env = dict(os.environ)
    client_env['PYTHONPATH'] = str(Path(transport_module.__file__).parent) + os.pathsep + client_env.get('PYTHONPATH','')
    invocation, ledger, digest = str(uuid4()), str(uuid4()), 'f'*64
    server = start_server(config_path)
    clients = []
    try:
        reserve = subprocess.run(args+[invocation,ledger,digest,'reserve-only'],
            capture_output=True,text=True,env=client_env,timeout=10)
        assert reserve.returncode == 0, reserve.stderr
        ticket_path.write_text(reserve.stdout)
        ticket_path.chmod(0o600)
        clients = [subprocess.Popen(args+[invocation,ledger,digest,'consume-race'],
            stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,env=client_env)
            for _ in range(2)]
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
        with sqlite3.connect(state_path) as db:
            assert db.execute("SELECT count(*) FROM witness_events "
                "WHERE event='consumed'").fetchone()[0] == 1
    finally:
        for client in clients:
            if client.poll() is None:
                client.terminate()
                client.wait(timeout=2)
        stop_server(server)


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
