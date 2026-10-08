# Phase 4 artifact and memory gate

Date: 2026-10-08. Branch: `phase-4-artifact-gate`. Parent: Phase 4.4 draft PR #23.

## Evidence and result

Phase 4's fixture gate passed. Prior slices added a scoped knowledge ledger,
owner-reviewed memory candidates, lexical search, and cited summaries with
bounded context. This slice adds exact artifact retrieval that validates the
project, immutable version chain, execution/task/author relationship, storage
path, byte count and SHA-256 digest. Agent reads authorize project execution
before looking up an artifact version. The owner exact-version response now
includes task, execution, author, parent, digest, MIME and size provenance.

An active memory record citing an artifact version cannot enter search results
or assembled model context when those artifact bytes are missing or corrupt.
The error fails closed. Explicit owner supersession checks an exact old-record
state hash and an active same-project, same-subject replacement, preserves the
old record and links it to the replacement. Search and context exclude the
superseded record; a summary citing it is omitted until revised.

Using the disposable PostgreSQL fixture databases and local Compose setup:

```sh
cd backend
APP_DATABASE_URL=postgresql+psycopg://postgres:phase1fixture@127.0.0.1:55433/workforce_test /tmp/foundation-venv/bin/alembic -c alembic.ini check
cd ..
PYTHONPATH=backend/src APP_DATABASE_URL=postgresql+psycopg://postgres:phase1fixture@127.0.0.1:55433/workforce_test INITIAL_ADMIN_PASSWORD_FILE=/tmp/test-secret SESSION_COOKIE_SECURE=false /tmp/foundation-venv/bin/pytest -q backend/tests
docker build --secret id=proxy_ca,src="$CODEX_PROXY_CERT" -f docker/backend.Dockerfile -t workforce-backend:phase1 .
docker compose up -d --no-build --force-recreate migrate api worker web
python scripts/smoke.py
```

Alembic reported no pending schema operations. **67 backend tests passed**.
The artifact fixture retrieved two different immutable versions from a fresh
session, traced a memory citation to the second version, denied the wrong
project, and rejected corrupted bytes and an out-of-store path. Existing
approval tests cover stale replacement, changed approval and retry after a
synthetic checkpoint failure. The supersession fixture verified stale-hash and
cross-project denial, preserved the old record, and removed it from current
retrieval while invalidating its summary. The non-root backend image built;
local Compose migration/API/worker/web started with a healthy API; fixture
smoke passed.

## Limits and next phase

The retrieval fixture is small and does not justify semantic search. The owner
memory and summary workflows currently have private APIs rather than a review
screen. No live model, production integration or public deployment was used.
Phase 5 adds a governed tool gateway, deterministic resource policy and durable
exact-effect approvals before any broader tool access.
