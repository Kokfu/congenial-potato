# Phase 4.3 lexical memory validation

Date: 2026-10-08. Branch: `phase-4-lexical-memory`. Parent: Phase 4.2 draft PR #21.

## Scope

Migration `f32c6ea491b8` adds a generated English PostgreSQL `tsvector` column
and GIN index to project memory. `search_records` authorizes the agent before
search, then filters active, currently valid records by project in SQL before
ranking. Snippets are built only from returned rows. The private owner API uses
the same search query after session authentication and a project existence
check. The query is capped at 200 characters, results at 50, snippets at about
240 characters. No embedding, vector extension or extra database is used.

## Reproduction and results

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

Alembic reported no new upgrade operations. **63 backend tests passed**.
Fixed fixtures found the current retention requirement and excluded an expired
rule, unreviewed candidate, superseded rule, unrelated conversation and a
different project's matching private rule. A denied agent could not search the
private project. Invalid bounds failed. The non-root backend image built;
local Compose migration/API/worker/web started with a healthy API; fixture
smoke passed.

During development, Alembic could not compare a raw expression index cleanly.
The final migration instead uses a generated `tsvector` column and GIN index.
Only the disposable test database's intermediate index was replaced while
verifying the final migration. The committed migration upgrades directly from
Phase 4.2 and was also exercised by local Compose.

## Limits

Lexical matching can miss paraphrases and rare terms. Retrieval quality is
measured only against a small deterministic fixture, so no semantic index is
justified yet. Cited summaries, context assembly and artifact provenance are
later Phase 4 tasks. All data and calls were local synthetic fixtures.
