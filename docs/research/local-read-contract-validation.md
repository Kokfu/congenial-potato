# Local external-read contract: Phase 7.1

Date: 2026-10-08. Branch: `phase-7-read-contract`. Parent: Phase 6 gate draft PR #34.

This is an **isolated local experiment**, not a registered agent tool or API.
`ReadRequest`, `LocalReadGrant` and `ReadResult` are strict typed contracts.
The test transport is disabled unless the caller explicitly enables it, and
the only allowed socket destination is the exact granted
`http://127.0.0.1:<port>` origin for one project and agent. It sends one GET,
does not use proxies or follow redirects, accepts only UTF-8 text/plain or
text/html, rejects compressed responses, and bounds bytes and socket time.
The result records URL, retrieval time, SHA-256, MIME type, size and an
`external_claim` trust label. The local server contains synthetic claims only.

The experiment uses Python 3.12.12 standard-library HTTP and the pinned
Pydantic 2.13.5 (MIT). There is no new dependency or credential. Installed
Pydantic metadata and the request/result methods were checked in the test
environment; the backend image imported the module as its non-root user with
network disabled and a read-only filesystem.

## Reproduce and result

```sh
PYTHONPATH=backend/src APP_DATABASE_URL=postgresql+psycopg://postgres:phase1fixture@127.0.0.1:55433/workforce_test INITIAL_ADMIN_PASSWORD_FILE=/tmp/test-secret SESSION_COOKIE_SECURE=false /tmp/foundation-venv/bin/pytest -q backend/tests/test_local_read_experiment.py
PYTHONPATH=backend/src APP_DATABASE_URL=postgresql+psycopg://postgres:phase1fixture@127.0.0.1:55433/workforce_test INITIAL_ADMIN_PASSWORD_FILE=/tmp/test-secret SESSION_COOKIE_SECURE=false /tmp/foundation-venv/bin/pytest -q backend/tests
docker build --secret id=proxy_ca,src="$CODEX_PROXY_CERT" -f docker/backend.Dockerfile -t workforce-backend:phase1 .
docker run --rm --network none --read-only --entrypoint python workforce-backend:phase1 -c 'from workforce.local_read_experiment import ReadRequest; print(ReadRequest.__name__)'
```

The **2 focused tests** passed against a local `ThreadingHTTPServer`, and
**104 backend tests** passed in the full suite. The fixture verified default
denial before any request; wrong project, agent, host, fragment, metadata
address and expired grant denial; bounded content and digest; 302 rejection
without fetching its target; content-length rejection; and a socket timeout.
The non-root backend image built and imported the isolated module in a
network-disabled, read-only container. No real external site or paid model
was contacted. Existing Compose runtime remains unchanged because this
experiment is not registered.

## Limits before any product network tool

The grant is an in-memory test contract, not a persistent policy record. The
code intentionally permits only a literal loopback address behind a test
flag. It does not validate public DNS resolution, socket peer IP, redirects
across origins, DNS rebinding, response decompression, or real egress
isolation. Phase 7.2 must provide those defenses and prove them before a
controlled outbound read can enter the tool gateway. Phase 7.3 must persist
source provenance and test prompt injection against the deterministic
permission boundary. Synthetic text is untrusted and never becomes an agent
instruction merely because a read returned it.
