# Explicit boolean witness initialization mode: Phase 8.4bl

Date: 2026-10-17. Branch: `phase-8-witness-initialization-mode`. Parent: draft PR [#135](https://github.com/Kokfu/congenial-potato/pull/135), commit `a5252ea47779ce670ef9b8aa70e98d7c31f0394a`.

The direct local fixture constructor previously accepted any truthy `initialize` value. Disposable probes reproduced creation of new witness state with `"false"`, integer `1` and bytes `b"false"`. Falsey non-booleans could silently select the reopen path. The [constructor](../../backend/tests/durable_local_recovery_witness.py) now requires an exact boolean before path handling or filesystem changes.

Eight [invalid-mode cases](../../backend/tests/test_durable_local_recovery_witness.py) cover text true/false, zero/one, None, list, dictionary and bytes. Each denies without creating a missing state directory, denies against existing state without changing its bytes, and preserves successful consumption of the retained pending ticket. A positive case verifies that explicit False denies missing state without creating directories, explicit True initializes a new fixture, and explicit False reopens it for authenticated consumption.

```sh
/tmp/witness-local-venv/bin/python scripts/check_local_witness.py
```

Result: **151 local cases passed in 5.67s**, **65 product Python files passed the static fixture-import guard**, and **15 files compiled**. Collection-only inventory is **58/13/46/1/24/9**. Changed-document links and `git diff --check` passed. Unix sockets ran locally with sandbox permission; PostgreSQL was not rerun after this direct-constructor input change. Its seven-case post-authentication-fix result remains [historical separate evidence](witness-auth-postgres-checkpoint.md).

This hardens the direct fixture API; server startup configuration does not expose an initialization flag. It does not establish independent bootstrap authority or stop a host operator explicitly creating/replacing local state. Anti-rollback storage, protected keys, remote transport, separate restore administration and physical power-loss behavior remain outside the evidence. Product dispatch, real writes, paid models, deployment, merging and production integration remain disabled under the [external prerequisites](witness-trust-boundary-lifecycle.md).
