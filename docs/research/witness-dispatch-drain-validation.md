# Local witness admission and dispatch drain: Phase 8.4aw

Date: 2026-10-16. Branch: `phase-8-witness-dispatch-drain`. Parent: stop-state dispatch gate draft PR #120.

## Reproduced gaps and change

Three coordinated local cases failed on the parent: close returned while an already admitted generation advance was paused; close did not report an expired drain as unknown; and a handler paused after the early stop check could resume into a generation advance after close returned.

Protocol calls now enter a counted dispatch section under the same condition lock used to set the stop flag. Admission either observes stop and denies or increments the active-call count before shutdown can inspect it. Every admitted call decrements in a `finally` block. After closing the listener/joining its accept thread, close waits for the count to reach zero with a two-second drain budget. Expiry raises `WitnessTransportDenied` with an in-flight/unknown outcome; it does not cancel or roll back the call, remove its durable identity, or grant retry permission. The socket path is removed only after this drain succeeds.

## Checks

The waiting case pauses a real generation advance, confirms close has not returned, then releases the call and verifies one durable generation operation/audit event and successful close. The timeout case uses a shortened drain budget, verifies the explicit unknown result while generation remains unchanged, then releases the call and observes its later commit; a subsequent close succeeds. The admission-race case pauses method lookup after the early stop check, closes the server before dispatch admission, resumes lookup and verifies denial with byte-identical witness state. Existing late-frame, capacity, deadline, key/process and rollback drills remain included.

```sh
/tmp/witness-local-venv/bin/python scripts/check_local_witness.py
git diff --check
```

Result: **94 local cases passed in 6.95s**, **65 product Python files passed the static import guard**, and **15 files compiled**. Changed-document Markdown links and whitespace checks passed. Unix sockets used sandbox permission. PostgreSQL/product integration were not run.

## Limits

Successful drain concerns synchronous protocol methods admitted through this server instance. It does not revoke direct in-process witness calls, stop another process/server, wait for every pending frame/response handler to exit, quiesce a caller's control/fake-ledger work, or establish a coordinated restore procedure. A failed drain remains uncertain and cannot authorize snapshot replacement or retry. The listener join and dispatch-drain phases have separate budgets; this is not a whole-operation or physical timing guarantee. Independently protected service/state/key/audit custody and cross-store reconciliation remain [external prerequisites](witness-trust-boundary-lifecycle.md). Product dispatch, real external writes, paid models, deployment and production integration stay disabled; no protected-infrastructure or physical power-loss claim is made.
