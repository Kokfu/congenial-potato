# Synthetic runner result recovery regressions: Phase 8.2b.7

Date: 2026-10-16. Branch: `phase-8-runner-result-recovery`. Parent: draft PR #61 (`4b00a51`).

## Behavior under test

These regressions exercise the existing fixture acceptance service without changing product code or adding a recovery/reissue API. All inputs, credentials, job computation and database state are synthetic and isolated locally. Private delivery files contain per-fixture admission/key/envelope state in temporary mode-0600 files; they are test inputs, not an implemented production key store.

One fresh interpreter receives an already-computed signed fixture envelope. A SQLAlchemy `before_commit` hook flushes the proposed accepted result, attempt hash/status, invocation status and accepted audit/activity. The hook asserts that all six proposed states are visible within its transaction, then calls `os._exit(74)` before commit. A new parent connection sees the exact original unknown admission with no result/hash/event. Admission still refuses a second launch. Retaining the original capability/key/envelope permits acceptance of that previously computed metadata and exact duplicate replay, with one accepted audit/activity. This exercises database rollback on actual process exit after SQL writes; it is not physical power-loss acceptance.

Eight further cases start a fresh interpreter with a missing or wrong host key, or missing or wrong private admission capability, both before and after durable acceptance. Each is denied and leaves attempt/invocation/result/audit/activity state unchanged. Admission still refuses reentry. A fresh interpreter retaining the original private identity accepts the original envelope (or returns the already accepted history); the parent duplicate has the same payload hash and there is only one accepted audit/activity. No interpreter invokes a job launcher or recomputes the receipt.

The earlier [result acceptance evidence](runner-result-acceptance-validation.md) separately covers actual process exit after commit, concurrency, expiry, in-flight Docker authority changes and guarded migration. The [governed runner matrix](governed-runner-acceptance.md) records the remaining product boundary.

## Validation

The final focused command passed **42 tests, 7 skipped in 43.85s**: all nine new process/recovery cases plus the 33 existing non-Docker acceptance cases. Seven actual Docker acceptance cases were skipped by the explicit gate; they passed in the parent Docker-enabled command. All **94 local links** across modified documents resolved, and `git diff --check` passed.

```sh
# Repository root; PYTHONPATH=backend/src and APP_DATABASE_URL points at the
# owned disposable loopback workforce_test PostgreSQL fixture:
/tmp/workforce-venv/bin/python -m pytest -q -x backend/tests/test_runner_result_recovery.py backend/tests/test_runner_result_acceptance.py
```

This is a tests/documentation slice. The parent full backend run (663 passed, 32 Docker skips), 152-test Docker-enabled runner command, migration/image probes and fresh isolated Compose acceptance are historical evidence and are not repeated here. The seven Docker cases in the acceptance file remain explicitly gated in this command. No schema, dependencies, product route, launcher or key/transport configuration changes.

## Limits and next task

Unavailable private identity denies metadata delivery; this does not recover lost secrets or reconstruct a missing envelope. A retained exact receipt is metadata delivery, never permission to rerun an uncertain job. Acceptance after rollback still requires fresh current authority and manifest lifetime. These tests do not restore a stale database/journal, rotate keys, survive physical power loss, establish external execution truth or protect from a hostile administrator/host.

Next define an inert synthetic external-write receipt/reconciliation contract, with exact approved effect identity and explicit unknown outcomes, before any isolated fake-ledger integration. Keep runner product dispatch, Phase 7 product reads, real outbound writes, paid activation, merge, public deployment and production integration disabled.
