# Background execution

Status: approved direction; validate exact pinned engine behavior.

## Ownership/dispatch

HTTP persists command and returns task/execution ID; never owns agent lifetime.

DBOS owns workflows/queues/waits/schedules. App owns task state/policy/budget/action records. Separate application and workflow databases/roles on one PostgreSQL instance; engine internal tables are not app APIs.

Persist task/outbox atomically. Dispatcher uses stable execution ID. Enqueue-success/ack-crash repeats submission harmlessly. Start with one dispatcher/worker; scale via engine-supported ownership/concurrency.

Every provider/custom-tool nondeterministic operation is an explicit durable step. Replay-compatible control flow required.

## Wait/recover

Persist reason before suspend. Approval/child/intervention sends correlated durable signal. On wake reload policy/connection/cancel/budget. Approval ledger, not signal content, determines authority.

Reuse checkpoints. Interrupted step can rerun; external effects need idempotency/reconciliation.

## Failures

| Failure | Response |
|---|---|
| Provider timeout/outage | Bounded backoff; uncertain usage retained |
| Rate limit | Retry guidance within deadline |
| Auth/model mismatch | Block/stop for correction |
| Malformed response | Bounded repair charged to limits |
| Invalid tool result | Record adapter failure |
| Worker/server restart | Resume checkpoint |
| Duplicate dispatch | Same logical execution |
| Unknown external write | Reconcile, no blind retry |
| Browser crash | Later restore allowed session/revalidate effect |
| Lost UI connection | Backend continues, SSE reconnect |
| Budget exhausted | No new calls/effects, typed reason |
| Policy/audit unavailable | Fail closed |
| Partial completion | Preserve results; report unmet criteria |

Classify retryability; no swallowed errors or indefinite retries.

## Schedules

Target/objective, timezone, recurrence, enabled state and limits.

Defaults: nonoverlap; skip while prior active; coalesce missed occurrences into one; no unbounded catch-up; stable occurrence key; explicit DST behavior.

MVP one human-configured daily recurrence. Agent-created schedules need later policy/approval.

## Budget

Atomically reserve conservative call cost; reconcile usage. Retain uncertain reservations. Aggregate root/agent/daily workspace; child shares root. Concurrent reservations cannot reuse funds.

Unknown price needs conservative operator cap or denial. Tool/search/media costs join ledger. In-flight charges cannot be reversed by app cap; provider caps add protection.

## Pause/stop

Pause blocks new work/effects. Emergency stop additionally aborts requests where possible/revokes runner handles. No unlimited catch-up or approval override.

## Versioning

Version/drain workflows before incompatible upgrades. Test restart on pinned dependencies. WorkflowEngine boundary allows later Temporal; old in-flight histories must drain, not be assumed portable.
