# Project progress

Updated: 2026-10-07. This is the execution ledger for the approved AI workforce architecture. Work moves through these tasks in order; each task requires evidence before it is marked complete. Keep this file current as the product grows.

## Current position

- [x] Phase 0: Paperclip adoption assessment and isolated DBOS recovery proof. Evidence: `docs/research/phase-0-validation.md`, `experiments/dbos/evidence.log`. Paperclip adoption gate did not clear; use a small custom control layer over existing components.
- [x] Phase 1: persistent, self-hosted foundation. Synthetic execution and artifact effects passed the acceptance checks below. Current task: Phase 2 provider/runtime boundaries.

## Phase 1 tasks

- [x] **1.1 Repository and persistence foundation.** Pin dependencies. Create typed FastAPI application and separate worker entry point. Add PostgreSQL models and Alembic migrations for owner/session, project, agent/config revision, task/execution, authorization/audit/outbox, root budget reservations, approvals, and immutable artifact metadata. Verify migrations on a clean database.
- [x] **1.2 Secure owner access and API shell.** Provision one owner from a mounted password secret. Add Argon2id password verification, opaque server-side session with HttpOnly cookie, CSRF protection, origin checks, login throttling and logout. Add liveness/readiness endpoints, authenticated project/agent/task reads and default-deny project access. Test authentication and scope denial.
- [x] **1.3 Durable worker and controlled fixture.** Dispatch with stable workflow IDs outside request lifetime. Use fake model/tool results only. Recheck cancellation, policy and shared budget before effects; record audit and reconcile unknown outcomes. Test restart, duplicate dispatch and concurrent reservations on PostgreSQL.
- [x] **1.4 Private UI shell.** React/TypeScript/Vite navigation for Projects, Agents, Approvals, Activity and Settings. Show real API state and authentication flow, without model calls or unrestricted tools. Verify build and core flow.
- [x] **1.5 Docker and operations.** Non-root backend/web images, Compose PostgreSQL/API/worker/web/migration topology, loopback binding, health checks, persistent volumes and `.env.example`. Document clean startup, backups and restore. Build and run Compose, then test restart and persistence.
- [x] **1.6 Exact approved artifact replacement.** Store immutable fixture artifact versions and content digests; bind approvals to payload, schema, resource and target version. Reject changed or stale proposals after restart/cancellation. Verify one logical effect and provenance.
- [x] **1.7 Reconciliation and Phase 1 gate.** Persist unknown external outcomes without blind retry. Exercise a synthetic effect ledger, restore artifact bytes with both database dumps, and verify the remaining Phase 1 acceptance criteria before marking the phase complete.

## Verified Phase 1 evidence

- Fresh synthetic Compose start: PostgreSQL healthy, migration exited 0, API healthy, worker running, web served through loopback. Backend and web images built from the pinned locks.
- Seven PostgreSQL backend tests passed. They cover owner authentication and throttle, default-deny grants, concurrent root reservations, duplicate reservation keys, fixture dispatch/replay, queued cancellation/revocation, and exact artifact approval/replacement.
- `scripts/smoke.py` passed: dispatch before grant returned 403, approved fixture execution succeeded, task reached review, and audit entry persisted. One Chromium end-to-end test passed for login, project/agent creation, explicit grant, task dispatch, approval and immutable artifact creation.
- Restarted API, worker and web. Two projects, two executions and 15 audit entries remained. Replayed one delivered outbox item after worker restart: two model-call rows and two fixture-effect audit entries remained, with no undelivered outbox row.
- A fixture approval persisted while the worker was stopped; after restart it produced one artifact version. Tests rejected changed payload and hash, changed schema, stale target, revoked project grant, duplicate decision and cancellation before effect. A simulated checkpoint failure after file creation left no version; retry verified the digest and recorded one version.
- Full disposable Compose restore on port 8081 passed: owner login, seven matching projects, three matching artifact versions and all content digests. The source stack was paused for consistent dumps of both databases and an artifact archive. Earlier independent restores also matched control database counts (2 projects, 2 executions, 15 audit entries) and DBOS schema tables (13). Workflow-code upgrade compatibility remains unverified and requires versioned rollout.
- Installed package metadata checked for pinned versions and licenses: FastAPI 0.142.2 MIT, Uvicorn 0.42.0 BSD-3-Clause, SQLAlchemy 2.1.3 MIT, Alembic 1.20.0 MIT, psycopg 3.3.6 LGPL-3.0-only, pydantic-settings 2.15.0 MIT, argon2-cffi 25.1.0 MIT, DBOS 3.2.0 MIT; React/React DOM 19.3.0 MIT, Vite 8.3.3 MIT, TypeScript 7.0.2 Apache-2.0, Playwright 1.63.0 Apache-2.0.

## Later MVP tasks

- [ ] Phase 2: stable/versioned agent identities, two provider adapters, capability discovery, limits and fake-provider contract tests before opt-in capped live tests. Current task.
- [ ] Phase 3: validated plans, tasks, messages and bounded Manager/direct delegation with cycle, duplicate and cancellation tests.
- [ ] Phase 4: project-scoped facts and retrieval, immutable artifact versions and provenance tests.
- [ ] Phase 5: governed tool gateway, default-deny policy and exact-effect durable approval, including mutation/replay/restart tests.
- [ ] Phase 6: daily schedule, SSE timeline and shared daily budget, including missed-run and reconnect tests.
- [ ] Phase 7: first bounded external read with SSRF and prompt-injection boundary tests.
- [ ] Phase 8: isolated execution and external writes with idempotency and reconciliation.

## Phase 2 tasks

- [x] **2.1 Provider contracts and fake adapters.** Define application-owned typed request/response/capability/catalog contracts, normalized errors and a registry. Provide two deterministic fake adapters with differing capabilities and explicit catalog refresh; keep embeddings and media out of the conversation interface.
- [x] **2.2 Stable agent configuration changes.** Add immutable config revisions and an authenticated update path. Keep the agent ID, project grants and history stable across fake provider switches; pin each execution to its recorded config revision.
- [x] **2.3 Worker boundary and limits.** Route fixture generation through the provider registry without provider-name branches in orchestration. Validate required capabilities and reserve shared root budget before a model call. Record actual provider, model and usage with unknown values preserved.
- [x] **2.4 Failure/restart contracts.** Test switching, incompatible capabilities, timeout, cancellation and replay with deterministic fake adapters and PostgreSQL/DBOS. Then run the private UI flow and Compose restart checks.
- [ ] **2.5 Native providers after fixture gate.** Implement OpenAI and Anthropic adapters using verified current SDK APIs and licenses, with credential references outside prompts/logs. Keep all live calls opt-in, capped and disabled by default.

## Verified Phase 2 fixture evidence

- Provider boundary defines typed generation, streaming events with an authoritative final response, capabilities, catalog snapshots, usage estimates, normalized errors and cancellation/health methods. Fixture alpha and beta have different capabilities; timeout is a third failure fixture. No live adapter is registered.
- Twelve PostgreSQL/DBOS backend tests passed. Agent switching preserved one identity and project grant; executions kept config versions 1 and 2 and recorded alpha and beta model calls. Unknown reported cost remained null. Unsupported models/capabilities failed closed; a timeout ended the workflow as failed, released its root reservation and recorded no model call.
- `scripts/provider_switch_smoke.py` passed on Compose: same agent ID, two config versions, two fake provider calls. Chromium passed project/task/approval flow, switched the agent to beta and verified the next call used beta. Backend and web images built; migration exited successfully; API, DB and web were healthy.
- Replayed a completed beta outbox dispatch after restarting the worker. Model-call and successful-completion audit counts remained 15 each, and undelivered outbox count returned to zero. No paid model requests or production credentials were used.
- Remaining Phase 2 work: verify current OpenAI/Anthropic SDK versions, licenses and APIs, implement native adapters behind this contract, and test them with HTTP fixtures only before any opt-in capped live check. Provider-specific workflow version migrations need a drain/rollout procedure.

## Working rules and evidence

Use synthetic data until a phase explicitly authorizes a live integration. Do not merge or deploy publicly as part of ordinary implementation. Record command, result and limitations with each completed task. Keep provider/runtime/tool boundaries replaceable and policy failures closed. Phase 1 must meet the acceptance criteria in `docs/research/phase-0-validation.md`; passing unit tests alone is not completion.
