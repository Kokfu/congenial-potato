# Canonical caller/key identity encoding: Phase 8.4aq

Date: 2026-10-16. Branch: `phase-8-witness-canonical-auth-identities`. Parent: typed admin configuration draft PR #114.

## Reproduction and change

The request HMAC input previously joined caller ID and key ID with NUL separators. Those configured strings could themselves contain NUL. With deliberately reused fixture key bytes, caller `a\0b` / key ID `c` and caller `a` / key ID `b\0c` produced identical MACs for the same request. Both the direct and exchange-nonce forms reproduced this byte-encoding collision. A request tag could therefore be relabeled as the second configured identity without changing the tag; the new rejection tests failed on the parent.

Request authentication now canonicalizes named `caller_id`, `caller_key_id` and `request` fields together, plus `exchange_nonce` when present. Direct and exchange request HMAC domains advance to v2; there is no fallback to the old delimiter format. Client/server fixtures use the same helper. The response envelope, reservation-ticket format and SQLite schema are unchanged.

## Checks

Two parametrized cases exercise the direct and nonce-bearing contexts. Each configures the ambiguous identity pairs, denies the relabeled tag before any generation/operation/audit mutation, rejects a correctly formed old-format tag, then accepts the correctly authenticated administrator request and verifies its exact audit identity. The tests deliberately reuse key bytes to isolate encoding behavior; they do not establish role isolation when callers share a secret. A holder of shared HMAC key bytes can compute a fresh tag for another identity, so independent key custody remains a separate prerequisite.

```sh
/tmp/witness-local-venv/bin/python scripts/check_local_witness.py
git diff --check
```

Result: **82 local cases passed in 2.22s**, and **15 files compiled**. Changed-document Markdown links and whitespace checks passed. The earlier process, key-rotation, fake-ledger, nonce and rollback regressions remain included; local Unix sockets used sandbox permission. PostgreSQL and product integration were not run.

## Limits

This removes an ambiguity in the local prototype's authenticated message encoding. It does not provide independent identities, protected key distribution or [protected anti-rollback/audit/restore controls](witness-trust-boundary-lifecycle.md). The local witness file remains replaceable and its rollback limitations remain reproducible. Product dispatch, real external writes, paid models, deployment and production integration stay disabled. No protected-infrastructure or physical power-loss claim is made.
