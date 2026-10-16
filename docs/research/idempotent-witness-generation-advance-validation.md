# Idempotent witness generation advancement: Phase 8.4d

Date: 2026-10-16. Branch: `phase-8-idempotent-generation-advance`. Parent: local witness transport draft PR #75 (`b45116b`).

## Operation semantics

Generation advancement now requires a caller-generated operation UUID. The witness stores that UUID, authenticated caller identity and resulting generation atomically with the increment and audit row. Exact retries return the same resulting generation, including after process restart and after a later distinct generation operation. Reusing an operation UUID under a different authenticated caller fails closed. Concurrent duplicate advances serialize and increment the high-water mark once.

This closes the local protocol ambiguity where a lost reply could cause an advance retry to increment again and stale unrelated reservations. The operation uses the configured witness caller-authentication keys, but does not define a separate recovery-administrator role, approval quorum or revocation policy. Production recovery control must add those safeguards independently.

## Validation

```sh
cp backend/tests/test_durable_local_recovery_witness.py /tmp/test_durable_local_recovery_witness.py
PYTHONPATH=/tmp/phase84-python:backend/tests python -m pytest -q -x -p no:cacheprovider /tmp/test_durable_local_recovery_witness.py
```

Result: **13 passed in 0.10s**, including a lost advance reply followed by restart, later generation advancement, cross-caller request-ID conflict, and eight concurrent retries of one operation ID.

Final combined commands for this checkpoint:

```sh
cp backend/tests/test_durable_local_recovery_witness.py /tmp/test_durable_local_recovery_witness.py
cp backend/tests/test_durable_witness_fake_ledger_recovery.py /tmp/test_durable_witness_fake_ledger_recovery.py
cp backend/tests/test_durable_local_witness_transport.py /tmp/test_durable_local_witness_transport.py
PYTHONPATH=/tmp/phase84-python:backend/tests:backend/src python -m pytest -q -x -p no:cacheprovider /tmp/test_durable_local_recovery_witness.py /tmp/test_durable_witness_fake_ledger_recovery.py /tmp/test_durable_local_witness_transport.py
python -m py_compile backend/tests/durable_local_recovery_witness.py backend/tests/durable_local_witness_transport.py backend/tests/run_durable_local_witness_server.py backend/tests/test_durable_local_recovery_witness.py backend/tests/test_durable_witness_fake_ledger_recovery.py backend/tests/test_durable_local_witness_transport.py backend/tests/test_synthetic_write_admission.py
PYTHONPATH=backend/tests python -m unittest -v test_synthetic_write_recovery_witness
git diff --check
```

Combined result: **22 passed in 0.62s**; existing process-local protocol regression: **9 passed**. Compilation, link check and whitespace check passed. Unix-socket checks ran with local socket permission enabled and made no network connection.

## Limits

The operation record and generation live in the same replaceable local SQLite witness file. This does not protect against witness-file rollback, a compromised host/key holder, unauthorized configured callers, or physical power loss. It does not provide an external high-water mark or production recovery administrator controls. Product dispatch remains disconnected.
