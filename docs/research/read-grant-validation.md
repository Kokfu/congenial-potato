# Persistent exact destination grants: Phase 7.4a

Date: 2026-10-08. Branch: `phase-7-read-grants`. Parent: Phase 7.3 draft PR #37.

An owner can now create, revise and disable a grant for one project, agent and canonical ASCII hostname over HTTPS port 443. The grant expires within 30 days and is useless without the agent's separate `project.execute` grant. The lookup denies absent, expired, disabled, foreign-project and foreign-host grants. The API requires the owner session and CSRF token for writes, lists only one requested project's grants, and records a revision, audit event and activity event for each change. A database uniqueness constraint covers the exact scope.

The existing isolated network experiment now uses the same pure URL validator that future proposal admission will call. It rejects malformed authorities, credentials, fragments, backslashes, leading whitespace, non-HTTPS schemes and ports other than 443 before DNS. DNS/public-address checks still occur in the isolated experiment. Grant creation does not resolve DNS, because a name's answers can change before execution; the effect path must revalidate immediately before dialing.

This slice does **not** register a product web-read tool. No worker can invoke a network effect through these grants. The gateway still recognizes only fixture memory/artifact tools. Persistent destination authority is necessary but insufficient: Phase 7.4b must bind the grant and its revision to an exact invocation, apply project and agent tool policy, cancellation, budget and any required approval, then recheck before an effect. A deployment egress boundary and complete fixture gate remain required before outbound use.

## Reproduce

```sh
cd backend
APP_DATABASE_URL=postgresql+psycopg://postgres:phase1fixture@127.0.0.1:55433/workforce_test /tmp/foundation-venv/bin/alembic -c alembic.ini upgrade head
APP_DATABASE_URL=postgresql+psycopg://postgres:phase1fixture@127.0.0.1:55433/workforce_test /tmp/foundation-venv/bin/alembic -c alembic.ini check
cd ..
PYTHONPATH=backend/src APP_DATABASE_URL=postgresql+psycopg://postgres:phase1fixture@127.0.0.1:55433/workforce_test INITIAL_ADMIN_PASSWORD_FILE=/tmp/test-secret SESSION_COOKIE_SECURE=false /tmp/foundation-venv/bin/pytest -q backend/tests/test_read_grants.py backend/tests/test_network_policy.py
PYTHONPATH=backend/src APP_DATABASE_URL=postgresql+psycopg://postgres:phase1fixture@127.0.0.1:55433/workforce_test INITIAL_ADMIN_PASSWORD_FILE=/tmp/test-secret SESSION_COOKIE_SECURE=false /tmp/foundation-venv/bin/pytest -q backend/tests
docker build --secret id=proxy_ca,src="$CODEX_PROXY_CERT" -f docker/backend.Dockerfile -t workforce-backend:phase1 .
docker compose up -d --no-build --force-recreate migrate api worker web
python scripts/smoke.py
```

Alembic reported no new metadata operations. Six focused tests and all **112 backend tests** passed. The non-root backend image built. Compose migration exited successfully, API reached healthy status, and the local fixture smoke reported `smoke=passed; unauthorized_dispatch=403; execution=succeeded; task=review; audit=present`.

No real destination, paid model, credential or production integration was contacted. The Phase 2 live activation gate remains closed.
