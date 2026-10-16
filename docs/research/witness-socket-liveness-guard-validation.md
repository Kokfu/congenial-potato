# Local witness socket liveness guard: Phase 8.4ar

Date: 2026-10-16. Branch: `phase-8-witness-active-socket-guard`. Parent: canonical authentication identities draft PR #115.

## Reproduction and change

Startup previously unlinked an existing owned Unix socket without checking whether it was live. A second local witness fixture using a different database could replace the active server's endpoint; the new active-socket rejection regression failed on the parent.

The server now probes an existing owned socket with a bounded local connection. A successful connection rejects startup as active. Errors other than connection refusal, including timeout and permission denial, fail closed without removing the path. After connection refusal it rechecks device/inode, socket type and owner before removing the stale path. An observed replacement inode is preserved. The existing stale-owned-socket recovery behavior remains exercised.

The process-test helper no longer unlinks an existing socket before launch. It waits for an authenticated generation response using the configured caller key instead of treating mere path existence as readiness. This ensures the process-restart fixtures exercise the server's stale-path guard rather than bypassing it.

## Checks

The new active-server test verifies startup denial, unchanged endpoint inode, continued authenticated access to the original server and unchanged databases. Two probe-error cases preserve the socket when liveness is unknown; another case replaces the inode during the probe and verifies that startup does not remove it. The existing stale-socket and process-restart/key-rotation cases remain in the combined run.

```sh
/tmp/witness-local-venv/bin/python scripts/check_local_witness.py
git diff --check
```

Result: **86 local cases passed in 2.54s** and **15 files compiled**. Changed-document Markdown links and whitespace checks passed. Unix-socket tests ran with sandbox permission; PostgreSQL and product integration were not run.

## Limits

The probe and inode recheck are local startup checks, not a lifetime lock or an atomic ownership protocol. They do not eliminate all filesystem/concurrent-start races, authenticate an independent host administrator, or attest which process answered a readiness query. The socket, keys and SQLite stores remain same-host replaceable fixtures. The [external lifecycle prerequisites](witness-trust-boundary-lifecycle.md), including independent state/key/audit custody and restore reconciliation, remain unmet. Product dispatch, real writes, paid models, deployment and production integration remain disabled. No protected-infrastructure or physical power-loss guarantee is claimed.
