# State-key process rotation at the fake-ledger boundary: Phase 8.4af

Date: 2026-10-16. Branch: `phase-8-witness-state-rotation-process-effect`. Parent: caller-key process race draft PR #103.

## Fixture and assertions

A separate client process reserves a synthetic ticket signed under `state-v1`. The server is restarted with only `state-v2`; consume is denied and the fake ledger stays empty. The server is then restarted with both keys and `state-v2` current. The original ticket is consumed successfully, and one verified fake-ledger receipt is applied. A final restart retires `state-v1`; replay is denied and the fake ledger retains exactly one record and one attempt.

This ties pending state-key overlap, fail-closed retirement, server restarts, and consumed identity to the local synthetic effect fixture.

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

Results: **44 pytest cases passed in 2.19s**; Python compilation passed; **9 in-memory witness regressions passed**; Markdown local-link check passed. The local Unix-socket tests needed sandbox socket permission.

## Limits

Keys, state, transport, control marker, and effect are local test fixtures. This does not establish remote or protected key custody, production server recovery, application PostgreSQL integration, external effect truth, physical power-loss behavior, or production guarantees. Product execution remains disabled.
