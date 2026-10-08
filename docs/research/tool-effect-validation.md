# Phase 5.4 synthetic tool effect validation

Date: 2026-10-08. Branch: `phase-5-synthetic-effects`. Parent: Phase 5.3 draft PR #27.

## Scope

Migration `f82a7c0d491e` adds a separate local synthetic effect ledger keyed
by one invocation ID. The worker rechecks source execution/cancellation, root
budget presence, canonical schema and arguments, project grant, current policy
and policy revisions, approval payload and expiry, and target preconditions
before a fake effect. Read actions store bounded IDs or artifact metadata;
write stores only a simulated digest/size. No tool writes an actual artifact or
calls an external service in this phase.

The fake ledger commits separately from the invocation checkpoint. A forced
crash immediately after ledger commit leaves the invocation admitted. On replay,
the worker sees the same ledger key and reconciles the existing effect instead
of issuing another one. A mismatched ledger fingerprint becomes `unknown` and
is never blindly retried. A later policy change, argument change or cancellation
blocks any new effect. This pattern demonstrates the need for external
idempotency/reconciliation; it does not make arbitrary external systems exactly
once. The worker only considers artifact approvals in the artifact effect sweep,
so an approved tool wait is not mistaken for an artifact approval.

## Reproduction and observed results

Using disposable PostgreSQL/DBOS fixtures and local Compose:

```sh
cd backend
APP_DATABASE_URL=postgresql+psycopg://postgres:phase1fixture@127.0.0.1:55433/workforce_test /tmp/foundation-venv/bin/alembic -c alembic.ini upgrade head
APP_DATABASE_URL=postgresql+psycopg://postgres:phase1fixture@127.0.0.1:55433/workforce_test /tmp/foundation-venv/bin/alembic -c alembic.ini check
cd ..
PYTHONPATH=backend/src APP_DATABASE_URL=postgresql+psycopg://postgres:phase1fixture@127.0.0.1:55433/workforce_test INITIAL_ADMIN_PASSWORD_FILE=/tmp/test-secret SESSION_COOKIE_SECURE=false /tmp/foundation-venv/bin/pytest -q backend/tests
docker build --secret id=proxy_ca,src="$CODEX_PROXY_CERT" -f docker/backend.Dockerfile -t workforce-backend:phase1 .
docker compose up -d --no-build --force-recreate migrate api worker web
python scripts/tool_approval_restart.py prepare --state /tmp/workforce-tool-effect-restart.json
docker compose restart api worker
python scripts/tool_approval_restart.py finish --state /tmp/workforce-tool-effect-restart.json
python scripts/smoke.py
```

Alembic reported no pending operations. **91 backend tests passed** on the
final code. Focused tests verified one fake write effect, replay with no second
effect, crash/reconciliation, mismatched unknown ledger outcome, revoked policy,
changed arguments and cancellation. The non-root image built; local Compose
migration/API/worker/web started with a healthy API. After API/worker restart,
the synthetic approval completed and the invocation succeeded with one ledger
effect and zero artifact versions. Fixture smoke passed on the final stack.

The first Compose attempt found that the artifact worker was sweeping approved
tool approvals and invalidating them. The artifact sweep was scoped to artifact
approvals, a regression test reproduced the worker loop order, and the second
Compose restart run passed. No paid model, external tool or production
credential was used.

## Phase 5 gate remaining

Task 5.5 checks concurrent admission, provenance, complete mediation, budgets
and restart behavior before closing the fixture gate. External writes and real
network tools remain deferred; an unknown real-world outcome still needs a
separate reconciliation mechanism.
