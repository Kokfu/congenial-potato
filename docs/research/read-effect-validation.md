# Mediated synthetic web-read effect: Phase 7.4d

Date: 2026-10-14. Branch: `phase-7-read-effect`. Parent: Phase 7.4c draft PR #40 (`0995e84`).

The previous workspace's uncommitted experiment was absent from the fetched branch. This implementation was reconstructed from the committed approval, destination, network and observation contracts. No prior experiment test result is assumed.

`run_read_effect_experiment` requires explicit opt-in and injected DNS and connection factories. Tests supply fake public DNS and map the connection to a loopback synthetic HTTP server. The service has no default resolver or transport, API route, outbox consumer or worker registration. Product workers continue selecting only admitted fixture tools; approved web reads remain staged unless the isolated harness invokes them.

The service locks the root and invocation, validates the exact approved payload and decision hash, expiry, typed schema/arguments/resource, successful uncancelled source, project execution grant, tool policy snapshot and destination grant ID/revision. The root must exist, remain uncancelled and have a USD budget with positive remaining capacity. This free synthetic transport records no fabricated monetary charge or paid reservation. Paid reads would require a separately verified cost envelope and holds.

Before any request it commits one `ReadEffectAttempt`, keyed by invocation, with exact payload hash, approval, agent and root. Its initial state is deliberately `unknown`: a process may disappear at any later instruction. A second caller or restarted caller returns the durable state and never redispatches. The original in-flight caller can finish; a duplicate cannot steal or resume it. A crash after fetching leaves no observation and retains `unknown`. There is no automatic retry or owner API to reset this fence. Unknown means the request may or may not have happened; it cannot be relabeled success without independently verified result evidence. Resolving it by issuing a fresh request is outside this slice.

After that commit, authority is checked again, DNS is re-resolved and required to match the prepared public-only answer set, and the bounded single GET runs outside database locks. Redirects are rejected. Immediately after fetch, fresh database reads under the root lock repeat all authority and attempt bindings. Changed authority discards the result. Only a valid result creates a cited observation and successful attempt in one transaction. The observation contains exact URL/time/MIME/bytes/digest and fixed `external_claim` trust; its invocation key links through the attempt to the approval. Audit/activity contain metadata rather than page text.

Cancellation and revocation cannot retract an already sent request. They can commit while transport runs, and post-effect checks prevent storing its result. The last authority check and external request are not one atomic transaction. The conservative unknown fence also applies to DNS/transport errors after attempt commit, even when the fixture can show no request occurred.

## Validation

**151 backend tests passed in 263.73 seconds**, including all 34 new mediated-effect cases. The first focused run had three test-fixture policy mutations aimed at an unrelated action; after correcting the fixture to mutate `project.web.read`, the full suite passed. The disposable PostgreSQL and DBOS test databases use loopback port 55433. Tests cover durable-before-request visibility, duplicate and concurrent dispatch, simulated crashes before request and after fetch, cancellation, changed grants/expiry, changed tool policy/project scope, exhausted root budget, changed approval/hash/expiry/arguments, rebinding to private/metadata/mapped and changed public addresses, redirects and oversize responses. Authority changes are injected both before request and after fetch; rejected results produce no observation.

## Remaining gate

This proves an isolated synthetic effect only. The full Phase 7 gate still requires a hostile page presented through an agent/tool boundary, broader adversarial integration coverage and an independently enforced egress boundary before any product outbound read. Real DNS deadlines, certificate handshakes and production transports are unverified here. Native model activation remains separately gated. No paid model or production integration is enabled.


Reproduced from the repository root (Alembic commands run inside `backend`):

```sh
UV_CACHE_DIR=/tmp/uv-cache uv pip install --python /tmp/workforce-venv/bin/python -r backend/requirements-dev.lock
PYTHONPATH=backend/src APP_DATABASE_URL=postgresql+psycopg://postgres:phase1fixture@127.0.0.1:55433/workforce_test /tmp/workforce-venv/bin/pytest -q backend/tests
APP_DATABASE_URL=postgresql+psycopg://postgres:phase1fixture@127.0.0.1:55433/workforce_migration_check /tmp/workforce-venv/bin/alembic -c alembic.ini upgrade head
APP_DATABASE_URL=postgresql+psycopg://postgres:phase1fixture@127.0.0.1:55433/workforce_migration_check /tmp/workforce-venv/bin/alembic -c alembic.ini downgrade -1
APP_DATABASE_URL=postgresql+psycopg://postgres:phase1fixture@127.0.0.1:55433/workforce_migration_check /tmp/workforce-venv/bin/alembic -c alembic.ini upgrade head
APP_DATABASE_URL=postgresql+psycopg://postgres:phase1fixture@127.0.0.1:55433/workforce_migration_check /tmp/workforce-venv/bin/alembic -c alembic.ini check
BUILDX_CONFIG=/tmp/workforce-buildx docker build --secret id=proxy_ca,src="$CODEX_PROXY_CERT" -f docker/backend.Dockerfile -t workforce-backend:phase1 .
BUILDX_CONFIG=/tmp/workforce-buildx docker build --secret id=proxy_ca,src="$CODEX_PROXY_CERT" -f docker/web.Dockerfile -t workforce-web:phase1 .
docker compose up -d --no-build --force-recreate migrate api worker web
/tmp/workforce-venv/bin/python scripts/smoke.py
```

Fresh migration, downgrade of the new revision and re-upgrade succeeded; `alembic check` reported `No new upgrade operations detected.` The test database also upgraded and passed metadata checks. Backend and web images built from the final source. A network-disabled/read-only container imported the experiment as UID 10001. Compose migration exited 0; API/database/web were healthy and worker ran. API and worker PID 1 each reported UID 10001. Loopback fixture smoke reported `smoke=passed; unauthorized_dispatch=403; execution=succeeded; task=review; audit=present`.

Environment limits and repairs: no app terminal was attached; checkout had reset to a clean initial commit and was fetched from origin. The managed checkout uses private file/directory modes. The first image import and Compose migration failed because copied application files were unreadable after dropping privileges. Docker COPY now assigns the backend and Caddy configuration to UID/GID 10001 without broadening workspace permissions. Buildx state uses `/tmp` because the home directory is read-only. Initial Compose PostgreSQL bootstrap could not read the bind-mounted init script; the missing local `workforce_dbos` database was created with `docker compose exec -T db createdb -U postgres workforce_dbos`, then services were recreated and the smoke passed. This was a repaired local startup, not an unassisted clean-start proof. No browser check, real DNS lookup for a read, real HTTPS read or egress firewall acceptance check was run.
