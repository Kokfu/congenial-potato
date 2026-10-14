# Local backend egress denial: Phase 7.4f

Date: 2026-10-15 (Asia/Kuala_Lumpur). Branch: `phase-7-egress-denial`. Parent: draft PR #42 (`1e28f25`).

The fixture Compose topology now places PostgreSQL, migration, API and worker only on `control`, a Docker Engine 28+ internal bridge using `gateway_mode_ipv4=isolated`. Unlike an ordinary internal bridge, isolated mode also omits the bridge's host gateway address. IPv6 is disabled. Only web joins a second `edge` network to serve the existing loopback host port. Caddy retains its fixed API/health reverse-proxy destinations; no forward proxy or CONNECT handler was added. Migration/API/worker explicitly drop `NET_ADMIN` and `NET_RAW` and prohibit privilege gain through exec. Images, provider registry and product tool dispatch are unchanged.

This is an independently enforced **deny-egress** boundary for the backend on the tested local Docker daemon. It is not an outbound broker, public deployment or authorization to read an external site. No external destination was probed. Backend connectivity to intended internal services, especially PostgreSQL, remains available; application-level SSRF policy still denies those private destinations for reads. Host/Docker administrators are trusted and can change network attachment. The dual-homed web service is trusted reviewed proxy code, not an untrusted code runner. Other Docker versions/drivers, rootless engines, Docker Desktop and deployment hosts have not been accepted by this proof.

## Acceptance probe

`scripts/egress_smoke.py` requires the running local Compose fixture and Engine 28+. It inspects the actual network attachments, isolated driver setting, absent gateway, disabled IPv6 and dropped capabilities. It launches one disposable, unprivileged, read-only synthetic HTTP server on `edge`, without secrets, host ports or volumes. A separate probe on `edge` reaches that server as a positive control. Numeric addresses are checked to be private; there are no public network or DNS probes.

As UID 10001 inside API and worker, it verifies no IPv4 default route and only loopback IPv6, checks PostgreSQL service DNS/connectivity, and then attempts a direct socket, direct HTTP and an explicit proxy connection to the synthetic server. All must fail. It also checks that web rejects a CONNECT tunnel and does not forward an absolute-form arbitrary URL to the server. The synthetic server must have received only the positive control request. The script removes only its own temporary server in a `finally` block and leaves application services/data intact. IPv6 routing and raw-socket capability checks reduce alternate paths; this is not an exhaustive kernel or malicious-code sandbox audit.

## Commands and results

```sh
docker compose config --quiet
docker compose up -d --no-build
python scripts/egress_smoke.py
/tmp/workforce-venv/bin/python scripts/smoke.py
PYTHONPATH=backend/src APP_DATABASE_URL=postgresql+psycopg://postgres:phase1fixture@127.0.0.1:55433/workforce_test /tmp/workforce-venv/bin/pytest -q backend/tests/test_network_policy.py backend/tests/test_read_fixture_gate.py backend/tests/test_tool_gateway.py
# From backend:
APP_DATABASE_URL=postgresql+psycopg://postgres:phase1fixture@127.0.0.1:55433/workforce_migration_check /tmp/workforce-venv/bin/alembic -c alembic.ini check
```

Tested Docker Engine **28.4.0**. Compose configuration validation passed; network recreation preserved the named volumes. Migration exited 0, API/database/web were healthy and worker ran. Normal fixture smoke reported `smoke=passed; unauthorized_dispatch=403; execution=succeeded; task=review; audit=present`. All **25 focused backend tests passed in 84.40 seconds**. Alembic reported `No new upgrade operations detected.` No new migration or backend source was added, so the existing verified non-root backend/web images were reused rather than claiming a new image build.

The final egress probe reported, for both API and worker:

```text
routes=isolated; db=reachable; direct=denied; http=denied; proxy=denied; connect=denied; web_forward=denied
egress_smoke=passed; synthetic_positive=passed; backend_bypass=denied
```

The script's first configuration check needed to normalize Docker's `CAP_` prefix in inspected capability names. The corrected final script passed the full synthetic probe. This reuses the local volumes and bootstrap repair recorded in `read-effect-validation.md`; no fresh-volume startup, image rebuild, full backend suite, browser check, real DNS deadline, real TLS handshake or production firewall test was run for this configuration-only slice.

## Remaining gate

Product outbound reads remain disabled and now have no backend external route in default Compose. A separately mediated, narrowly authorized egress broker would be required to permit a controlled read without restoring general backend egress. Real resolver deadlines and TLS acceptance remain the next transport proof. Paid/native activation and production integrations remain gated.
