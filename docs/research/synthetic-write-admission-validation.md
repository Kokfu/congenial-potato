# Governed fake-write admission: Phase 8.3c

Date: 2026-10-16. Branch: `phase-8-governed-synthetic-write-admission`. Parent: draft PR #64 (`370ea3c`).

## Boundary

`backend/tests/synthetic_write_admission.py` is a trusted test-only bridge. It accepts only an existing `project.artifact.write` invocation with its exact durable owner approval. It derives the fake record ID, expected revision and content bytes from that persisted approved payload; binds project, agent, root, invocation, approval payload hash and current policy snapshot into the existing strict synthetic intent; and rechecks the live approval, current tool policy, project execution grant, active agent, source/root scope, root cancellation and positive USD root budget. The expected ledger UUID is supplied separately by the trusted fixture configuration; a caller-provided intent cannot select or replace it.

Before opening or creating the SQLite ledger, the bridge commits an independent PostgreSQL admission row and singleton ledger identity. The admission row is keyed by invocation and the `(ledger, record, expected revision)` tuple is unique. A foreign key prevents ordinary deletion of the pinned ledger identity while admissions exist. A consumed row stays `unknown`; neither a later receipt nor reconciliation changes database result state. Ordinary migration downgrade refuses to erase either the ledger identity or a consumed admission.

The bridge opens the trusted private SQLite fixture only after the control-DB commit. It then rechecks authority in a new transaction and holds the root, invocation, approval, grant, policy, agent and budget locks through the local mutation. A process loss between the admission commit and ledger open leaves the independent admission consumed. Deleting the fake ledger after a successful write or replacing its contents cannot authorize a repeat of the same invocation or target revision. A concurrently inserted policy rule is excluded by a PostgreSQL table share lock for the duration of the local effect.

The existing approval is for a fixture-only synthetic proposal; the SQLite mutation does not modify the application artifact table. The signed SQLite receipt is returned transiently and may be reconciled only through the existing fake-ledger contract. There is no application result acceptance, product dispatch, tool/API registration, model-context promotion or external effect. A positive root budget is checked but not reserved because this local synthetic write has no monetary charge.

## Validation

The focused command passed **145 tests in 121.57s**, with no skips: 27 new admission cases, all 25 fake-ledger cases, all 64 write-contract cases, nine runner recovery cases, and the existing tool approval/gateway cases. The tests include concurrent same-invocation delivery, substitutions across every intent scope/resource/precondition/content/approval/policy field, current policy/grant/agent/approval/budget/cancellation denials, a process exit in a fresh interpreter immediately after the control-DB commit, missing-ledger retry refusal, deletion and recreation of an empty ledger after an applied effect, a different invocation targeting an already consumed revision, and downgrade refusal with a committed fence. After strengthening the empty-ledger replacement assertions, that focused replacement case passed again separately (**1 passed in 3.61s**).

The test used PostgreSQL 17.6 and Python 3.12.15 in disposable containers joined only to an internal Docker network with no external route; database storage was tmpfs and the repository mount was read-only. The official database/runtime images were pulled as test dependencies, then removed with the containers and network after validation; the running test containers had no external route. The database migration upgraded from a fresh schema. An empty-table downgrade/upgrade round trip passed (**1 test**); the data-bearing downgrade refusal is included in the 145-test run. `alembic check` reported `No new upgrade operations detected.` PostgreSQL metadata compilation emitted 47 statements. Python compilation, a fixture-module import, the product main/worker/tool-effects AST import boundary check, and `git diff --check` passed. The existing 64 contract cases also passed separately (**64 passed in 0.20s**).

From `backend/` inside the disposable Python test container, the final migration checks were:

```sh
PYTHONPATH=src APP_DATABASE_URL='postgresql+psycopg://postgres:phase1fixture@workforce-swrite-admission-test:5432/workforce_test' \
  python -m alembic upgrade head
PYTHONPATH=src APP_DATABASE_URL='postgresql+psycopg://postgres:phase1fixture@workforce-swrite-admission-test:5432/workforce_test' \
  python -m alembic check
```

The test also ran `alembic downgrade ca53e6f90274` followed by `alembic upgrade head` on an empty application schema, and proved downgrade refusal with consumed admission data.

The combined command, from the repository root, inside the disposable Python test container was:

```sh
cd backend
python -m pytest -q -x -p no:cacheprovider \
  tests/test_synthetic_write_admission.py \
  tests/test_synthetic_write_ledger.py \
  tests/test_synthetic_write_contract.py \
  tests/test_runner_result_recovery.py \
  tests/test_tool_approval.py \
  tests/test_tool_gateway.py
```

`APP_DATABASE_URL` and `DBOS_SYSTEM_DATABASE_URL` pointed to the two PostgreSQL databases by their Docker-internal hostname. The test-runner container and database were attached only to the internal, no-egress fixture network. All labeled containers and that network were removed after validation.

All **81 local links** across the changed progress, docs index and evidence documents resolved. `git diff --check` passed.

The full backend suite, backend image build, Compose smoke, external-read/write integration and product dispatch were not repeated. The control database is assumed intact: deleting/replacing it together with the ledger, stale database-plus-ledger restore, physical power loss, production key/transport lifecycle, hostile hosts and production integrations remain unverified. The fixture signature authenticates a local key holder's metadata, not external execution truth.

## Next task and limits

Next add a separate fixture-only acceptance step for an exact signed fake-ledger receipt under fresh authority. It must persist at most one immutable synthetic receipt for a consumed admission, preserve unknown admission after rejected or missing receipts, and replay an exact accepted result without another ledger mutation. Keep this separate from product dispatch and model context. Continue to leave real writes, paid activation, merge, public deployment and production integration disabled.
