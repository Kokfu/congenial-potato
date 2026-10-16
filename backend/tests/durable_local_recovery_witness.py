"""Durable local protocol prototype; never a production trust anchor.

The file-backed SQLite state is deliberately separate from the application and
fake-ledger fixtures. It models protocol ordering across process restarts only.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import sqlite3
import stat
from pathlib import Path
from uuid import UUID, uuid4


_REQUEST_DOMAIN = b'workforce.synthetic.write.witness.request.v1\0'
_EXCHANGE_REQUEST_DOMAIN = b'workforce.synthetic.write.witness.exchange.request.v1\0'
_RESPONSE_DOMAIN = b'workforce.synthetic.write.witness.response.v2\0'
_TICKET_DOMAIN = b'workforce.synthetic.write.witness.ticket.v1\0'
_MAX_GENERATION = 2**63 - 1


class WitnessDenied(ValueError):
    """Fail-closed response for invalid, unavailable, or conflicting state."""


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'),
                      ensure_ascii=True).encode('ascii')


def _identity(value, label):
    try:
        if type(value) is not str or str(UUID(value)) != value:
            raise ValueError
        return value
    except (ValueError, TypeError, AttributeError):
        raise WitnessDenied(f'witness {label} unavailable') from None


def _digest(value):
    if type(value) is not str or re.fullmatch(r'[0-9a-f]{64}', value) is None:
        raise WitnessDenied('witness intent unavailable')
    return value


def request_mac(key: bytes, caller_id: str, request: dict, key_id='caller-v1', *, exchange_nonce=None) -> str:
    """Fixture client helper. Callers must keep the key outside request data."""
    domain, message = _REQUEST_DOMAIN, request
    if exchange_nonce is not None:
        _identity(exchange_nonce, 'exchange nonce')
        domain = _EXCHANGE_REQUEST_DOMAIN
        message = {'exchange_nonce': exchange_nonce, 'request': request}
    return hmac.digest(key, domain + caller_id.encode() + b'\0' + key_id.encode() + b'\0' +
                       _canonical(message), 'sha256').hex()


def verify_response(key: bytes, envelope: dict, key_id='caller-v1', *, expected_request_mac=None) -> dict:
    """Authenticate a response; callers with an outstanding request must bind it."""
    if type(envelope) is not dict or set(envelope) != {'body', 'key_id', 'request_mac', 'mac'} or envelope['key_id'] != key_id:
        raise WitnessDenied('witness response unavailable')
    body, mac = envelope['body'], envelope['mac']
    if type(body) is not dict or type(mac) is not str or re.fullmatch(r'[0-9a-f]{64}', mac) is None:
        raise WitnessDenied('witness response unavailable')
    binding = envelope['request_mac']
    if type(binding) is not str or re.fullmatch(r'[0-9a-f]{64}', binding) is None:
        raise WitnessDenied('witness response binding unavailable')
    message = {'body': body, 'request_mac': binding}
    expected = hmac.digest(key, _RESPONSE_DOMAIN + key_id.encode() + b'\0' + _canonical(message), 'sha256').hex()
    if not hmac.compare_digest(expected, mac):
        raise WitnessDenied('witness response authentication failed')
    if expected_request_mac is not None and (type(expected_request_mac) is not str or
            not hmac.compare_digest(binding, expected_request_mac)):
        raise WitnessDenied('witness response request binding failed')
    return body


class DurableLocalRecoveryWitness:
    """SQLite-backed protocol fixture with caller authentication and atomic state."""

    def __init__(self, path, *, caller_keys: dict[str, bytes],
                 current_caller_key_ids: dict[str, str] | None = None,
                 state_key: bytes | None = None,
                 state_keys: dict[str, bytes] | None = None,
                 current_state_key_id='state-v1', advance_callers=frozenset(), initialize=False):
        self.path = Path(path)
        if state_keys is None and type(state_key) is bytes:
            state_keys = {'state-v1': state_key}
        if not isinstance(caller_keys, dict) or not caller_keys:
            raise WitnessDenied('witness key configuration unavailable')
        caller_keyrings = {}
        for name, keys in caller_keys.items():
            if type(name) is not str or not name:
                raise WitnessDenied('witness key configuration unavailable')
            keys = {'caller-v1': keys} if type(keys) is bytes else keys
            if (not isinstance(keys, dict) or not keys or
                    any(type(key_id) is not str or not key_id or type(key) is not bytes or len(key) != 32
                        for key_id, key in keys.items())):
                raise WitnessDenied('witness key configuration unavailable')
            caller_keyrings[name] = dict(keys)
        if current_caller_key_ids is None:
            current_caller_key_ids = {name: 'caller-v1' for name in caller_keyrings}
        if (not isinstance(current_caller_key_ids, dict) or
                set(current_caller_key_ids) != set(caller_keyrings) or
                any(type(key_id) is not str or key_id not in caller_keyrings[name]
                    for name, key_id in current_caller_key_ids.items()) or
                not isinstance(state_keys, dict) or not state_keys or
                any(type(key_id) is not str or not key_id or type(key) is not bytes or len(key) != 32
                    for key_id, key in state_keys.items()) or
                type(current_state_key_id) is not str or current_state_key_id not in state_keys or
                not isinstance(advance_callers, (set, frozenset)) or
                any(type(name) is not str or name not in caller_keyrings for name in advance_callers)):
            raise WitnessDenied('witness key configuration unavailable')
        self._caller_keys = caller_keyrings
        self._current_caller_key_ids = dict(current_caller_key_ids)
        self._state_keys = dict(state_keys)
        self._current_state_key_id = current_state_key_id
        self._advance_callers = frozenset(advance_callers)
        self._available = True
        if initialize:
            self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            self._validate_private_path(allow_missing=True)
            self.path.touch(mode=0o600, exist_ok=False)
            self._validate_private_path()
            with self._connect() as db:
                db.executescript('''
                    CREATE TABLE witness_state (
                        singleton INTEGER PRIMARY KEY CHECK(singleton=1),
                        generation INTEGER NOT NULL CHECK(generation BETWEEN 1 AND 9223372036854775807)
                    );
                    INSERT INTO witness_state(singleton,generation) VALUES(1,1);
                    CREATE TABLE reservations (
                        request_id TEXT PRIMARY KEY,
                        caller_id TEXT NOT NULL,
                        ledger_id TEXT NOT NULL,
                        invocation_id TEXT NOT NULL UNIQUE,
                        intent_sha256 TEXT NOT NULL,
                        generation INTEGER NOT NULL,
                        state_key_id TEXT NOT NULL,
                        nonce TEXT NOT NULL,
                        ticket_mac TEXT NOT NULL,
                        consumed INTEGER NOT NULL DEFAULT 0 CHECK(consumed IN (0,1))
                    );
                    CREATE TABLE witness_events (
                        sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                        event TEXT NOT NULL,
                        generation INTEGER NOT NULL,
                        request_id TEXT,
                        invocation_id TEXT,
                        binding_sha256 TEXT NOT NULL,
                        caller_id TEXT NOT NULL,
                        caller_key_id TEXT NOT NULL,
                        state_key_id TEXT
                    );
                    CREATE TABLE generation_operations (
                        request_id TEXT PRIMARY KEY,
                        caller_id TEXT NOT NULL,
                        generation INTEGER NOT NULL
                    );
                ''')
        else:
            try:
                with self._connect() as db:
                    state = db.execute('SELECT generation FROM witness_state WHERE singleton=1').fetchone()
                    if (state is None or type(state['generation']) is not int or
                            not 1 <= state['generation'] <= _MAX_GENERATION):
                        raise WitnessDenied('witness state unavailable')
                    db.execute('SELECT request_id,caller_id,caller_key_id,state_key_id '
                        'FROM witness_events LIMIT 0')
                    db.execute('SELECT request_id,caller_id,generation,state_key_id,consumed '
                        'FROM reservations LIMIT 0')
                    db.execute('SELECT request_id,caller_id,generation '
                        'FROM generation_operations LIMIT 0')
            except (sqlite3.Error, OSError):
                raise WitnessDenied('witness state unavailable') from None

    def _validate_private_path(self, allow_missing=False):
        try:
            parent = self.path.parent.lstat()
            if (not stat.S_ISDIR(parent.st_mode) or parent.st_uid != os.getuid() or
                    stat.S_IMODE(parent.st_mode) != 0o700):
                raise WitnessDenied('private witness state directory required')
            try:
                info = self.path.lstat()
            except FileNotFoundError:
                if allow_missing:
                    return
                raise WitnessDenied('witness state unavailable') from None
            if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or
                    stat.S_IMODE(info.st_mode) != 0o600):
                raise WitnessDenied('private witness state file required')
        except OSError:
            raise WitnessDenied('witness state unavailable') from None

    def set_available(self, value):
        if type(value) is not bool:
            raise WitnessDenied('witness availability unavailable')
        self._available = value

    def _connect(self):
        self._validate_private_path()
        db = sqlite3.connect(self.path, timeout=2, isolation_level=None)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        return db

    def _authenticate(self, caller_id, request, mac, caller_key_id='caller-v1', *, exchange_nonce=None):
        if self._available is not True:
            raise WitnessDenied('witness unavailable')
        key = self._caller_keys.get(caller_id, {}).get(caller_key_id) if type(caller_id) is str and type(caller_key_id) is str else None
        expected = request_mac(key, caller_id, request, caller_key_id,
            exchange_nonce=exchange_nonce) if key else ''
        if type(mac) is not str or not hmac.compare_digest(expected, mac):
            raise WitnessDenied('witness caller authentication failed')
        return key

    @staticmethod
    def _envelope(key, body, key_id='caller-v1', *, request_binding):
        message = {'body': body, 'request_mac': request_binding}
        mac = hmac.digest(key, _RESPONSE_DOMAIN + key_id.encode() + b'\0' + _canonical(message), 'sha256').hex()
        return {**message, 'key_id': key_id, 'mac': mac}

    def _ticket_mac(self, generation, ledger_id, invocation_id, intent_sha256, nonce,
                    state_key_id):
        state_key = self._state_keys.get(state_key_id)
        if state_key is None:
            raise WitnessDenied('witness state key unavailable')
        body = {'generation': generation, 'ledger_id': ledger_id,
                'invocation_id': invocation_id, 'intent_sha256': intent_sha256,
                'nonce': nonce, 'state_key_id': state_key_id}
        return hmac.digest(state_key, _TICKET_DOMAIN + _canonical(body), 'sha256').hex()

    def _record(self, db, event, generation, request_id, invocation_id, binding,
                caller_id, caller_key_id, state_key_id=None):
        db.execute('INSERT INTO witness_events(event,generation,request_id,invocation_id,binding_sha256,caller_id,caller_key_id,state_key_id) '
                   'VALUES(?,?,?,?,?,?,?,?)', (event, generation, request_id, invocation_id,
                       hashlib.sha256(_canonical(binding)).hexdigest(), caller_id,
                       caller_key_id, state_key_id))

    def generation(self, *, caller_id, request, mac, caller_key_id='caller-v1', exchange_nonce=None):
        key = self._authenticate(caller_id, request, mac, caller_key_id, exchange_nonce=exchange_nonce)
        if request != {'operation': 'generation'}:
            raise WitnessDenied('witness request unavailable')
        try:
            with self._connect() as db:
                row = db.execute('SELECT generation FROM witness_state WHERE singleton=1').fetchone()
                if row is None:
                    raise WitnessDenied('witness state unavailable')
                return self._envelope(key, {'generation': row['generation'], 'status': 'current'}, caller_key_id,
                    request_binding=mac)
        except (sqlite3.Error, OSError):
            raise WitnessDenied('witness state unavailable') from None

    def reserve(self, *, caller_id, request, mac, caller_key_id='caller-v1', exchange_nonce=None):
        key = self._authenticate(caller_id, request, mac, caller_key_id, exchange_nonce=exchange_nonce)
        if type(request) is not dict or set(request) != {'operation','request_id','ledger_id','invocation_id','intent_sha256'} or request.get('operation') != 'reserve':
            raise WitnessDenied('witness request unavailable')
        request_id = _identity(request['request_id'], 'request identity')
        ledger_id = _identity(request['ledger_id'], 'ledger identity')
        invocation_id = _identity(request['invocation_id'], 'invocation identity')
        intent_sha256 = _digest(request['intent_sha256'])
        binding = (ledger_id, invocation_id, intent_sha256)
        try:
            with self._connect() as db:
                db.execute('BEGIN IMMEDIATE')
                state = db.execute('SELECT generation FROM witness_state WHERE singleton=1').fetchone()
                if state is None:
                    raise WitnessDenied('witness state unavailable')
                generation = state['generation']
                old = db.execute('SELECT * FROM reservations WHERE request_id=?', (request_id,)).fetchone()
                if old:
                    if old['caller_id'] != caller_id or (old['ledger_id'],old['invocation_id'],old['intent_sha256']) != binding or old['consumed']:
                        raise WitnessDenied('witness reservation conflict or consumed invocation')
                    body = self._reservation_body(old)
                    db.commit()
                    return self._envelope(key, body, caller_key_id, request_binding=mac)
                by_invocation = db.execute('SELECT * FROM reservations WHERE invocation_id=?', (invocation_id,)).fetchone()
                if by_invocation:
                    if by_invocation['consumed']:
                        raise WitnessDenied('witness invocation already consumed or unknown')
                    raise WitnessDenied('witness invocation already reserved')
                nonce = str(uuid4())
                state_key_id = self._current_state_key_id
                ticket_mac = self._ticket_mac(generation, ledger_id, invocation_id,
                    intent_sha256, nonce, state_key_id)
                db.execute('INSERT INTO reservations(request_id,caller_id,ledger_id,invocation_id,intent_sha256,generation,state_key_id,nonce,ticket_mac) VALUES(?,?,?,?,?,?,?,?,?)',
                           (request_id,caller_id,ledger_id,invocation_id,intent_sha256,
                            generation,state_key_id,nonce,ticket_mac))
                self._record(db, 'reserved', generation, request_id, invocation_id, binding,
                    caller_id, caller_key_id, state_key_id)
                row = db.execute('SELECT * FROM reservations WHERE request_id=?', (request_id,)).fetchone()
                body = self._reservation_body(row)
                db.commit()
                return self._envelope(key, body, caller_key_id, request_binding=mac)
        except WitnessDenied:
            raise
        except (sqlite3.Error, OSError):
            raise WitnessDenied('witness state unavailable') from None

    @staticmethod
    def _reservation_body(row):
        return {'status': 'spent' if row['consumed'] else 'reserved',
                'generation': row['generation'], 'request_id': row['request_id'],
                'ledger_id': row['ledger_id'], 'invocation_id': row['invocation_id'],
                'intent_sha256': row['intent_sha256'], 'state_key_id': row['state_key_id'],
                'nonce': row['nonce'],
                'ticket_mac': row['ticket_mac']}

    def consume(self, *, caller_id, request, mac, caller_key_id='caller-v1', exchange_nonce=None):
        key = self._authenticate(caller_id, request, mac, caller_key_id, exchange_nonce=exchange_nonce)
        expected_fields = {'operation','request_id','ledger_id','invocation_id',
            'intent_sha256','generation','state_key_id','nonce','ticket_mac'}
        if type(request) is not dict or set(request) != expected_fields or request.get('operation') != 'consume':
            raise WitnessDenied('witness request unavailable')
        request_id = _identity(request['request_id'], 'request identity')
        ledger_id = _identity(request['ledger_id'], 'ledger identity')
        invocation_id = _identity(request['invocation_id'], 'invocation identity')
        intent_sha256 = _digest(request['intent_sha256'])
        if type(request['generation']) is not int or not 1 <= request['generation'] <= _MAX_GENERATION:
            raise WitnessDenied('witness generation unavailable')
        _identity(request['nonce'], 'nonce')
        try:
            with self._connect() as db:
                db.execute('BEGIN IMMEDIATE')
                row = db.execute('SELECT * FROM reservations WHERE request_id=?', (request_id,)).fetchone()
                state = db.execute('SELECT generation FROM witness_state WHERE singleton=1').fetchone()
                if row is None or state is None:
                    raise WitnessDenied('witness reservation unavailable')
                binding = (ledger_id,invocation_id,intent_sha256)
                if type(request['state_key_id']) is not str or not request['state_key_id']:
                    raise WitnessDenied('witness state key unavailable')
                valid_ticket = self._ticket_mac(row['generation'], row['ledger_id'],
                    row['invocation_id'], row['intent_sha256'], row['nonce'],
                    row['state_key_id'])
                if ((row['caller_id'] != caller_id) or
                    (row['ledger_id'],row['invocation_id'],row['intent_sha256']) != binding or
                    row['generation'] != request['generation'] or row['generation'] != state['generation'] or
                    row['state_key_id'] != request['state_key_id'] or row['nonce'] != request['nonce'] or
                    type(request['ticket_mac']) is not str or
                    not hmac.compare_digest(row['ticket_mac'], request['ticket_mac']) or
                    not hmac.compare_digest(valid_ticket, row['ticket_mac'])):
                    raise WitnessDenied('witness ticket binding unavailable')
                if row['consumed']:
                    raise WitnessDenied('witness invocation already consumed or unknown')
                db.execute('UPDATE reservations SET consumed=1 WHERE request_id=? AND consumed=0', (request_id,))
                self._record(db, 'consumed', row['generation'], request_id, invocation_id,
                    binding, caller_id, caller_key_id, row['state_key_id'])
                db.commit()
                body = {'status': 'spent', 'generation': row['generation'],
                        'request_id': request_id, 'invocation_id': invocation_id}
                return self._envelope(key, body, caller_key_id, request_binding=mac)
        except WitnessDenied:
            raise
        except (sqlite3.Error, OSError):
            raise WitnessDenied('witness state unavailable') from None

    def advance_generation(self, *, caller_id, request, mac, caller_key_id='caller-v1', exchange_nonce=None):
        key = self._authenticate(caller_id, request, mac, caller_key_id, exchange_nonce=exchange_nonce)
        if caller_id not in self._advance_callers:
            raise WitnessDenied('witness recovery administrator unavailable')
        if (type(request) is not dict or set(request) != {'operation','request_id'} or
                request.get('operation') != 'advance'):
            raise WitnessDenied('witness request unavailable')
        request_id = _identity(request['request_id'], 'generation operation identity')
        try:
            with self._connect() as db:
                db.execute('BEGIN IMMEDIATE')
                previous = db.execute('SELECT * FROM generation_operations WHERE request_id=?',
                    (request_id,)).fetchone()
                if previous is not None:
                    if previous['caller_id'] != caller_id:
                        raise WitnessDenied('witness generation operation conflict')
                    db.commit()
                    return self._envelope(key, {'generation': previous['generation'],
                        'request_id': request_id, 'status': 'advanced'}, caller_key_id, request_binding=mac)
                row = db.execute('SELECT generation FROM witness_state WHERE singleton=1').fetchone()
                if row is None or row['generation'] >= _MAX_GENERATION:
                    raise WitnessDenied('witness generation unavailable')
                generation = row['generation'] + 1
                db.execute('UPDATE witness_state SET generation=? WHERE singleton=1', (generation,))
                db.execute('INSERT INTO generation_operations VALUES (?,?,?)',
                    (request_id, caller_id, generation))
                self._record(db, 'generation_advanced', generation, request_id, None,
                    {'request_id': request_id, 'generation': generation},
                    caller_id, caller_key_id)
                db.commit()
                return self._envelope(key, {'generation': generation,
                    'request_id': request_id, 'status': 'advanced'}, caller_key_id, request_binding=mac)
        except WitnessDenied:
            raise
        except (sqlite3.Error, OSError):
            raise WitnessDenied('witness state unavailable') from None

