# PostgreSQL checkpoint after witness authentication fix: Phase 8.4bj

Date: 2026-10-17. Branch: `phase-8-witness-auth-postgres-checkpoint`. Parent: draft PR [#133](https://github.com/Kokfu/congenial-potato/pull/133), commit `8534de30226ef74294ec6dd0c92175f4a298c135`.

After the [missing-key/empty-MAC fix](witness-missing-auth-key-denial-validation.md), the focused PostgreSQL witness command was rerun against fresh disposable databases. This refreshes the valid authenticated wrapper/transport paths alongside the parent's 139-case direct/RPC authentication regression result.

```sh
/tmp/witness-postgres-venv/bin/python scripts/check_local_witness_postgres.py
```

The resumed environment required recreating the separate PostgreSQL test venv from `backend/requirements-dev.lock`; the pinned image remained present and was not pulled. The [repository command](witness-postgres-check-command.md) used its explicit local Docker socket, uniquely labeled unpublished internal network, tmpfs data and fresh application/workflow databases. Database URLs were overridden to the inspected private fixture address, inherited DBOS cloud/pytest selectors removed, and the daily cap set to zero.

Result: **7 passed, 28 deselected in 12.72s**, with **65 product Python files passing the static fixture-import guard** and successful application/DBOS migrations. The cases cover direct and authenticated local RPC control-only, fake-ledger-only and joint simulated rollback, plus abandoned consume reply before admission. Exact control/ledger absence/count checks and retained witness consumption still hold. The command removed its own label-verified container and network, including tmpfs data. Changed-document local links and `git diff --check` passed.

The parent's **139 cases in 5.63s** and **15 compilation checks** were not repeated for this documentation-only increment. The older **35-case full admission file** pass remains historical; this run selected seven cases and does not update full-file or full-backend acceptance.

This is local synthetic PostgreSQL/Unix-socket/SQLite evidence, with row/file deletion modeling rollback. It is not an actual backup restoration or protected-infrastructure drill, does not repair state mutated before the authentication fix, and does not prove external effect truth or physical power-loss behavior. Independent anti-rollback state, separate restore authority, remote authenticated transport, protected keys/audit and caller/effect fencing remain [external prerequisites](witness-trust-boundary-lifecycle.md). Product dispatch, real external writes, paid models, deployment, merge and production integration remain disabled.
