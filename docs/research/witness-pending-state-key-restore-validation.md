# Pending state-key restore at the synthetic effect boundary: Phase 8.4z

Date: 2026-10-16. Branch: `phase-8-witness-state-key-restore-boundary`. Parent: state-key rotation effect-boundary draft PR #97.

## Fixture and assertions

The test creates a pending ticket under `state-v1`, then reopens the witness with only `state-v2`. Consume fails with `state key unavailable`; the reservation remains unconsumed and the control admission and fake-ledger record/attempt counts remain zero. It then reopens with both keys restored and `state-v2` current, consumes the original ticket, and applies the synthetic fake-ledger operation once. The resulting ledger has exactly one record and one attempt.

This exercises local fail-closed behavior and an explicit fixture keyring restoration. It does not model external key recovery or key custody.

## Validation

```sh
cp backend/tests/test_durable_witness_fake_ledger_recovery.py /tmp/test_durable_witness_fake_ledger_recovery.py
PYTHONPATH=/tmp/phase84-python:backend/tests:backend/src python -m pytest -q -x -p no:cacheprovider /tmp/test_durable_witness_fake_ledger_recovery.py
python -m py_compile backend/tests/test_durable_witness_fake_ledger_recovery.py
PYTHONPATH=backend/tests python -m unittest -v test_synthetic_write_recovery_witness
git diff --check
```

Result: **11 passed in 0.19s** for the copied fake-ledger recovery module; Python compilation passed; all **9** in-memory witness regression tests passed; Markdown local-link and whitespace checks passed. The copy avoids the backend tree's PostgreSQL conftest requirement.

## Limits

This is local in-process SQLite state with synthetic keys and a test fake ledger. It does not establish external key custody, operator recovery, protected infrastructure, PostgreSQL integration, physical power-loss durability, or production behavior. Product dispatch and real writes remain disabled.
