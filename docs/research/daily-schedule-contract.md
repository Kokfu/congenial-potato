# Daily schedule contract: Phase 6.1

Date: 2026-10-08. Branch: `phase-6-schedule-contract`. Parent: Phase 5 draft PR #29.

An authenticated owner can create and list project-scoped daily schedule
definitions. Creation requires the target agent's `project.execute` grant.
Input validates an IANA timezone, `HH:MM` local wall time and positive root
cap. Schedules are stored **disabled**; no clock loop or automatic execution
was enabled in this slice. The migration adds project/agent foreign keys and
database bounds for time, cap and revision.

The pure due-time function takes an explicit `after` and `now`, so tests do
not depend on the host clock. It returns at most one latest occurrence in a
24-hour window, keyed by schedule ID and local calendar date. A nonexistent
spring-forward wall time is skipped. A repeated fall-back wall time uses its
first occurrence. UTC instants are stored for dispatch; the local date stays
in the key. `after` is exclusive and `now` inclusive. The 24-hour lookback
prevents unbounded catch-up after a long outage.

## Verification

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

Alembic upgraded the disposable database and reported no pending metadata
operations. **96 backend tests passed**, including due-time coalescing, DST
gap/fold behavior, grant denial and schedule API validation. The non-root
backend image built. Compose migration exited successfully; API and database
were healthy, the worker ran, and the fixture smoke test passed. The first
image had unreadable new source files for the non-root user; file modes were
fixed and the image rebuilt. A later Compose recreation ran out of disk
space; unused build cache and dangling images were pruned, then recreation
succeeded. No volumes or application records were removed.

## Next acceptance boundary

Phase 6.2 must add an occurrence ledger and durable dispatch, recheck grants
and budgets, and enforce nonoverlap while another occurrence is active. Tests
must restart before/after a due time, submit the same occurrence concurrently
and bound missed runs. The current `latest_due` function is a contract, not a
running scheduler. No paid provider or external integration was used.
