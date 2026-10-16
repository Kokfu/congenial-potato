# Missing authentication key and empty MAC denial: Phase 8.4bi

Date: 2026-10-17. Branch: `phase-8-witness-missing-auth-key-denial`. Parent: draft PR [#132](https://github.com/Kokfu/congenial-potato/pull/132), commit `79c418569ed9d91f131eb9fc55d8da84f42517d0`.

## Reproduced local flaw and fix

The fixture authenticator used an empty expected MAC when a caller/key lookup failed. An empty supplied MAC therefore compared equal and returned a missing key as if authenticated. Reservation, consumption and an allowlisted caller's generation advance could commit before response signing raised TypeError. The Unix server catches that error, but its denial response does not undo an already committed mutation.

Disposable parent-source probes reproduced an unknown caller creating one reservation and an allowlisted caller with an unknown key advancing generation from 1 to 2; audit rows recorded both. A separate parent-source probe consumed an existing ticket with an unknown key and empty MAC before response-signing failure. No product or external service was involved. Valid caller keys with non-ASCII MAC strings also leaked TypeError from constant-time comparison across all four methods.

The [core authenticator](../../backend/tests/durable_local_recovery_witness.py) now requires a found configured key and an exact 64-character lowercase hexadecimal MAC before computing/comparing the expected HMAC. There is no empty-string authentication fallback. This rejects malformed Unicode MACs through WitnessDenied before any state connection or protocol mutation.

## Focused evidence

Twelve direct missing-caller/key cases exercise all four operations against unknown caller, unknown key, and both missing. Four method cases check nine malformed MAC variants each. All assert byte-identical state after denial and retain successful authenticated consumption afterward. Three real Unix-socket cases send an unknown key and empty MAC for reserve, consume and advance; the server denies with byte-identical state, then answers a valid generation query and consumes the original ticket once. Audit history remains exactly reserved/consumed.

```sh
/tmp/witness-local-venv/bin/python scripts/check_local_witness.py
```

The resumed workspace retained the source checkout but not its temporary virtual environment; pytest 8.4.2 and pydantic 2.13.5 were reinstalled into a fresh disposable venv through the configured package proxy. Result: **139 local cases passed in 5.63s**, **65 product Python files passed the static fixture-import guard**, and **15 files compiled**. Collection-only verification confirms six-module inventory **49/13/43/1/24/9**. Changed-document links and `git diff --check` passed. Unix sockets used sandbox permission; PostgreSQL was not rerun. Its previous 35-case result is historical evidence from before this fix.

## Limits and existing state

This fixes fixture authentication before mutation; it does not repair or automatically roll back state altered under the prior behavior. Historical error replies alone cannot establish that no mutation committed. Existing in-file audit is still replaceable and is not independently protected evidence. No product runtime or dispatch setting changed.

The witness remains a same-host replaceable prototype. This does not provide protected storage, remote identity, independent administration, physical power-loss or production-safety guarantees. The [external prerequisites](witness-trust-boundary-lifecycle.md) and disabled product dispatch, real writes, paid models, deployment, merge and production integration remain unchanged.
