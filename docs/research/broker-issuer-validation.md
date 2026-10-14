# Database-bound broker issuance: Phase 7.4i

Date: 2026-10-15 (Asia/Kuala_Lumpur). Branch: `phase-7-broker-issuer`. Parent: draft PR #45 (`8aa306a`).

The disabled-by-default issuer experiment derives each signed ticket from the actual staged invocation, exact approved payload, source/root identity, current policy/schema and destination grant revision. It rechecks cancellation, scope, approval expiry/decision hash, grant expiry/revision and root budget before preparation and issuance. DNS is injected and revalidated against the original prepared public address set. Ticket expiry is capped by the approval, destination grant and 30-second contract limit.

Preparation commits an unknown `ReadEffectAttempt` before returning a random 32-byte caller capability. Only its SHA256 digest is stored. Issuance requires that capability under the root/attempt locks, commits the ticket digest and issue time before returning the signed envelope, and permits issuance once. A restarted caller cannot recover the capability or mint another ticket. Any existing attempt blocks preparation, including an unknown local fetch; the local experiment likewise returns the existing broker attempt without fetching. No fallback transport silently repeats an unknown outcome.

Migration `e9a4c13f6d82` adds nullable capability/ticket digests and issue time with consistency constraints. Existing attempts remain fenced and cannot be adopted by the issuer. Audit records contain metadata/digests only, never capability bytes, key, signed envelope or response body. No HTTP issuer endpoint, broker deployment, worker registration, result acceptance or outbound read is enabled.

## Validation

The focused issuer suite passed **29 tests in 50.57 seconds**. It exercises actual approved fixture invocations, all derived authority bindings, nine authority mutations before preparation and issuance, wrong/lost capabilities, concurrent issuance, DNS changes, lifetime bounds, cross-transport fallback denial and real subprocess exits after preparation/issuance. All DNS is fake; this suite performs no external request.

The full backend suite passed **258 tests in 321.04 seconds**. The disposable test database upgraded successfully. A separate migration-check database upgraded, downgraded one revision, upgraded again, and Alembic reported `No new upgrade operations detected.` A mistaken working-directory command failed before writing files and was rerun from the repository root; it is not counted as validation.

The backend image built successfully (`sha256:f7afcb5c7fbc7cfded6284f8b04a5236d9499a9c34e33f232aa553bf0edb158a`). A network-disabled/read-only container running UID 10001 imported the issuer and new model fields. Compose migration/API/worker/web were recreated using existing local volumes. Fixture smoke passed with unauthorized dispatch 403, successful fixture execution, task review and audit present. The independent egress probe passed: both API and worker could reach the database but could not reach the positively tested synthetic sink by direct socket, HTTP, explicit proxy, CONNECT or arbitrary web forwarding. This is not a fresh-volume startup or browser check.

```sh
PYTHONPATH=backend/src APP_DATABASE_URL=postgresql+psycopg://postgres:phase1fixture@127.0.0.1:55433/workforce_test /tmp/workforce-venv/bin/pytest -q backend/tests/test_read_broker_issuer.py
PYTHONPATH=backend/src APP_DATABASE_URL=postgresql+psycopg://postgres:phase1fixture@127.0.0.1:55433/workforce_test /tmp/workforce-venv/bin/pytest -q backend/tests
# From backend, with the separate workforce_migration_check database:
/tmp/workforce-venv/bin/alembic -c alembic.ini upgrade head
/tmp/workforce-venv/bin/alembic -c alembic.ini downgrade -1
/tmp/workforce-venv/bin/alembic -c alembic.ini upgrade head
/tmp/workforce-venv/bin/alembic -c alembic.ini check
# From repository root, managed proxy CA build secret:
BUILDX_CONFIG=/tmp/workforce-buildx docker build --secret id=proxy_ca,src="$CODEX_PROXY_CERT" -f docker/backend.Dockerfile -t workforce-backend:phase1 .
docker compose up -d --no-build --force-recreate migrate api worker web
/tmp/workforce-venv/bin/python scripts/smoke.py
/tmp/workforce-venv/bin/python scripts/egress_smoke.py
```

The issuer stops at issuance. Authenticated broker results, fresh pre-fetch and post-fetch checks across the broker boundary, and an isolated local broker transport proof remain open. No public DNS/site, paid model, native activation or production integration was used. Filesystem power-loss, storage corruption, stale restore and multiple independent broker journals sharing a key remain unproved/unsupported as documented in the contract evidence.
