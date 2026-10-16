"""Process-boundary checks for authenticated local Unix-socket witness RPC."""
import json
import os
import socket
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
import json, sys
from durable_local_witness_transport import UnixWitnessClient
from durable_local_recovery_witness import WitnessDenied
from durable_local_witness_transport import WitnessTransportDenied
config=json.load(open(sys.argv[1]))
client=UnixWitnessClient(config['socket_path'], caller_id='socket-fixture-caller', key=b'u'*32)
invocation, ledger, digest, mode=sys.argv[2:]
if mode == 'reserve-consume':
    request={'operation':'reserve','request_id':invocation,'ledger_id':ledger,
        'invocation_id':invocation,'intent_sha256':digest}
    first=client.request(request)
    retry=client.request(request)
    assert first == retry
    consume={'operation':'consume',**{key:first[key] for key in
        ('request_id','ledger_id','invocation_id','intent_sha256','generation','nonce')},
        'ticket_mac':first['ticket_mac']}
    result=client.request(consume)
    print(json.dumps({'first':first,'retry':retry,'consumed':result},sort_keys=True))
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
    config = {'socket_path': str(socket_dir/'witness.sock'),
        'state_path': str(state_path), 'caller_keys': {CALLER: CALLER_KEY.hex()},
        'state_key': STATE_KEY.hex()}
    config_path = tmp_path/'server-config.json'
    config_path.write_text(json.dumps(config))
    config_path.chmod(0o600)
    config_path.parent.chmod(0o700)
    invocation, ledger, digest = str(uuid4()), str(uuid4()), 'd'*64
    args = [sys.executable, '-c', client_program(), str(config_path),
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
        wrong_key = subprocess.run(args+['wrong-key'], capture_output=True,
            text=True, env=client_env, timeout=10)
        assert wrong_key.returncode == 0, wrong_key.stderr
        assert wrong_key.stdout.strip() == 'denied'
    finally:
        stop_server(server)

    unavailable = UnixWitnessClient(config['socket_path'], caller_id=CALLER,
        key=CALLER_KEY, timeout=0.1)
    with pytest.raises(WitnessTransportDenied, match='unavailable'):
        unavailable.request({'operation':'generation'})

    restarted = start_server(config_path)
    try:
        retry = subprocess.run(args+['retry-consumed'], capture_output=True,
            text=True, env=client_env, timeout=10)
        assert retry.returncode == 0, retry.stderr
        assert retry.stdout.strip() == 'denied'
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
