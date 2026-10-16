# Durable synthetic write receipt acceptance: Phase 8.3d

Date: 2026-10-16. Branch: `phase-8-synthetic-write-receipt-acceptance`. Parent: draft PR #65 (`c17aa15`).

## Boundary

`backend/tests/synthetic_write_receipt_acceptance.py` is a fixture-only acceptance bridge. It loads the independent consumed admission and singleton ledger identity, verifies the domain-separated HMAC receipt against the exact intent and trusted fixture key, and checks admission bindings for invocation, approval, project, agent, root, policy snapshot, ledger, target and expected revision. The first acceptance rechecks live approval, policy, project grant, active agent, source/root scope, cancellation and positive root budget under database locks, then commits one immutable receipt row and audit event.

The receipt table has one row per consumed invocation and a foreign key to its admission. Its migration downgrade refuses to delete non-empty receipt history. Exact repeated delivery returns that stored receipt as history and creates neither another audit event nor a ledger mutation. A malformed signature or stale authority leaves the independent admission `unknown` and writes no accepted row. Neither receipt acceptance nor replay changes the tool invocation status, clears the admission, writes an application artifact, creates product activity, or promotes model context.

The HMAC authenticates a private fixture key holder's receipt metadata. It does not establish external execution truth. The accepted metadata is therefore fixture-only and cannot open product dispatch. Missing receipts remain unaccepted; rejected receipts preserve the consumed unknown admission.

## Validation

The final focused command passed **120 tests in 66.18s** with no skips: four receipt-acceptance tests, 27 governed-admission tests, 25 private-ledger tests and 64 inert-contract tests. Coverage includes exact durable acceptance/replay, unchanged SQLite record revision and receipt bytes on replay, one audit record, rejection of invalid signatures, fresh-authority denial, retained unknown admission, consumed-admission retry refusal, and refusal to downgrade accepted receipt history. After adding the explicit SQLite no-mutation replay assertion, its targeted test passed again (**1 passed in 2.08s**).

The combined command, run from `backend/` in the isolated test runner, was:

```sh
PYTHONPATH=src:tests python -m pytest -q -x -p no:cacheprovider \
  tests/test_synthetic_write_receipt_acceptance.py \
  tests/test_synthetic_write_admission.py \
  tests/test_synthetic_write_ledger.py \
  tests/test_synthetic_write_contract.py
```

`APP_DATABASE_URL` addressed the disposable `workforce_test` PostgreSQL database; `DBOS_SYSTEM_DATABASE_URL` addressed its separate `workforce_system_test` database. Both were private to the internal fixture network.

On PostgreSQL 17.6 / Python 3.12.15, the new migration upgraded from a fresh schema; empty receipt-table downgrade to `c4e6a819d0b2` and re-upgrade passed; and `alembic check` reported `No new upgrade operations detected.` The data-bearing downgrade refusal passed in the four receipt tests. Python source compilation and `git diff --check` passed.

The database used tmpfs storage. Test containers were attached only to an internal Docker network with no external route; the repository mount was read-only. The official runtime/database images and locked Python test dependencies were prepared before the runner was disconnected from the default network. Temporary containers, network and images were removed after validation.

The full backend suite, backend image/Compose smoke, product dispatch and real external writes were not run. Replacement or joint restore of both the control database and fake ledger, stale restores, physical power loss, hostile-host integrity, key lifecycle and production transport remain unverified. Acceptance proves only that a fixture signature and current application authority bind to one durable metadata record.

## Next task and limits

Inspect the consolidated Phase 8.3 fixture gate and identify the remaining bounded local recovery/restore checks before considering any product dispatch. Continue to keep real writes, paid activation, merge, public deployment and production integration disabled.
