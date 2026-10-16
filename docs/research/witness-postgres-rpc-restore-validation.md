# PostgreSQL restore wrapper over local RPC: Phase 8.4bd

Date: 2026-10-16. Branch: `phase-8-witness-postgres-rpc-restore`. Parent: draft PR [#127](https://github.com/Kokfu/congenial-potato/pull/127), commit `81f980d9dae1522b7c1715107aa7bd79a2cfd7ad`.

The [existing restore wrapper test](../../backend/tests/test_synthetic_write_admission.py) now runs each control-only, fake-ledger-only and joint simulated rollback through both direct authenticated calls and the authenticated Unix-socket client/server. The RPC path reserves/consumes a ticket before the existing PostgreSQL admission and actual SQLite fake-ledger fixture operation. It then closes the server, reopens retained witness state and starts a fresh server instance before retrying after rollback. A successful authenticated generation query verifies the restarted endpoint is healthy before replay denial; the RPC error intentionally does not expose the internal consumed-state reason.

Both paths preserve the assertions that deleted control rows are not recreated, removed ledger files stay absent, and a retained ledger still has one record and one attempt. Temporary mode-0700 socket directories use short paths to respect AF_UNIX limits and are cleaned by context managers; unsupported peer-credential platforms skip only the RPC parameter. This uses server threads in the test process, not separate-server-process PostgreSQL evidence.

## Focused validation

The [disposable PostgreSQL setup](witness-postgres-restore-wrapper-validation.md) was repeated with fresh application/workflow databases, the same pinned PostgreSQL 17.6 image, an unpublished internal network and tmpfs data. Application and DBOS migration commands succeeded. With the same scoped test URLs, zero daily cap and plugin isolation:

```sh
/tmp/witness-postgres-venv/bin/python -m pytest -q -x -p no:cacheprovider \
  backend/tests/test_synthetic_write_admission.py \
  -k test_live_witness_blocks_single_or_joint_store_rollback
```

Result: **6 passed, 28 deselected in 9.76s** (three direct and three Unix-RPC cases). Only the fixture's label-verified container and network were removed afterward, including tmpfs data; the preceding development run also passed six cases and cleaned up.

The changed test module compiled to a temporary bytecode directory; changed-document local links and `git diff --check` passed. No full backend run or repeat of the separate 120-case local checker is claimed.

## Limits and disabled gate

This remains local synthetic evidence: control row deletion and fake-ledger file deletion model rollback, not actual backup restoration. The witness remains replaceable SQLite; a fresh server object does not create an independent restore domain. Coordinated witness/control/ledger rollback remains an observed replay gap. No protected storage, physical power-loss, remote identity, real effect adapter or production-safety guarantee follows. Product dispatch, real external writes, paid activation, deployment, merging and production integration remain disabled; the [external prerequisites](witness-trust-boundary-lifecycle.md) are unchanged.
