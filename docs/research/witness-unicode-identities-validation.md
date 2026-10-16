# Valid Unicode identity configuration: Phase 8.4bb

Date: 2026-10-16. Branch: `phase-8-witness-unicode-identities`. Parent: consolidated acceptance checkpoint draft PR #125.

The prototype previously accepted unpaired surrogate code points in caller/key/state identity names because it checked only nonempty strings. A disposable probe configured such a caller key ID, successfully authenticated a generation request, then raised `UnicodeEncodeError` while constructing the response. The initializer-denial regression also failed on the parent: invalid identity configuration created storage instead of failing early.

A shared predicate now requires identity names to be nonempty strings representable as UTF-8. Witness configuration validates caller names, caller/state key IDs and current IDs before creating/opening state. The client validates caller/key/current IDs before socket use, and response verification validates the expected key ID plus returned state key ID before encoding/use. Unhashable current-ID inputs also deny instead of leaking `TypeError`. Names retain their exact text; valid Unicode is not normalized or changed. Request/response HMAC domains, ticket format and SQLite schema are unchanged.

## Checks

Six initializer cases reject high/low unpaired surrogates in caller, caller-key and state-key names before creating the state directory. Three configuration-file cases reject before server construction and preserve byte-identical existing state. Client/verifier matrices deny invalid names and malformed current IDs. Two direct protocol cases and a real local Unix-socket case preserve valid Unicode/emoji names through reservation, consumption and exact audit identity; direct cases also exercise generation advance. A signed surrogate state-key metadata reply rejects. Existing NUL-boundary and key-rotation regressions remain included.

```sh
/tmp/witness-local-venv/bin/python scripts/check_local_witness.py
git diff --check
```

Result: **120 local cases passed in 4.93s**, **65 product Python files passed the static import guard**, and **15 files compiled**. Collection-only verification confirms the six-module inventory is 33/13/40/1/24/9. Changed-document Markdown links and whitespace checks passed. Unix sockets used sandbox permission; PostgreSQL/product integration were not run.

## Limits

This validates identifier representation in the local fixture. It does not enroll independent identities, establish name ownership, protect key delivery/custody or supply the [external lifecycle prerequisites](witness-trust-boundary-lifecycle.md). State remains replaceable and the documented rollback/caller-effect limits remain reproducible. Product dispatch, real writes, paid models, deployment and production integration stay disabled; no protected-infrastructure or physical power-loss claim is made.
