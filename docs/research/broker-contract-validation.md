# Exact single-use broker contract: Phase 7.4h

Date: 2026-10-15 (Asia/Kuala_Lumpur). Branch: `phase-7-broker-contract`. Parent: draft PR #44 (`95d16d9`).

The next broker boundary has a strict, frozen version-1 ticket for one GET: attempt/approval/project/agent/root IDs, exact approval payload hash, tool policy/schema hashes, destination grant ID/revision/expiry, exact URL, byte/time limits, prepared public address set and a maximum 30-second lifetime. Canonical JSON is authenticated with HMAC-SHA256 under an injected 32-byte trusted key. Verification rejects altered scope/bounds/authority metadata, wrong keys, unknown or duplicate fields, invalid versions, malformed/oversized envelopes, noncanonical/private/mapped address sets, future/expired tickets and invalid grant lifetimes. No caller-supplied method, headers, credentials, proxy, shell program or arbitrary broker operation is accepted.

This is a **contract experiment**, not database authorization. The signing function attests what trusted application code supplies; it does not itself prove that an owner approved a ticket. The next issuer must derive every field from a committed `ReadEffectAttempt` and current source/approval/grant/policy/budget authority, prevent reissuance of an unknown dispatch, and preserve the mediator's post-effect checks. No issuer endpoint, HTTP broker server, service deployment, product worker route or default real resolver/transport is added here.

## Independent broker fence

Before DNS revalidation or fetch, the broker exclusively creates a private marker named by the canonical attempt UUID, writes the ticket digest, fsyncs the marker and then fsyncs the journal directory. Existing markers fail as unknown outcomes, including a correctly signed changed ticket for the same attempt. Markers are never reset, removed on failure or used to blindly repeat a request. A partial marker or failed sync prevents fetch and remains conservatively consumed. The configured journal directory must be private, owned by the broker UID and not a final symlink; only trusted configuration selects its path. Its parent path and the host/Docker administrator remain trusted.

The marker contains a digest only, never the URL, signing key, response body or cited observation. Broker results remain transient and still require the mediator's post-effect authority checks before provenance can be stored. Re-resolved DNS must match the signed public set; byte/time bounds and expiry apply before and after the effect. Expiry after fencing leaves the marker consumed without sending a request. TLS/response handling uses the previously checked network adapter when injected by the harness.

Durability relies on supported Linux filesystem fsync semantics and preserving the private journal across restarts. Process-exit tests establish restart fencing; they do not establish survival of storage corruption, physical power loss, journal deletion or restoring a stale backup. Do not clear the journal to retry an unknown outcome. A key and journal form one logical broker namespace: sharing a key across independent journals would permit cross-instance replay and is not supported. A production retention/restore policy is not implemented or accepted by this slice.

## Validation

The focused contract suite passed **43 tests in 11.59 seconds**. It covers tampered fields, wrong keys, duplicates/unknown fields, invalid destinations, expiry, concurrency, symlink/permission rejection, fsync failure, rebinding, changed signed replays and real process exits after fence or after fetch. Fresh broker processes reuse the same private journal and never repeat the request. All network reads used an injected loopback synthetic HTTP transport and fake public DNS.

The first run had 15 fixture assertions fail because the common backend fixture stores its password file in pytest's temporary directory; the broker tests now use a dedicated private journal subdirectory. No credential value was exposed and that run is not counted as passed.

The full backend suite passed **229 tests in 272.47 seconds** on the final contract implementation. Alembic reported `No new upgrade operations detected.` No database metadata or migration changed. The backend image rebuilt successfully. A UID 10001, network-disabled/read-only image with a temporary writable `/tmp` verified signing, verification and durable marker creation without any network request.

Compose migration exited 0; API/database/web were healthy and worker was running. Fixture smoke reported `smoke=passed; unauthorized_dispatch=403; execution=succeeded; task=review; audit=present`. The independent egress probe passed again for API and worker, including direct socket, HTTP, explicit proxy, CONNECT and arbitrary web forwarding denial to a positively reachable local synthetic sink. Existing local volumes and the documented bootstrap repair were reused; no fresh-volume startup or browser check was run.

```sh
PYTHONPATH=backend/src APP_DATABASE_URL=postgresql+psycopg://postgres:phase1fixture@127.0.0.1:55433/workforce_test /tmp/workforce-venv/bin/pytest -q backend/tests/test_read_broker_contract.py
PYTHONPATH=backend/src APP_DATABASE_URL=postgresql+psycopg://postgres:phase1fixture@127.0.0.1:55433/workforce_test /tmp/workforce-venv/bin/pytest -q backend/tests
# From backend:
APP_DATABASE_URL=postgresql+psycopg://postgres:phase1fixture@127.0.0.1:55433/workforce_migration_check /tmp/workforce-venv/bin/alembic -c alembic.ini check
# From repository root:
BUILDX_CONFIG=/tmp/workforce-buildx docker build --secret id=proxy_ca,src="$CODEX_PROXY_CERT" -f docker/backend.Dockerfile -t workforce-backend:phase1 .
docker compose up -d --no-build --force-recreate migrate api worker web
/tmp/workforce-venv/bin/python scripts/smoke.py
/tmp/workforce-venv/bin/python scripts/egress_smoke.py
```

No database-bound issuer, deployed broker transport, public DNS/site, paid model or production integration was exercised or enabled by this slice.

## Next slice

Implement the trusted database-bound issuer and a verified broker result boundary, then integrate the mediator through a local isolated broker fixture. Test cancellation and changed grants/budgets around issuance and response, replay/unknown dispatches, broker isolation and bypass denial. Keep the default backend deny-egress topology and product read dispatch disabled until the full gate clears. Native activation stays separately gated.
