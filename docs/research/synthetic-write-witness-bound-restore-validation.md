# Witness-bound fake-write restore harness: Phase 8.3h

Date: 2026-10-16. Branch: `phase-8-witness-bound-restore-harness`. Parent: simulated recovery witness draft PR #69 (`67afbbc`).

## Harness behavior

The test wraps the real fixture-only `execute_governed_fake_write` call with `SimulatedMonotonicRecoveryWitness.issue` and `.consume`, binding the current ticket to that intent's ledger UUID, invocation UUID and canonical intent digest. The witness object remains live while the test resets PostgreSQL admission/control rows, the SQLite ledger file, or both. On every repeat, the witness denies the already-consumed invocation before the database admission or SQLite fake writer can run.

Three disposable cases passed: control state rollback while retaining the ledger; ledger deletion while retaining current control state; and coordinated rollback of both stores. Assertions verify that post-restore state remains exactly as restored: retained SQLite still has one record/attempt, removed SQLite stays absent, and removed PostgreSQL fences remain absent. The same test-only witness memory blocks all three repeats.

## Validation

```sh
PYTHONPATH=src:tests python -m pytest -q -x -p no:cacheprovider \
  tests/test_synthetic_write_admission.py::test_live_witness_blocks_single_or_joint_store_rollback
```

Result: **3 passed in 5.48s** on PostgreSQL 17.6 / Python 3.12.15. PostgreSQL used tmpfs; runner and DB were attached to an internal no-egress fixture network during tests; the repository mount was read-only. The runtime/database images and disposable containers/network were removed after the run.

All **86 local Markdown links** across the updated progress, docs index and evidence document resolved; `git diff --check` passed.

## Limits

This is a pre-effect test wrapper, not atomic integration between a remote witness, PostgreSQL and SQLite. In particular, a process loss after witness consumption but before database admission safely burns the invocation and may leave no write. The in-memory witness, if restarted or restored too, loses its consumed history and offers no protection. No ticket or witness result is persisted in the admission row, delivered over an authenticated transport, protected by a hardware monotonic counter, or deployed outside this test process. The positive cases do not establish restore safety for any real system.

## Next task

Review crash ordering, lost witness replies, idempotent witness retries and stale-generation recovery before specifying any external witness API. The safe default is to keep the product gate closed and preserve the consumed invocation when witness state is uncertain. Production witness integration, physical power-loss guarantees, real writes, merge and deployment remain outside this fixture work.
