"""Untrusted local RPC responses must be unambiguous before authentication."""
import json
import socket
import sqlite3
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from uuid import uuid4
from unittest.mock import patch

from durable_local_recovery_witness import (
    DurableLocalRecoveryWitness, WitnessDenied, request_mac, verify_response,
)
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

    def test_deep_response_json_maps_to_transport_denial(self):
        depth = 6000
        payload = b'[' * depth + b'0' + b']' * depth
        self.assertLess(len(payload), 16 * 1024)
        with self.assertRaises(WitnessTransportDenied):
            self.request_from_fixture_peer(payload)

    def test_decoder_recursion_failure_maps_to_transport_denial(self):
        payload = json.dumps(self.response).encode('ascii')
        with patch('durable_local_witness_transport.json.loads',
                side_effect=RecursionError('fixture decoder recursion failure')):
            with self.assertRaises(WitnessTransportDenied):
                self.request_from_fixture_peer(payload)

    def test_large_integer_decode_failure_maps_to_transport_denial(self):
        limit = sys.get_int_max_str_digits()
        if not limit:
            self.skipTest('interpreter integer-string limit is disabled')
        payload = b'9' * (limit + 100)
        self.assertLess(len(payload), 16 * 1024)
        with self.assertRaises(WitnessTransportDenied):
            self.request_from_fixture_peer(payload)

    def test_nonfinite_response_numbers_reject_even_with_valid_fixture_mac(self):
        numbers = [('nan', float('nan'), None),
            ('infinity', float('inf'), None), ('negative_infinity', float('-inf'), None),
            ('exponent_overflow', float('inf'), '1e999'),
            ('negative_exponent_overflow', float('-inf'), '-1e999')]
        for label, value, replacement in numbers:
            def payload(frame):
                reply = DurableLocalRecoveryWitness._envelope(self.key,
                    {'generation': value, 'status': 'current'}, request_binding=frame['mac'])
                raw = json.dumps(reply)
                if replacement is not None:
                    raw = raw.replace('-Infinity' if value < 0 else 'Infinity', replacement)
                return raw.encode('ascii')

            with self.subTest(number=label):
                with self.assertRaises(WitnessTransportDenied):
                    self.request_from_fixture_peer(payload)

    def test_deep_request_json_is_denied_without_mutation_and_service_continues(self):
        depth = 6000
        payload = b'[' * depth + b'0' + b']' * depth + b'\n'
        self.assertLess(len(payload), 16 * 1024)
        path = self.root/'nested.sock'
        before = self.witness.path.read_bytes()
        with LocalWitnessUnixServer(self.witness, path):
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
                connection.settimeout(2)
                connection.connect(str(path))
                connection.sendall(payload)
                self.assertEqual(json.loads(_read_frame(connection)), {'error': 'denied'})
            client = UnixWitnessClient(path, caller_id=self.caller, key=self.key)
            self.assertEqual(client.request(self.request)['generation'], 1)
        self.assertEqual(self.witness.path.read_bytes(), before)

    def signed_body(self, frame, body):
        reply = DurableLocalRecoveryWitness._envelope(self.key, body,
            request_binding=frame['mac'])
        return json.dumps(reply).encode('ascii')

    def test_authenticated_generation_bodies_require_exact_fields_and_integer_generation(self):
        bodies = {
            'missing_generation': {'status': 'current'},
            'missing_status': {'generation': 1},
            'extra_field': {'status': 'current', 'generation': 1, 'extra': True},
            'wrong_status': {'status': 'spent', 'generation': 1},
            'boolean_generation': {'status': 'current', 'generation': True},
            'float_generation': {'status': 'current', 'generation': 1.0},
            'zero_generation': {'status': 'current', 'generation': 0},
            'overflow_generation': {'status': 'current', 'generation': 2**63},
        }
        for label, body in bodies.items():
            with self.subTest(body=label):
                with self.assertRaises(WitnessTransportDenied):
                    self.request_from_fixture_peer(lambda frame: self.signed_body(frame, body))

    def test_authenticated_reservation_bodies_require_echoes_and_ticket_shape(self):
        self.request = {'operation': 'reserve', 'request_id': str(uuid4()),
            'ledger_id': str(uuid4()), 'invocation_id': str(uuid4()),
            'intent_sha256': 'a' * 64}
        updates = {'request_id': {'request_id': str(uuid4())},
            'ledger_id': {'ledger_id': str(uuid4())},
            'invocation_id': {'invocation_id': str(uuid4())},
            'intent': {'intent_sha256': 'b' * 64},
            'nonce': {'nonce': 'not-a-uuid'}, 'ticket_mac': {'ticket_mac': 'not-a-mac'},
            'state_key': {'state_key_id': ''}, 'state_key_surrogate': {'state_key_id': '\ud800'},
            'status': {'status': 'spent'},
            'extra': {'extra': True}, 'missing': {}}
        for label, update in updates.items():
            def payload(frame):
                reply = self.witness.reserve(caller_id=self.caller, request=self.request,
                    mac=frame['mac'], exchange_nonce=frame['exchange_nonce'])
                body = {**reply['body'], **update}
                if label == 'missing':
                    body.pop('state_key_id')
                return self.signed_body(frame, body)

            with self.subTest(body=label):
                with self.assertRaises(WitnessTransportDenied):
                    self.request_from_fixture_peer(payload)
        with sqlite3.connect(self.witness.path) as db:
            self.assertEqual(db.execute('SELECT count(*), sum(consumed) FROM reservations').fetchone(), (1, 0))
            self.assertEqual(db.execute('SELECT count(*) FROM witness_events').fetchone(), (1,))

    def test_authenticated_consume_bodies_require_exact_echoes_and_status(self):
        self.request = self.reserve_consume_request()
        base = {'status': 'spent', 'generation': self.request['generation'],
            'request_id': self.request['request_id'], 'invocation_id': self.request['invocation_id']}
        updates = {'request_id': {'request_id': str(uuid4())},
            'invocation_id': {'invocation_id': str(uuid4())},
            'generation': {'generation': base['generation'] + 1},
            'status': {'status': 'reserved'}, 'extra': {'extra': True}, 'missing': {}}
        for label, update in updates.items():
            body = {**base, **update}
            if label == 'missing':
                body.pop('request_id')
            with self.subTest(body=label):
                with self.assertRaises(WitnessTransportDenied):
                    self.request_from_fixture_peer(lambda frame: self.signed_body(frame, body))
        with sqlite3.connect(self.witness.path) as db:
            self.assertEqual(db.execute('SELECT sum(consumed) FROM reservations').fetchone(), (0,))

    def test_historical_advance_body_is_valid_but_wrong_request_id_is_not(self):
        self.request = {'operation': 'advance', 'request_id': str(uuid4())}
        first = self.witness.advance_generation(caller_id=self.caller, request=self.request,
            mac=request_mac(self.key, self.caller, self.request))
        later = {'operation': 'advance', 'request_id': str(uuid4())}
        self.witness.advance_generation(caller_id=self.caller, request=later,
            mac=request_mac(self.key, self.caller, later))

        def historical(frame):
            reply = self.witness.advance_generation(caller_id=self.caller, request=self.request,
                mac=frame['mac'], exchange_nonce=frame['exchange_nonce'])
            return json.dumps(reply).encode('ascii')

        self.assertEqual(self.request_from_fixture_peer(historical)['generation'], 2)
        bad = {**first['body'], 'request_id': str(uuid4())}
        with self.assertRaises(WitnessTransportDenied):
            self.request_from_fixture_peer(lambda frame: self.signed_body(frame, bad))
        with sqlite3.connect(self.witness.path) as db:
            self.assertEqual(db.execute('SELECT generation FROM witness_state').fetchone(), (3,))
            self.assertEqual(db.execute('SELECT count(*) FROM witness_events').fetchone(), (2,))

    def test_active_verification_requires_both_complete_request_expectations(self):
        expectations = [
            {'expected_request_mac': self.response['request_mac']},
            {'expected_request': self.request},
            {'expected_request_mac': 'é' * 64, 'expected_request': self.request},
        ]
        for expected in expectations:
            with self.subTest(expectation=tuple(expected)):
                with self.assertRaises(WitnessDenied):
                    verify_response(self.key, self.response, **expected)
        self.assertEqual(verify_response(self.key, self.response), self.response['body'])

    def test_client_rejects_invalid_unicode_and_unhashable_identity_config(self):
        configs = []
        for bad in ('\ud800', '\udfff'):
            configs.append({'caller_id': bad, 'key': self.key})
            configs.append({'caller_id': self.caller, 'keys': {bad: self.key}, 'current_key_id': bad})
        configs.append({'caller_id': self.caller, 'key': self.key, 'current_key_id': []})
        path = self.root/'unused.sock'
        for index, config in enumerate(configs):
            with self.subTest(config=index):
                with self.assertRaises(WitnessTransportDenied):
                    UnixWitnessClient(path, **config)
        self.assertFalse(path.exists())

    def test_response_verifier_rejects_invalid_expected_key_identity(self):
        for index, bad in enumerate(('\ud800', '\udfff', [])):
            with self.subTest(identity=index):
                reply = {**self.response, 'key_id': bad}
                with self.assertRaises(WitnessDenied):
                    verify_response(self.key, reply, bad)

    def test_valid_unicode_client_identities_round_trip_over_local_socket(self):
        caller, key_id, state_id = 'RPC-😀', 'caller-鍵', 'state-🔐'
        witness = DurableLocalRecoveryWitness(self.root/'unicode'/'state.sqlite3',
            caller_keys={caller: {key_id: self.key}}, current_caller_key_ids={caller: key_id},
            state_keys={state_id: b's' * 32}, current_state_key_id=state_id, initialize=True)
        path = self.root/'unicode.sock'
        with LocalWitnessUnixServer(witness, path):
            client = UnixWitnessClient(path, caller_id=caller, keys={key_id: self.key}, current_key_id=key_id)
            request = {'operation': 'reserve', 'request_id': str(uuid4()),
                'ledger_id': str(uuid4()), 'invocation_id': str(uuid4()), 'intent_sha256': 'a' * 64}
            ticket = client.request(request)
            self.assertEqual(ticket['state_key_id'], state_id)
            consume = {'operation': 'consume', **{key: ticket[key] for key in
                ('request_id', 'ledger_id', 'invocation_id', 'intent_sha256',
                 'generation', 'state_key_id', 'nonce', 'ticket_mac')}}
            self.assertEqual(client.request(consume)['status'], 'spent')
        with sqlite3.connect(witness.path) as db:
            self.assertEqual(db.execute('SELECT caller_id, caller_key_id FROM witness_events').fetchall(),
                [(caller, key_id), (caller, key_id)])


if __name__ == '__main__':
    unittest.main()
