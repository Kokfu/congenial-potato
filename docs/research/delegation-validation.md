# Phase 3 bounded synthetic delegation

Validated 2026-10-08 on `phase-3-governed-delegation`, based on PR #16's commit `6bd1cf8`. This is an owner-submitted synthetic command linked to a running or completed Manager or specialist execution. Agents do not yet submit delegation proposals automatically. No paid provider or external tool was used.

## Admission and execution

- The one delegation service accepts both Manager and specialist sources, with no special Manager privilege. It requires a live source/root, current source and target project grants, an active configured target, an unused project work key and a current root budget with room for at least one fixture model reservation.
- Limits are three child levels, four children per source and twelve executions per root. A request key is unique per source; an exact repeat returns the existing child, while changed arguments under the same key are denied. The child points to an existing parent, so admission cannot create a parent cycle.
- The new task and assignment, child execution, outbox dispatch and audit record commit together. Child executions retain the root ID and use its `BudgetAccount`; no child budget is minted. The existing worker rechecks grant and budget before model work. The owner can list child executions for provenance.
- Root-tree cancellation propagation and stopping queued children are part of 3.5. A single execution cancel currently does not cancel its descendants. This boundary must be closed before autonomous delegation is enabled.

## Reproduce

Use disposable PostgreSQL `workforce_test` and `workforce_dbos_test` databases.

```sh
cd backend
APP_DATABASE_URL=postgresql+psycopg://postgres:phase1fixture@127.0.0.1:55433/workforce_test /tmp/foundation-venv/bin/alembic -c alembic.ini upgrade head
APP_DATABASE_URL=postgresql+psycopg://postgres:phase1fixture@127.0.0.1:55433/workforce_test /tmp/foundation-venv/bin/alembic -c alembic.ini check
cd ..
PYTHONPATH=backend/src APP_DATABASE_URL=postgresql+psycopg://postgres:phase1fixture@127.0.0.1:55433/workforce_test INITIAL_ADMIN_PASSWORD_FILE=/tmp/test-secret SESSION_COOKIE_SECURE=false /tmp/foundation-venv/bin/pytest -q backend/tests
```

## Evidence and limits

- The disposable database upgraded to `c72f9d08b1e4`; Alembic found no pending metadata operations.
- All 42 backend tests passed. The two delegation tests executed a Manager source and child/grandchild/third-level fixture work through DBOS. They checked shared root ID and one budget account, exact replay, changed-key rejection, project grant denial, duplicate work denial, exhausted root hold denial, the fourth child-level rejection, the fifth sibling rejection and a revoked source grant. One logical delegation audit event was recorded for a replayed child.
- The non-root backend image built from the pinned lock. Local Compose recreated migration, API and worker containers; migration exited successfully and API/PostgreSQL reported healthy. `python scripts/smoke.py` passed with unauthorized dispatch 403, synthetic execution succeeded, task in review and audit present.
- The existing fixture model does not generate delegation requests. Synthetic owner submission validates admission and worker dispatch only. Approval policies for autonomous delegation, tree cancellation, automatic reply limits and agent message provenance remain future slices.
