# Authenticated response body contracts: Phase 8.4az

Date: 2026-10-16. Branch: `phase-8-witness-response-body-contract`. Parent: strict JSON decoder draft PR #123.

The client previously returned any authenticating dictionary body after checking the request MAC. Twenty-five signed fixture variants reproduced acceptance of missing/extra fields, wrong status/echoes, invalid ticket metadata, and boolean/finite-float/out-of-range generations. The fixture peer holds only synthetic keys; these tests distinguish message authentication from metadata validation, not a trusted service from a compromised key holder.

Active verification now requires both the expected request MAC and original request. After authentication/binding, it checks the exact operation fields/status, generation as a strict integer in the protocol range, canonical UUIDs, request echoes, and reservation digest/ticket-MAC shape plus nonempty state key ID:

| Operation | Status | Additional checks |
| --- | --- | --- |
| Generation | `current` | Exact status/generation fields |
| Reserve | `reserved` | Exact request/ledger/invocation/intent echoes; canonical nonce; digest/MAC shape; state key ID |
| Consume | `spent` | Exact request/invocation/generation echoes |
| Advance | `advanced` | Exact operation request ID; historical returned generation remains valid metadata |

The RPC client and active direct fixture helpers supply both expectations. Supplying only one expectation or a malformed expected MAC denies; passing neither retains authentication-only inspection of captured metadata and does not perform request/body validation. The PostgreSQL fixture helper was updated and compiled, but its database-backed test was not run. No wire, ticket or SQLite schema changed.

## Checks

```sh
/tmp/witness-local-venv/bin/python scripts/check_local_witness.py
git diff --check
```

Result: **106 local cases passed in 4.53s**, **65 product Python files passed the static import guard**, and **15 files compiled**. The new tests cover 25 malformed signed bodies, incomplete/invalid expectations, and a positive historical advance reply returning generation 2 while current state is 3 without duplicate audit. Reservation-reply rejection leaves one pending reservation; consume-body rejection does not consume it. Changed-document Markdown links and whitespace checks passed. Unix sockets used sandbox permission; PostgreSQL/product integration were not run.

## Limits

This checks authenticated metadata structure and matching fields. Ticket MAC shape is not verification of the state-key signature, and a well-formed signed claim is not proof of external execution, independent key custody, current authority or protected storage. Historical advance metadata does not assert the current generation. The [external lifecycle prerequisites](witness-trust-boundary-lifecycle.md), including anti-rollback/audit controls and coordinated caller/effect recovery, remain unmet. Product dispatch, real writes, paid models, deployment and production integration stay disabled; no protected-infrastructure or physical power-loss claim is made.
