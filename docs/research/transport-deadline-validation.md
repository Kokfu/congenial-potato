# Bounded OS resolver and local TLS proof: Phase 7.4g

Date: 2026-10-15 (Asia/Kuala_Lumpur). Branch: `phase-7-transport-deadlines`. Parent: local egress denial draft PR #43 (`a7aa6da`).

This slice closes two transport gaps in the isolated network experiment: an OS `getaddrinfo` call could block without a Python deadline, and a peer could extend status/header/body reads by trickling bytes before each socket timeout. The experiment stays disabled by default, has no API/worker/outbox registration, and the mediated effect proof still requires explicitly injected transport and fake DNS. The default Compose backend remains unable to route externally.

## Resolver lifecycle

The default resolver now runs a fixed, trusted standard-library program in an isolated Python interpreter. Host and port are argv data, never shell syntax or model-generated program text. The parent bounds process communication, kills and reaps on timeout or interruption, limits answer count/output size, validates the returned socket-answer structure, and sanitizes errors. The child also arms a POSIX `SIGALRM` timer before resolution so a wedged resolver cannot depend on a surviving parent for termination. Python isolated mode ignores environment-based Python path customization; inherited runtime networking/guard variables are preserved, not printed. This is a trusted resolver helper, not an arbitrary code runner.

The public-address policy still validates every returned IP, including mixed/private/mapped answers, and requires the same answer set immediately before connection. Resolution is independently bounded during preparation; during execution it consumes the same request time budget as the ensuing transport. Injected resolver/connection factories remain trusted test seams; an arbitrary blocking injected function is not converted into a safe production adapter.

## Absolute transport deadline

The execution deadline starts before DNS revalidation. Expired resolution is rejected before constructing a connection. Numeric-IP connection and TLS handshake use the remaining time. A socket wrapper places a deadline-aware raw reader underneath the standard HTTP parser's buffered file. Each underlying receive recalculates the remaining time, including status lines, headers, body and chunk framing. This avoids replacing the HTTP parser or relying on private stdlib socket-file fields. The socket's own `makefile` retains descriptor ownership semantics. Responses are explicitly closed on success or rejection, including when HTTPConnection has already dropped its socket reference. TLS still verifies the certificate and original hostname with SNI; no insecure fallback, redirect following or proxy support is added.

This is a finite I/O budget under normal OS scheduling, not a hard real-time guarantee. POSIX timers and the Linux/Debian image are the supported proof target. No public resolver, public certificate chain or deployed egress broker was contacted or accepted.

## Tests

The transport tests use only the OS lookup for `localhost`, fixed synthetic child programs for DNS failure/stall cases, fake public DNS answers and loopback TCP/TLS servers. OpenSSL generates an ephemeral one-day self-signed test certificate and key under pytest's private temporary directory; the key is not committed, logged or used as an application credential. Tests verify:

- OS resolver response and bounded/validated answers; malformed results and metadata/private IP denial.
- A wedged resolver killed/reaped by the parent; interruption cleanup; and independent child termination without any parent-side kill.
- Resolution exhausting the request budget before any dial.
- Real TLS success with the test CA and original-host SNI, wrong-host rejection, untrusted-certificate rejection and stalled handshake timeout.
- Trickle attacks during HTTP status, headers, body and chunk framing over both plain local HTTP and actual local TLS; rejected responses close their file even when retained by a caller.
- The real mediated attempt/provenance service with local TLS: trusted success stores one `external_claim`; a failed certificate leaves one unknown attempt, no observation and no blind retry.

The broader suite also covers grant/policy/approval/budget/cancellation changes, concurrent duplicate effects, process exit after fetch, hostile-page proposals, scope and SSRF/rebinding boundaries from earlier slices.

## Reproduce and results

The expanded full backend suite passed **185 tests in 262.04 seconds**. A subsequent response-file cleanup and one additional cleanup test were verified with **all 73 affected read/transport tests passing in 172.94 seconds** on the final code, including the 26 transport cases. A single full 186-case run is not claimed. The earlier pre-watchdog run also passed 178 tests; it is not used as evidence for the final additions.

```sh
PYTHONPATH=backend/src APP_DATABASE_URL=postgresql+psycopg://postgres:phase1fixture@127.0.0.1:55433/workforce_test /tmp/workforce-venv/bin/pytest -q backend/tests
PYTHONPATH=backend/src APP_DATABASE_URL=postgresql+psycopg://postgres:phase1fixture@127.0.0.1:55433/workforce_test /tmp/workforce-venv/bin/pytest -q backend/tests/test_transport_deadlines.py backend/tests/test_network_policy.py backend/tests/test_read_effect_experiment.py backend/tests/test_read_fixture_gate.py
# Run inside backend:
APP_DATABASE_URL=postgresql+psycopg://postgres:phase1fixture@127.0.0.1:55433/workforce_migration_check /tmp/workforce-venv/bin/alembic -c alembic.ini check
# Run from repository root:
BUILDX_CONFIG=/tmp/workforce-buildx docker build --secret id=proxy_ca,src="$CODEX_PROXY_CERT" -f docker/backend.Dockerfile -t workforce-backend:phase1 .
docker compose up -d --no-build --force-recreate migrate api worker web
/tmp/workforce-venv/bin/python scripts/smoke.py
/tmp/workforce-venv/bin/python scripts/egress_smoke.py
```

The host tests used Python **3.12.14**, Python's OpenSSL **3.5.8** and the OpenSSL **3.5.7** CLI to generate certificates. The rebuilt image uses Python **3.12.12** and OpenSSL **3.0.18**. UID 10001, network-disabled/read-only image probes successfully ran the local resolver child and independent child watchdog; the final response-cleanup image was rebuilt and its resolver child/import check passed again. TLS handshakes were tested on the host with the application classes; TLS handshake tests were not rerun inside the production image. Test certificate generation requires the `openssl` CLI on the test host; no runtime Python dependency was added.

Alembic reported `No new upgrade operations detected.` No metadata or migration changed. Final-image Compose migration exited 0; API, database and web were healthy and worker was running. Fixture smoke reported `smoke=passed; unauthorized_dispatch=403; execution=succeeded; task=review; audit=present`. The final egress acceptance script again passed both API and worker checks for absent external routes, PostgreSQL reachability, and denied direct socket/HTTP/proxy/CONNECT/arbitrary web forwarding to the synthetic sink. Named volumes and the previously documented local bootstrap repair were reused; a fresh-volume startup and browser check were not run.

A transient execution-server disconnection interrupted a launch attempt. File/log inspection confirmed it had not started those checks; successful reruns are the results above. No failed or unrun launch is counted as a passed check.

## Remaining gate

Local backend egress denial, bounded resolver lifecycle and local TLS acceptance are fixture evidence. A controlled, narrowly authorized egress broker is still absent; backend general egress must remain denied rather than attaching API/worker to the ingress network to make a read work. Broker policy, bypass denial and end-to-end isolated integration must pass before any product read dispatch or automatic observation consumption can be considered. Native model activation remains a separate gate. No paid model, public deployment or production integration is enabled.
