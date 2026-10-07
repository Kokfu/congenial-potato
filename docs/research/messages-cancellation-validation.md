# Phase 3 sender-bound messages and execution-tree cancellation

Validated 2026-10-08 on `phase-3-messages-cancellation`, based on PR #17's commit `b07075b`. These are synthetic owner commands; no live provider, external tool or production integration was used.

## Behavior

- An authenticated owner can record a task message on behalf of a running or completed source execution. The sender agent ID comes from that execution, not request input. The source and recipient must have current `project.execute` grants in the target task's project. Messages are stored with task, sender execution, recipient, correlation key, payload digest, reply link and audit event. Reads identify their trust origin as `agent_message`.
- An exact correlation replay returns the same message; changed payload or task is refused. A reply must be from the prior recipient to the prior sender on the same task. Reply depth is capped at three, with twenty messages per execution and one hundred per task. Recording a message triggers no model response.
- Cancelling any execution cancels its descendants under the root admission lock. Queued/running descendants become cancelled; succeeded descendants retain their recorded result but become ineligible for new delegation, messages or artifact effects. Pending/approved artifact proposals are invalidated where immediately lockable; the worker sweeps any rows that were locked during cancellation. The artifact gateway rechecks cancellation before effect.
- Delegation and message admission now refresh locked ORM objects after waiting for a row lock. The concurrency test first exposed a stale identity-map race that could create a child after root cancellation. Refreshing the locked root and source rows closes that race. The task graph and plan admission paths received the same lock-refresh correction.

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

- The disposable database upgraded to `d2b084f1ac95`; Alembic found no pending metadata operations.
- All 45 backend tests passed. Three new tests verified cancellation of two queued children after an approved artifact proposal, no child model calls or artifact effect after DBOS dispatch, single audit record per cancelled execution, sender/recipient binding, exact message replay, reply depth and rejection after cancellation. The delegation/cancellation race passed four targeted runs after the lock-refresh fix and passed in the full suite.
- The non-root backend image built from the pinned lock. Local Compose recreated migration, API and worker containers; migration exited successfully and API/PostgreSQL reported healthy. `python scripts/smoke.py` passed with unauthorized dispatch 403, synthetic execution succeeded, task in review and audit present.
- Running provider calls may still return after cancellation; completion rechecks cancellation and cannot propose a later artifact. A provider-side unknown outcome still needs cost/effect reconciliation. Message contents remain untrusted model input. Automatic agent message generation, plan extraction and delegation requests are not yet wired to the runtime; the Phase 3 product gate stays open for that work.
