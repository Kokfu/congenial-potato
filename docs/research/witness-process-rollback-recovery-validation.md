# Process race and coordinated restore drill: Phase 8.4ad

Date: 2026-10-16. Branch: `phase-8-witness-process-rollback-recovery`. Parent: lost consume reply effect-boundary draft PR #101.

## Fixture and assertions

The local RPC test starts two separate client processes behind a barrier and has them consume the same reservation. Exactly one reply is `spent` and one is `denied`. The harness then applies the synthetic intent once to a separate fake ledger and records a control-fixture admission marker. It snapshots the initial control and ledger SQLite fixtures, stops and restarts the witness server while retaining its state, restores both effect-side snapshots, and retries from a fresh client process. Replay is denied; the restored control and ledger fixtures remain empty; the witness still has one consumed reservation and one `consumed` event.

This combines process concurrency, a synthetic effect, coordinated fixture rollback, server restart, and recovery denial in one local scenario. Product dispatch is not involved.

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

Results: **44 pytest cases passed in 1.99s**; Python compilation passed; **9 in-memory witness regressions passed**; Markdown local-link check passed. The Unix-socket tests required local socket permission in this sandbox.

## Limits

All stores in the combined restore remain local, replaceable SQLite fixtures. The control database is not the application's PostgreSQL database; the effect is the test fake ledger; the witness service is a same-host prototype. This does not establish independent administration, remote transport, protected storage, physical power-loss durability, external execution truth, or production guarantees. The PostgreSQL wrapper remains unrun. Product execution remains disabled.
