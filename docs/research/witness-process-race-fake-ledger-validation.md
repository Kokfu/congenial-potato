# Separate-process consume race at the fake-ledger boundary: Phase 8.4ab

Date: 2026-10-16. Branch: `phase-8-witness-process-race-fake-ledger`. Parent: local witness acceptance matrix draft PR #99.

## Fixture and assertions

The existing Unix-socket transport race now binds its reservation to a real test-only synthetic intent. Two separate client processes wait at a barrier and submit consume for the same ticket. Exactly one authenticated reply is `spent` and one is `denied`; only after those assertions does the test apply the synthetic intent to a separate fake ledger. The receipt verifies as revision 1, with exactly one fake-ledger record and one attempt. The witness fixture contains exactly one durable consumed event.

This closes the local test gap between separate-process consume concurrency and the fake effect boundary. It does not connect product dispatch or external systems.

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

Results: **44 pytest cases passed in 1.86s**; Python compilation passed; **9 in-memory witness regressions passed**. Markdown local-link validation passed. Unix-socket process tests require local socket permission in this sandbox.

## Limits

The race is between local client processes and a same-host Unix-socket server. The effect target is a test fake ledger. This does not establish distributed fencing, independent administration, protected storage or key custody, remote transport, PostgreSQL integration, physical power-loss behavior, or production guarantees. Product execution remains disabled.
