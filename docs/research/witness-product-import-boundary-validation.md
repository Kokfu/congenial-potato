# Product/fixture static import guard: Phase 8.4as

Date: 2026-10-16. Branch: `phase-8-witness-product-import-boundary`. Parent: socket liveness guard draft PR #116.

The local acceptance command now checks product Python source before running pytest. It parses the files under `backend/src` without importing them and rejects static imports of the durable witness, local transport/server launcher, in-memory witness or fake-ledger fixture modules. It checks module components in both `import` and `from ... import ...` statements, including conditional imports and relative imported names. An absent product source tree fails instead of reporting an empty successful scan. A violation exits nonzero before the local suites run.

## Recorded checks

```sh
/tmp/witness-local-venv/bin/python scripts/check_local_witness.py
git diff --check
```

Result: **65 product Python files passed the static import check**, **86 local cases passed in 2.37s**, and **15 files compiled**. Changed-document Markdown links and whitespace checks passed. Existing Unix-socket fixtures ran with sandbox permission; product Python was parsed only, and no application, PostgreSQL or Docker service was started.

An isolated temporary copy of the checker was also given three synthetic product-source probes: `import durable_local_recovery_witness as witness`, `from backend.tests import synthetic_write_ledger`, and a conditional `from . import durable_local_witness_transport`. All three exited with the import-boundary error before pytest. The repository's product source files were not modified by these probes.

## Limits

This guard detects the named static imports; it does not analyze dynamic `importlib`/`__import__` calls, string-built subprocess launches, copied fixture implementations, native extensions or the complete runtime call graph. Passing is a source boundary check, not proof of disabled dispatch or production safety. This increment changes only the developer checker and Markdown evidence; the product runtime and its dispatch gates are untouched.

All witness/fake-ledger behavior remains synthetic and local. The [external trust-boundary prerequisites](witness-trust-boundary-lifecycle.md) remain unmet; product dispatch, real external writes, paid models, deployment and production integration remain disabled. No protected-infrastructure or physical power-loss claim is made.
