# Retired caller key and empty MAC across process restart: Phase 8.4bk

Date: 2026-10-17. Branch: `phase-8-witness-retired-key-empty-mac`. Parent: draft PR [#134](https://github.com/Kokfu/congenial-potato/pull/134), commit `784016e354d14cf2cb15c02c96209fad4019ebbb`.

The [missing-key authentication fix](witness-missing-auth-key-denial-validation.md) now has explicit caller-key retirement evidence across separate server processes. Three new [transport cases](../../backend/tests/test_durable_local_witness_transport.py) cover reservation, consumption and generation advance under the retired key ID with an empty MAC.

Each case starts a separate server process with old/replacement caller-key overlap and a stable recovery-admin identity. The old key validly advances generation to 2 and reserves a pending ticket. The server stops, the old key is removed from its private synthetic configuration, and a new process starts using only the replacement key. Both a normal old-key request and a raw retired-key/empty-MAC request deny; the retained SQLite file remains byte-identical across those denials.

The replacement key then authenticates generation 2 and consumes the pending ticket once. The final database has one reservation, generation 2 and exactly three audit rows: generation advance and reservation under caller-v1, then consumption under caller-v2. This checks stable caller identity across rotation while denying a retired authentication key; it does not revoke or rotate the separate ticket-signing state key.

```sh
/tmp/witness-local-venv/bin/python scripts/check_local_witness.py
```

Result: **142 local cases passed in 6.29s**, **65 product Python files passed the static fixture-import guard**, and **15 files compiled**. Collection-only inventory is **49/13/46/1/24/9**. Changed-document links and `git diff --check` passed. Only test/evidence files changed; the protocol fix remains in parent PR #133. PostgreSQL was not rerun; its post-fix seven-case checkpoint remains [separate evidence](witness-auth-postgres-checkpoint.md).

These are separate local server processes on one host with replaceable SQLite state and mode-restricted synthetic key configuration. They do not establish protected key retirement/destruction, remote enrollment, independent restore administration, physical power-loss behavior or production safety. The [external prerequisites](witness-trust-boundary-lifecycle.md) remain open; product dispatch, real external writes, paid models, deployment, merge and production integration remain disabled.
