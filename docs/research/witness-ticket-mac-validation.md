# Consume ticket MAC validation: Phase 8.4bm

Date: 2026-10-17. Branch: `phase-8-witness-ticket-mac-validation`. Parent: draft PR [#136](https://github.com/Kokfu/congenial-potato/pull/136), commit `74faf2969bfa5b39f7bb4e3788fd9c03d2fc3da4`.

An authenticated direct consume request containing a non-ASCII ticket MAC previously reached `hmac.compare_digest` and raised `TypeError` rather than `WitnessDenied`. A disposable parent-source probe reproduced that error with unchanged state, and the new direct regression failed on the parent for the same reason. The Unix handler already caught `TypeError` and denied these requests; this change makes the direct protocol boundary consistent and rejects malformed ticket MACs before opening the database.

Consume now requires a strict string containing exactly 64 lowercase hexadecimal characters before comparing ticket bindings. Authentication and exact stored-ticket/state-key checks still apply. No protocol format, key material, product code or dispatch configuration changes.

## Checks

The two new direct/real Unix-socket cases each exercise 11 authenticated malformed ticket bodies: non-ASCII, unpaired surrogate, empty, short, long, non-hexadecimal, uppercase, null, integer, list and mapping values. Every denial leaves the SQLite file byte-identical. The retained original ticket then consumes once and replay denies. The direct case reopens retained state before valid consumption; the RPC case also verifies authenticated service health after each denial and exactly one reservation/consumption event pair.

```sh
/workspace/witness-venv/bin/python scripts/check_local_witness.py
```

Result: **153 passed in 6.98s**, **65 product-source static import checks passed**, **15 files compiled**. Collection inventory: **59/13/47/1/24/9** across the six fixed modules. Changed-document Markdown targets and `git diff --check` passed. The isolated venv uses the relevant versions pinned in `backend/requirements-dev.lock`; Unix sockets required the sandbox network grant. Initial sandboxed Git access failed; connector recovery verified all 359 blob hashes and the exact checkpoint commit, and subsequent Git fetch succeeded with that grant.

PostgreSQL was not rerun for this input-validation change. Its [seven-case post-authentication checkpoint](witness-auth-postgres-checkpoint.md) predates both initialization-mode and ticket-MAC changes. Compilation of the PostgreSQL helper is not database execution. No full backend, Docker isolation, protected storage or external effect check is claimed.

This is error normalization and pending-ticket preservation in a same-host replaceable fixture. It supplies no protected state, key custody, independent service, anti-rollback or production recovery guarantee. The [external prerequisites](witness-trust-boundary-lifecycle.md) remain required. Product dispatch, real effects, paid models, production integration, deployment and merging remain disabled.
