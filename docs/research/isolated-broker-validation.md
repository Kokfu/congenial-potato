# Separate-container broker proof: Phase 7.4l

Date: 2026-10-15 (Asia/Kuala_Lumpur). Branch: `phase-7-isolated-broker-gate`. Parent: draft PR #48 (`d4e4074`).

An opt-in Docker fixture connects the existing Compose API/worker to a temporary private broker link. A separate synthetic TLS origin lives on another internal isolated network. The broker is the only process attached to both fixture networks; it is absent from the database/control and ingress networks. Neither fixture network has a host bridge gateway, default route or public egress. The actual Compose topology is restored and checked after every case. The Compose configuration and product dispatch remain unchanged.

The application fixture creates a real read proposal, staged exact owner approval and root budget. An explicitly injected client runs as UID 10001 inside API or worker and exchanges the signed ticket over the new RPC. When its authenticated challenge arrives, a trusted test harness calls the real database authority service and returns the decision over a protected subprocess pipe; the client then signs the nonce-bound permit. This is an acceptance seam, **not a deployed mediator endpoint or product worker effect route**. The broker performs a real TLS handshake and bounded GET against the separate synthetic origin, with fake public DNS and an injected transport mapping to that exact private fixture. Original-host SNI, certificate verification and peer pinning are exercised in the backend image. The cited URL remains the exact approved `https://example.test/...` URL.

## Isolation and uncertainty checks

- API and worker each completed a successful mediated read and persisted one cited `external_claim`. Both failed direct socket, HTTP and explicit-proxy access to the origin; CONNECT sent to the broker was rejected. The broker could reach its TLS origin but could not reach the database network.
- The broker/fixture origin run as UID 10001 with read-only base filesystems, all capabilities dropped, no-new-privileges, one CPU, 192 MiB memory and 64 PID limits. The broker receives no database URL, owner/provider secret or database import. Its only persistent mount is its private journal; `/tmp` is ephemeral. A root initializer changes ownership/mode only on the newly created unique fixture volume, then application processes run non-root.
- Before the mediator issues a permit, the private journal contains exactly one UID 10001/mode 0600 marker containing 64 hex digest bytes and a newline. Broker logs contain only the fixed readiness line. Keys, ticket bytes and result bodies are passed transiently through private pipes/RPC, not recorded in broker logs or the journal.
- A broker process exits with code 73 after fetch, before returning a result. Its container is removed and recreated with the same key and named volume. Replay from the other backend service refuses to fetch, the server sees one GET, and the database remains unknown with no observation. An issuer restart cannot create another attempt/ticket.
- A changed destination grant before the permit prevents the GET. Root cancellation commits while a TLS response is paused; releasing it produces a discarded attempt and no observation. A private rebound DNS answer causes no origin request. A 302 is rejected with no request to its target. Every uncertain/rejected effect remains fenced.
- A fetched hostile page reaches the actual worker GenerationRequest through the existing style of test-only exact-citation seam. A deliberately compliant fake adapter follows its request for an ungranted exfiltration destination. The actual gateway denies it; grants, policy, approvals and read-attempt count stay unchanged, and replay adds no model call. No model resistance or product context-consumption feature is claimed.

## Validation

The first seven focused container cases passed **7 tests in 283.81 seconds**. The added hostile-content case passed separately: **1 passed, 7 deselected in 55.62 seconds**. These establish eight distinct cases across two commands; the single final full run is recorded below.

Initial runs were not passes: one failed during fixture setup because a parameter shadowed the shared HTTP client fixture; another failed because container IPs were read before startup; a probe failed because its function shadowed the `http` import. The hostile worker helper initially read project scope from an Execution field that does not exist, after fetch/provenance had succeeded; it now uses the project returned by the approved fixture. Each failed fixture cleaned up its own resources and restored existing network attachments. Ticket issuance occurs after fixture startup/bypass probes so its lifetime bounds dispatch, not container setup.

The final full backend suite, with `WORKFORCE_DOCKER_GATE=1`, passed **343 tests in 670.24 seconds**. This single run includes all eight container acceptance cases and the existing PostgreSQL/DBOS/provider/tool fixtures.

Alembic reported `No new upgrade operations detected.` No production source or database schema changes were needed. The shared approved-read test helper now permits a five-second timeout override for the in-flight container cancellation case; its existing default remains one second. The final backend image built (`sha256:2d9e3fb44b984bf5bd4e2aac5beb52f88cf1380308c21be17ca52f9de538c662`). The UID 10001, read-only/network-none RPC image probe passed. Compose migration exited 0; fixture smoke and independent egress smoke passed before the full test run. After execution-environment reattachment the old shell-session handle was unavailable, so post-test smoke results were explicitly rerun and captured: fixture smoke and independent API/worker egress smoke both passed. The original checkout, changes and complete test log were preserved.

```sh
# Requires Docker Engine 28+, the built backend image, running local Compose,
# and disposable workforce_test / workforce_dbos_test databases.
WORKFORCE_DOCKER_GATE=1 PYTHONPATH=backend/src APP_DATABASE_URL=postgresql+psycopg://postgres:phase1fixture@127.0.0.1:55433/workforce_test /tmp/workforce-venv/bin/pytest -q backend/tests/test_broker_isolation_gate.py
WORKFORCE_DOCKER_GATE=1 PYTHONPATH=backend/src APP_DATABASE_URL=postgresql+psycopg://postgres:phase1fixture@127.0.0.1:55433/workforce_test /tmp/workforce-venv/bin/pytest -q backend/tests
# From backend with APP_DATABASE_URL selecting workforce_migration_check:
/tmp/workforce-venv/bin/alembic -c alembic.ini check
# From repository root, managed build CA secret:
BUILDX_CONFIG=/tmp/workforce-buildx docker build --secret id=proxy_ca,src="$CODEX_PROXY_CERT" -f docker/backend.Dockerfile -t workforce-backend:phase1 .
docker run --rm -i --network none --user 10001:10001 --read-only --tmpfs /tmp:rw,mode=1777 --entrypoint python workforce-backend:phase1 - < scripts/broker_rpc_image_probe.py
docker compose up -d --no-build --force-recreate migrate api worker web
/tmp/workforce-venv/bin/python scripts/smoke.py
/tmp/workforce-venv/bin/python scripts/egress_smoke.py
```

Without `WORKFORCE_DOCKER_GATE=1`, these eight acceptance cases are explicitly skipped; a normal backend run alone cannot establish this isolation proof. The harness creates unique resources, removes only those resources, and checks that all original backend/database attachments remain. Existing repaired application volumes were reused; no clean-volume startup, browser test or host reboot was performed.

## Limits and next check

Only a local synthetic origin and fake DNS were used. The RPC is authenticated but unencrypted and private; remote confidentiality/clock skew and production key distribution/rotation are not accepted. Restart evidence preserves the journal volume; physical power loss, storage corruption, journal deletion and stale restore are not established. Independent journals sharing a key remain unsupported. A useful next check is an independent mediator admission fence so a missing/replaced broker journal cannot authorize the same unknown ticket again.

No product web-read effect is registered, no automatic external context consumption is enabled, and no real destination read, paid/native activation, production integration, public deployment or merge occurred. The Phase 7 product gate remains closed while the remaining lifecycle/admission checks are completed.
