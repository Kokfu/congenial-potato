# Local witness stop-state dispatch gate: Phase 8.4av

Date: 2026-10-16. Branch: `phase-8-witness-stop-dispatch-gate`. Parent: handler capacity draft PR #119.

A connection accepted before `close()` could previously complete a valid reservation frame after the listener closed and its socket path disappeared. The handler still dispatched the request and returned an authenticated reservation, creating durable state after close returned. The new regression reproduced that behavior on the parent.

The handler now checks the server's stop flag after frame validation and before selecting/calling the protocol method. A frame completed after shutdown observes the flag and receives the generic denial without protocol dispatch. This changes no authentication, SQLite or ticket format.

## Checks

The test coordinates an accepted handler with events, sends only the first byte of a correctly authenticated reservation frame, calls `close()`, verifies the socket path is removed, then completes the old connection's frame. It receives denial and confirms the entire witness file remains byte-identical. It waits for that handler to finish before cleaning up.

```sh
/tmp/witness-local-venv/bin/python scripts/check_local_witness.py
git diff --check
```

Result: **91 local cases passed in 3.83s**, **65 product Python files passed the static import guard**, and **15 files compiled**. Changed-document Markdown links and whitespace checks passed. Unix sockets ran with sandbox permission; PostgreSQL/product integration were not run.

## Limits

This rejects dispatch when a handler observes the stop flag. The check is not atomic with later method execution, and it does not drain operations that already passed the check. Successful listener close therefore still does not establish quiescence for snapshot/restore, and it does not revoke direct calls to the in-process witness object. Further recovery work must distinguish stopped admission from completed in-flight work. Independent protected service/state/key/audit custody and restore reconciliation remain [external prerequisites](witness-trust-boundary-lifecycle.md). Product dispatch, real writes, paid models, deployment and production integration stay disabled; no protected-infrastructure or physical power-loss claim is made.
