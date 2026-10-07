# Phase 3 synthetic Manager plan validation

Validated 2026-10-08 on `phase-3-manager-plans`, based on PR #15's commit `38577e7`. This slice evaluates deterministic plan admission with fixture executions. The fixture model does not generate structured plans. An authenticated owner submits a typed synthetic candidate and links it to a completed Manager execution; `submitted_by` records that distinction. Automatic model-originated proposals remain future work.

## Contract and admission

- A proposal contains one to twelve tasks. Each has a project-local `work_key`, title, assignee and zero or more in-plan prerequisite keys. The input rejects extra fields and oversized plans. Duplicate keys, missing prerequisites, repeated edges and cycles are denied.
- The source execution must have succeeded without cancellation, belong to the target project and run under an agent whose role is Manager. Source and assignees require current `project.execute` grants; assignment never creates a grant.
- A project plan revision is checked under a project row lock. A proposal key is unique to its source execution and exact repeated submission returns the same record. Admission verifies the stored payload digest and rechecks execution, grants, keys, graph and revision. It atomically creates tasks, executor assignments, dependency edges and audit events, then advances the project plan revision. Repeated admission creates no additional work.
- Standalone owner-created tasks have no work key. Project-local work keys are unique for plan-created tasks. The owner remains the only actor allowed to admit a proposal.

## Reproduce

Use the disposable `workforce_test` and `workforce_dbos_test` PostgreSQL databases. No live provider or production integration is involved.

```sh
cd backend
APP_DATABASE_URL=postgresql+psycopg://postgres:phase1fixture@127.0.0.1:55433/workforce_test /tmp/foundation-venv/bin/alembic -c alembic.ini upgrade head
APP_DATABASE_URL=postgresql+psycopg://postgres:phase1fixture@127.0.0.1:55433/workforce_test /tmp/foundation-venv/bin/alembic -c alembic.ini check
cd ..
PYTHONPATH=backend/src APP_DATABASE_URL=postgresql+psycopg://postgres:phase1fixture@127.0.0.1:55433/workforce_test INITIAL_ADMIN_PASSWORD_FILE=/tmp/test-secret SESSION_COOKIE_SECURE=false /tmp/foundation-venv/bin/pytest -q backend/tests
```

## Evidence and limits

- The disposable database upgraded to `b8e4c1936a02`; `alembic check` found no pending operations.
- All 40 backend tests passed. The two plan tests ran a completed fixture Manager workflow through DBOS, then verified a two-task graph, one assignment per new task, one admission audit event, exact replay and rejection of a changed hash, cycles, repeated edges, duplicate keys, foreign assignees, invalid source and stale project revision.
- The non-root backend image built from the pinned lock. Local Compose recreated migration, API and worker containers; migration exited successfully and API/PostgreSQL reported healthy. `python scripts/smoke.py` passed with unauthorized dispatch 403, synthetic execution succeeded, task in review and audit present.
- A `Manager` role string is a source eligibility check, not elevated authorization. Agent-generated structured plans, owner edits, delegation, retries and cancellation of admitted child work are not implemented here. Plan tasks cannot yet be reassigned; this is the one executor bound introduced in 3.2.
