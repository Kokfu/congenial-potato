# Recovery-administrator allowlist: Phase 8.4e

Date: 2026-10-16. Branch: `phase-8-recovery-admin-allowlist`. Parent: idempotent generation-advance draft PR #76 (`79e7eb2`).

## Authorization rule

Generation advancement now requires both caller authentication and an explicit `advance_callers` allowlist entry. The default is empty, including for the local socket server config, so a valid ordinary witness caller cannot advance the generation unless the fixture operator explicitly assigns that role. A missing or malformed allowlist fails closed at configuration or request handling. Authorized generation operations retain the durable operation UUID idempotency behavior from 8.4d.

Tests verify that an authenticated non-admin caller cannot change the generation or create a generation-operation row, and that the separate socket server denies an advance when no admin identity is configured. The prototype does not include human approval, quorum, owner API, policy evaluator, or a secure mechanism for changing the allowlist. The allowlist is local startup configuration and therefore is not a production authorization control.

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

Result: **23 pytest cases passed** across the durable-state, restore, and transport suites; **9** original process-local protocol tests passed. Python compilation and whitespace checks passed. The Unix-socket tests use local filesystem sockets only. Pytest files are copied to `/tmp` because repository `conftest.py` requires PostgreSQL for in-tree collection.

## Limits

The allowlist and all keys are local fixture configuration. The SQLite generation, reservations and allowlist can be changed or rolled back by the host operator. This does not provide an independently administered recovery identity, auditable approval, protected high-water mark, actual PostgreSQL integration, remote transport, physical power-loss durability, or production authorization. Product execution remains disabled.
