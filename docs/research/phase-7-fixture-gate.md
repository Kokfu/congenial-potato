# Phase 7 fixture gate: agent/tool injection evidence

Date: 2026-10-14. Branch: `phase-7-fixture-gate`. Parent: mediated-effect draft PR #41.

The isolated read proof now feeds a synthetic hostile page into a deliberately compliant fake adapter through the real worker request boundary. A **test-only** context seam selects the exact persisted observation and wraps its URL, digest, `external_claim` label and text as quoted data. The worker places it in a user message with external trust; the human system instruction stays separate. The adapter intentionally follows the page's requested action and emits it through the normal structured response, execution completion and tool gateway. There is no production observation-to-context connection and no claim that a model detects or resists the injection.

Seven deterministic attacks request an ungranted exfiltration host, another project's scope, a secret-reading tool, a grant-changing tool, an injected approval field, an artifact write, or another read at the granted host. The gateway rejects invalid/cross-project/unknown actions; the foreign destination is denied; the write remains pending owner approval; and the same-host read remains an inert proposal. No artifact, synthetic tool effect or second read attempt is created. Original grants, policy revisions and approvals remain unchanged. The canary is synthetic text, not a credential. One generated model call is persisted and repeated DBOS result retrieval performs no new generation.

An additional threaded test pauses response retrieval after sending the local request. Owner cancellation commits while the transport is in flight, without waiting for network completion. Releasing the response leads to a discarded attempt and no stored observation. A separate subprocess test exits with `os._exit(73)` after fetch, then invokes the experiment from a fresh interpreter: the durable attempt must remain unknown and the local server must see only one GET.

## Gate matrix

| Requirement | Evidence and scope |
| --- | --- |
| Exact scope and authority | Real proposal/approval/effect services; grant, policy, budget, payload, expiry and cancellation mutation tests in `test_read_effect_experiment.py` |
| SSRF, redirect and rebinding | Fake DNS, numeric pinning/peer checks and bounded loopback responses; no real destination read |
| Durable attempts and provenance | Attempt committed before request; observation only after post-effect checks; one cited external claim on success |
| Duplicate/restart safety | Concurrent duplicate, simulated interruption and real process exit/fresh-interpreter replay; unknown never auto-retries |
| Hostile content at an agent boundary | Fetched content reaches real worker GenerationRequest through a test-only seam; malicious fake output faces real gateway |
| Build/migrations/Compose | Exact commands/results below; initial local bootstrap repair documented in `read-effect-validation.md` |
| Independent product egress enforcement | **FOLLOW-UP 2026-10-15**: local deny-egress Compose isolation passed synthetic bypass checks; see [egress evidence](egress-denial-validation.md). A controlled product broker remains undeployed. The [separate-container fixture](isolated-broker-validation.md) subsequently verified mediated TLS and backend bypass denial. |
| Resolver deadlines and TLS | **FOLLOW-UP 2026-10-15**: bounded OS resolver lifecycle and real local TLS handshakes passed; see [transport evidence](transport-deadline-validation.md). No public resolver or remote certificate acceptance is claimed. |
| Single-use broker authority and replies | **FOLLOW-UP 2026-10-15**: [contract](broker-contract-validation.md), [database issuer](broker-issuer-validation.md) and [authenticated results](broker-result-validation.md) have fixture evidence. The [private RPC](broker-rpc-validation.md) and focused [separate-container proof](isolated-broker-validation.md) subsequently passed; the earlier full suite passed 343 tests. [Independent mediator admission](broker-admission-validation.md) now adds a database fence and cold-journal replacement evidence; the final Docker-enabled full suite passed 351 tests. |
| Product read dispatch | **DISABLED**: no read experiment API/outbox/worker route or automatic context consumption |

The Phase 7 gate remains open. These fixture results do not authorize product outbound reads. Local deny-egress isolation was subsequently verified in Phase 7.4f. Bounded resolver lifecycle and local TLS acceptance subsequently passed in Phase 7.4g. A controlled outbound broker and its end-to-end isolation proof remain before any product outbound path can be considered. Paid/native activation and production integrations remain gated separately.

## Validation results

The initial eight focused gate tests passed in 34.30 seconds. The expanded full backend suite then passed **159 tests in 339.12 seconds**. The subprocess crash/restart test was added after that full run began; the final gate file passed **all nine tests in 35.19 seconds**, including the fresh-interpreter replay. This exercises 160 distinct backend cases across the full and final focused commands; a single full 160-case run is not claimed.

```sh
PYTHONPATH=backend/src APP_DATABASE_URL=postgresql+psycopg://postgres:phase1fixture@127.0.0.1:55433/workforce_test /tmp/workforce-venv/bin/pytest -q backend/tests
PYTHONPATH=backend/src APP_DATABASE_URL=postgresql+psycopg://postgres:phase1fixture@127.0.0.1:55433/workforce_test /tmp/workforce-venv/bin/pytest -q backend/tests/test_read_fixture_gate.py
# Run inside backend:
APP_DATABASE_URL=postgresql+psycopg://postgres:phase1fixture@127.0.0.1:55433/workforce_migration_check /tmp/workforce-venv/bin/alembic -c alembic.ini check
# Run from repository root:
BUILDX_CONFIG=/tmp/workforce-buildx docker build --secret id=proxy_ca,src="$CODEX_PROXY_CERT" -f docker/backend.Dockerfile -t workforce-backend:phase1 .
docker compose up -d --no-build --force-recreate migrate api worker web
/tmp/workforce-venv/bin/python scripts/smoke.py
```

Alembic again reported `No new upgrade operations detected.` This slice adds no migration or product code. The backend image was rebuilt after the final test addition; the web image remains the verified Phase 7.4d build. The local Compose stack was recreated and fixture smoke was repeated. Final migration exited 0; API, database and web were healthy and worker was running. Smoke reported `smoke=passed; unauthorized_dispatch=403; execution=succeeded; task=review; audit=present`. This reuses the repaired local bootstrap described in `read-effect-validation.md`; it is not a new clean-volume proof.

No browser test, real destination read, real resolver deadline test, real TLS handshake test or egress firewall acceptance test was run in this slice.

## Follow-up: separate-container broker acceptance

Phase 7.4l adds a private, resource-bounded broker and synthetic TLS origin in separate Docker networks. API/worker fixture clients can use the broker but cannot bypass it; the broker cannot reach the database network and holds no database/owner/provider configuration. Container replacement preserves the private journal and does not repeat a fetched unknown outcome. Changed grants, in-flight cancellation, private rebinding and redirects create no cited observation. A broker-fetched hostile claim reaches the actual worker through a test-only citation seam; the gateway denies its ungranted destination without another read attempt.

Eight distinct focused cases passed across two commands; the final full backend run with Docker acceptance enabled passed all 343 tests in 670.24 seconds. Exact commands, temporary topology, image proof and limits are in [separate-container broker validation](isolated-broker-validation.md). No product route/service or automatic external context consumption is enabled. Independent mediator admission and production key/journal lifecycle remain before product network activation; native/paid activation stays separately gated.

## Follow-up: independent mediator admission

Phase 7.4m found and reproduced a missing independent fence: replacing the broker journal could previously allow a still-issued unknown ticket to fetch again. The mediator now commits one-time permit consumption in the control database before returning authorization. Its conservative migration fences every previously issued ticket. Focused database/migration tests, a separate-container replacement with a new empty volume, and the final 351-case Docker-enabled full suite passed; exact final results are maintained in [admission validation](broker-admission-validation.md).

The remaining product activation gate is separate from these local proofs: no broker is deployed or worker read route enabled. Production key distribution/rotation, confidential remote transport, clock-skew policy, and stale database-plus-journal restore procedures are unverified. Real outbound reads remain outside the owner's authorization. A complete synthetic gate cannot authorize those actions.
