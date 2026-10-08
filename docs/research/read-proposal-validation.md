# Inert web-read proposals: Phase 7.4b

Date: 2026-10-08. Branch: `phase-7-read-proposals`. Parent: Phase 7.4a draft PR #38.

The gateway now parses `project.web.read` version 1 with an exact project, HTTPS URL, at most 65,536 response bytes and a maximum five-second request deadline. It canonicalizes the URL's host into `project:{id}/web-origin:{host}`, rejecting credentials, fragments, non-443 ports and malformed authorities. The policy evaluator requires both the project ceiling and agent grant; exact origin denies override broader allows. An active persistent destination grant and `project.execute` scope are also required before a proposal can remain open. Redirect responses remain blocked by the isolated network connector; the product effect path is not connected.

Authorized proposals are stored with status `proposed`. The action has a definition-level approval requirement, but **no approval is created yet**. The worker scans only `admitted` invocations, so it cannot execute this action. Cancellation invalidates a proposed invocation. Denied proposals are retained for owner visibility, without performing DNS or making a request. This staging is deliberate: Phase 7.4c must build the exact approval and effect path with grant revision, cancellation and budget rechecks before an action may become admitted. Changing the action's schema or approval contract changes the schema hash and invalidates old proposals.

The gateway tests use fixture-provider output and disposable PostgreSQL/DBOS. They confirm a scoped proposal remains inert, cancellation invalidates it, missing policy denies it, and the policy evaluator applies exact-origin deny precedence. No real external site, paid model, credential or production integration was contacted.

## Reproduce

```sh
PYTHONPATH=backend/src APP_DATABASE_URL=postgresql+psycopg://postgres:phase1fixture@127.0.0.1:55433/workforce_test INITIAL_ADMIN_PASSWORD_FILE=/tmp/test-secret SESSION_COOKIE_SECURE=false /tmp/foundation-venv/bin/pytest -q backend/tests/test_tool_gateway.py backend/tests/test_tool_policy.py backend/tests/test_read_grants.py
PYTHONPATH=backend/src APP_DATABASE_URL=postgresql+psycopg://postgres:phase1fixture@127.0.0.1:55433/workforce_test INITIAL_ADMIN_PASSWORD_FILE=/tmp/test-secret SESSION_COOKIE_SECURE=false /tmp/foundation-venv/bin/pytest -q backend/tests
docker build --secret id=proxy_ca,src="$CODEX_PROXY_CERT" -f docker/backend.Dockerfile -t workforce-backend:phase1 .
docker compose up -d --no-build --force-recreate migrate api worker web
python scripts/smoke.py
```

All **115 backend tests** passed on the proposal implementation. After a final pure URL whitespace check, **18 focused gateway, policy, grant and network tests** passed. The non-root backend image built on final source. Compose migration exited successfully, API reached healthy status, and the local fixture smoke reported `smoke=passed; unauthorized_dispatch=403; execution=succeeded; task=review; audit=present`.
