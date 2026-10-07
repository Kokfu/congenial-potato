# Phase 3 task graph foundation

Date: 2026-10-08. This is a deterministic task-control slice with synthetic data. It does not implement Manager planning, agent messages or direct delegation yet.

## Contract

`TaskDependency` persists a project-scoped prerequisite edge. The owner API creates or lists edges. The application service locks the project before mutating its graph and the dependent task before adding an edge. It rejects self-links, cross-project links, cycles and changes after the dependent task has been admitted. A duplicate request returns the same edge without another audit event. Task dispatch checks that every prerequisite is `completed`; incomplete dependencies block the transition before execution/outbox creation.

The project lock serializes competing edge additions. The dependent task lock serializes edge admission against dispatch. PostgreSQL also enforces distinct endpoints and unique prerequisite/dependent pairs. Migration `d07f414db7a2` adds the table and lookup index.

## Reproduce

With disposable PostgreSQL `workforce_test` and `workforce_dbos_test` databases:

```sh
cd backend
APP_DATABASE_URL=postgresql+psycopg://postgres:<test-password>@127.0.0.1:55433/workforce_test alembic -c alembic.ini upgrade head
APP_DATABASE_URL=postgresql+psycopg://postgres:<test-password>@127.0.0.1:55433/workforce_test alembic -c alembic.ini check
cd ..
PYTHONPATH=backend/src APP_DATABASE_URL=postgresql+psycopg://postgres:<test-password>@127.0.0.1:55433/workforce_test INITIAL_ADMIN_PASSWORD_FILE=<synthetic-secret-file> SESSION_COOKIE_SECURE=false pytest -q backend/tests
```

The targeted PostgreSQL tests create an A→B→C chain, reject C→A, a self-link and a cross-project link, verify duplicate edge idempotency, and deny dispatch of B until A is marked completed. Two concurrent opposite edge requests leave exactly one edge and one cycle rejection. `alembic check` reported no new operations after the migration.

## Remaining Phase 3 work

The test marks a prerequisite completed directly in its disposable database. An owner acceptance transition, Manager plan proposals, assignment/delegation authority, root-shared limits, messages and cancellation-tree behavior remain separate tasks. This graph service cannot by itself authorize a new agent execution or create a child budget.

Result: **37 backend tests passed**. The backend image built; the local Compose migration reached `d07f414db7a2`, API/worker restarted, and `python scripts/smoke.py` passed (unauthorized dispatch denied, synthetic execution succeeded, task review and audit present). No paid call or production integration was used.
