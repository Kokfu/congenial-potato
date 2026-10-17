# SQLite connection lifecycle: Phase 8.4bo

Date: 2026-10-17. Branch: `phase-8-witness-sqlite-connection-lifecycle`. Parent: draft PR [#138](https://github.com/Kokfu/congenial-potato/pull/138), commit `4a2e547e3bbab250d018fe9cd698df15fe9490fb`.

The local witness used SQLite connections as context managers, which provide transaction commit/rollback but do not close the handle. A disposable parent-source probe disabled cyclic garbage collection, made 100 authenticated generation queries and observed 100 additional retained file descriptors. The same probe after this fix observes zero additional descriptors. This isolates deterministic release from eventual garbage collection; it is not a service-wide resource bound.

The private connection helper now manages the transaction context and closes the handle in `finally`, including failures while configuring the connection. Existing explicit transaction and commit ordering remains intact.

Four regression cases failed on the parent because retained connections remained usable. They now verify closure after initialization/reopen, normal queries, reservation retry, consumption/replay denial, generation advancement/retry, injected protocol/SQLite failures after the consumed update, and injected PRAGMA setup failure. Failure cases verify rollback leaves the ticket consumable once and produces exactly one reservation/consume audit pair. Tests retain connection references so garbage collection cannot conceal an omitted close.

```sh
/workspace/witness-venv/bin/python scripts/check_local_witness.py
/workspace/witness-postgres-venv/bin/python scripts/check_local_witness_postgres.py
```

Results: **157 local cases passed in 6.48s**, **65 product-source import checks passed**, **15 files compiled**, with inventory **63/13/47/1/24/9**. The disposable PostgreSQL command then passed **7 cases, 28 deselected in 11.45s**, with fresh application/DBOS migrations and its own 65-file source check. Its exact label-verified container `witness-pg-ec5d2668916a47d7a51bed42e171864e` and network `witness-net-ec5d2668916a47d7a51bed42e171864e` were removed. Markdown targets and whitespace checks passed. The full 35-case admission result remains the [prior checkpoint](witness-current-postgres-checkpoint.md), without rerun or count aggregation.

This changes test-only fixture resource management. It does not establish filesystem race resistance, protected storage, power-loss behavior, service availability, caller/effect quiescence or independent recovery guarantees. All [external prerequisites](witness-trust-boundary-lifecycle.md) and disabled product dispatch/paid-model/real-effect/deployment/merge gates remain in force.
