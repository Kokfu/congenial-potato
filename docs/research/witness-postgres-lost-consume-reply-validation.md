# Abandoned consume reply before PostgreSQL admission: Phase 8.4bf

Date: 2026-10-16. Branch: `phase-8-witness-postgres-lost-consume-reply`. Parent: draft PR [#129](https://github.com/Kokfu/congenial-potato/pull/129), commit `c5ef2030473707ad594b40fdc22977425d45dfd5`.

The new [PostgreSQL-backed case](../../backend/tests/test_synthetic_write_admission.py) reserves through the real authenticated Unix client, sends a valid authenticated consume frame on a separate local connection, and closes that connection without reading a response. An event observes return from the original durable consume method; no successful consume result is supplied to the effect caller. This is an abandoned reply, without claiming whether a kernel send succeeded or failed.

After server close and witness reopen, a new server answers an authenticated generation query. Both a fresh reserve and exact consume retry are denied. The latter guards the real fixture admission/fake-write call, so denial prevents entering it. PostgreSQL has no admission or singleton ledger-control row and no admission audit event; the fake-ledger file remains absent. Witness state retains exactly one consumed reservation and exactly two events, reserved then consumed. There is no guessed retry or compensating unconsume.

## Focused checks

The [disposable PostgreSQL setup](witness-postgres-restore-wrapper-validation.md) used fresh application/workflow databases, the same pinned PostgreSQL 17.6 image, unpublished internal networking and tmpfs storage. Both migration commands succeeded. With explicit fixture URLs, zero daily cap, backend source/tests on `PYTHONPATH` and plugin autoload disabled:

```sh
/tmp/witness-postgres-venv/bin/python -m pytest -q -x -p no:cacheprovider \
  backend/tests/test_synthetic_write_admission.py \
  -k 'test_live_witness_blocks_single_or_joint_store_rollback or test_lost_rpc_consume_reply_keeps_postgres_and_fake_ledger_empty'
```

Result: **7 passed, 28 deselected in 11.66s**, including all six direct/RPC restore regressions. The fixture's label-verified container/network and tmpfs data were removed. The changed test module compiled to temporary bytecode; changed-document links and `git diff --check` passed. The prior 34-case admission-file and 120-case local-suite passes remain separate historical results; neither complete command was repeated after adding this case.

## Limits

This is same-process local Unix transport, a real disposable PostgreSQL control database and synthetic SQLite ledger boundary. Burning an invocation on unknown consumption sacrifices availability; it is not evidence that an external effect occurred. Replaceable witness state can still be rolled back, and witness/control/effect stores are not atomically committed. Protected storage, remote transport, independent administration and physical power-loss behavior remain outside the evidence. The [lifecycle prerequisites](witness-trust-boundary-lifecycle.md) are unchanged; product dispatch, real external writes, paid models, deployment, merge and production integration remain disabled.
