# Synthetic external-write fixture gate: Phase 8.3e

Date: 2026-10-16. Branch: `phase-8-synthetic-write-gate`. Parent: durable receipt acceptance draft PR #66 (`6a9c639`).

## Acceptance matrix

| Slice | Established in local fixtures | Not established |
| --- | --- | --- |
| [8.3a contract](synthetic-write-contract-validation.md) | Strict canonical intent, exact receipt binding, HMAC metadata authentication, nonce-bound `applied` / `not_applied` / `unknown` reconciliation shapes. | Approval, database authority, ledger mutation, actual execution truth, retry permission, key lifecycle or transport. |
| [8.3b ledger](synthetic-write-ledger-validation.md) | Private SQLite fake ledger consumes an invocation marker before mutation; applied bytes/receipt commit together; unknown and terminal precondition failures never reexecute in an intact ledger. Process-exit and historical replay cases were exercised. | Database authority, full-ledger loss/replacement safety, stale restore, physical power loss or external truth. |
| [8.3c independent admission](synthetic-write-admission-validation.md) | Exact owner-approved proposal and current policy/grant/agent/scope/root budget/cancellation gate a committed PostgreSQL target-revision fence before SQLite open. Empty/deleted ledger replacement cannot replay while that control database remains intact. | Joint control-database plus ledger deletion/restore, cross-system atomicity, production identity or dispatch. |
| [8.3d receipt acceptance](synthetic-write-receipt-acceptance-validation.md) | One exact signed receipt is durably stored against its consumed admission under fresh authority. Invalid/missing delivery leaves `unknown`; exact historical replay adds no ledger mutation or duplicate audit. | Proof the signed receipt reflects external execution; ledger re-discovery/independent reconciliation at acceptance; accepted metadata is not product output or model context. |

The 8.3a–8.3d evidence is slice-specific; counts are not summed as one unique test total. Latest combined receipt/admission/ledger/contract command passed 120 tests. Its exact command, database versions, migration checks and limitations are in the 8.3d evidence.

## Product boundary inspection

The worker calls the existing `apply_admitted_tools` fixture effect service. That service makes `project.artifact.write` a deterministic simulated result in the application database and explicitly skips the inert `project.runner.digest` action. It does not import or invoke `synthetic_write_admission`, `synthetic_write_ledger`, `synthetic_write_receipt_acceptance` or the write receipt contract. The new private fake-ledger bridge and receipt acceptance remain test-only modules; the product dispatcher has no import or route to them. The three-module AST import check for `main.py`, `worker.py` and `tool_effects.py` passed. This source inspection does not prove a deployed topology or hostile-host isolation.

## Closed gate and required follow-up

**Do not connect this fake ledger or receipt acceptance to product dispatch.** An intact independent control database prevents an empty/replaced SQLite ledger from authorizing the same approved target again, but jointly deleting/restoring both stores can erase both consumed fences. A signed receipt authenticates metadata from the fixture key holder, not external truth. No deployed key custody, protected transport, recovery epoch, stale-restore procedure, physical power-loss behavior or production integration has been validated.

The next bounded task is to define a recovery-continuity design and local adversarial fixture matrix for loss/replacement of one store versus both stores, including the external trust anchor needed to reject joint stale restore. This is research and isolated fixture work only; do not add product dispatch. Real writes, paid activation, merge, public deployment and production integration remain disabled.

## Validation

This consolidation changes documentation only. The AST check inspected `backend/src/workforce/main.py`, `backend/src/workforce/worker.py` and `backend/src/workforce/tool_effects.py`; it found no imports of the new synthetic-write admission, ledger, receipt-acceptance or contract fixture modules. All **87 local Markdown links** across the modified docs/progress resolved and `git diff --check` passed. The 120-test suite and migration checks are the separate 8.3d evidence above; they were not rerun for this documentation-only matrix.
