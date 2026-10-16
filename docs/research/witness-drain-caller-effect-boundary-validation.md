# Witness drain versus caller effect work: Phase 8.4ax

Date: 2026-10-16. Branch: `phase-8-witness-drain-caller-effect-boundary`. Parent: local dispatch drain draft PR #121.

## Observed boundary

The new local drill reserves and consumes an exact synthetic intent through the authenticated Unix-socket client and retains its verified spent reply. The witness server then successfully drains its admitted protocol calls, closes and removes its socket path. At that point the SQLite control fixture and actual fake ledger still have no admission, record or attempt.

The trusted fixture caller resumes afterward, inserts its synthetic control admission and applies the exact intent to the fake ledger. The signed receipt verifies at revision 1; the ledger has one record and one attempt, while the stopped witness file is byte-identical to its post-drain copy and still contains one consumed reservation and two audit events.

This is expected boundary evidence, not a failing regression or another replay: exactly one fake effect occurs, after a successful witness-method drain. It confirms that stopping/draining the witness does not stop a caller that already received a valid consume result, and therefore does not quiesce the control/effect restore domains.

## Checks

```sh
/tmp/witness-local-venv/bin/python scripts/check_local_witness.py
git diff --check
```

Result: **95 local cases passed in 4.33s**, **65 product Python files passed the static import guard**, and **15 files compiled**. Changed-document Markdown links and whitespace checks passed. The new fixture uses temporary Unix sockets and three local SQLite stores; the suite ran with sandbox permission. PostgreSQL/product integration were not run.

## External prerequisite and limits

Before a real coordinated restore, independently administered controls must stop new admission, fence or quiesce outstanding caller/effect work, reconcile consumed-but-unapplied and unknown outcomes, and resolve divergent witness/control/effect snapshots before admission reopens. A successful witness-method drain alone is insufficient. This repository does not implement that cross-domain recovery procedure, and this test's direct SQLite admission is trusted fixture glue, not a product authority check. See the [lifecycle prerequisites](witness-trust-boundary-lifecycle.md).

No real external effect is performed. Product dispatch, real external writes, paid models, deployment and production integration stay disabled. Independent anti-rollback state/key/audit custody remain unmet prerequisites; no protected-infrastructure or physical power-loss claim is made.
