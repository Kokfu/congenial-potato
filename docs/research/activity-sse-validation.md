# Project activity and SSE: Phase 6.3

Date: 2026-10-08. Branch: `phase-6-activity-sse`. Parent: Phase 6.2 draft PR #31.

The project activity ledger has a per-project sequence number allocated while
holding the project row lock. This makes the cursor follow commit order for
writers using `record_activity`, without PostgreSQL sequence gaps exposing
uncommitted events. The authenticated REST endpoint reads at most 100 events
after a cursor. The SSE endpoint accepts a query cursor or `Last-Event-ID`,
sends an immediate connection frame, polls persisted rows, sends heartbeat
comments and closes after 30 seconds so reconnect revalidates the owner
session. It checks project existence before streaming and reads only rows
whose project ID matches the URL. Streams run outside the HTTP command
lifetime; they are an observation channel over committed state.

The Activity tab loads a scoped snapshot, then subscribes after its last
sequence. It closes the EventSource on tab/project change and keeps the last
100 displayed rows. The initial coverage records project and task creation,
execution dispatch/completion or model failure, root cancellation, artifact
approval and schedule occurrence admission or skip. The global audit ledger
still retains the fuller action history. Future work should emit project
activity for tool and collaboration transitions before treating this timeline
as complete provenance.

## Reproduce and observed result

```sh
cd backend
APP_DATABASE_URL=postgresql+psycopg://postgres:phase1fixture@127.0.0.1:55433/workforce_test /tmp/foundation-venv/bin/alembic -c alembic.ini upgrade head
APP_DATABASE_URL=postgresql+psycopg://postgres:phase1fixture@127.0.0.1:55433/workforce_test /tmp/foundation-venv/bin/alembic -c alembic.ini check
cd ..
PYTHONPATH=backend/src APP_DATABASE_URL=postgresql+psycopg://postgres:phase1fixture@127.0.0.1:55433/workforce_test INITIAL_ADMIN_PASSWORD_FILE=/tmp/test-secret SESSION_COOKIE_SECURE=false /tmp/foundation-venv/bin/pytest -q backend/tests
cd frontend && npm run build && npm run test:e2e && cd ..
docker build --secret id=proxy_ca,src="$CODEX_PROXY_CERT" -f docker/backend.Dockerfile -t workforce-backend:phase1 .
docker build --secret id=proxy_ca,src="$CODEX_PROXY_CERT" -f docker/web.Dockerfile -t workforce-web:phase1 .
docker compose up -d --no-build --force-recreate migrate api worker web
python scripts/smoke.py
```

Alembic upgraded the disposable database and reported no pending operations.
**100 backend tests** passed, including project scope and concurrent writers
with contiguous cursors. Frontend build and **4 Chromium tests** passed. The
activity browser test observed a new event over SSE, left the tab, then
reloaded a missed event from persisted state. Explicit query-cursor and
`Last-Event-ID` streams both resumed at sequence 3. The first browser run
found the SSE handshake waited for a heartbeat; an immediate comment frame
fixed it. Both non-root images built, Compose migrated and started with a
healthy API, and fixture smoke passed. One web image build without the
configured proxy certificate failed inside `npm ci`; the build with that
certificate succeeded. No live provider or external service was used.

## Remaining limits

The stream uses database polling every 0.5 seconds for the single-owner MVP.
Each connection lasts at most 30 seconds, with a 10-second heartbeat; this
sets a bound on stale authentication. The initial REST snapshot returns the
oldest 100 rows after the requested cursor, and the stream catches up in
batches. Browser reload starts at its REST snapshot rather than retaining a
cursor in local storage. Activity events are metadata only; detailed audit
records remain in the audit ledger. The SSE endpoint has not been load-tested
for many simultaneous clients.
