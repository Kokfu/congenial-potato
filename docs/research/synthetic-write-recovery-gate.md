# Synthetic-write recovery and product gate: Phase 8.3j

Date: 2026-10-16. Branch: `phase-8-recovery-witness-gate`. Parent: witness reply-ordering draft PR #71 (`448e234`).

## Verified fixture chain

The test-only chain now has strict inert intent/receipt/reconciliation contracts, a private SQLite fake ledger, independent current-authority PostgreSQL admission, and durable exact receipt acceptance. Slice evidence is linked in the [8.3 acceptance matrix](synthetic-write-fixture-gate.md). Focused evidence separately includes 120 contract/ledger/admission/receipt checks, a coordinated two-store rollback experiment that **does reexecute**, three witness-wrapper rollback cases that block only while the in-memory witness retains state, and nine issue/consume/reply-ordering checks.

This demonstrates local fixture behavior, including a known two-store recovery failure. It does not establish external execution truth, whole-system at-most-once effects, stale snapshot recovery safety, physical durability, or production authorization.

## Required independent witness properties

Any future external witness must be outside both the application DB and fake-ledger restore domains, preserve a monotonic generation and consumed invocation identities through restore/restart, and authenticate callers/responses over a protected transport. Its durable issue operation must be idempotent by a caller request identity plus exact ledger/invocation/intent binding. Its consume operation must be a one-way durable transition; after a lost consume response it may report spent/unknown, never issue a second effect permit. The service must fail closed on unavailable, stale, conflicting, unauthenticated or malformed state. Recovery operations need an auditable high-water mark and a verified restore/rotation procedure.

The in-memory simulator does not satisfy these properties: its key and state disappear on process restart, and it is not transactionally coupled to PostgreSQL or SQLite. A third local file/container/database without a separate trust boundary is not an independent witness. A witness ticket alone cannot prove that a fake or external effect occurred.

## Product boundary and decision

The new write admission, fake ledger, receipt acceptance and witness modules remain under `backend/tests`. Product `main.py`, `worker.py` and `tool_effects.py` do not import them. The existing admitted-artifact-write path returns a deterministic `simulated` result in application storage; it is distinct from the new private SQLite ledger. The runner digest proposal remains explicitly skipped by the product tool-effect dispatcher. The AST boundary check passed.

**Phase 8.3 fixture research is complete; product dispatch remains closed.** Do not wire the fake writer, receipt acceptance or simulated witness into the application. No product or deployed recovery integration is authorized in this task. Real writes, public deployment, paid model activation, merge and production credentials remain disabled.

Before a future production-integration task, require an explicitly authorized external witness and reviewable identity/key/transport lifecycle; independent multi-store restore drills; clock, concurrency, outage and incident-revocation policy; proof of fail-closed behavior after lost consume replies; and an end-to-end deployment acceptance plan. A local fixture or architecture description cannot substitute for those controls.

## Validation

This consolidation changes documentation only. The AST check inspected `backend/src/workforce/main.py`, `backend/src/workforce/worker.py` and `backend/src/workforce/tool_effects.py`; it found no product imports of the new test-only modules. Exact test commands, results and limitations are in the linked slice evidence; tests were not rerun for this matrix. `git diff --check` passed, all **89 local Markdown links** across the changed docs/progress resolved.
