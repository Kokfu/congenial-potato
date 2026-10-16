"""Private Unix-socket RPC prototype; test-only and same-host only."""
import json
import os
import socket
import socketserver
import stat
import struct
import threading
from pathlib import Path

from durable_local_recovery_witness import (DurableLocalRecoveryWitness,
    WitnessDenied, request_mac, verify_response)

_MAX_FRAME = 16 * 1024


class WitnessTransportDenied(ConnectionError):
    """Transport, peer, framing, or authenticated response failed closed."""


def _json_bytes(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':')).encode('ascii')


def _read_frame(connection):
    data = bytearray()
    while len(data) <= _MAX_FRAME:
        chunk = connection.recv(min(4096, _MAX_FRAME + 1 - len(data)))
        if not chunk:
            break
        newline = chunk.find(b'\n')
        if newline >= 0:
            data.extend(chunk[:newline])
            if len(data) > _MAX_FRAME:
                break
            return bytes(data)
        data.extend(chunk)
    raise WitnessTransportDenied('witness transport frame unavailable')


class UnixWitnessClient:
    """Authenticated fixture client. No TCP/IP connection is opened."""
    def __init__(self, socket_path, *, caller_id, key=None, keys=None,
                 current_key_id='caller-v1', timeout=2):
        if type(key) is bytes and keys is None:
            keys = {'caller-v1': key}
        if (type(caller_id) is not str or not caller_id or not isinstance(keys, dict) or
                not keys or any(type(key_id) is not str or not key_id or
                type(value) is not bytes or len(value) != 32 for key_id, value in keys.items()) or
                current_key_id not in keys):
            raise WitnessTransportDenied('witness client identity unavailable')
        self.socket_path = str(socket_path)
        self.caller_id, self.keys, self.current_key_id, self.timeout = caller_id, dict(keys), current_key_id, timeout

    def request(self, request):
        if type(request) is not dict:
            raise WitnessTransportDenied('witness request unavailable')
        key = self.keys[self.current_key_id]
        frame = {'caller_id': self.caller_id, 'caller_key_id': self.current_key_id,
                 'request': request,
                 'mac': request_mac(key, self.caller_id, request, self.current_key_id)}
        payload = _json_bytes(frame) + b'\n'
        if len(payload) > _MAX_FRAME:
            raise WitnessTransportDenied('witness transport frame unavailable')
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
                connection.settimeout(self.timeout)
                connection.connect(self.socket_path)
                connection.sendall(payload)
                response = json.loads(_read_frame(connection).decode('ascii'))
        except WitnessTransportDenied:
            raise
        except (OSError, UnicodeError, json.JSONDecodeError, TimeoutError):
            raise WitnessTransportDenied('witness transport unavailable') from None
        if type(response) is not dict or set(response) == {'error'}:
            raise WitnessTransportDenied('witness request denied or response unavailable')
        try:
            return verify_response(key, response, self.current_key_id)
        except WitnessDenied:
            raise WitnessTransportDenied('witness response authentication failed') from None


class _UnixHandler(socketserver.BaseRequestHandler):
    def handle(self):
        connection = self.request
        try:
            if not hasattr(socket, 'SO_PEERCRED'):
                raise WitnessTransportDenied('peer credentials unavailable')
            raw = connection.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED,
                                        struct.calcsize('3i'))
            _, peer_uid, _ = struct.unpack('3i', raw)
            if peer_uid != self.server.allowed_uid:
                raise WitnessTransportDenied('peer identity unavailable')
            envelope = json.loads(_read_frame(connection).decode('ascii'))
            if (type(envelope) is not dict or set(envelope) != {'caller_id','caller_key_id','request','mac'} or
                    type(envelope['caller_id']) is not str or type(envelope['request']) is not dict):
                raise WitnessTransportDenied('witness request unavailable')
            operation = envelope['request'].get('operation')
            methods = {'generation': self.server.witness.generation,
                       'reserve': self.server.witness.reserve,
                       'consume': self.server.witness.consume,
                       'advance': self.server.witness.advance_generation}
            method = methods.get(operation)
            if method is None:
                raise WitnessDenied('witness request unavailable')
            response = method(caller_id=envelope['caller_id'], request=envelope['request'],
                              mac=envelope['mac'], caller_key_id=envelope['caller_key_id'])
        except (WitnessDenied, WitnessTransportDenied, OSError, UnicodeError,
                json.JSONDecodeError, ValueError, KeyError, TypeError):
            response = {'error': 'denied'}
        try:
            connection.sendall(_json_bytes(response) + b'\n')
        except OSError:
            pass


class LocalWitnessUnixServer:
    """Single-host socket server with private path and kernel peer-UID check."""
    def __init__(self, witness: DurableLocalRecoveryWitness, socket_path):
        self.witness = witness
        self.socket_path = Path(socket_path)
        self.allowed_uid = os.getuid()
        self._stop = threading.Event()
        self._socket = None
        self._thread = None
        self._socket_identity = None

    def start(self):
        parent = self.socket_path.parent
        info = parent.lstat()
        if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or
                stat.S_IMODE(info.st_mode) != 0o700):
            raise WitnessTransportDenied('private witness socket directory required')
        try:
            existing = self.socket_path.lstat()
        except FileNotFoundError:
            existing = None
        if existing is not None:
            if (not stat.S_ISSOCK(existing.st_mode) or existing.st_uid != os.getuid()):
                raise WitnessTransportDenied('witness socket path unavailable')
            self.socket_path.unlink()
        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            server.bind(str(self.socket_path))
            os.chmod(self.socket_path, 0o600, follow_symlinks=False)
            bound = self.socket_path.lstat()
            self._socket_identity = (bound.st_dev, bound.st_ino)
            server.listen(32)
            server.settimeout(0.2)
        except OSError:
            server.close()
            raise WitnessTransportDenied('witness socket unavailable') from None
        self._socket = server
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._thread.start()
        return self

    def _serve(self):
        while not self._stop.is_set():
            try:
                connection, _ = self._socket.accept()
            except TimeoutError:
                continue
            except OSError:
                return
            thread = threading.Thread(target=self._handle, args=(connection,), daemon=True)
            thread.start()

    def _handle(self, connection):
        with connection:
            _UnixHandler(connection, ('local', 0), self)

    def close(self):
        self._stop.set()
        if self._socket is not None:
            self._socket.close()
        if self._thread is not None:
            self._thread.join(timeout=2)
        try:
            info = self.socket_path.lstat()
            if (stat.S_ISSOCK(info.st_mode) and
                    (info.st_dev, info.st_ino) == self._socket_identity):
                self.socket_path.unlink()
        except FileNotFoundError:
            pass

    def __enter__(self):
        return self.start()

    def __exit__(self, exc_type, exc, traceback):
        self.close()


def serve_config(path):
    """Load synthetic fixture keys from a private config and serve until stopped."""
    config_path = Path(path)
    info = config_path.lstat()
    if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or
            stat.S_IMODE(info.st_mode) != 0o600):
        raise WitnessTransportDenied('private witness config required')
    config = json.loads(config_path.read_text())
    if 'caller_keyrings' in config:
        caller_keys = {name: {key_id: bytes.fromhex(value) for key_id, value in keys.items()}
                       for name, keys in config['caller_keyrings'].items()}
        current_caller_key_ids = config['current_caller_key_ids']
    else:
        caller_keys = {name: bytes.fromhex(value) for name, value in config['caller_keys'].items()}
        current_caller_key_ids = None
    witness_config = {
        'caller_keys': caller_keys,
        'current_caller_key_ids': current_caller_key_ids,
        'advance_callers': frozenset(config.get('advance_callers', [])),
    }
    if 'state_keys' in config:
        witness_config['state_keys'] = {name: bytes.fromhex(value)
                                        for name, value in config['state_keys'].items()}
        witness_config['current_state_key_id'] = config['current_state_key_id']
    else:
        witness_config['state_key'] = bytes.fromhex(config['state_key'])
    witness = DurableLocalRecoveryWitness(config['state_path'], **witness_config)
    server = LocalWitnessUnixServer(witness, config['socket_path']).start()
    try:
        while True:
            threading.Event().wait(3600)
    finally:
        server.close()

