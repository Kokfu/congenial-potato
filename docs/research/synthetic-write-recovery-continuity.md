# Synthetic-write recovery continuity: Phase 8.3f

Date: 2026-10-16. Branch: `phase-8-synthetic-write-recovery-continuity`. Parent: synthetic-write gate draft PR #67 (`7e38154`).

## Recovery matrix

| Control database | Private fake ledger | Fixture evidence | Result |
| --- | --- | --- | --- |
| Current admission retained | Missing or replaced | [8.3c](synthetic-write-admission-validation.md) deletes/recreates an empty SQLite ledger after the PostgreSQL fence. | Same invocation/target is denied; no second effect. |
| Rolled back before admission | Current ledger retained | Existing ledger logic in [8.3b](synthetic-write-ledger-validation.md) preserves the attempt marker and historical receipt in an intact ledger. | A duplicate `apply` of that exact intent returns history or unknown, not a fresh SQLite mutation. End-to-end restoration from real snapshots has not been tested. |
| Rolled back before admission | Rolled back to matching empty state | `test_joint_control_and_ledger_restore_exposes_reexecution_gap` removes the consumed PostgreSQL admission and pinned control identity, removes the fake-ledger database, and retries the unchanged invocation/intent/approval. | **A second distinct signed event is produced.** Both stores losing their fence permits re-execution. This is a deliberate failing-safety demonstration; the test passes because it detects the gap. |
| Current admission and current ledger retained | Current | [8.3d](synthetic-write-receipt-acceptance-validation.md) stores one exact receipt and verifies historical replay leaves ledger revision/receipt bytes and audit count unchanged. | Exact authenticated historical metadata replay; no second mutation. |

The experiment uses disposable application rows and a temporary SQLite directory. It approximates restoration to pre-admission state by removing those rows and the matching ledger file; it does not use filesystem/database backups, crash recovery, multi-store snapshot tooling, production data or external writes. The distinct event UUID is evidence that the fake mutation path ran again, not an external execution attestation.

## Recovery anchor requirements

The paired local stores cannot detect a rollback that restores both to a mutually consistent earlier state. Safe recovery therefore needs at least one independently protected, monotonic witness outside both restore domains. Before any future attempt, trusted code must obtain a fresh authenticated recovery epoch/generation and bind it into the durable admission and signed fake-ledger intent. Restore or replacement must either prove it is at the witness's current generation or remain closed. The witness must reject epoch reuse/rollback, bind the service and ledger identities, and preserve a high-water mark across restoration of the application DB and ledger.

Unavailable, stale, unauthenticated or conflicting witness responses must fail closed without clearing the consumed admission or authorizing retry. Historical receipt reads may return already accepted exact metadata but cannot issue a generation or permit a new effect. Key rotation, witness outage, concurrent issuers, recovery ordering, application DB restore, ledger restore and partial restore all need explicit cases.

A third file, container or database on the same host is not an independent trust anchor merely because it has a different path or UUID; it can be rolled back together with the first two. A local fake witness can test the protocol but cannot establish deployment trust, monotonic hardware, remote service availability, key custody, physical power-loss behavior or a production recovery guarantee.

## Validation

The disposable PostgreSQL 17.6 / Python 3.12.15 internal-network test ran:

```sh
PYTHONPATH=src:tests python -m pytest -q -x -p no:cacheprovider \
  tests/test_synthetic_write_admission.py::test_joint_control_and_ledger_restore_exposes_reexecution_gap
```

Result: **1 passed in 2.31s**; the assertions observed two distinct signed event IDs for the same approved logical invocation after both local fences were restored. The control DB used tmpfs, runner and DB had only an internal no-egress network during the test, and the repository mount was read-only. Containers, network and temporary images were removed afterward.

## Next task and limits

Specify a test-only monotonic recovery-witness contract and exercise fresh-generation, stale-generation, witness-loss and concurrent-consumption cases with an explicitly simulated external witness. The simulation must be labeled as protocol evidence only and must not be treated as protected infrastructure. Do not connect it to product dispatch or claim restore safety. Real writes, paid activation, merge, public deployment, production integration, production keys/transports and physical power-loss claims remain disabled.
