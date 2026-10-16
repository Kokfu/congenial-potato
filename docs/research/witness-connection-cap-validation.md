# Local witness handler capacity: Phase 8.4au

Date: 2026-10-16. Branch: `phase-8-witness-connection-cap`. Parent: frame receive deadline draft PR #118.

The local server previously started a new worker thread for every accepted connection. A one-slot fixture held an unfinished request open while a second authenticated request still entered another handler; the new saturation-rejection test failed on the parent.

The server now admits at most 32 connection handlers through a bounded semaphore. Excess accepted connections close before protocol parsing instead of starting a thread. A handler releases its slot in a `finally` block, including after malformed frames/timeouts; failed thread creation/start also closes the connection and releases the slot. Shutdown stops admitting newly accepted connections once the stop flag is observed. The frame deadline, authentication, SQLite and ticket formats are unchanged.

## Checks

The one-slot Unix-socket regression verifies rejection during saturation, releases the partial request with a malformed completed frame, then confirms an authenticated request succeeds after the handler finishes. A second one-slot case injects a thread-start failure and confirms that the next request succeeds. Both verify byte-identical witness state. Capacity errors remain unauthenticated transport failures; they do not supply retry permission or resolve an unknown consume outcome.

```sh
/tmp/witness-local-venv/bin/python scripts/check_local_witness.py
git diff --check
```

Result: **90 local cases passed in 4.03s**, **65 product Python files passed the static import guard**, and **15 files compiled**. Changed-document Markdown links and whitespace checks passed. The suite used temporary local Unix sockets with sandbox permission; PostgreSQL/product integration were not run.

## Limits

This caps the fixture's active connection-handler threads. It does not bound the operating system's connection backlog, all process memory/CPU resources, database scheduling, deployment-wide capacity or production availability. Closing the listener is not a guarantee that every in-flight handler has quiesced. Independent service/state/key/audit administration and restore reconciliation remain [external prerequisites](witness-trust-boundary-lifecycle.md). Product dispatch, real external writes, paid models, deployment and production integration remain disabled. No protected-infrastructure or physical power-loss claim is made.
