# Caller-key process race at fake-ledger boundary: Phase 8.4ae

Date: 2026-10-16. Branch: `phase-8-witness-key-rotation-process-effect-race`. Parent: process race and coordinated restore draft PR #102.

## Fixture and assertions

The existing coordinated restore drill now configures one stable caller identity with `caller-v1` and `caller-v2` overlapping. It issues one ticket, then races two separate client processes at a barrier: one authenticates with each key ID. Exactly one receives `spent`, and one receives `denied`. The harness applies the bound synthetic intent once to the fake ledger, verifies one receipt/record/attempt, and observes one consumed witness event. It then restores the control and ledger fixture snapshots, restarts the witness service, and verifies the consumed invocation remains denied.

This checks stable caller identity and key overlap across separate local processes through effect and recovery fixtures. It does not establish key custody or remote identity.

## Validation

```sh
cp backend/tests/test_durable_local_recovery_witness.py /tmp/test_durable_local_recovery_witness.py
cp backend/tests/test_durable_witness_fake_ledger_recovery.py /tmp/test_durable_witness_fake_ledger_recovery.py
cp backend/tests/test_durable_local_witness_transport.py /tmp/test_durable_local_witness_transport.py
PYTHONPATH=/tmp/phase84-python:backend/tests:backend/src python -m pytest -q -x -p no:cacheprovider /tmp/test_durable_local_recovery_witness.py /tmp/test_durable_witness_fake_ledger_recovery.py /tmp/test_durable_local_witness_transport.py
python -m py_compile backend/tests/durable_local_recovery_witness.py backend/tests/durable_local_witness_transport.py backend/tests/run_durable_local_witness_server.py backend/tests/test_durable_local_recovery_witness.py backend/tests/test_durable_witness_fake_ledger_recovery.py backend/tests/test_durable_local_witness_transport.py backend/tests/test_synthetic_write_admission.py
PYTHONPATH=backend/tests python -m unittest -v test_synthetic_write_recovery_witness
git diff --check
```

Results: **44 pytest cases passed in 2.14s**; Python compilation passed; **9 in-memory witness regressions passed**; Markdown local-link check passed. The Unix-socket tests required local socket permission in this sandbox.

## Limits

This is a same-host Unix-socket fixture using in-process configured synthetic keys, local SQLite state, SQLite control fixture, and test fake ledger. It does not prove independent key custody, remote caller authentication or transport, protected storage, PostgreSQL integration, physical power-loss behavior, or production guarantees. Product execution remains disabled.
