# Phase 3 runtime-originated collaboration gate

Validated 2026-10-08 on `phase-3-runtime-collaboration`, based on PR #18's commit `46eaf50`. The runtime uses only deterministic fixture providers. No paid model, external tool or production integration was contacted. Dependencies remain the pinned versions in the backend and frontend lockfiles; this slice adds no package.

## Boundary

- Agent configuration pins an explicit `text` or `collaboration.v1` output contract. The latter requires validated structured-output capability. A deterministic fixture adapter returns JSON through the ordinary provider response path. The orchestrator branches on the application-owned contract, not a provider name.
- The DBOS worker records the model response and, for collaboration output, parses at most one bounded candidate. Strict plan, delegation and message schemas reject extra fields, duplicate JSON keys, invalid constants, excessive size and free-form instructions. The execution creates no collaboration effect. A valid candidate is persisted with source execution, project, kind, canonical payload digest and pending status. Invalid output records a denied parse audit without granting authority.
- An authenticated owner sees pending candidates and their exact canonical payload and digest in the private UI. Approval or rejection requires CSRF and the same digest. Approval revalidates source, project scope, role, grants, root budget, revision, work keys, reply limits and cancellation through the existing deterministic services. The approved plan, child or message and decision record commit in one transaction. Exact replay creates no second effect. Cancelling an execution invalidates its pending candidate; a worker sweep handles a proposal row locked during cancellation.
- Fixture JSON is deliberately deterministic. These tests validate the execution and authorization boundary, not the quality or reliability of a real model's planning. A model may propose only one collaboration action per execution; it cannot grant itself permissions or cause automatic replies. Native adapters remain disabled.

## Reproduce

Use the disposable PostgreSQL `workforce_test` and `workforce_dbos_test` databases from Phase 1. The local Compose stack uses synthetic secrets.

```sh
cd backend
APP_DATABASE_URL=postgresql+psycopg://postgres:phase1fixture@127.0.0.1:55433/workforce_test /tmp/foundation-venv/bin/alembic -c alembic.ini upgrade head
APP_DATABASE_URL=postgresql+psycopg://postgres:phase1fixture@127.0.0.1:55433/workforce_test /tmp/foundation-venv/bin/alembic -c alembic.ini check
cd ..
PYTHONPATH=backend/src APP_DATABASE_URL=postgresql+psycopg://postgres:phase1fixture@127.0.0.1:55433/workforce_test INITIAL_ADMIN_PASSWORD_FILE=/tmp/test-secret SESSION_COOKIE_SECURE=false /tmp/foundation-venv/bin/pytest -q backend/tests
cd frontend
npm run build
npm run test:e2e
```

## Evidence

- Alembic upgraded the disposable database to `e91b0267c3d4` and found no pending metadata operations. All 55 backend tests passed. Ten new tests exercised worker-originated plan, delegation and message candidates through DBOS, exact owner review and replay, no effect before decision, malformed/prompt-injected output, changed stored payload, an ineligible source role, a full root hold, a revoked target grant, cancellation, and capability refusal. The fixture worker was stopped before each owner decision in these tests, so the pending proposal survived outside the worker lifetime.
- TypeScript/Vite built. The non-root backend and web images built; local Compose migration exited successfully, PostgreSQL/API/web were healthy and the fixture API smoke check passed. Both Chromium tests passed, including review and admission of a worker-generated child proposal in the private UI.
- The first browser run could not start because the workspace was full (`ENOSPC`). Removing unused Docker build cache freed space; the same browser suite then passed. No application data or active image was removed.

## Remaining limits

This is a fixture-only Phase 3 gate. Real provider output quality, live costs and credential policy remain unverified. The Phase 2 live native activation gate stays closed. The current UI reviews proposals for the selected project; agent creation for the structured contract is available through the owner API. Phase 4 begins project-scoped memory, cited retrieval and artifact provenance checks. No vector extension is justified yet.
