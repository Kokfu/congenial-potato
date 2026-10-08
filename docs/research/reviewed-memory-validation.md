# Phase 4.2 reviewed memory validation

Date: 2026-10-08. Branch: `phase-4-reviewed-memory`. Parent: Phase 4.1 draft PR #20.

## Scope and behavior

`memory.v1` is an application-owned structured output contract. The synthetic
`fixture-memory` adapter emits JSON into the ordinary worker completion path.
Strict parsing rejects duplicate keys, extra fields and false authority. A
successful execution creates at most one unverified candidate with its own
execution as the source. The candidate hash binds its project, agent, execution,
subject, content, trust origin and source references. Invalid output creates an
audit denial and no memory effect.

The private, CSRF-protected owner API lists project candidates and accepts an
exact hash for approve/reject. Approval rechecks the agent grant, cited sources,
execution state and current project claims. A decision becomes an
`approved_decision` only on owner approval. When active records share the subject,
the owner must acknowledge their exact IDs; a conflict edge is stored and both
records remain. Cancellation invalidates pending candidates. No agent can
promote itself or overwrite an existing record.

## Reproduction and observed results

Using the disposable PostgreSQL fixture databases and local Compose setup:

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

Alembic found no pending schema operations. **61 backend tests passed**. The
new tests exercise worker-generated candidates, owner promotion, exact conflict
acknowledgment, changed payload denial, malformed JSON denial, revoked grants
and cancellation. The non-root backend image built; local Compose migration,
API, worker and web started with a healthy API; fixture smoke passed.

## Boundary

This is a private API review flow, with no Phase 4 memory review screen yet.
It uses synthetic provider output and local fixture databases. Lexical retrieval,
cited summaries, artifact provenance and a Phase 4 gate are next. Reviewed
approval records the owner's decision; it does not prove a model claim true.
