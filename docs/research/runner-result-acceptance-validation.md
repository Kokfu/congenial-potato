# Durable synthetic runner result acceptance: Phase 8.2b.5b

Date: 2026-10-16. Branch: `phase-8-runner-result-acceptance`. Parent: draft PR #59 (`5a97890`).

## Boundary and behavior

The explicitly enabled fixture service authenticates the exact host-signed envelope and private admission capability, locks existing root/invocation/approval/attempt authority, and records one bounded metadata payload keyed by consumed invocation. First acceptance rechecks current approval, policy, project/agent grants, image/code/profile/input/scope, source/root cancellation and positive available root budget. It rechecks after waiting for the independent activity cursor, then checks manifest/result time immediately before staging acceptance. A project FK/key-share lock precedes grant locks to avoid inversion with the owner grant writer.

The result row, attempt status/hash, invocation status and audit/activity commit together. The trust origin is explicitly `synthetic_runner`; the record contains digests and sizes, no input text, raw admission capability or result key. A duplicate must authenticate and match the stored payload, payload hash, accepted-attempt hash and scope exactly. It returns frozen historical metadata without another audit, result or job launch. Historical identity verification permits this exact replay after expiry or grant revision; it never authorizes first acceptance or further execution. Altered signed deliveries or corrupted recorded payloads cannot overwrite history.

Invalid current authority retains an unknown attempt and invalidates approval/invocation authority. Wrong signature/capability does not burn valid ongoing authority. Lost/unaccepted results never clear consumed admission; neither replacement journals nor response loss permits a second launch. The migration preserves existing unknown fences and refuses to erase accepted results on downgrade. Service immutability and digest validation do not protect against a database administrator rewriting all linked records.

The test-only bridge may explicitly request durable acceptance after host-only signing. API/worker imports and normal tool dispatch do not import this service, runner admission or the job. There is no product result API, runner transport/service, Docker socket, result-to-context promotion, cost settlement or external-write integration. HMAC authenticates a trusted host key holder; it is not execution attestation or evidence of external truth.

## Validation

The initial focused result/admission command passed **141 tests, 2 skipped in 63.39s**. After adding real PostgreSQL lock waits, the acceptance file passed **33 tests, 7 skipped in 28.36s**. The skips were explicitly gated Docker cases. The first Docker command stopped at a test callback signature error after **34 passes**; correcting that fixture hook is included in the final run below.

The new tests cover one result/audit/activity under concurrent delivery, exact replay after real expiry, authentication failures without burning authority, each changed authority/binding, first-delivery expiry, changed validly signed metadata, stored-payload corruption, disabled-before-database behavior, data-bearing migration preservation/refusal and actual process exit after commit followed by fresh-interpreter replay without launching again. Two lock tests observe PostgreSQL `wait_event_type = Lock`: approval expiry during an activity cursor wait is denied, and an owner holding Project can lock/change the runner grant without a deadlock while acceptance waits on Project.

Seven real pinned-image/no-network fixture jobs cover successful acceptance and grant revision, cancellation or approval expiry after computation and after signing. Each verifies accepted-or-unknown database state, refusal to reenter the bridge with a replacement empty journal, and removal of the runner container. These are trusted local test seams, not an untrusted RPC.

The backend image built as `sha256:1393ce660ff60447048b982b9d6cb40c063a5094f3eb63c185158cb54ab34ea1`. Its UID 10001/read-only/network-none probe passed inert product imports and explicit fixture-service import. Two earlier probes omitted the explicit non-root user and could not import owner-only source with all capabilities dropped; those failed invocations are not validation. Fresh isolated Compose passed fresh volumes, both databases, non-root processes, authenticated fixture execution, independent API/worker egress denial and resource cleanup.

The corrected final Docker-enabled result/contract/admission command passed **152 tests in 186.11s**, with no skips. This includes nine actual runner bridge cases: the seven new acceptance cases plus existing admission and host-signing cases. Alembic metadata check reported `No new upgrade operations detected.` All 76 local links across the changed documents resolved, and `git diff --check` passed.

The final full backend suite passed **663 tests, 32 skipped in 546.99s (9:06)**. The 32 skips are the 23 legacy Docker isolation/broker cases plus nine runner admission/signing/result bridge cases. All nine runner bridge cases passed in the separate 152-test Docker-enabled command; the legacy 23-case Docker gate was not repeated. Host tests used Python 3.12.14; built-image imports and actual jobs used Python 3.12.12.

```sh
# Disposable local PostgreSQL; synthetic credentials, no application stack adopted:
docker run -d --name workforce-runner-result-test --label workforce.fixture=runner-result -p 127.0.0.1:55433:5432 -e POSTGRES_PASSWORD=phase1fixture -e POSTGRES_DB=workforce_test postgres:17.6
# From backend/, APP_DATABASE_URL points at this workforce_test database:
/tmp/workforce-venv/bin/alembic upgrade head
# From repository root, PYTHONPATH=backend/src, same APP_DATABASE_URL:
WORKFORCE_DOCKER_GATE=1 /tmp/workforce-venv/bin/python -m pytest -q -x backend/tests/test_runner_result_acceptance.py backend/tests/test_runner_result_contract.py backend/tests/test_runner_admission.py
/tmp/workforce-venv/bin/python -m pytest -q backend/tests
BUILDX_CONFIG=/tmp/workforce-buildx docker build --secret id=proxy_ca,src="$CODEX_PROXY_CERT" -f docker/backend.Dockerfile -t workforce-backend:phase1 .
/tmp/workforce-venv/bin/python scripts/clean_compose_smoke.py
# From backend/ with the same database:
/tmp/workforce-venv/bin/alembic check
```

## Limits and next task

Only synthetic metadata is accepted. Positive root budget is an authority check; no monetary cost or compute reservation is invented. Durable means the local database commit survived process exit; physical power loss, stale restore, a hostile host/kernel, malicious key holder, production image/key/transport lifecycle and real outbound integrations remain unproved. Earlier full kernel isolation evidence is distinct from this bridge integration. Browser behavior is unchanged and was not retested.

Next consolidate the governed-runner fixture gate and its acceptance matrix, explicitly distinguishing lost-before-commit, lost-after-commit, historical replay and restore/key/transport limits. Keep Phase 8 product execution and Phase 7 outbound product reads closed. No paid model activation, merge, public deployment or production integration is authorized.
