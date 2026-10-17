# Existing-file-only SQLite open: Phase 8.4bp

Date: 2026-10-17. Branch: `phase-8-witness-no-create-open`. Parent: draft PR [#139](https://github.com/Kokfu/congenial-potato/pull/139), commit `484353d067597127320307a0a9dc6696dd65ea39`.

The private path validator rejects missing state, but SQLite's default open mode could recreate an empty database if the file disappeared after validation and before connect. Five deterministic parent-source regressions removed the file immediately before SQLite opened it. Reopen, generation, reserve, consume and advance each returned denial but left a newly created empty file. None established valid replacement witness state or permission to retry an effect.

The connection helper now opens an absolute, correctly escaped file URI with `mode=rw` and `uri=True`. SQLite requires an existing database file. Explicit initialization still creates its private file separately; ordinary open never gains file-creation permission. The five removal cases now deny and leave the path absent. Two compatibility cases preserve initialization, reopen and consumption for absolute/relative paths containing spaces, `#`, `?`, `%` and Unicode characters; URI punctuation cannot become connection options.

```sh
/workspace/witness-venv/bin/python scripts/check_local_witness.py
/workspace/witness-postgres-venv/bin/python scripts/check_local_witness_postgres.py
```

Results: **164 local cases passed in 5.57s**, **65 product-source import checks passed**, **15 files compiled**; inventory **70/13/47/1/24/9**, with the changed durable module independently collecting 70 cases. Focused PostgreSQL checks passed **7 cases, 28 deselected in 11.32s**, with fresh application/DBOS migrations and 65 source checks. The command removed its exact label-verified container `witness-pg-6bfcb616f7a14200951a17dfdc91f3db` and network `witness-net-6bfcb616f7a14200951a17dfdc91f3db`. Changed-document Markdown targets and whitespace checks passed. The [35-case admission result](witness-current-postgres-checkpoint.md) remains historical and was not rerun.

This prevents file creation in one deletion window. Path validation and SQLite open remain separate operations: replacement, symlink/ancestor races, deletion after open, rollback, external key custody and protected restore are not solved. No filesystem-wide race resistance, independent storage, physical power-loss or production recovery guarantee follows. All [external prerequisites](witness-trust-boundary-lifecycle.md) remain required, with product dispatch, real effects, paid models, production connections, deployment and merging disabled.
