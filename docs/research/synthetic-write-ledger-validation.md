# Private local fake-write ledger: Phase 8.3b

Date: 2026-10-16. Branch: `phase-8-synthetic-write-ledger`. Parent: draft PR #63 (`f488a5c`).

## Fixture boundary

`backend/tests/synthetic_write_ledger.py` is trusted test-only adapter code, outside product dispatch. It uses a caller-selected existing owner-private mode-0700 directory and mode-0600 SQLite database with a fixed ledger UUID. It rejects symlink/nonregular ledger files, mismatched ledger identity, missing/wrong key shape and disabled use before file access. SQLite synchronous mode is FULL and each transaction/connection closes explicitly. This establishes local fixture behavior; it is not a hostile-host sandbox or physical power-loss/restore proof.

The ledger binds one consumed attempt per logical invocation to the full canonical intent. It commits that unknown marker **before** changing any synthetic record. Only that original ongoing call proceeds to the mutation transaction. Another concurrent/restarted call finding unknown refuses execution. Repeated applied calls return the original receipt without changing the record, including after a later separately identified invocation replaces it. Changed intent, content or ledger identity cannot transfer a consumed invocation.

The mutation transaction checks exact record ownership/project and expected revision. A failed precondition persists a terminal `not_applied` attempt and no mutation, then denies reexecution. A successful mutation persists record bytes/revision and the exact applied receipt together. Receipt event/time/digests remain historical and stable; later lookups/signatures do not invent another event. Raw bytes are synthetic fixture content, separate from the metadata-only receipt; no content is promoted to model context.

Authenticated reconciliation uses the exact nonce/time/intent query contract. A missing attempt is `not_applied` **only as an observation of this intact fixture ledger**. A consumed marker without a committed receipt is `unknown`, even when its mutation transaction rolled back. A committed effect returns `applied` with its original receipt. No reply permits retry or clears a consumed marker. A definitive precondition failure and an uncertain process loss have distinct outcomes/exceptions.

The adapter checks no application approval, current policy/grant, root budget or cancellation. Intent approval/policy hashes are bindings supplied by the trusted test caller, not permission. No application DB admission or accepted effect record is added. Replacing/restoring the entire ledger can erase its markers; an independent control-DB fence and safe recovery/key policy remain necessary before any governed integration. This slice does not claim empty-ledger replacement safety.

## Validation

The first fixture run stopped after 20 passes because its disabled-use assertion overlooked the shared test bootstrap's existing synthetic password file. After comparing against the preexisting file set, another run stopped after 24 passes because the process umask turned a requested 0755 directory into a safe 0700 directory. Explicitly setting the intended unsafe test mode corrected that negative probe. Neither failed assertion indicated a product execution path.

The final focused command passed **98 tests in 34.57s**, with no skips: all **25 new ledger cases**, 64 write-contract cases and nine prior runner recovery cases. All **80 local links** across modified documents resolved; AST inspection of main/worker/tool-effect imports confirmed no synthetic write contract/ledger imports, and `git diff --check` passed.

The tests observe actual SQLite bytes/revisions/attempt rows. They cover successful replacement and historical duplicate lookup after a later version, a paused committed marker plus concurrent caller, changed identity/resource/project/agent/root/approval/policy/content/precondition, stale/foreign record denial, no attempt for unbound input, private-directory/file identity and corrupted receipt denial. Three actual subprocesses exit after marker commit, after SQL mutation but before effect commit, or after effect commit. Fresh interpreters reconcile and attempt delivery: the first two retain unknown with no record and refuse execution; the third returns one exact committed receipt and revision without another write.

```sh
# Repository root, APP_DATABASE_URL points at the owned disposable loopback
# workforce_test PostgreSQL used by the shared test bootstrap:
PYTHONPATH=backend/src:backend/tests /tmp/workforce-venv/bin/python -m pytest -q -x backend/tests/test_synthetic_write_ledger.py backend/tests/test_synthetic_write_contract.py backend/tests/test_runner_result_recovery.py
```

The fake ledger itself uses only its private SQLite fixture, not the control PostgreSQL database. No product source, schema, dependencies, configuration, images or tool registry changed. Parent #63's 212-pass contract command, metadata/image probe and earlier full backend/Compose checks are separate evidence and were not repeated here. This is no real outbound write or deployed service.

## Next task and limits

Next bind a fake-write invocation to exact durable owner approval/current policy/scope and an **independent control-database admission fence**, then exercise changed authority and an empty/replaced fake ledger without authorizing another effect. Keep that service fixture-only and distinguish result acceptance/reconciliation from execution permission. Product registration/dispatch, real effects, arbitrary shell/browser, paid activation, merge, public deployment and production integrations remain disabled. Host clock/key integrity, lost key/ledger recovery, stale DB-plus-ledger restores and physical power loss remain unverified.
