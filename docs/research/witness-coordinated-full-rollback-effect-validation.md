# Coordinated witness and effect-state rollback: Phase 8.4ah

Date: 2026-10-16. Branch: `phase-8-witness-coordinated-witness-rollback-effect`. Parent: witness generation rollback boundary draft PR #105.

## Fixture and assertion

The synthetic intent is first admitted through the durable local witness and applied to the fake ledger. The test then restores pre-operation copies of all three local SQLite files: witness, control fixture, and fake ledger. After reopening the witness, the same intent is admitted again and the fake ledger creates a second distinct event ID for the same intent digest. The restored ledger contains one record and attempt, reflecting the post-replay fixture state; an out-of-rollback test observer confirms that the apply method ran twice.

This deliberately demonstrates the coordinated rollback boundary: the local witness prevents replay when it is retained, but cannot prevent replay after its own consumed state is rolled back together with effect-side state.

## Validation

```sh
cp backend/tests/test_durable_witness_fake_ledger_recovery.py /tmp/test_durable_witness_fake_ledger_recovery.py
PYTHONPATH=/tmp/phase84-python:backend/tests:backend/src python -m pytest -q -x -p no:cacheprovider /tmp/test_durable_witness_fake_ledger_recovery.py
python -m py_compile backend/tests/test_durable_witness_fake_ledger_recovery.py
git diff --check
```

Results: **12 pytest cases passed in 0.27s**; Python compilation passed; `git diff --check` passed.

## Limits

The control fixture, witness, fake ledger, and test observer are all local synthetic fixtures. This does not model protected independent storage, physical power loss, a production service boundary, or real external effects. It confirms why independent protected witness state and independently administered recovery are required; product dispatch remains disabled.
