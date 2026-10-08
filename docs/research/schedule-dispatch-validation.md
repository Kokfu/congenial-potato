# Durable daily schedule dispatch: Phase 6.2

Date: 2026-10-08. Branch: `phase-6-schedule-dispatch`. Parent: Phase 6.1 draft PR #30.

DBOS owns a single UTC minute tick (`workforce-daily-tick-v1`, six-field cron
`0 * * * * *`, automatic backfill disabled). Each tick calls the application
occurrence admission service. Worker startup also reconciles due schedules so
an occurrence missed while the process is stopped is considered once. The
application keeps the configured IANA local time, a monotonic checked cursor
and an occurrence ledger with a unique schedule/date key. A single database
transaction locks each enabled schedule, checks due time and overlap, checks
the current agent project grant and config, then creates a task, assignment,
root budget, execution and outbox event. The existing DBOS execution worker
consumes that event outside the HTTP request. Repeated or concurrent ticks
cannot create a second logical occurrence.

An active prior task (`queued`, `running`, `review` or `unknown`) causes the
next due occurrence to be recorded as skipped. A revoked project grant also
records a skipped occurrence with a reason. A disabled schedule never runs;
enabling it requires the grant and resets the cursor to activation time.
Schedule status changes require the expected revision. The owner can list
occurrences by schedule. The ledger's `queued` status records the admission
outcome; execution status is read from the execution endpoint.

## Reproduce

```sh
cd backend
APP_DATABASE_URL=postgresql+psycopg://postgres:phase1fixture@127.0.0.1:55433/workforce_test /tmp/foundation-venv/bin/alembic -c alembic.ini upgrade head
APP_DATABASE_URL=postgresql+psycopg://postgres:phase1fixture@127.0.0.1:55433/workforce_test /tmp/foundation-venv/bin/alembic -c alembic.ini check
cd ..
PYTHONPATH=backend/src APP_DATABASE_URL=postgresql+psycopg://postgres:phase1fixture@127.0.0.1:55433/workforce_test INITIAL_ADMIN_PASSWORD_FILE=/tmp/test-secret SESSION_COOKIE_SECURE=false /tmp/foundation-venv/bin/pytest -q backend/tests
docker build --secret id=proxy_ca,src="$CODEX_PROXY_CERT" -f docker/backend.Dockerfile -t workforce-backend:phase1 .
docker compose up -d --no-build --force-recreate migrate api worker web
python scripts/smoke.py
python scripts/schedule_restart.py prepare --state /tmp/workforce-schedule-restart.json
docker compose stop worker
# After the printed due time:
docker compose start worker
python scripts/schedule_restart.py finish --state /tmp/workforce-schedule-restart.json
```

Alembic upgraded the disposable database and found no pending operations.
**99 backend tests passed.** Deterministic fixtures covered concurrent ticks,
replay, monotonic cursor, one occurrence/root/outbox, overlap, revocation and
disabled state. The non-root backend image built. Compose migration succeeded,
API/database were healthy, and the fixture smoke test passed. The DBOS
workflow database contained exactly one active minute schedule with automatic
backfill disabled; its `last_fired_at` advanced to a real UTC minute before
the worker was stopped. The restart fixture scheduled a synthetic run for
07:56 UTC, stopped the worker before that time, restarted it after 07:56 and
reported `occurrences=1; execution=succeeded`. Startup reconciliation,
rather than an HTTP request or browser session, admitted that missed run. At
07:57 the DBOS minute tick advanced `last_fired_at`, and repeating the finish
check still found one occurrence.

## Remaining limits

The startup reconciler coalesces missed daily occurrences to one inside 24
hours; older occurrences are intentionally skipped. An occurrence admitted
just before a crash is recovered through the application outbox. The
application schema and DBOS workflow database need consistent backup and
restore. Schedule code changes still require versioned workflow rollout;
this test does not prove incompatible version recovery. Daily budget
integration and activity SSE are tasks 6.4 and 6.3. No paid provider or
external integration was enabled.
