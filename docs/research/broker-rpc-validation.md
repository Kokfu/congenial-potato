# Private broker RPC: Phase 7.4k

Date: 2026-10-15 (Asia/Kuala_Lumpur). Branch: `phase-7-broker-rpc`. Parent: draft PR #47 (`2e3cdd2`).

The opt-in RPC experiment moves broker fetch into a separate process without putting a database client or credentials in its protocol. A trusted configured private numeric IPv4 endpoint receives one signed exact ticket. After verifying the ticket and committing its existing durable fence, the broker sends a random authenticated challenge bound to the exact ticket digest. The caller verifies that challenge, performs fresh database authority checks, and returns a separately authenticated permit bound to that nonce/ticket, valid for at most one second and never beyond ticket expiry. Only then can the broker revalidate DNS and fetch. The reply uses the previously checked result contract, and the caller still needs the mediator's post-effect acceptance transaction before any cited content is stored.

The final check cannot retract a request sent concurrently with cancellation; post-effect checks discard content when authority changed. Nonces, permit expiry, the broker fence and the mediator attempt prevent a delayed/replayed exchange from authorizing a fresh dispatch. Losing either process or its reply never clears the fence or reissues the ticket.

## Channel bounds and scope

Four-byte length prefixes bound the request to 16,384 bytes, challenge/permit messages to 4,096 bytes and the authenticated result to 409,600 bytes (including worst-case JSON escaping of the 65,536-byte text limit). Unknown/duplicate fields and invalid UTF-8 are rejected. The server handles one active connection with a fixed backlog of four; socket reads/writes share a ten-second absolute deadline so trickling does not extend a request. Ticket/permit/fetch deadlines also apply. Proxy methods, arbitrary headers/operations, hostnames, public/metadata/link-local channel endpoints and caller-selected programs are not protocol features. The configured origin transport and fake resolver remain mandatory trusted injections.

This is an authenticated **unencrypted private fixture channel**, not a production/public RPC service or availability claim. Endpoint configuration, key, journal and adapters are trusted; local containers share a clock. Remote confidentiality, clock skew, production key distribution/rotation, high availability and journal restore/retention remain open. One key and one durable logical journal remain a single namespace; independent journals sharing a key are unsupported. No Compose broker service, product API/worker registration or real resolver/transport default is added.

## Validation

The initial focused suite passed **27 tests in 25.28 seconds**. The expanded focused suite passed **33 tests in 31.62 seconds**. Cases cover authenticated challenge/result correlation, pre-authority durable fencing, invalid/expired/future/changed permits, malformed/non-UTF-8/oversized frames, CONNECT rejection, absolute trickle deadline and recovery, denied channel destinations, actual database success, cancellation/grant/policy/budget changes before permit, changed grant before provenance, redirect/rebinding denial, caller loss and actual broker process exit after fetch. A fresh broker reuses the same journal and refuses to fetch again; the database stays unknown without an observation. The broker subprocess environment was subsequently restricted to PATH/PYTHONPATH and asserts that neither the database URL nor `workforce.db` is present; the final focused rerun passed **all 33 tests in 35.23 seconds**.

The related PostgreSQL/DBOS regression command passed **158 tests in 203.36 seconds**, covering all broker contracts, issuer/result/RPC behavior and the hostile-content worker fixture gate. The parent slice passed all 302 backend tests; this slice uses focused/related regression coverage and does not claim a new full 335-case run.

Alembic reported `No new upgrade operations detected.` The final backend image built (`sha256:a93d1d598a9c08142d89e82e28538a36acabb3cdc4b1893d5b3a70513a5a1b96`). The final UID 10001, read-only/network-none image probe passed a complete synthetic RPC round trip, durable-before-request fence and replay denial without database configuration/imports. Compose migration exited 0 and fixture smoke passed. Independent egress smoke passed again for API and worker with direct/HTTP/proxy/CONNECT/arbitrary web forwarding denied to a positively reachable synthetic sink. Existing repaired volumes were reused; no fresh-volume startup or browser check was run.

```sh
PYTHONPATH=backend/src APP_DATABASE_URL=postgresql+psycopg://postgres:phase1fixture@127.0.0.1:55433/workforce_test /tmp/workforce-venv/bin/pytest -q backend/tests/test_read_broker_rpc.py
PYTHONPATH=backend/src APP_DATABASE_URL=postgresql+psycopg://postgres:phase1fixture@127.0.0.1:55433/workforce_test /tmp/workforce-venv/bin/pytest -q backend/tests/test_read_broker_contract.py backend/tests/test_read_broker_issuer.py backend/tests/test_read_broker_result.py backend/tests/test_read_broker_rpc.py backend/tests/test_read_fixture_gate.py
# From backend, with APP_DATABASE_URL selecting workforce_migration_check:
/tmp/workforce-venv/bin/alembic -c alembic.ini check
# From repository root, managed build CA secret:
BUILDX_CONFIG=/tmp/workforce-buildx docker build --secret id=proxy_ca,src="$CODEX_PROXY_CERT" -f docker/backend.Dockerfile -t workforce-backend:phase1 .
docker run --rm -i --network none --user 10001:10001 --read-only --tmpfs /tmp:rw,mode=1777 --entrypoint python workforce-backend:phase1 - < scripts/broker_rpc_image_probe.py
docker compose up -d --no-build --force-recreate migrate api worker web
/tmp/workforce-venv/bin/python scripts/smoke.py
/tmp/workforce-venv/bin/python scripts/egress_smoke.py
```

Only fake DNS and an injected loopback synthetic origin were used. The standalone image probe uses a trusted fixture authorizer stub; database authorization is tested separately with real fixture invocations. Separate-container broker/origin isolation and backend bypass denial through the new broker channel remain the next acceptance task. No public destination, paid/native activation, production integration or product outbound dispatch was enabled.
