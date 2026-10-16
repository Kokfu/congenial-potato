# State-key rotation at the synthetic effect boundary: Phase 8.4y

Date: 2026-10-16. Branch: `phase-8-witness-state-key-effect-boundary`. Parent: caller-key rotation effect-boundary draft PR #96.

## Fixture and assertions

The test reserves a ticket under `state-v1`, reopens the witness with both `state-v1` and `state-v2` available and `state-v2` selected for new tickets, and consumes the pending ticket. Only after verified consume does it record control fixture admission and apply one test-only fake-ledger write. It then restarts with only `state-v2`; a retry for that invocation is denied as consumed, and the fake ledger contains exactly one record and one attempt.

This checks that a ticket's recorded signing key remains available during overlap, while consumed identity survives its later retirement. All state and key material are local synthetic fixtures.

## Validation

```sh
cp backend/tests/test_durable_witness_fake_ledger_recovery.py /tmp/test_durable_witness_fake_ledger_recovery.py
PYTHONPATH=/tmp/phase84-python:backend/tests:backend/src python -m pytest -q -x -p no:cacheprovider /tmp/test_durable_witness_fake_ledger_recovery.py
python -m py_compile backend/tests/test_durable_witness_fake_ledger_recovery.py
PYTHONPATH=backend/tests python -m unittest -v test_synthetic_write_recovery_witness
git diff --check
```

Result: **10 passed in 0.33s** for the copied fake-ledger recovery module; Python compilation passed; all **9** in-memory witness regression tests passed; Markdown local-link and whitespace checks passed. The copied test avoids the backend tree's PostgreSQL conftest requirement.

## Limits

This is in-process local SQLite rotation and a test fake ledger. It does not establish key custody, remote transport, key operator procedures, external execution truth, protected storage, PostgreSQL integration, physical power-loss behavior or production guarantees. Product dispatch and real external writes remain disabled.
