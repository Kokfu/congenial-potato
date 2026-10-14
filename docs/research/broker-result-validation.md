# Authenticated broker results: Phase 7.4j

Date: 2026-10-15 (Asia/Kuala_Lumpur). Branch: `phase-7-broker-results`. Parent: draft PR #46 (`7ace6d5`).

The broker reply is a strict bounded version-1 envelope authenticated with a response-specific HMAC domain. It binds the exact issued ticket bytes by SHA256 digest and attempt UUID. Result validation fixes trust to `external_claim`, checks the requested URL and byte limit, allowed text media type, UTF-8 size/digest and a timezone-aware retrieval time between ticket issuance and the current unexpired ticket lifetime. Unknown/duplicate fields, altered content, a different ticket, bad keys and oversized/malformed replies are denied. Authentication attests output from the trusted broker; it does not establish that an external claim is true.

An isolated execution wrapper requires an injected trusted authorization callback. After the broker's fsynced fence and immediately before DNS/fetch, that callback invokes the database mediator to recheck the exact committed ticket digest, attempt state, approval, grant revision/expiry, policy, source/root scope, root budget and cancellation. Database locks are released before network work so cancellation can commit in flight. Cancellation after the final check cannot retract a request already sent; the post-fetch checks discard its result.

The mediator authenticates the complete reply before opening the observation transaction, correlates the exact issued ticket, then repeats current authority checks under the root lock. Only a valid current result can atomically create cited provenance and mark success. Concurrent duplicate deliveries acknowledge the same immutable observation once. A changed result cannot replace it. A historical success can be acknowledged without creating new provenance; an expired ticket/reply is conservatively rejected even on replay. Transport loss, malformed/unverified replies and process loss after fetch leave the attempt unknown; neither broker replay nor issuer restart repeats the request.

No migration, HTTP endpoint, worker route, real resolver default, broker service or product outbound path is introduced. The callback is trusted injected harness code in this slice, not an implemented remote authorization channel. That channel and independent local broker isolation are the next tasks.

## Validation

The initial corrected focused suite passed **43 tests in 88.39 seconds**. After closing the lock-wait expiry gap, the final focused suite passed **44 tests in 88.01 seconds**. Tests cover authenticated correlation and domain separation, malformed/tampered/oversized replies, requested limits, concurrent one-observation acceptance, all nine authority mutations before fetch and before persistence, a correctly signed but unissued ticket, rejected redirect/oversize, cancellation while a real loopback response is paused, and actual subprocess exit after fetch followed by a fresh broker that refuses to fetch again. A forged body leaves the database unknown with no observation; the original valid reply can still be accepted without another fetch.

The first focused run reported **one failed and 42 passed**. Its extra-field assertion used a base `ReadResult.model_copy` value whose dump had already discarded the extra field. The corrected test places an unknown field in the actual incoming JSON envelope and verifies rejection. That earlier run is not counted as passed.

A full run was intentionally interrupted after **150 passing tests** when review found that ticket verification could precede a wait on the root database lock. The mediator now checks expiry after acquiring that lock, after grant/budget checks and after the observation flush; expiry rolls the transaction back. A real held-root-lock test verifies that an expired queued reply creates no observation and leaves the attempt unknown. The focused rerun passed as reported above. The final full backend suite passed **302 tests in 509.10 seconds**.

Alembic reported `No new upgrade operations detected.` No schema changes were needed. The backend image built (`sha256:1234972d9ff686818e6d95e95fb27a55c51600e10cb1a2e391916a67445a224b`); a UID 10001 network-disabled/read-only container imported the result and mediator modules. Compose migrated with exit 0; API/database/web were healthy and worker was running on the new image. API and worker PID 1 UIDs were independently verified as 10001. Fixture smoke passed with unauthorized dispatch 403, fixture success, review task and audit. Independent egress smoke passed for both API and worker, including direct, HTTP, explicit proxy, CONNECT and arbitrary web-forwarding denial against a positively reachable synthetic sink.

Existing repaired local volumes were reused. No clean-volume startup, browser, real public destination or real broker transport was exercised. The effect tests use fake DNS and an injected loopback HTTP transport. Process crash fencing does not prove physical power-loss/storage-restore durability or independent journals sharing one key.

```sh
PYTHONPATH=backend/src APP_DATABASE_URL=postgresql+psycopg://postgres:phase1fixture@127.0.0.1:55433/workforce_test /tmp/workforce-venv/bin/pytest -q backend/tests/test_read_broker_result.py
PYTHONPATH=backend/src APP_DATABASE_URL=postgresql+psycopg://postgres:phase1fixture@127.0.0.1:55433/workforce_test /tmp/workforce-venv/bin/pytest -q backend/tests
# From backend with APP_DATABASE_URL selecting workforce_migration_check:
/tmp/workforce-venv/bin/alembic -c alembic.ini check
# From repository root:
BUILDX_CONFIG=/tmp/workforce-buildx docker build --secret id=proxy_ca,src="$CODEX_PROXY_CERT" -f docker/backend.Dockerfile -t workforce-backend:phase1 .
docker compose up -d --no-build --force-recreate migrate api worker web
/tmp/workforce-venv/bin/python scripts/smoke.py
/tmp/workforce-venv/bin/python scripts/egress_smoke.py
```

The full Phase 7 gate remains open for controlled transport and its end-to-end isolation proof. Product read dispatch, native/paid activation and production integrations stay disabled.
