# Pending-ticket snapshot and audit rollback: Phase 8.4ak

Date: 2026-10-16. Branch: `phase-8-witness-pending-snapshot-audit-rollback`. Parent: lifecycle prerequisites draft PR #108.

## Fixture and observations

The standard-library drill in `backend/tests/test_witness_pending_snapshot_audit_rollback.py` snapshots the private local SQLite witness after reservation but before consumption. It retains the exact ticket, including its nonce and MAC, outside the restored file.

1. The first authenticated consume succeeds and records audit sequence 2 after the reservation at sequence 1.
2. Reopening the retained witness denies that same consume request as spent; the audit rows remain unchanged.
3. Restoring the pending snapshot removes the consumed audit event and restores the reservation's pending state.
4. Replaying the exact consume request succeeds without a new reservation. Its authenticated response envelope equals the first response, and every final audit row, including sequence numbers and binding hashes, equals the history after the first consume.

The test observer retains both successful responses outside the restored file. The witness's own final audit table cannot distinguish those two consumes from one. Transactional audit recording and authenticated responses therefore do not establish independent rollback detection. This extends the [generation rewind](witness-generation-rollback-boundary-validation.md) and [coordinated full-fixture rollback](witness-coordinated-full-rollback-effect-validation.md) evidence to a pending snapshot and reuse of the exact old ticket.

## Validation

```sh
PYTHONPATH=backend/tests python -m unittest -v test_witness_pending_snapshot_audit_rollback test_synthetic_write_recovery_witness
python -m py_compile backend/tests/durable_local_recovery_witness.py backend/tests/test_witness_pending_snapshot_audit_rollback.py
git diff --check
```

Results: **10 unittest cases passed** (one new durable witness drill and nine existing in-memory regressions); Python compilation and whitespace checks passed. Local Markdown targets in the changed documents were checked against the complete repository tree at parent commit `ac880be98b2d6f93f861cb38f2edbf284b8da428`, plus the new files; all resolved. Shell Git transport could not reach its configured proxy, so the validation workspace contains selected files fetched at that pinned commit through the GitHub connector. The GitHub Git-data API publishes the change on that exact parent. The earlier 46-case pytest result remains historical and was not rerun here.

## Limits and prerequisites

This test exercises only replaceable local witness state, synthetic keys and an out-of-rollback in-memory observer. It does not apply a fake-ledger effect, integrate PostgreSQL, or implement detection or recovery. It makes no claim about protected infrastructure or physical power loss.

Further trust-boundary work needs separately authorized infrastructure: independently administered anti-rollback state for generation and consumed identities, independently retained tamper-evident audit evidence, authenticated remote identities/transport, protected key custody, and a reviewed reconciliation procedure for divergent witness/control/effect restores before admission reopens. See the [lifecycle prerequisites](witness-trust-boundary-lifecycle.md). Product dispatch, real external writes, paid models, deployment and production integration remain disabled.
