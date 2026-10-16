"""Untrusted local RPC responses must be unambiguous before authentication."""
import json
import socket
import sqlite3
import tempfile
import threading
import unittest
from pathlib import Path
from uuid import uuid4

from durable_local_recovery_witness import DurableLocalRecoveryWitness, request_mac
from durable_local_witness_transport import UnixWitnessClient, WitnessTransportDenied


class WitnessResponseValidationTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.key = b'c' * 32
        self.caller = 'response-fixture'
        self.request = {'operation': 'generation'}
        self.witness = DurableLocalRecoveryWitness(self.root/'state'/'witness.sqlite3',
            caller_keys={self.caller: self.key}, state_key=b's' * 32, initialize=True)
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
                        connection.sendall(payload + b'\n')
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
        body = self.request_from_fixture_peer(json.dumps(self.response).encode('ascii'))
        self.assertEqual(body, {'generation': 1, 'status': 'current'})

    def test_rejects_duplicate_response_fields_even_when_last_value_has_valid_mac(self):
        raw = json.dumps(self.response)
        payloads = {
            'body': '{"body":{},' + raw[1:],
            'key_id': '{"key_id":"retired",' + raw[1:],
            'mac': '{"mac":"invalid",' + raw[1:],
            'request_mac': '{"request_mac":"invalid",' + raw[1:],
            'nested_generation': raw.replace('"generation": 1', '"generation": 999, "generation": 1'),
        }
        for label, payload in payloads.items():
            with self.subTest(field=label):
                with self.assertRaises(WitnessTransportDenied):
                    self.request_from_fixture_peer(payload.encode('ascii'))

    def test_rejects_authenticated_response_for_another_operation(self):
        self.request = {'operation': 'advance', 'request_id': str(uuid4())}
        with self.assertRaises(WitnessTransportDenied):
            self.request_from_fixture_peer(json.dumps(self.response).encode('ascii'))

    def test_rejects_other_consumed_ticket_response_while_current_ticket_is_pending(self):
        def reserve():
            request = {'operation': 'reserve', 'request_id': str(uuid4()),
                'ledger_id': str(uuid4()), 'invocation_id': str(uuid4()),
                'intent_sha256': 'a' * 64}
            reply = self.witness.reserve(caller_id=self.caller, request=request,
                mac=request_mac(self.key, self.caller, request))
            ticket = reply['body']
            return {'operation': 'consume', **{key: ticket[key] for key in
                ('request_id', 'ledger_id', 'invocation_id', 'intent_sha256',
                 'generation', 'state_key_id', 'nonce', 'ticket_mac')}}

        first = reserve()
        captured = self.witness.consume(caller_id=self.caller, request=first,
            mac=request_mac(self.key, self.caller, first))
        self.request = reserve()
        with self.assertRaises(WitnessTransportDenied):
            self.request_from_fixture_peer(json.dumps(captured).encode('ascii'))

        with sqlite3.connect(self.witness.path) as db:
            rows = dict(db.execute('SELECT invocation_id, consumed FROM reservations'))
        self.assertEqual(rows, {first['invocation_id']: 1, self.request['invocation_id']: 0})

    def test_rejects_binding_tampering_without_a_new_response_mac(self):
        self.response['request_mac'] = '0' * 64
        with self.assertRaises(WitnessTransportDenied):
            self.request_from_fixture_peer(json.dumps(self.response).encode('ascii'))

    def test_rejects_response_for_another_caller_even_when_keys_are_reused(self):
        self.caller = 'other-caller-with-same-fixture-key'
        with self.assertRaises(WitnessTransportDenied):
            self.request_from_fixture_peer(json.dumps(self.response).encode('ascii'))

    def test_rejects_legacy_response_without_request_binding(self):
        self.response.pop('request_mac', None)
        with self.assertRaises(WitnessTransportDenied):
            self.request_from_fixture_peer(json.dumps(self.response).encode('ascii'))


if __name__ == '__main__':
    unittest.main()
