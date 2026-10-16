# Phase 8.4 local witness acceptance matrix: Phase 8.4ai

Date: 2026-10-16. Branch: `phase-8-witness-acceptance-matrix-rollback-results`. Parent: coordinated witness rollback draft PR #106.

This checkpoint reruns the durable protocol, fake-ledger restore drills, and local process transport suites as one focused set. It includes explicit generation-file rewind and coordinated witness/control/ledger rollback cases, which show that local monotonicity and consumed state can be rolled back with their SQLite file. The table maps claims to the fixtures that exercise them; all results remain synthetic and local.

| Area | Evidence exercised | Test module |
| --- | --- | --- |
| Reservation and consume | Exact binding, idempotent retry, one-way consume after lost reply, restart continuity, concurrent winner | `test_durable_local_recovery_witness.py` |
| Generation/admin | Monotonic increment, idempotent advance retry, stale ticket denial, caller allowlist, overlapping admin keys, generation rewind after file restore | `test_durable_local_recovery_witness.py` |
| Authentication and keys | Request/response HMAC, caller/state key overlap and retirement, fail-closed pending key removal | `test_durable_local_recovery_witness.py` |
| State path and schema | Private path checks, malformed/missing state denial, no replacement bootstrap, invocation reopening and generation rewind after replaceable-file rollback | `test_durable_local_recovery_witness.py` |
| Effect boundary and recovery | Actual test fake-ledger writes, control/ledger rollback and replacement, coordinated witness/control/ledger rollback showing a second fake event, outage/restore, lost consume reply, authentication denial, caller/state key rotations | `test_durable_witness_fake_ledger_recovery.py` |
| Local RPC transport | Separate server/client processes, process consume/admin races, restart/lost reply, peer/socket/config/JSON/frame denial | `test_durable_local_witness_transport.py` |

## Validation commands and results

The pytest files are copied outside `backend/tests` so the repository-wide `conftest.py` does not require PostgreSQL for these local-only suites.

```sh
cp backend/tests/test_durable_local_recovery_witness.py /tmp/test_durable_local_recovery_witness.py
cp backend/tests/test_durable_witness_fake_ledger_recovery.py /tmp/test_durable_witness_fake_ledger_recovery.py
cp backend/tests/test_durable_local_witness_transport.py /tmp/test_durable_local_witness_transport.py
PYTHONPATH=/tmp/phase84-python:backend/tests:backend/src python -m pytest -q -x -p no:cacheprovider /tmp/test_durable_local_recovery_witness.py /tmp/test_durable_witness_fake_ledger_recovery.py /tmp/test_durable_local_witness_transport.py
python -m py_compile backend/tests/durable_local_recovery_witness.py backend/tests/durable_local_witness_transport.py backend/tests/run_durable_local_witness_server.py backend/tests/test_durable_local_recovery_witness.py backend/tests/test_durable_witness_fake_ledger_recovery.py backend/tests/test_durable_local_witness_transport.py backend/tests/test_synthetic_write_admission.py
PYTHONPATH=backend/tests python -m unittest -v test_synthetic_write_recovery_witness
```

Results: **46 pytest cases passed in 2.09s**; Python compilation passed; **9 in-memory witness regressions passed**. Local Markdown links and `git diff --check` also passed.

## Limits

This matrix does not exercise the PostgreSQL-backed wrapper, an independently administered witness, remote caller authentication or transport, external effect systems, protected key custody, tamper-evident external audit, protected backups, physical power-loss behavior, or production recovery. The SQLite witness and fake ledger are local replaceable fixtures, and coordinated rollback confirms the replay risk when all copies are restored together. The local Unix socket is same-host only. No production safety claim follows. Product execution and external writes remain disabled pending the prerequisites in [the lifecycle note](witness-trust-boundary-lifecycle.md).
