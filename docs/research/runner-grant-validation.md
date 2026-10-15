# Inert owner-pinned runner grants: Phase 8.2b.1

Date: 2026-10-15 (Asia/Kuala_Lumpur). Branch: `phase-8-runner-grants`. Parent: draft PR #54 (`c89fa48`).

## Boundary

Persist one owner-controlled grant per project/agent/reviewed profile. Each grant binds the fixed profile ID, revision and canonical hash; an exact immutable Docker image ID (`sha256:` plus 64 lowercase hex digits); and the reviewed fixture job source digest. The authenticated metadata endpoint publishes the reviewed pins without importing or reading executable fixture code. Owner pins are attestations: this route neither contacts Docker nor proves an image contains the reviewed code/imports. The test-only launcher still performs its separate image/code checks.

Creation requires `expected_revision: 0`; every update must match the current revision, then increments it. Project row locking serializes concurrent first writes. Expiry is timezone-aware and at most 30 days ahead while enabled. An expired grant can be disabled without renewing its authority. Every successful update records audit and project activity; rejected writes persist neither. Unknown fields, mutable image tags, alternate profiles, wrong code/profile hashes and primitive coercions are rejected. Python callers and copied models are revalidated too.

The lookup locks and refreshes the exact grant and agent, requires an active agent and current project execution grant, matches all requested binding fields, and checks expiry after lock waits. The shared project authorization helper now refreshes locked grant rows, so an already-loaded ORM object cannot hide committed revocation. Lookup requires the caller to retain the transaction; it supplies no approval, policy, root-budget, cancellation or independent attempt admission guarantee.

There is no runner tool registration, proposal/approval route, launcher import, Docker socket, worker effect route or result provenance in this slice. Product read activation, arbitrary code/shell/browser, paid models and real external effects remain closed.

## Validation

The focused grant/read/policy command passed **30 tests in 8.94s**, including concurrent first creation (one success, one stale revision), copied-model bypass rejection, cross-scope/image denial, expiry, inactive agents, revocation with retained ORM objects, and absence of rejected-write audit rows. The earlier grant/read/contract command passed **85 tests in 17.80s** before the shared refresh refinement.

The final full backend command passed **459 tests, 23 skipped in 462.31s (7:42)**. Docker acceptance was deliberately not enabled for that run: its 14 runner and nine broker container cases were skipped. The parent's 456-test Docker-enabled run remains historical evidence, not a rerun on this change. No independent arbitrary-code/runner acceptance is claimed here.

Fresh schema upgrade, a sequential post-suite downgrade/upgrade of the new migration, and Alembic metadata check passed (`No new upgrade operations detected.`). The full run also passed the existing data-bearing broker migration cases across this new head. The backend image built as `sha256:ca54d2b97fe7c56c7045f0c2c4e8df764ecb5f78678e7006fed1e8e1015dc44d`. Its UID 10001/read-only/network-none import probe passed without importing the fixture executable. Source/OpenAPI inspection confirmed the two metadata routes and no launcher import. All 71 local links from modified linked documents passed; whitespace check passed.

Fresh isolated Compose initialized both databases, verified non-root PID 1 identities, passed authenticated fixture execution, independently denied API/worker direct/HTTP/proxy/CONNECT/web-forward access to the synthetic sink, and verified removal of its containers/networks/volumes. The environment began with no containers/images; the separate disposable test PostgreSQL container was not adopted from a previous session.

Initial default-sandbox Git/local-socket commands failed; adding permitted network access allowed the normal proxy/local fixture path. The first uv command targeted a read-only default cache, then succeeded with `/tmp` cache/venv. The initial buildx default directory was read-only; `/tmp/workforce-buildx` fixed it. The Compose web build omitted the session CA and failed in npm (`Exit handler never called`); the direct web build with the provided CA secret passed TypeScript/Vite. TLS verification stayed enabled. No failed attempt is counted as validation.

```sh
# From repository root unless otherwise stated.
uv --cache-dir /tmp/workforce-uv-cache pip sync --python /tmp/workforce-venv/bin/python backend/requirements-dev.lock
PYTHONPATH=backend/src APP_DATABASE_URL=postgresql+psycopg://postgres:phase1fixture@127.0.0.1:55433/workforce_test /tmp/workforce-venv/bin/pytest -q backend/tests/test_runner_grants.py backend/tests/test_read_grants.py backend/tests/test_tool_policy.py
PYTHONPATH=backend/src APP_DATABASE_URL=postgresql+psycopg://postgres:phase1fixture@127.0.0.1:55433/workforce_test /tmp/workforce-venv/bin/pytest -q backend/tests
# From backend/, with the same APP_DATABASE_URL:
/tmp/workforce-venv/bin/alembic downgrade -1
/tmp/workforce-venv/bin/alembic upgrade head
/tmp/workforce-venv/bin/alembic check
# Builds use the inherited proxy and the mounted session CA:
BUILDX_CONFIG=/tmp/workforce-buildx docker build --secret id=proxy_ca,src="$CODEX_PROXY_CERT" -f docker/backend.Dockerfile -t workforce-backend:phase1 .
BUILDX_CONFIG=/tmp/workforce-buildx docker build --secret id=proxy_ca,src="$CODEX_PROXY_CERT" -f docker/web.Dockerfile -t workforce-web:phase1 .
/tmp/workforce-venv/bin/python scripts/clean_compose_smoke.py
```

## Limits and next slice

The image ID is owner-supplied inert metadata. Image contents, independent database admission, cold/lost journal behavior, authenticated receipts and restore/key lifecycle remain separate gates. Future proposals must derive pins from this grant, bind its exact ID/revision and keep status `proposed` until exact approval and attempt governance are independently verified. No real outbound read, paid call, merge, public deployment or production integration is authorized.
