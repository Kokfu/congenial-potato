# Phase 5 governed tool fixture gate

Date: 2026-10-08. Branch: `phase-5-tool-gate`. Parent: Phase 5.4 draft PR #28.

## Boundary and result

The registered fixture tools are `project.memory.search`,
`project.artifact.read` and `project.artifact.write`. Typed proposal parsing,
canonical project resources, the agent project grant, both project and agent
policy rules, budget/cancellation checks, durable approval where required,
and a persisted invocation precede the synthetic effect. Unknown tools and
arguments fail closed. `project.artifact.write` now has a definition-level
minimum approval requirement; an `allow` policy cannot remove it. Its schema
hash includes the effect and approval requirement, so changing either
invalidates an existing approval. The owner UI displays the exact arguments,
resource, target version, expiry and approval hash before a decision.

The gate **passed for the registered fake-provider and synthetic-effect
paths**. A concurrent worker test attempted the same approved write twice;
one call applied it and the other did no work. It found one synthetic ledger
row and traced the project, execution, invocation, approval, payload hash and
audit event. A read fixture retrieved one validated artifact version. The
write produced no real artifact version or external effect.

Earlier Phase 5 evidence covers changed arguments/schema/target, policy
revocation, cancellation, duplicate dispatch, crash after the separate
synthetic ledger commit, unknown outcome and API/worker restart around an
approval. Root budget and cancellation behavior were also tested in the
provider and collaboration phases. The API/worker restart script from Phase
5.4 succeeded with one fake ledger effect and zero artifact versions.

## Reproduce

Use the disposable test PostgreSQL on `127.0.0.1:55433`, the mounted owner
password file, and the locked backend/frontend dependencies. The local web
server is bound to loopback port 8080. From the repository root:

```sh
cd backend
APP_DATABASE_URL=postgresql+psycopg://postgres:phase1fixture@127.0.0.1:55433/workforce_test /tmp/foundation-venv/bin/alembic -c alembic.ini check
cd ..
PYTHONPATH=backend/src APP_DATABASE_URL=postgresql+psycopg://postgres:phase1fixture@127.0.0.1:55433/workforce_test INITIAL_ADMIN_PASSWORD_FILE=/tmp/test-secret SESSION_COOKIE_SECURE=false /tmp/foundation-venv/bin/pytest -q backend/tests
cd frontend && npm run build && npm run test:e2e && cd ..
docker build --secret id=proxy_ca,src="$CODEX_PROXY_CERT" -f docker/backend.Dockerfile -t workforce-backend:phase1 .
docker build --secret id=proxy_ca,src="$CODEX_PROXY_CERT" -f docker/web.Dockerfile -t workforce-web:phase1 .
docker compose up -d --no-build --force-recreate migrate api worker web
docker compose ps
python scripts/smoke.py
```

Alembic reported no pending operations. **93 backend tests** passed; the
frontend build passed; **3 Chromium tests** passed, including owner review of
the synthetic tool invocation. Both non-root images built. Compose migration,
API, worker and web started; API, database and web were healthy. The smoke
test reported `unauthorized_dispatch=403`, `execution=succeeded`, task in
review and an audit record. One Compose recreation initially ran out of disk
space while creating the migration container. Pruning unused Docker builder
cache freed space, and the next recreation succeeded. No application state
was removed for that cleanup.

## Remaining limits and next work

This is a fixture gate, not proof of universal mediation. There is no exposed
model-generated shell, arbitrary filesystem, broad network, MCP or alternate
native runtime tool path to test. Adding one requires a new bypass review and
isolation before use. The fake effect ledger demonstrates idempotency and
reconciliation only for its own key; an unknown external result must be
reconciled with the external system before retry. No paid provider, external
write, public service or production credential was used. Native activation
remains gated separately.

No ADR change was required: the tested boundary matches the custom control
layer decisions from Phase 0. The smallest next phase is 6.1: migrate a
bounded owner-managed UTC daily schedule with a durable occurrence key,
overlap rule and explicit missed-run policy. Acceptance requires deterministic
restart and duplicate-occurrence fixtures before enabling automatic dispatch.
