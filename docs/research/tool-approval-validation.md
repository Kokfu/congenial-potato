# Phase 5.3 durable tool approval validation

Date: 2026-10-08. Branch: `phase-5-tool-approval`. Parent: Phase 5.2 draft PR #26.

## Scope

Migration `f72a0d46b931` links an approval to exactly one tool invocation.
For `require_approval` policy, the worker persists a pending approval with a
canonical payload binding execution, project, action/version, arguments,
argument and schema hashes, resource and target version. It has a one-day
expiry and stable invocation key. The private owner decision API checks the
exact payload hash, current schema and canonical arguments, source execution,
project grant, policy decision/revision snapshot, cancellation, expiry and
artifact target precondition. Changed state invalidates or expires the wait;
approval admits only the existing invocation and does not execute a tool.
Artifact approvals remain on their separate route and are not confused with
tool approvals in the owner list.

## Reproduction and observed results

Using disposable PostgreSQL/DBOS fixtures, the local Compose stack and its
synthetic owner password file:

```sh
cd backend
APP_DATABASE_URL=postgresql+psycopg://postgres:phase1fixture@127.0.0.1:55433/workforce_test /tmp/foundation-venv/bin/alembic -c alembic.ini upgrade head
APP_DATABASE_URL=postgresql+psycopg://postgres:phase1fixture@127.0.0.1:55433/workforce_test /tmp/foundation-venv/bin/alembic -c alembic.ini check
cd ..
PYTHONPATH=backend/src APP_DATABASE_URL=postgresql+psycopg://postgres:phase1fixture@127.0.0.1:55433/workforce_test INITIAL_ADMIN_PASSWORD_FILE=/tmp/test-secret SESSION_COOKIE_SECURE=false /tmp/foundation-venv/bin/pytest -q backend/tests
docker build --secret id=proxy_ca,src="$CODEX_PROXY_CERT" -f docker/backend.Dockerfile -t workforce-backend:phase1 .
docker compose up -d --no-build --force-recreate migrate api worker web
python scripts/tool_approval_restart.py prepare --state /tmp/workforce-tool-approval-restart.json
docker compose restart api worker
python scripts/tool_approval_restart.py finish --state /tmp/workforce-tool-approval-restart.json
python scripts/smoke.py
```

Alembic found no pending operations. **84 backend tests passed**. The new
approval fixtures covered owner approval/rejection, wrong hash, changed
arguments/schema/policy/target, expiry and cancellation. Each invalidated case
left no tool effect. The non-root backend image built and local Compose was
healthy. The `prepare` script persisted a pending approval with zero effects;
after API and worker container restart, a fresh client observed it and approved
the same invocation. It became admitted with zero effects. Fixture smoke passed.

The first script attempt failed before creating a proposal because an `httpx`
client was entered twice; the script was corrected and both stages then passed.
No paid model, external tool or production credential was used.

## Remaining boundary

The tool invocation is admitted but intentionally has no execution adapter
yet. Phase 5.4 must recheck this exact approval and current policy immediately
before a bounded synthetic effect, and reconcile unknown outcomes without
blind retries. Approval is an authorization decision, not proof of success.
