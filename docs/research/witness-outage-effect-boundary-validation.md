# Witness outage at the synthetic effect boundary: Phase 8.4u

Date: 2026-10-16. Branch: `phase-8-witness-outage-effect-boundary`. Parent: consolidated local witness recovery draft PR #92.

## Fixture and assertions

The test first reserves and consumes one synthetic invocation, then renames the separate SQLite witness file to model local state unavailability. An attempt to pass through the real test-only fake-ledger wrapper is denied with `state unavailable`. The control fixture has no admission row, and the fake ledger has neither a record nor an attempt. Constructing a witness against the missing path fails instead of bootstrapping replacement state. After renaming the retained fixture file back and reopening the witness, replay is denied as consumed and the spent reservation remains present.

This is a local file-path outage drill only. It uses synthetic payloads and does not call product dispatch or external services.

## Validation

```sh
cp backend/tests/test_durable_witness_fake_ledger_recovery.py /tmp/test_durable_witness_fake_ledger_recovery.py
PYTHONPATH=/tmp/phase84-python:backend/tests:backend/src python -m pytest -q -x -p no:cacheprovider /tmp/test_durable_witness_fake_ledger_recovery.py
python -m py_compile backend/tests/test_durable_witness_fake_ledger_recovery.py
PYTHONPATH=backend/tests python -m unittest -v test_synthetic_write_recovery_witness
git diff --check
```

Results: **7 passed in 0.12s** for the copied fake-ledger recovery module; Python compilation passed; all **9** in-memory witness regression tests passed; whitespace and local Markdown link checks passed. Tests are copied outside the backend test tree to avoid its global PostgreSQL fixture requirement.

## Limits

The test models a file temporarily absent on one local filesystem. It does not establish behavior under concurrent filesystem replacement, storage corruption while open, host failure, physical power loss, protected storage, independent administration, PostgreSQL integration, remote transport or production infrastructure. Restoring the exact retained fixture is a scenario condition, not evidence of backup guarantees. The witness database itself remains replaceable. Product execution remains disabled.
