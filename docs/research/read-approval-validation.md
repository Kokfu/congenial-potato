# Staged exact web-read approval: Phase 7.4c

Date: 2026-10-08. Branch: `phase-7-read-approval`. Parent: Phase 7.4b draft PR #39.

An owner can stage an existing `project.web.read` proposal for approval. The server locks the root execution and invocation, verifies the source remains successful and uncancelled, reparses the typed arguments, rechecks project and agent tool policy, the exact destination grant ID/revision, and the root budget account, then creates an exact payload-bound approval. The approval's target version contains the destination grant ID and revision. Changing the grant after proposal or after staging invalidates admission. Cancellation invalidates pending and approved staged reads.

An owner approval moves the invocation to `approved_staged`. The synthetic tool worker selects only `admitted` invocations, so no network effect can run. The staging API is owner-only with CSRF protection. It cannot be used for another tool action or a denied/rejected proposal. This is an approval integrity experiment, not authorization for outbound use.

Phase 7.4d must recheck the exact approval and all authority before a bounded fixture effect, persist an observation with the invocation provenance, handle duplicate/unknown outcomes and cancellation, then pass the complete gate. No real external site, paid model, credential or production integration was contacted.

## Reproduce

```sh
PYTHONPATH=backend/src APP_DATABASE_URL=postgresql+psycopg://postgres:phase1fixture@127.0.0.1:55433/workforce_test INITIAL_ADMIN_PASSWORD_FILE=/tmp/test-secret SESSION_COOKIE_SECURE=false /tmp/foundation-venv/bin/pytest -q backend/tests/test_tool_gateway.py backend/tests/test_tool_approval.py backend/tests/test_read_grants.py
PYTHONPATH=backend/src APP_DATABASE_URL=postgresql+psycopg://postgres:phase1fixture@127.0.0.1:55433/workforce_test INITIAL_ADMIN_PASSWORD_FILE=/tmp/test-secret SESSION_COOKIE_SECURE=false /tmp/foundation-venv/bin/pytest -q backend/tests
docker build --secret id=proxy_ca,src="$CODEX_PROXY_CERT" -f docker/backend.Dockerfile -t workforce-backend:phase1 .
docker compose up -d --no-build --force-recreate migrate api worker web
python scripts/smoke.py
```

All **117 backend tests** passed on the staged approval implementation. After the source refresh under the root lock, **25 focused gateway, approval, grant and cancellation tests** passed. The non-root backend image built on final source. Compose migration exited successfully, API reached healthy status, and the local fixture smoke reported `smoke=passed; unauthorized_dispatch=403; execution=succeeded; task=review; audit=present`.
