# Independent mediator admission: Phase 7.4m

Date: 2026-10-15 (Asia/Kuala_Lumpur). Branch: `phase-7-mediator-admission`. Parent: draft PR #49 (`c535cad`).

A regression reproduced two synthetic GETs when a fetched unknown ticket was replayed through an empty replacement broker journal. The earlier contract correctly fenced a preserved journal, but database authority alone did not consume permission to release a permit. The initial regression failed with `['/source', '/source']`; that run is evidence of the gap, not a passing check.

The mediator now consumes `ReadEffectAttempt.broker_permit_consumed` under the root/attempt locks and commits it with metadata-only audit/activity before returning authorization to the RPC caller. Concurrent or restarted authorization fails as unknown once consumed. Current approval, grant revision/expiry, policy, source/root scope, root budget, cancellation and ticket expiry are still checked before consumption. Database locks are released before network work. A valid authenticated reply cannot create provenance without confirmed admission; post-effect authority and expiry checks still precede observation success.

This flag records conservative permission consumption, not a claim that a request reached the origin. Process loss after the database commit but before permit delivery may produce no request and still stays unknown. Issuance is already one-time and binds the exact ticket bytes; changing keys/transport/journal cannot mint another ticket for that attempt. The broker's own fsynced fence remains in place before its authorization challenge. These two independent fences protect different failure points.

## Migration

Revision `f1b5d24e7a93` adds a non-null false-default boolean and requires a consumed admission to have an issued ticket. Every existing issued broker ticket is conservatively backfilled as consumed, including an issued ticket whose actual dispatch never became known. Existing prepared/unissued and local-only attempts remain unconsumed; existing-attempt/capability checks still prevent adopting a local unknown through the broker. No invented dispatch timestamp or successful outcome is recorded.

The actual migration tests downgrade to the old schema and upgrade again with issued, prepared and local attempts present. Issued attempts cannot gain another permit after upgrade. A still-live original caller can issue its previously unissued prepared attempt once, while a local unknown remains fenced. Live mixed-version admission/downgrade is not accepted; an eventual deployment must quiesce old mediators and expire outstanding tickets before rollback. No product mediator is deployed here.

## Validation

The focused admission suite passed **7 tests in 21.93 seconds**. It covers the reproduced cold-journal retry, concurrent one-time admission/audit, valid replies without admission, actual process exit after admission but before permit delivery, and all three data-bearing migration cases. A separate disposable migration database upgraded, downgraded one revision, upgraded again, and Alembic reported `No new upgrade operations detected.`

The new container case passed **1 test, 8 deselected in 63.18 seconds**. A broker fetched and exited with code 73. A replacement broker used the same key/ticket but a newly initialized empty journal volume, then asked for another permit. The database refused; the origin saw one GET, the attempt stayed unknown, and no observation was created. Both private journal volumes were cleaned up and the original backend topology was restored. This extends the eight earlier container cases to nine.

The final backend run with Docker acceptance enabled passed **351 tests in 936.84 seconds (15:36)**. This includes all nine separate-container cases and the seven new admission/migration tests in one run.

The backend image built (`sha256:c6d12fa47b93d21e92aa973b281fd67c72e44f14d95035532940d21ee7ae0472`). A UID 10001, read-only/network-none probe imported the new model/mediator, and the standalone synthetic RPC probe passed. That standalone probe has a trusted stub authorizer and is not evidence of database admission; PostgreSQL and container cases establish that boundary. Compose migration/API/worker/web were recreated, fixture smoke passed, and independent API/worker egress smoke passed before the full run. The post-suite fixture smoke passed again (`unauthorized_dispatch=403; execution=succeeded; task=review; audit=present`). Independent API/worker egress checks again reported isolated routes, reachable database, and denied direct/HTTP/proxy/CONNECT/web-forward bypasses; the reachable synthetic positive control passed.

```sh
PYTHONPATH=backend/src APP_DATABASE_URL=postgresql+psycopg://postgres:phase1fixture@127.0.0.1:55433/workforce_test /tmp/workforce-venv/bin/pytest -q backend/tests/test_broker_admission.py
WORKFORCE_DOCKER_GATE=1 PYTHONPATH=backend/src APP_DATABASE_URL=postgresql+psycopg://postgres:phase1fixture@127.0.0.1:55433/workforce_test /tmp/workforce-venv/bin/pytest -q backend/tests/test_broker_isolation_gate.py -k cold_journal
WORKFORCE_DOCKER_GATE=1 PYTHONPATH=backend/src APP_DATABASE_URL=postgresql+psycopg://postgres:phase1fixture@127.0.0.1:55433/workforce_test /tmp/workforce-venv/bin/pytest -q backend/tests
# From backend with APP_DATABASE_URL selecting workforce_migration_check:
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

Only fake DNS and an injected local synthetic transport/TLS origin were used. The RPC is an authenticated unencrypted private fixture protocol. Production key distribution/rotation, remote confidentiality/clock skew, physical power loss, corruption, and restoring stale copies of both the control database and broker journal remain unproved. The new fence assumes the current control database survives; it cannot reconstruct external truth from a stale database backup. Existing repaired application volumes were reused; no clean-volume startup, browser test or host reboot was run.

Product worker read dispatch, real outbound reads, automatic external context consumption, paid/native activation and production integrations remain disabled. No merge or public deployment occurred.
