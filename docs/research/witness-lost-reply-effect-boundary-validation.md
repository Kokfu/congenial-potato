# Lost consume reply at the effect boundary: Phase 8.4ac

Date: 2026-10-16. Branch: `phase-8-witness-lost-reply-effect-boundary`. Parent: separate-process consume race draft PR #100.

## Fixture and assertions

The existing local Unix-socket drill reserves a synthetic intent and has the client abandon the consume response after sending the request. The test observes one durable `consumed` event, stops and restarts the local witness server, then verifies that replay is denied and the reservation remains consumed. The client has no confirmed consume reply, so the harness does not proceed to the fake effect. A separate test-only fake ledger is initialized and verified to have zero records and zero attempts.

This exercises conservative handling of an unknown consume outcome across process restart. It does not claim that an external caller or production dispatcher will follow this harness policy.

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

Results: **44 pytest cases passed in 1.98s**; Python compilation passed; **9 in-memory witness regressions passed**; Markdown local-link validation passed. Unix-socket process tests require local socket permission in this sandbox.

## Limits

This uses a same-host Unix socket, local SQLite witness state, and test fake ledger. It does not prove production client behavior, distributed recovery, protected storage, external effect outcome, remote transport, PostgreSQL integration, physical power-loss behavior, or production safety. The witness file remains replaceable and product dispatch remains disabled.
