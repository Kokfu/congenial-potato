# External read observations and trust: Phase 7.3

Date: 2026-10-08. Branch: `phase-7-read-provenance`. Parent: Phase 7.2 draft PR #36.

An isolated trusted-adapter service now stores a project-scoped external
read observation with the agent, invocation key, exact source URL, retrieval
time, MIME type, byte size, SHA-256 digest, text and fixed
`external_claim` trust origin. It rechecks the agent project grant, URL,
digest, size and type before insertion. A transaction lock on the invocation
key and a unique constraint make duplicate submission one observation;
changed replay fails. The audit and activity events record metadata without
copying the untrusted text. Owner reads are project scoped, and listing
returns metadata until an exact observation is requested.

The observation table is separate from project memory. Storing an external
claim does not promote it to a human instruction, approved decision or model
system message. A synthetic hostile page asked to set grants, reveal
credentials and approve effects; the fixture observed no policy or approval
changes, and bounded model context did not include the page. These tests
exercise storage and retrieval only. A later gateway test must prove the
same behavior when the content is actually presented to an agent.

## Reproduce and observed results

```sh
cd backend
APP_DATABASE_URL=postgresql+psycopg://postgres:phase1fixture@127.0.0.1:55433/workforce_test /tmp/foundation-venv/bin/alembic -c alembic.ini upgrade head
APP_DATABASE_URL=postgresql+psycopg://postgres:phase1fixture@127.0.0.1:55433/workforce_test /tmp/foundation-venv/bin/alembic -c alembic.ini check
cd ..
PYTHONPATH=backend/src APP_DATABASE_URL=postgresql+psycopg://postgres:phase1fixture@127.0.0.1:55433/workforce_test INITIAL_ADMIN_PASSWORD_FILE=/tmp/test-secret SESSION_COOKIE_SECURE=false /tmp/foundation-venv/bin/pytest -q backend/tests/test_read_observations.py
PYTHONPATH=backend/src APP_DATABASE_URL=postgresql+psycopg://postgres:phase1fixture@127.0.0.1:55433/workforce_test INITIAL_ADMIN_PASSWORD_FILE=/tmp/test-secret SESSION_COOKIE_SECURE=false /tmp/foundation-venv/bin/pytest -q backend/tests
docker build --secret id=proxy_ca,src="$CODEX_PROXY_CERT" -f docker/backend.Dockerfile -t workforce-backend:phase1 .
docker compose up -d --no-build --force-recreate migrate api worker web
python scripts/smoke.py
```

Alembic upgraded the disposable database and reported no pending metadata
operations. **2 focused tests** and **110 backend tests** passed. They
covered missing project grant, forged trust origin, changed URL/content,
concurrent duplicate submission, immutable digest check, project-scoped
reads, metadata without page text, and unchanged grants/policies/approvals
after a synthetic injection. The non-root backend image built; local Compose
migration exited successfully, API/database were healthy, worker/web ran,
and fixture smoke passed. No real external site or paid model was contacted.

## Remaining limits

No HTTP or agent tool path writes this table yet. The service accepts a
`ReadResult` from trusted application code, but is not yet bound to a durable
tool invocation and checked network grant. Prompt injection has not been
tested inside a model turn using this page text. Phase 7.4 must connect the
approved gateway to the pinned read adapter, recheck cancellation, budget
and policy around the effect, and test a hostile result against the actual
agent/tool boundary. Persistent destination grants and egress isolation
remain required before any product outbound read is enabled.
