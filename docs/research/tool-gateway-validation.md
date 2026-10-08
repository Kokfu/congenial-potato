# Phase 5.1 typed tool gateway validation

Date: 2026-10-08. Branch: `phase-5-tool-gateway`. Parent: Phase 4.5 draft PR #24.

## Scope

Migration `f52a183b64d0` records one tool proposal per execution. The
application-owned registry defines three versioned local actions: project
memory search, artifact version read and synthetic artifact write. Each pins a
strict input schema and hash, effect classification and canonical resource
extractor. The `tool.v1` output contract parses fixture model JSON, rejects
duplicate keys, unexpected fields, unknown actions, wrong versions, invalid
UUIDs, oversized content and cross-project resources. Project authority is
checked against the execution task. No proposal executes a tool in this slice;
its persisted status is `proposed`. Replayed completion does not create another
invocation, and cancellation invalidates a pending proposal. The owner can
inspect proposals through an authenticated private API.

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

Alembic found no pending schema operations. **73 backend tests passed**.
The six gateway tests include a worker-generated write proposal with canonical
resource and hashes, no artifact effect, replay deduplication, cancellation,
cross-project denial, extra-field denial, unknown action and wrong-version
denial. The non-root backend image built; local Compose migration/API/worker/web
started with a healthy API; fixture smoke passed.

## Next boundary

Phase 5.2 adds deterministic policy and resource grants. Phase 5.3 binds
approval to an exact effect, and Phase 5.4 executes only isolated synthetic
effects. Current tool proposals confer no permission and have no execution
path. No external tool, paid model or production credential was used.
