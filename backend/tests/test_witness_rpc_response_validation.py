"""Untrusted local RPC responses must be unambiguous before authentication."""
import json
import socket
import sqlite3
import tempfile
import threading
import unittest
from pathlib import Path
from uuid import uuid4

from durable_local_recovery_witness import DurableLocalRecoveryWitness, WitnessDenied, request_mac
from durable_local_witness_transport import (
    LocalWitnessUnixServer, UnixWitnessClient, WitnessTransportDenied, _read_frame,
)


class WitnessResponseValidationTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.key = b'c' * 32
        self.caller = 'response-fixture'
        self.request = {'operation': 'generation'}
        self.witness = DurableLocalRecoveryWitness(self.root/'state'/'witness.sqlite3',
            caller_keys={self.caller: self.key}, state_key=b's' * 32,
            advance_callers={self.caller}, initialize=True)
        self.response = self.witness.generation(caller_id=self.caller, request=self.request,
            mac=request_mac(self.key, self.caller, self.request))

    def request_from_fixture_peer(self, payload):
        path = self.root/'response.sock'
        errors = []
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as listener:
            listener.bind(str(path))
            listener.listen(1)
            listener.settimeout(2)

            def respond():
                try:
                    connection, _ = listener.accept()
                    with connection:
                        connection.settimeout(2)
                        data = bytearray()
                        while b'\n' not in data:
                            chunk = connection.recv(4096)
                            if not chunk:
                                raise AssertionError('client did not send a complete request')
                            data.extend(chunk)
                        reply = payload(json.loads(data)) if callable(payload) else payload
                        connection.sendall(reply + b'\n')
                except Exception as error:
                    errors.append(error)

            peer = threading.Thread(target=respond, daemon=True)
            peer.start()
            try:
                return UnixWitnessClient(path, caller_id=self.caller,
                    key=self.key, timeout=2).request(self.request)
            finally:
                peer.join(timeout=3)
                self.assertFalse(peer.is_alive(), 'fixture peer did not finish')
                self.assertEqual(errors, [])
                path.unlink()

    def test_accepts_unambiguous_authenticated_response(self):
        body = self.request_from_fixture_peer(lambda frame:
            json.dumps(self.generation_response(frame)).encode('ascii'))
        self.assertEqual(body, {'generation': 1, 'status': 'current'})

    def generation_response(self, frame):
        request = {'operation': 'generation'}
        caller = 'response-fixture'
        nonce = frame['exchange_nonce']
        return self.witness.generation(caller_id=caller, request=request,
            mac=request_mac(self.key, caller, request, exchange_nonce=nonce),
            exchange_nonce=nonce)

    def test_rejects_duplicate_response_fields_even_when_last_value_has_valid_mac(self):
        transforms = {
            'body': lambda raw: '{"body":{},' + raw[1:],
            'key_id': lambda raw: '{"key_id":"retired",' + raw[1:],
            'mac': lambda raw: '{"mac":"invalid",' + raw[1:],
            'request_mac': lambda raw: '{"request_mac":"invalid",' + raw[1:],
            'nested_generation': lambda raw: raw.replace('"generation": 1', '"generation": 999, "generation": 1'),
        }
        for label, transform in transforms.items():
            with self.subTest(field=label):
                with self.assertRaises(WitnessTransportDenied):
                    self.request_from_fixture_peer(lambda frame:
                        transform(json.dumps(self.generation_response(frame))).encode('ascii'))

    def test_rejects_authenticated_response_for_another_operation(self):
        self.request = {'operation': 'advance', 'request_id': str(uuid4())}
        with self.assertRaises(WitnessTransportDenied):
            self.request_from_fixture_peer(lambda frame:
                json.dumps(self.generation_response(frame)).encode('ascii'))

    def reserve_consume_request(self):
        request = {'operation': 'reserve', 'request_id': str(uuid4()),
            'ledger_id': str(uuid4()), 'invocation_id': str(uuid4()),
            'intent_sha256': 'a' * 64}
        reply = self.witness.reserve(caller_id=self.caller, request=request,
            mac=request_mac(self.key, self.caller, request))
        ticket = reply['body']
        return {'operation': 'consume', **{key: ticket[key] for key in
            ('request_id', 'ledger_id', 'invocation_id', 'intent_sha256',
             'generation', 'state_key_id', 'nonce', 'ticket_mac')}}

    def test_rejects_other_consumed_ticket_response_while_current_ticket_is_pending(self):
        first = self.reserve_consume_request()
        self.request = self.reserve_consume_request()

        def captured(frame):
            nonce = frame['exchange_nonce']
            reply = self.witness.consume(caller_id=self.caller, request=first,
                mac=request_mac(self.key, self.caller, first, exchange_nonce=nonce),
                exchange_nonce=nonce)
            return json.dumps(reply).encode('ascii')

        with self.assertRaises(WitnessTransportDenied):
            self.request_from_fixture_peer(captured)

        with sqlite3.connect(self.witness.path) as db:
            rows = dict(db.execute('SELECT invocation_id, consumed FROM reservations'))
        self.assertEqual(rows, {first['invocation_id']: 1, self.request['invocation_id']: 0})

    def test_rejects_binding_tampering_without_a_new_response_mac(self):
        def tampered(frame):
            reply = self.generation_response(frame)
            reply['request_mac'] = '0' * 64
            return json.dumps(reply).encode('ascii')
        with self.assertRaises(WitnessTransportDenied):
            self.request_from_fixture_peer(tampered)

    def test_rejects_response_for_another_caller_even_when_keys_are_reused(self):
        self.caller = 'other-caller-with-same-fixture-key'
        with self.assertRaises(WitnessTransportDenied):
            self.request_from_fixture_peer(lambda frame:
                json.dumps(self.generation_response(frame)).encode('ascii'))

    def test_rejects_legacy_response_without_request_binding(self):
        def legacy(frame):
            reply = self.generation_response(frame)
            reply.pop('request_mac')
            return json.dumps(reply).encode('ascii')
        with self.assertRaises(WitnessTransportDenied):
            self.request_from_fixture_peer(legacy)

    def test_rejects_captured_response_for_identical_request_after_generation_advances(self):
        advance = {'operation': 'advance', 'request_id': str(uuid4())}
        current = self.witness.advance_generation(caller_id=self.caller, request=advance,
            mac=request_mac(self.key, self.caller, advance))
        self.assertEqual(current['body']['generation'], 2)
        self.assertEqual(self.response['body']['generation'], 1)
        with self.assertRaises(WitnessTransportDenied):
            self.request_from_fixture_peer(json.dumps(self.response).encode('ascii'))

    def test_rejects_captured_spent_reply_on_a_new_exchange_for_the_same_consume(self):
        self.request = self.reserve_consume_request()
        captured = []
        frames = []

        def consume(frame):
            frames.append(frame)
            reply = self.witness.consume(caller_id=self.caller, request=self.request,
                mac=frame['mac'], exchange_nonce=frame['exchange_nonce'])
            captured.append(reply)
            return json.dumps(reply).encode('ascii')

        self.assertEqual(self.request_from_fixture_peer(consume)['status'], 'spent')

        def replay(frame):
            frames.append(frame)
            return json.dumps(captured[0]).encode('ascii')

        with self.assertRaises(WitnessTransportDenied):
            self.request_from_fixture_peer(replay)
        self.assertEqual(frames[0]['request'], frames[1]['request'])
        self.assertNotEqual(frames[0]['exchange_nonce'], frames[1]['exchange_nonce'])
        self.assertNotEqual(frames[0]['mac'], frames[1]['mac'])
        with self.assertRaisesRegex(WitnessDenied, 'consumed'):
            self.witness.consume(caller_id=self.caller, request=self.request,
                mac=frames[1]['mac'], exchange_nonce=frames[1]['exchange_nonce'])
        with sqlite3.connect(self.witness.path) as db:
            self.assertEqual(db.execute("SELECT count(*) FROM witness_events WHERE event='consumed'").fetchone(), (1,))

    def test_fresh_exchange_reservation_retries_return_the_same_ticket(self):
        self.request = {'operation': 'reserve', 'request_id': str(uuid4()),
            'ledger_id': str(uuid4()), 'invocation_id': str(uuid4()),
            'intent_sha256': 'a' * 64}
        frames, replies = [], []

        def reserve(frame):
            frames.append(frame)
            reply = self.witness.reserve(caller_id=self.caller, request=self.request,
                mac=frame['mac'], exchange_nonce=frame['exchange_nonce'])
            replies.append(reply)
            return json.dumps(reply).encode('ascii')

        first = self.request_from_fixture_peer(reserve)
        second = self.request_from_fixture_peer(reserve)
        self.assertEqual(first, second)
        self.assertNotEqual(frames[0]['exchange_nonce'], frames[1]['exchange_nonce'])
        self.assertNotEqual(replies[0]['mac'], replies[1]['mac'])
        with sqlite3.connect(self.witness.path) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM reservations').fetchone(), (1,))
            self.assertEqual(db.execute('SELECT count(*) FROM witness_events').fetchone(), (1,))

    def test_server_rejects_bad_exchange_nonce_frames_before_reservation(self):
        request = {'operation': 'reserve', 'request_id': str(uuid4()),
            'ledger_id': str(uuid4()), 'invocation_id': str(uuid4()),
            'intent_sha256': 'a' * 64}
        nonce = str(uuid4())
        frame = {'caller_id': self.caller, 'caller_key_id': 'caller-v1',
            'request': request, 'exchange_nonce': nonce,
            'mac': request_mac(self.key, self.caller, request, exchange_nonce=nonce)}
        missing = dict(frame)
        missing.pop('exchange_nonce')
        frames = {'missing': missing,
            'null': {**frame, 'exchange_nonce': None},
            'integer': {**frame, 'exchange_nonce': 1},
            'malformed': {**frame, 'exchange_nonce': 'not-a-uuid'},
            'noncanonical': {**frame, 'exchange_nonce': nonce.replace('-', '')},
            'tampered': {**frame, 'exchange_nonce': str(uuid4())},
            'legacy_mac': {**frame, 'mac': request_mac(self.key, self.caller, request)}}
        path = self.root/'server.sock'
        with LocalWitnessUnixServer(self.witness, path):
            for label, bad in frames.items():
                with self.subTest(frame=label):
                    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
                        connection.settimeout(2)
                        connection.connect(str(path))
                        connection.sendall(json.dumps(bad).encode('ascii') + b'\n')
                        self.assertEqual(json.loads(_read_frame(connection)), {'error': 'denied'})
                    with sqlite3.connect(self.witness.path) as db:
                        self.assertEqual(db.execute('SELECT count(*) FROM reservations').fetchone(), (0,))
                        self.assertEqual(db.execute('SELECT count(*) FROM witness_events').fetchone(), (0,))


if __name__ == '__main__':
    unittest.main()
