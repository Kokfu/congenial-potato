# Admission/receipt fixture import guard: Phase 8.4bh

Date: 2026-10-16. Branch: `phase-8-witness-admission-import-guard`. Parent: draft PR [#131](https://github.com/Kokfu/congenial-potato/pull/131), commit `d641cde4a13b083c74c9df49c993c747c3565f81`.

The shared static checker previously named five witness/ledger fixture modules but omitted `synthetic_write_admission` and `synthetic_write_receipt_acceptance`. These modules can open the real fixture control database or accept fake-ledger receipt metadata, so the developer command now also rejects their static import from product Python. This expands the named set to seven; no product runtime file or dispatch setting changes.

## Focused checks

Before the change, an isolated temporary product-source file containing all four probes below passed the parent guard. After the change, each probe separately failed both the database-free and PostgreSQL command preflights:

```python
import synthetic_write_admission as admission
from backend.tests import synthetic_write_receipt_acceptance
if False:
    from . import synthetic_write_admission
from synthetic_write_receipt_acceptance import accept_synthetic_write_receipt
```

The probes substitute a temporary source root; repository product source was not modified. Sentinels would raise if pytest or Docker were invoked, and neither was reached for any of the eight command/probe combinations.

```sh
/tmp/witness-local-venv/bin/python scripts/check_local_witness.py
```

Result: **65 product Python files passed**, **120 local cases passed in 6.14s**, and **15 files compiled**. Changed-document links and `git diff --check` passed. Real Unix-socket fixtures ran locally; PostgreSQL/Docker were not started by this increment. The prior 35-case PostgreSQL result is retained separately, without a rerun claim.

## Limits

This remains a developer-command static import check. It does not analyze dynamic imports, copied fixture implementations, subprocess/native loading or the complete dispatch graph, and cannot establish production authorization or guarantee that runtime effects are disabled. The [external prerequisites](witness-trust-boundary-lifecycle.md) remain unmet. Product dispatch, real external writes, paid models, deployment, merge and production integration remain disabled.
