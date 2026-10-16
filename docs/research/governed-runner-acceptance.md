# Governed runner fixture acceptance and closed product gate

Date: 2026-10-16. Branch: `phase-8-runner-fixture-acceptance`. Parent: durable result acceptance draft PR #60 (`f3b686f`).

The fixed synthetic digest job now has a local governed path through exact owner pins, staged approval, independent consumed admission, isolated computation and durable authenticated metadata acceptance. This is a **test-only fixture path**. Product runner execution remains disabled. Phase 7 product outbound reads and Phase 2 paid/native activation remain closed independently.

## Acceptance matrix

| Requirement | Evidence and practical boundary |
| --- | --- |
| Fixed reviewed job and bounded input | Strict versioned manifest and canonical UTF-8 input; exact project/agent/root/attempt/expiry; no model-selected commands/images/env/paths/mounts/network/credentials. [Contract](reviewed-runner-contract-validation.md). |
| Independent OS isolation | Pinned image and reviewed job digest; UID 10001, read-only root, no network/mounts, dropped capabilities, bounded CPU/memory/PIDs/time/output and independent watchdog. Shared host kernel remains trusted. [Isolation](isolated-runner-validation.md). |
| Owner-pinned grants | Current project/agent execution authority plus owner-controlled exact profile/revision/hash/image/job pins and expiry/revocation. [Grants](runner-grant-validation.md). |
| Inert proposals and exact approval | Typed proposal, project and agent policy ceilings, exact staged payload/policy/grant/input/scope, changed-authority rejection. Product approval stays staged. [Proposals](runner-proposal-validation.md), [approval](runner-approval-validation.md). |
| Independent prelaunch admission | One committed DB attempt before private capability delivery or launcher entry; repeated/concurrent/restarted admission is unknown regardless of local journal replacement. Root cancellation/budget and current authority checked throughout one trusted bridge invocation. [Admission](runner-admission-validation.md). |
| Host-authenticated bounded metadata | Domain-separated strict HMAC envelope binds capability hash, exact scope/image/manifest/profile/code/input hashes/size/time. Host-only key never enters job configuration/mounts. This authenticates a key holder, not external truth or execution attestation. [Result contract](runner-result-contract-validation.md). |
| Fresh result acceptance | Rechecks database authority, bindings and expiry before first acceptance, including after a real activity lock wait. Project-before-grant locking avoids owner-writer inversion. Result/attempt hash/status/audit/activity commit atomically. [Acceptance](runner-result-acceptance-validation.md). |
| Single result and historical replay | One PK-bound metadata row and one accepted audit/activity under concurrent delivery. Exact authenticated duplicates return immutable service metadata after expiry/grant revision; never another execution. Changed or corrupted payloads cannot overwrite the record. [Acceptance](runner-result-acceptance-validation.md). |
| In-flight authority changes | Seven actual no-network jobs cover success plus grant revision/cancellation/approval expiry after computation and after signing. Failure retains unknown admission, replacement empty journal cannot launch again, and known runner containers are cleaned. [Acceptance](runner-result-acceptance-validation.md). |
| Migrations/build/startup | Admission rollback refuses consumed fences; result downgrade preserves unknown attempts and refuses accepted results. Alembic metadata check, pinned non-root image import and fresh isolated Compose fixture/egress/cleanup passed. [Admission](runner-admission-validation.md), [acceptance](runner-result-acceptance-validation.md). |

Exact commands, earlier failed probes, final counts and their limits remain in the linked slice evidence. The final acceptance run passed 152 focused Docker-enabled tests, including nine actual admission/signing/result bridge cases. The full backend run passed **663 tests, 32 skipped in 546.99s**: 23 legacy Docker cases were not repeated, while the nine runner bridge cases passed in the separate focused command. Historical full kernel-isolation and Phase 7 separate-container results are separate evidence; a single current full Docker-enabled suite is not claimed.

## Recovery distinctions

| Durable state or failure | Permitted behavior and evidence limit |
| --- | --- |
| No admitted row | Admission may proceed only with fresh exact authority; an approved proposal alone is insufficient. |
| Admission committed, capability delivery lost | Outcome remains unknown; no second manifest/capability or launcher entry. Actual admission-process exit and fresh-interpreter refusal are tested. |
| Computation may have happened, result missing/rejected | Retain consumed unknown admission. Do not rerun, infer non-execution, invent a receipt or promote context. Authority mutations and journal replacement are tested. |
| Accepted result commit, response lost | Return the exact authenticated historical record; no new job, row or accepted event. Actual postcommit process exit and fresh-interpreter replay are tested. |
| Exact replay after expiry/revision | Read historical fixture metadata only. Private capability/key and exact stored identity remain required; this is no execution permit. |
| Private capability or host result key lost | Fresh-interpreter missing/wrong identity tests preserve unknown and accepted history; retained original identity only accepts/replays metadata. No recovery/rotation/reissuance mechanism is implemented. DB hashes alone cannot authenticate delivery. [Recovery regressions](runner-result-recovery-validation.md). |
| Stale DB plus journal/key restore | May erase admission/unknown/result history. Existing process-crash tests do not establish safe restore. Keep product activation closed pending a quiesced recovery/epoch/key policy and independent acceptance. |
| Physical power loss or hostile host/kernel/key holder | Not verified. Local DB commit/process-exit evidence and HMAC cannot establish these guarantees. |

These outcomes concern synthetic computation metadata only. There is no external side-effect receipt/reconciliation, cost settlement or invented monetary charge. Positive available root budget is a current admission/acceptance check; container resource caps are separate enforcement.

## Product activation remains closed

Source inspection shows `main.py`, `worker.py` and `tool_effects.py` do not import the runner admission, fixture job or result-acceptance modules. The ordinary dispatcher selects `admitted` invocations and explicitly blocks the runner action if one is forced into that state. Runner proposals/approvals remain inert. `RunnerResult` is not a memory/context source. Compose has only db/migrate/api/worker/web, with no runner service, Docker socket or result-key settings. The fixed provider registry remains fake-only. These observations describe the current deployed code boundary; they are not an arbitrary-code sandbox claim.

Before product execution, independently verify trusted runner identity, protected key/capability lifecycle, image supply chain/update/revocation, authenticated confidential transport, clock policy, admission continuity across recovery, bounded service queue/concurrency/cleanup and incident cancellation in a deployed isolated topology. A host fixture callback and caller-supplied key are not that topology. Real destinations/credentials/paid activations still require explicit user authorization outside current scope.

## Consolidation validation

This slice changes documentation only. AST inspection of the three product modules found no imports of runner admission/job/result acceptance; registry introspection confirmed all seven installed adapters inherit `FakeAdapter`. Source inspection confirmed the explicit runner-action dispatcher guard and no result consumption outside its fixture service/model/contract. `docker compose config --services` returned only db/migrate/api/web/worker. All **95 local links** across modified documents resolved, and `git diff --check` passed. The parent full backend, Docker-enabled runner, migration/image and clean Compose checks above were not rerun for this documentation slice.

## Recovery follow-up and next bounded task

The [synthetic recovery follow-up](runner-result-recovery-validation.md) now verifies actual process exit after accepted-state SQL flush but before commit, and missing/wrong private identity across fresh interpreters. Rollback preserves consumed unknown admission and no result/events; retained original identity only accepts/replays the original metadata. Its exact counts and limits remain separate from the parent full suite.

Next define an inert synthetic external-write receipt/reconciliation contract with exact approved effect identity and explicit unknown outcomes. Keep any later fake-ledger integration isolated; general shell/browser execution, real writes and production integration stay deferred.
