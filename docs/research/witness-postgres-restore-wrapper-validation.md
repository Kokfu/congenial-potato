# PostgreSQL witness-bound restore wrapper: Phase 8.4bc

Date: 2026-10-16. Branch: `phase-8-witness-postgres-restore-validation`. Parent: draft PR [#126](https://github.com/Kokfu/congenial-potato/pull/126), commit `94620757e4c928df99e7bcc16614084f2b1ab5e6`.

## Local setup and focused result

The existing [three witness-bound wrapper cases](../../backend/tests/test_synthetic_write_admission.py) now ran against a fresh disposable PostgreSQL database. The test calls the durable SQLite witness directly with authenticated request/response binding, then the real PostgreSQL fixture admission wrapper and SQLite fake ledger. This closes the previously recorded unrun-wrapper gap for these cases only.

Dependencies came from `backend/requirements-dev.lock` in a separate temporary virtual environment. The official PostgreSQL 17.6 image was pinned to `postgres@sha256:00bc86618629af00d2937fdc5a5d63db3ff8450acf52f0636ec813c7f4902929`. A uniquely named/labeled container used a private internal Docker network, no published ports or host data mounts, tmpfs database storage, and 512 MiB/one CPU/128 PID limits. Test authentication used trust only inside this unpublished disposable fixture. The test process connected to that container's inspected private bridge address. Both database URLs explicitly named new `workforce_test` / `workforce_dbos_test` databases; no configured product database was used.

With `APP_DATABASE_URL` and `DBOS_SYSTEM_DATABASE_URL` pointing only to those fixture databases, `DAILY_CAP_USD=0`, pytest plugin autoload disabled, and backend source/tests on `PYTHONPATH`:

```sh
# From backend:
/tmp/witness-postgres-venv/bin/python -m alembic -c alembic.ini upgrade head
/tmp/witness-postgres-venv/bin/python -m workforce.migrate_workflows
# From repository root, with ordinary integration conftest enabled:
/tmp/witness-postgres-venv/bin/python -m pytest -q -x -p no:cacheprovider \
  backend/tests/test_synthetic_write_admission.py \
  -k test_live_witness_blocks_single_or_joint_store_rollback
```

Result: both migration commands exited successfully; **3 passed, 28 deselected in 4.66s**. The cases cover control-only, ledger-only and joint simulated rollback. Each first applies one fake effect, reopens the retained witness, then deletes the selected admission/control rows and/or SQLite ledger file. Replay is denied as consumed before recreating deleted control state or ledger files; a retained ledger has exactly one record and one attempt. This is row/file deletion modeling, not a PostgreSQL backup restore drill.

The FastAPI test client and existing synthetic DBOS fixture prepare exact approved artifacts; no standalone product API/worker service or live provider was started. Cloud/conductor/OTLP environment selectors were absent. No product runtime files or dispatch settings changed. After checks, only the fixture's label-verified container/network were removed, including tmpfs data. An earlier setup attempt was also cleaned up. Changed-document links and `git diff --check` passed.

## Scope and remaining gate

The separate six-module local command remains at its recorded **120-case** Phase 8.4bb pass; it was not rerun for this documentation increment, and these three cases are reported separately. No full backend-suite or migration parity/downgrade claim follows.

The witness and fake ledger remain replaceable same-host SQLite fixtures. The wrapper uses direct authenticated calls, not a PostgreSQL-plus-Unix-RPC end-to-end drill. This does not mitigate coordinated witness/control/ledger rollback, prove protected storage or physical power-loss behavior, or establish real external effect truth. Actual effect adapters, protected backup/restore infrastructure, independently administered anti-rollback state and remote authenticated transport remain untested/unimplemented prerequisites in the [lifecycle checklist](witness-trust-boundary-lifecycle.md). Product dispatch, real external writes, paid models, deployment, merges and production integration remain disabled.
