# Inert typed runner proposals: Phase 8.2b.2

Date: 2026-10-15 (Asia/Kuala_Lumpur). Branch: `phase-8-runner-proposals`. Parent: draft PR #55 (`a4d6e76`).

## Boundary

`project.runner.digest` accepts only a project UUID and an input object containing at most 4096 UTF-8 bytes of text. The registered definition conservatively labels execution as a write with mandatory approval. It is a proposal definition, not an executor. Models cannot select profiles, revisions, code, images, commands, credentials, environment, mounts or resource limits. The canonical policy resource is the exact fixed `runner-profile:synthetic.text-digest` within the project. The owner policy API accepts this fixed `profile_id` separately from artifact UUIDs and web hosts and rejects mixed resource kinds.

Deterministic admission requires current project execution authority, both project and agent policy ceilings, explicit-deny precedence, an active agent and a current exact owner runner grant. Resolve pins from owner metadata, revalidate them, then lock and recheck the grant and agent. Persist the exact grant ID/revision, profile revision/hash, immutable image ID and reviewed job digest in the invocation policy snapshot; canonical arguments/hash bind the exact input. A concurrent pin change during resolution fails conservatively. Refresh locked policy rows so retained ORM objects cannot hide a committed owner deny.

Accepted invocations remain `proposed`, never `awaiting_approval` or `admitted`. No automatic approval is created. Generic approval creation and decision explicitly reject runner actions; the web-specific staging route also rejects them. The product effect dispatcher explicitly skips runner actions even if an internal fixture mutates status to `admitted`. Cancellation invalidates the proposal using the existing subtree path. There is no launcher import, Docker access, runner service, manifest issuance, receipt/provenance or model-context promotion.

## Validation

The initial focused command passed **75 tests in 60.03s**. After adding retained-policy refresh and explicit approval-creation coverage, the final focused command passed **79 tests in 68.73s**. It includes actual synthetic DBOS worker output; canonical input/resource/hash and exact owner pins; missing project/agent ceilings; missing/expired/revoked/corrupt grants; explicit deny; rejected arbitrary configuration and oversized Unicode; duplicate recording; cancellation; closed decision/web-staging/approval-creation paths; and a deliberately forged `admitted` row producing no product effect. Existing artifact and staged-read approvals/effects and concurrent fake-write gate cases also passed.

Alembic metadata check passed with no new operations. No schema change is introduced. The backend image built as `sha256:ac328db4d59eb03c3f2c4ec52d4dbf12bc9943806a0f680999ee862cb5ec68a2`. Its UID 10001/read-only/network-none import probe verified mandatory approval declaration, metadata-only runner endpoints and no fixture-job import. All 72 modified-document local links and whitespace checks passed.

Fresh isolated Compose initialized both databases, ran non-root processes, passed authenticated fixture execution and independent API/worker egress-denial probes, and removed all fixture-owned resources. The full 459-pass/23-skipped backend run belongs to parent #55; it was not repeated after this proposal change. Docker runner/broker acceptance and browser tests were not run for this slice; no new runner execution or hostile-code acceptance is claimed.

```sh
PYTHONPATH=backend/src APP_DATABASE_URL=postgresql+psycopg://postgres:phase1fixture@127.0.0.1:55433/workforce_test /tmp/workforce-venv/bin/pytest -q -x backend/tests/test_runner_proposals.py backend/tests/test_runner_grants.py backend/tests/test_tool_policy.py backend/tests/test_tool_gateway.py backend/tests/test_tool_approval.py backend/tests/test_tool_effects.py backend/tests/test_tool_gate.py
# From backend/, with the same APP_DATABASE_URL:
/tmp/workforce-venv/bin/alembic check
# From repository root, with inherited proxy/CA:
BUILDX_CONFIG=/tmp/workforce-buildx docker build --secret id=proxy_ca,src="$CODEX_PROXY_CERT" -f docker/backend.Dockerfile -t workforce-backend:phase1 .
/tmp/workforce-venv/bin/python scripts/clean_compose_smoke.py
```

## Limits and next task

These rows are reviewable candidates, not durable execution authorization. An existing proposal may remain visible after grant expiry/revision changes; the next exact staged-approval slice must rederive current authority and invalidate stale snapshots. Approval must bind image/code/profile/input/scope and exact grant revision. Independent database attempt admission, current root-budget/cancellation checks around isolated execution, authenticated result handling, unknown/cold-journal fences and recovery remain subsequent work.

The owner image pin remains an attestation until the separate launcher verifies reviewed code/image contents. No arbitrary shell/browser, real outbound read/write integration, paid model activation, merge, public deployment or production integration is enabled.
