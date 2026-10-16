# Local witness frame receive deadlines: Phase 8.4at

Date: 2026-10-16. Branch: `phase-8-witness-frame-receive-deadline`. Parent: product import guard draft PR #117.

## Reproduction and change

Accepted server connections previously had no receive timeout, and the client's socket timeout applied anew to each read. A deterministic slow-stream fixture returned a complete frame after three chunks, each within the per-read timeout but together beyond the intended receive budget. Its new rejection test failed on the parent implementation.

The decoder now uses one monotonic deadline for the entire frame read and reduces each read's timeout to the remaining budget. A connection's configured timeout supplies that budget; a blocking connection uses the two-second fixture default. Accepted server connections explicitly receive that timeout. Missing/oversized frames retain their existing denial behavior. This changes no authentication fields, database state or ticket format.

## Checks

The slow-stream test uses a controlled clock and receive-timeout stub, so it verifies budget exhaustion without real sleeps. A real local Unix-socket case uses a shortened fixture timeout, sends an unfinished JSON frame and observes denial without reservation or audit mutation. A subsequent authenticated generation query succeeds against the same server.

```sh
/tmp/witness-local-venv/bin/python scripts/check_local_witness.py
git diff --check
```

Result: **88 local cases passed in 3.06s**, **65 product Python files passed the static import guard**, and **15 files compiled**. Changed-document Markdown links and whitespace checks passed. Unix sockets used sandbox permission. No PostgreSQL, application or production service was started.

## Limits

This is a frame receive budget, not an end-to-end operation deadline. It does not cap concurrent worker threads, database work, process scheduling delays, connect/send stages or total service resources, and it does not establish production availability. The same-host fixture keys/storage remain replaceable; the [external trust-boundary prerequisites](witness-trust-boundary-lifecycle.md) remain unmet. Product dispatch, real external writes, paid models, deployment and production integration stay disabled. No protected-infrastructure or physical power-loss claim is made.
