# Phase 5.2 tool policy validation

Date: 2026-10-08. Branch: `phase-5-tool-policy`. Parent: Phase 5.1 draft PR #25.

## Scope

Migration `f62a9d017c3b` constrains policy effect/revision, makes each
subject/action/resource rule unique, and records a proposal policy decision and
rule revision snapshot. Owner-only API writes canonical project or agent rules
for known tools and resources. Evaluation requires the existing project grant,
at least one project ceiling rule and one agent rule. Empty or malformed policy
denies. Any explicit deny wins; otherwise `require_approval` wins over allow.
Rules can cover a project or one exact artifact/version resource. A policy edit
increments the rule revision and creates an audit event.

Worker-generated tool proposals are now persisted as `denied`, `admitted` or
`awaiting_approval` according to the deterministic evaluator. Even admitted
proposals have no effect execution path yet. Cancellation invalidates admitted
or awaiting-approval proposals. MCP discovery/transport remains outside this
authority decision.

## Reproduction and observed results

Using disposable PostgreSQL and DBOS fixture databases plus local Compose:

```sh
cd backend
APP_DATABASE_URL=postgresql+psycopg://postgres:phase1fixture@127.0.0.1:55433/workforce_test /tmp/foundation-venv/bin/alembic -c alembic.ini upgrade head
APP_DATABASE_URL=postgresql+psycopg://postgres:phase1fixture@127.0.0.1:55433/workforce_test /tmp/foundation-venv/bin/alembic -c alembic.ini check
cd ..
PYTHONPATH=backend/src APP_DATABASE_URL=postgresql+psycopg://postgres:phase1fixture@127.0.0.1:55433/workforce_test INITIAL_ADMIN_PASSWORD_FILE=/tmp/test-secret SESSION_COOKIE_SECURE=false /tmp/foundation-venv/bin/pytest -q backend/tests
docker build --secret id=proxy_ca,src="$CODEX_PROXY_CERT" -f docker/backend.Dockerfile -t workforce-backend:phase1 .
docker compose up -d --no-build --force-recreate migrate api worker web
python scripts/smoke.py
```

Alembic found no pending operations. **76 backend tests passed**. Fixtures
verified default deny, a missing project or agent rule, exact-resource deny
over broader allow, project approval ceiling, rule revision, unknown action,
malformed resource and revoked project grant. Worker tests persisted denied,
admitted and awaiting-approval decisions without artifact effects. The non-root
image built; local Compose migration/API/worker/web started with a healthy API;
fixture smoke passed.

## Remaining boundary

Approval and effect execution are not implemented for tool invocations yet.
Tasks 5.3 and 5.4 must recheck current policy and resource state at those
boundaries and reject stale policy snapshots. No external tool, paid model or
production credential was used.
