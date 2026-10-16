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

Current follow-up command (Phase 8.4ao): [the local witness checker](witness-local-check-command.md) runs the current checkout directly with a fixed six-module list and excludes PostgreSQL conftest loading. The Phase 8.4av run passed the [static fixture-import guard](witness-product-import-boundary-validation.md) over **65 product Python files**, **91 local cases**, and **15 compilation checks**, including [typed recovery-admin configuration](witness-server-config-validation.md), [canonical caller/key authentication encoding](witness-canonical-auth-identities-validation.md), the [socket liveness guard](witness-socket-liveness-guard-validation.md), [frame receive deadlines](witness-frame-receive-deadline-validation.md), [handler capacity](witness-connection-cap-validation.md), and the [stop-state dispatch gate](witness-stop-dispatch-gate-validation.md). The copy-based commands and Phase 8.4ai results below remain historical evidence.

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

Follow-up Phase 8.4an: [per-exchange nonce binding](witness-rpc-exchange-freshness-validation.md) rejects captured replies for identical requests across different random exchanges. Nonce tampering fails before mutation and reservation retries keep one stable ticket body. **67 local cases passed**; this supplies neither anti-rollback storage nor a production transport boundary. The follow-ups below describe their historical results and limits.

Follow-up Phase 8.4am: the [response/request binding increment](witness-rpc-response-binding-validation.md) signs the exact request MAC in a v2 response envelope and checks it at the RPC client. Mismatched operation/ticket/caller responses now reject; **63 local cases passed**. Identical-request response freshness remains unresolved, and the earlier follow-up results below describe their own historical checkpoints.

Follow-up Phase 8.4al: the client rejects duplicate response JSON fields before authentication, including nested fields whose last value otherwise authenticates. The [RPC JSON evidence](witness-rpc-json-validation.md) records the regression and a combined local run of **58 cases** including all earlier 46 durable/protocol/process cases, nine in-memory regressions, the pending-snapshot audit drill and two response-parser tests. This does not add response freshness or request correlation.

Follow-up Phase 8.4ak: a separate standard-library [pending-snapshot audit rollback drill](witness-pending-snapshot-audit-rollback-validation.md) verifies exact consumed-ticket replay and identical recreated audit rows after restoring a pending witness snapshot. Its focused results are recorded separately; the 46-case pytest result above is the Phase 8.4ai checkpoint.

This matrix does not exercise the PostgreSQL-backed wrapper, an independently administered witness, remote caller authentication or transport, external effect systems, protected key custody, tamper-evident external audit, protected backups, physical power-loss behavior, or production recovery. The SQLite witness and fake ledger are local replaceable fixtures, and coordinated rollback confirms the replay risk when all copies are restored together. The local Unix socket is same-host only. No production safety claim follows. Product execution and external writes remain disabled pending the prerequisites in [the lifecycle note](witness-trust-boundary-lifecycle.md).
