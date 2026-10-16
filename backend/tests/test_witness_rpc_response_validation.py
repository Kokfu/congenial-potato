"""Untrusted local RPC responses must be unambiguous before authentication."""
import json
import socket
import tempfile
import threading
import unittest
from pathlib import Path

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
        witness = DurableLocalRecoveryWitness(self.root/'state'/'witness.sqlite3',
            caller_keys={self.caller: self.key}, state_key=b's' * 32, initialize=True)
        self.response = witness.generation(caller_id=self.caller, request=self.request,
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
        body = json.dumps(self.response['body'])
        key_id = json.dumps(self.response['key_id'])
        mac = json.dumps(self.response['mac'])
        payloads = {
            'body': '{"body":{},"body":%s,"key_id":%s,"mac":%s}' % (body, key_id, mac),
            'key_id': '{"body":%s,"key_id":"retired","key_id":%s,"mac":%s}' % (body, key_id, mac),
            'mac': '{"body":%s,"key_id":%s,"mac":"invalid","mac":%s}' % (body, key_id, mac),
            'nested_generation': '{"body":{"generation":999,"generation":1,"status":"current"},"key_id":%s,"mac":%s}' % (key_id, mac),
        }
        for label, payload in payloads.items():
            with self.subTest(field=label):
                with self.assertRaises(WitnessTransportDenied):
                    self.request_from_fixture_peer(payload.encode('ascii'))


if __name__ == '__main__':
    unittest.main()
