# Phase 4.4 cited context validation

Date: 2026-10-08. Branch: `phase-4-cited-context`. Parent: Phase 4.3 draft PR #22.

## Scope

Migration `f42d97ea61c0` adds immutable project summary versions and citation
edges to memory records. The owner API creates a new version under a project
lock with an expected version and one to twenty active, current, same-project
citations. A prior version remains available. The API rejects unknown fields,
including attempts to assign human-instruction authority to a summary.

The worker now adds at most 4,000 characters of current project evidence to a
separate `external` trust message when active memory exists. It rechecks the
agent's project grant, filters records by project/status/validity, orders
approved decisions before observed results and external/model claims, and
labels each record with its stable ID and origin. It includes the newest summary
only while all its citations remain current, labels it as derived, and shows
its citation IDs. The task title remains the separate human message; the
summary is never a system instruction. No full conversation history is added.

## Reproduction and observed results

Using disposable PostgreSQL fixture databases and local Compose:

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

Alembic reported no pending operations. **65 backend tests passed**. The
new fixtures verify version preconditions, cross-project citation rejection,
summary lineage, trust ordering, bounded context, denied project reads,
expired-citation exclusion and rejection of an authority field. The non-root
backend image built; local Compose migration/API/worker/web started with a
healthy API; fixture smoke passed.

## Limits and next gate

The content of an owner-written summary is still derived data; citations and
owner review do not prove every sentence true. The deterministic orchestrator
continues to enforce authorization and approvals independently of prompt text.
Memory prompt integration was exercised by regression and fixture smoke, while
the fixed tests validate the context builder directly. Phase 4.5 must verify
artifact digest, version, project scope and citation provenance before closing
the Phase 4 gate. No paid model or external integration was used.
