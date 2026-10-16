"""Protocol-shape checks; importing no application DB or external service."""
import unittest
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

from synthetic_write_recovery_witness import (RecoveryWitnessDenied,
    SimulatedMonotonicRecoveryWitness)

KEY = b'r' * 32
LEDGER = str(uuid4())
INVOCATION = str(uuid4())
INTENT = '1' * 64


def ticket(witness, **changes):
    values = {'ledger_id': LEDGER, 'invocation_id': INVOCATION,
        'intent_sha256': INTENT}
    values.update(changes)
    return witness.issue(**values)


def consume(witness, permit, **changes):
    values = {'ledger_id': LEDGER, 'invocation_id': INVOCATION,
        'intent_sha256': INTENT}
    values.update(changes)
    return witness.consume(permit, **values)


class RecoveryWitnessTests(unittest.TestCase):
    def test_ticket_is_bound_to_current_generation_and_exact_intent(self):
        witness = SimulatedMonotonicRecoveryWitness(KEY)
        permit = ticket(witness)
        self.assertTrue(consume(witness, permit))
        with self.assertRaisesRegex(RecoveryWitnessDenied, 'already consumed'):
            consume(witness, ticket(witness))
        other = ticket(witness, invocation_id=str(uuid4()))
        with self.assertRaisesRegex(RecoveryWitnessDenied, 'binding'):
            consume(witness, other)

    def test_stale_generation_is_denied_and_consumed_identity_survives_epoch_advance(self):
        witness = SimulatedMonotonicRecoveryWitness(KEY)
        stale = ticket(witness)
        self.assertEqual(witness.advance_generation(), 2)
        with self.assertRaisesRegex(RecoveryWitnessDenied, 'binding'):
            consume(witness, stale)
        fresh = ticket(witness)
        self.assertTrue(consume(witness, fresh))
        witness.advance_generation()
        with self.assertRaisesRegex(RecoveryWitnessDenied, 'already consumed'):
            consume(witness, ticket(witness))

    def test_unavailable_witness_fails_closed_for_issue_and_consume(self):
        witness = SimulatedMonotonicRecoveryWitness(KEY)
        permit = ticket(witness)
        witness.set_available(False)
        with self.assertRaisesRegex(RecoveryWitnessDenied, 'unavailable'):
            ticket(witness)
        with self.assertRaisesRegex(RecoveryWitnessDenied, 'unavailable'):
            consume(witness, permit)

    def test_lost_issue_reply_can_retry_before_identity_is_consumed(self):
        witness = SimulatedMonotonicRecoveryWitness(KEY)
        lost = ticket(witness)  # response is lost before any consume request
        retry = ticket(witness)
        self.assertEqual(retry, lost)  # idempotent reservation identity
        self.assertTrue(consume(witness, retry))

    def test_lost_consume_reply_keeps_identity_unknown_and_denies_new_ticket(self):
        witness = SimulatedMonotonicRecoveryWitness(KEY)
        permit = ticket(witness)
        witness.consume(permit, ledger_id=LEDGER, invocation_id=INVOCATION,
            intent_sha256=INTENT)  # response is lost; caller cannot infer no effect
        with self.assertRaisesRegex(RecoveryWitnessDenied, 'already consumed'):
            consume(witness, ticket(witness))

    def test_simulator_restart_erases_state_and_reopens_identity(self):
        first = SimulatedMonotonicRecoveryWitness(KEY)
        consume(first, ticket(first))
        restarted = SimulatedMonotonicRecoveryWitness(KEY)
        # Demonstrates why this process-local object cannot be the external anchor.
        self.assertTrue(consume(restarted, ticket(restarted)))

    def test_concurrent_tickets_consume_one_invocation_once(self):
        witness = SimulatedMonotonicRecoveryWitness(KEY)
        permits = [ticket(witness), ticket(witness)]
        barrier = Barrier(2)
        def attempt(permit):
            barrier.wait(timeout=3)
            try:
                consume(witness, permit)
                return 'consumed'
            except RecoveryWitnessDenied:
                return 'denied'
        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(attempt, permits))
        self.assertEqual(sorted(outcomes), ['consumed', 'denied'])

    def test_invalid_generation_is_rejected(self):
        for generation in (True, 0, -1, 2**63):
            with self.subTest(generation=generation), self.assertRaises(RecoveryWitnessDenied):
                SimulatedMonotonicRecoveryWitness(KEY, generation=generation)

    def test_invalid_key_is_rejected(self):
        with self.assertRaises(RecoveryWitnessDenied):
            SimulatedMonotonicRecoveryWitness(b'short')
