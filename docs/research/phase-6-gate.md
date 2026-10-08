# Phase 6 fixture gate: schedules, activity and daily budget

Date: 2026-10-08. Branch: `phase-6-fixture-gate`. Parent: Phase 6.4 draft PR #33.

## Result

**Passed for the fixture-only control plane.** Phase 6 now has an
owner-managed daily schedule contract, a DBOS minute tick and worker startup
reconciliation, a unique occurrence ledger, nonoverlap and bounded missed-run
rules, project-scoped persisted activity with SSE reconnect cursors, and a
shared UTC daily cost hold used by scheduled and delegated priced fixtures.
Individual experiments and commands are in the Phase 6.1–6.4 documents.

This gate filled activity gaps for tool proposals, exact approval decisions,
synthetic tool effects and runtime collaboration proposals/decisions. The
activity rows contain action, resource, outcome and time; tests verified that
tool payload and message content do not appear in them. The full audit
ledger remains the detailed provenance source. The activity cursor moved
from the Project row to a dedicated per-project row. That avoids a lock
cycle between worker execution completion and delegation's Project lock.
Migration backfilled the cursor from existing project sequence values.

## Gate evidence

From the repository root with the disposable PostgreSQL/DBOS fixtures and
the loopback-only Compose stack:

```sh
cd backend
APP_DATABASE_URL=postgresql+psycopg://postgres:phase1fixture@127.0.0.1:55433/workforce_test /tmp/foundation-venv/bin/alembic -c alembic.ini upgrade head
APP_DATABASE_URL=postgresql+psycopg://postgres:phase1fixture@127.0.0.1:55433/workforce_test /tmp/foundation-venv/bin/alembic -c alembic.ini check
cd ..
PYTHONPATH=backend/src APP_DATABASE_URL=postgresql+psycopg://postgres:phase1fixture@127.0.0.1:55433/workforce_test INITIAL_ADMIN_PASSWORD_FILE=/tmp/test-secret SESSION_COOKIE_SECURE=false /tmp/foundation-venv/bin/pytest -q backend/tests
cd frontend && npm run test:e2e && cd ..
docker build --secret id=proxy_ca,src="$CODEX_PROXY_CERT" -f docker/backend.Dockerfile -t workforce-backend:phase1 .
docker compose up -d --no-build --force-recreate migrate api worker web
python scripts/smoke.py
```

Alembic reported no pending metadata operations. **102 backend tests**
passed; the **4 Chromium tests** passed, including SSE disconnect and
`Last-Event-ID` resume. The non-root backend image built. Compose migration
exited successfully, API/database were healthy, worker and web ran, and
fixture smoke passed (`unauthorized_dispatch=403`, execution succeeded,
task in review, audit present). Before the Compose migration there were 68
projects with a maximum activity sequence of 8; after backfill there were
68 cursor rows with the same maximum sequence. Focused tests traced pending
tool approval through owner decision and fake effect, plus a reviewed
collaboration message, without activity content leakage.

Earlier Phase 6 evidence includes an actual stopped-worker schedule
occurrence recovered once after restart, a later DBOS minute tick that did
not duplicate it, concurrent tick deduplication, overlap and revoked-grant
skips, DST gap/fold rules, 24-hour missed-run coalescing, and a scheduled
root/delegated child competing for one daily allowance with an uncertain
hold retained. No browser session is needed for dispatch or recovery.

## Limits and next slice

The running provider registry remains fixture-only. No paid calls, public
deployment, production integration, arbitrary shell, browser automation or
external write was enabled. SSE uses short database polling and has not been
load-tested for many clients. The initial activity set now covers core tool
and collaboration milestones; other detailed audit actions can be promoted
as product needs become concrete. DBOS workflow-code upgrade compatibility
still needs a versioned rollout and drain test. An uncertain real provider or
external effect requires independent reconciliation before retry.

No ADR revision was needed: the implementation follows the approved
deterministic control layer and DBOS workflow boundary. The smallest next
slice is Phase 7.1: define one bounded external-read request/result contract
and a deny-by-default destination policy, exercised only against a local
synthetic HTTP server. It must reject private/loopback destinations unless a
test-only local fixture route is explicitly authorized, and preserve source
provenance without treating returned content as instructions.
