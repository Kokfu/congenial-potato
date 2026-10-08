# Pinned destination boundary: Phase 7.2

Date: 2026-10-08. Branch: `phase-7-network-boundary`. Parent: Phase 7.1 draft PR #35.

This remains an **isolated experiment**. No public read action is registered
in the product gateway, and execution is disabled unless a test caller opts
in. A strict `PublicReadGrant` names one project, agent and HTTPS host on
port 443 with an expiry. Preparation validates the exact URL authority and
resolves all DNS answers. Any non-global address, including loopback,
private, link-local, mapped metadata or a mixed public/private set, denies
the whole destination. Before an effect, the resolver runs again and the
answer set must match the prepared set. The connector dials the selected
numeric IP, checks the socket peer, and for HTTPS uses the original hostname
for TLS SNI and certificate verification. It uses no proxy. A single GET is
bounded by the Phase 7.1 text/byte/deadline response reader; redirects are
rejected rather than followed.

The local synthetic server tests the pinned socket and response handling.
A fake resolver supplies public and rebound answers without contacting a
real external site. A test-only connection factory maps the otherwise
public-address path to the local server; no product API or worker route
exposes that factory. Python 3.12.12 standard-library socket, IP address, HTTP and
TLS APIs are used, with Pydantic 2.13.5 for grant validation. No dependency
or credential was added.

## Reproduce and observed results

```sh
PYTHONPATH=backend/src APP_DATABASE_URL=postgresql+psycopg://postgres:phase1fixture@127.0.0.1:55433/workforce_test INITIAL_ADMIN_PASSWORD_FILE=/tmp/test-secret SESSION_COOKIE_SECURE=false /tmp/foundation-venv/bin/pytest -q backend/tests/test_local_read_experiment.py backend/tests/test_network_policy.py
PYTHONPATH=backend/src APP_DATABASE_URL=postgresql+psycopg://postgres:phase1fixture@127.0.0.1:55433/workforce_test INITIAL_ADMIN_PASSWORD_FILE=/tmp/test-secret SESSION_COOKIE_SECURE=false /tmp/foundation-venv/bin/pytest -q backend/tests
docker build --secret id=proxy_ca,src="$CODEX_PROXY_CERT" -f docker/backend.Dockerfile -t workforce-backend:phase1 .
docker run --rm --network none --read-only --entrypoint python workforce-backend:phase1 -c 'from workforce.network_policy import PublicReadGrant, PinnedHTTPSConnection; print(PublicReadGrant.__name__, PinnedHTTPSConnection.__name__)'
```

The **6 focused tests** passed. They verified exact grants, public-answer
pinning, changed and private/mixed DNS answer denial, malformed authorities,
explicit port 0 denial, wrong socket peer rejection, original-host TLS SNI
argument, default-disabled execution, and no connection after a rebound
answer. The synthetic read succeeded only through the test transport, and
a redirect did not reach its target. **108 backend tests** passed before the
port-0 corner fix; the focused six were rerun after that fix. The backend
image built on the final source and imported the module as the non-root user
with network disabled and a read-only filesystem. No real external site,
paid model or production integration was contacted.

## Remaining security gates

The grant is still in memory and not connected to persistent tool policy,
budgets, cancellation, approval or audit. Synthetic tests supplied DNS
answers; real resolver deadlines and a real HTTPS certificate handshake
have not been measured. A proxy/firewall must enforce outbound egress
independently of application code before a product fetch is enabled.
Phase 7.3 will persist external observation provenance and verify prompt
injection cannot gain authority. Phase 7.4 must exercise the complete
gateway with local deterministic network fixtures, cancellation and restart
before permitting a controlled outbound read.
