# Admission regression checkpoint: Phase 8.4be

Date: 2026-10-16. Branch: `phase-8-witness-admission-regression-checkpoint`. Parent: draft PR [#128](https://github.com/Kokfu/congenial-potato/pull/128), commit `5442b898a89dd31b18d4f024d49650aa4234c28b`.

After adding [local RPC restore coverage](witness-postgres-rpc-restore-validation.md), the complete [synthetic admission test file](../../backend/tests/test_synthetic_write_admission.py) passed against fresh disposable PostgreSQL. This checks that the six witness restore cases coexist with the surrounding admission safeguards.

## Command and result

The [scoped local setup](witness-postgres-restore-wrapper-validation.md) used the same pinned PostgreSQL 17.6 image, separate fresh test databases, unpublished internal network and tmpfs data. Both application and DBOS migration commands succeeded. With explicit fixture database URLs, `DAILY_CAP_USD=0`, backend source/tests on `PYTHONPATH` and pytest plugin autoload disabled:

```sh
/tmp/witness-postgres-venv/bin/python -m pytest -q -x -p no:cacheprovider \
  backend/tests/test_synthetic_write_admission.py
```

Result: **34 passed in 55.79s**. This includes current-authority changes before/after committed admission, exact-intent substitution, concurrent delivery, missing/replaced-ledger denial, actual child-process exit after control commit, retained unknown admission, pinned ledger/target revision, disabled-experiment denial, consumed-state migration downgrade refusal, and empty admission-schema downgrade/upgrade. It also retains the expected gap case where deleting both control rows and fake-ledger state without a witness permits a second distinct event; the six retained-witness direct/RPC cases deny retries.

Only the fixture's label-verified container and internal network were removed after the run, including tmpfs database data. Changed-document links and `git diff --check` passed. No runtime source changed and no repeat of the separate six-module 120-case local suite is claimed.

## Limits

This is the complete admission test file, not the full backend suite, complete migration parity, or receipt-acceptance coverage. Row/file deletion models rollback; it is not a database backup restore drill. Local fixture success does not supply independently administered anti-rollback storage, external effect adapters, remote authenticated transport, protected restore infrastructure or physical power-loss evidence. The [lifecycle prerequisites](witness-trust-boundary-lifecycle.md) and disabled product-dispatch/external-write/paid-model/deployment/merge/production gates remain unchanged.
