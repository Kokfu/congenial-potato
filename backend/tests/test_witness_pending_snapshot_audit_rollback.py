"""Replaceable witness audit history is not independent rollback evidence."""
import shutil
import sqlite3
import tempfile
import unittest
from pathlib import Path
from uuid import uuid4

from durable_local_recovery_witness import (
    DurableLocalRecoveryWitness, WitnessDenied, request_mac, verify_response,
)


class PendingSnapshotAuditRollbackTests(unittest.TestCase):
    def test_exact_consumed_ticket_replays_and_recreates_identical_audit_history(self):
        caller = 'audit-rollback-drill'
        caller_key = b'c' * 32
        state_key = b's' * 32

        def authenticated(method, request):
            mac = request_mac(caller_key, caller, request)
            envelope = method(caller_id=caller, request=request,
                mac=mac)
            verify_response(caller_key, envelope, expected_request_mac=mac)
            return envelope

        def audit_rows(path):
            with sqlite3.connect(path) as db:
                return db.execute('SELECT * FROM witness_events ORDER BY sequence').fetchall()

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root/'witness'/'witness.sqlite3'
            witness = DurableLocalRecoveryWitness(path,
                caller_keys={caller: caller_key}, state_key=state_key, initialize=True)
            reserve = {'operation': 'reserve', 'request_id': str(uuid4()),
                'ledger_id': str(uuid4()), 'invocation_id': str(uuid4()),
                'intent_sha256': 'a' * 64}
            permit = verify_response(caller_key, authenticated(witness.reserve, reserve))
            consume = {'operation': 'consume', **{key: permit[key] for key in
                ('request_id', 'ledger_id', 'invocation_id', 'intent_sha256',
                 'generation', 'state_key_id', 'nonce', 'ticket_mac')}}

            # Snapshot a pending ticket, retaining its exact nonce and MAC.
            pending = root/'pending.sqlite3'
            shutil.copy2(path, pending)
            reserved_history = audit_rows(path)
            self.assertEqual([row[1] for row in reserved_history], ['reserved'])
            first_reply = authenticated(witness.consume, consume)
            self.assertEqual(verify_response(caller_key, first_reply)['status'], 'spent')
            first_history = audit_rows(path)
            self.assertEqual([row[0] for row in first_history], [1, 2])
            self.assertEqual([row[1] for row in first_history], ['reserved', 'consumed'])

            # A normal reopen retains denial and the committed audit rows.
            del witness
            witness = DurableLocalRecoveryWitness(path,
                caller_keys={caller: caller_key}, state_key=state_key)
            with self.assertRaisesRegex(WitnessDenied, 'consumed'):
                authenticated(witness.consume, consume)
            self.assertEqual(audit_rows(path), first_history)

            # Replace the entire local file after all operations have returned.
            del witness
            shutil.copy2(pending, path)
            restored = DurableLocalRecoveryWitness(path,
                caller_keys={caller: caller_key}, state_key=state_key)
            self.assertEqual(audit_rows(path), reserved_history)
            with sqlite3.connect(path) as db:
                self.assertEqual(db.execute('SELECT consumed FROM reservations').fetchone(), (0,))

            # The exact old ticket succeeds again without a new reservation.
            second_reply = authenticated(restored.consume, consume)
            self.assertEqual(second_reply, first_reply)
            self.assertEqual(audit_rows(path), first_history)
            with sqlite3.connect(path) as db:
                self.assertEqual(db.execute('SELECT consumed FROM reservations').fetchone(), (1,))


if __name__ == '__main__':
    unittest.main()
