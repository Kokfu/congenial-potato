# Phase 4.1 scoped knowledge ledger validation

Date: 2026-10-08. Branch: `phase-4-memory-ledger`. Parent: Phase 3.6 draft PR #19.

## Scope

Migration `f02a917b45e6` adds project-scoped `memory_records` and normalized
`memory_sources`. Records distinguish facts, decisions, observations and claims;
trust origin, creator, status, validity and supersession are explicit. Database
checks reject invalid kind, trust origin, status and validity intervals. Agent
candidates may carry only external-claim or model-inference authority and must
cite one to twenty same-project sources. They stay unverified until later review.
The ledger service authorizes project execution before record metadata/content
queries, and all reads retain a project predicate. Active-only listing excludes
unreviewed candidates; exact lookup still supports authorized review.

## Reproduction and observed results

Use the disposable `workforce_test` PostgreSQL database and fixture Compose
configuration documented in the repository README. The commands run were:

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

Migration succeeded; Alembic reported no new upgrade operations. The complete
backend suite passed **57 tests**. The backend image built, the local Compose
migration/API/worker/web started with a healthy API, and fixture smoke passed.
The two ledger tests cover same-project lineage, candidate isolation,
cross-project record denial, source mismatch denial and false authority denial.

## Boundary and next work

This slice introduces no model-driven memory write or public memory API. The
next task adds reviewed promotion, contradiction preservation and source
lineage rules. Lexical retrieval, cited summaries and artifact provenance remain
separate Phase 4 tasks. All data and calls used local synthetic fixtures.
