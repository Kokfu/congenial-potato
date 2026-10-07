# Phase 3 task acceptance and assignment validation

Validated 2026-10-08 on branch `phase-3-task-acceptance`, based on task graph commit `cca2e7b`. This remains synthetic Phase 3 work. No paid provider or external tool was used.

## Behavior

- One executor assignment per task is persisted with agent, owner and creation time. Owner assignment requires a current `project.execute` grant and active agent. A repeat for the same executor is idempotent; a different executor is refused. Assignment itself does not grant access: dispatch and the worker still check the grant.
- Owner dispatch creates the assignment in the same transaction if needed, preserving the existing dispatch flow. A preassigned task can only dispatch to its recorded executor. Task revision advances on assignment and dispatch.
- A reviewed task can be accepted by the owner at its current revision. Pending or approved artifact proposals must first be resolved. Acceptance writes an audit event, advances the revision and marks the task completed. Prerequisite checks use that completed status.
- The application retains the execution attempt and artifact approval records independently from the accepted task state. This slice allows one executor assignment per task and does not implement reassignment or retry of a failed task.

## Reproduce

Use the disposable PostgreSQL `workforce_test` and `workforce_dbos_test` databases described in the Phase 1 setup. No production database is involved.

```sh
cd backend
APP_DATABASE_URL=postgresql+psycopg://postgres:phase1fixture@127.0.0.1:55433/workforce_test /tmp/foundation-venv/bin/alembic -c alembic.ini upgrade head
APP_DATABASE_URL=postgresql+psycopg://postgres:phase1fixture@127.0.0.1:55433/workforce_test /tmp/foundation-venv/bin/alembic -c alembic.ini check
cd ..
PYTHONPATH=backend/src APP_DATABASE_URL=postgresql+psycopg://postgres:phase1fixture@127.0.0.1:55433/workforce_test INITIAL_ADMIN_PASSWORD_FILE=/tmp/test-secret SESSION_COOKIE_SECURE=false /tmp/foundation-venv/bin/pytest -q backend/tests
```

## Evidence and limits

- Alembic upgraded the disposable database to `e3a9c2704f1b`; `alembic check` found no pending metadata operations.
- All 38 backend tests passed. The Phase 3 tests verify denied assignment without a grant, one durable assignment and audit event despite repeats, rejection of a second executor, and dependent dispatch only after a synthetic workflow finishes, its artifact is approved and applied, and the owner accepts the prerequisite. Acceptance is rejected while the artifact is pending or approved and on a stale revision.
- The non-root backend image built from the pinned lock. Local Compose recreated migration, API and worker containers; migration exited successfully and API/PostgreSQL reported healthy. `python scripts/smoke.py` passed with unauthorized dispatch 403, fixture execution succeeded, task in review and audit present.
- Manager plan proposals, delegation, retries and reassignment are still outside this slice. A single assignment row is intentionally a conservative bound; future delegation will need explicit assignment lifecycle and root execution limits.
