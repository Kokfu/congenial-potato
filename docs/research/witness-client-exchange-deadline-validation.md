# Shared client transport deadline: Phase 8.4bq

Date: 2026-10-17. Branch: `phase-8-witness-client-exchange-deadline`. Parent: draft PR [#140](https://github.com/Kokfu/congenial-potato/pull/140), commit `c2ab7d6fc9e2584f10e12ede1e66e0a1251c85fd`.

The local Unix client previously reset its time budget across connect, send and frame receive. A controlled peer spent 0.6 seconds connecting, 0.2 sending and 0.3 receiving a correctly authenticated response; the parent accepted that reply despite a one-second configured timeout. The new regression reproduced acceptance before the fix. The constructor also accepted `None`, permitting unbounded socket operations, and malformed/unsupported timeout values could fail outside the transport denial API.

Client construction now requires an exact integer or float, greater than zero and no greater than two seconds. Booleans, non-finite numbers, missing/nonnumeric values and out-of-range values deny before socket creation. The default remains two seconds; smaller finite positive values remain supported. Callers configuring longer fixture timeouts must now use the bounded range.

The transport starts one monotonic deadline immediately before opening the socket, passes remaining time to connect/send and the same deadline through frame receiving, then checks for expiry after decoding. The existing server frame deadline remains independent. This is a socket-exchange budget, not a hard bound on request serialization/signing, response authentication, operating-system scheduling or server execution.

## Validation

Five new cases cover 12 invalid timeout values and four controlled-clock exchange scenarios: within-budget acceptance, connect expiry, send expiry after connect consumed part of the budget, and receive expiry after the peer committed consumption. The controlled peer honors socket timeouts and uses the actual durable witness to sign fresh nonce-bound responses. Expired exchanges close the socket. When consume committed before the delayed response, one durable consumed row and one audit pair remain and authenticated replay denies. Earlier controlled failures leave only the pending reservation. Those inspected fixture states do not tell a real caller whether an arbitrary failed send committed; no retry or reconciliation permission is added.

```sh
/workspace/witness-venv/bin/python scripts/check_local_witness.py
/workspace/witness-postgres-venv/bin/python scripts/check_local_witness_postgres.py
```

Final results: **169 local cases passed in 5.45s**, **65 product-source import checks passed**, **15 files compiled**; inventory **70/13/52/1/24/9**. The changed transport module independently collected 52 cases. The focused PostgreSQL command passed **7 cases, 28 deselected in 11.21s**, after fresh application/DBOS migrations and 65 source checks. Its label-verified container `witness-pg-3d81f5c54c624278b4770c0f904a0004` and network `witness-net-3d81f5c54c624278b4770c0f904a0004` were removed. Changed-document Markdown targets and whitespace checks passed. The [35-case full admission checkpoint](witness-current-postgres-checkpoint.md) remains historical and was not rerun.

Shell Git push lacked authentication on resumption. The validated file tree was published through the GitHub connector Git-data API, with the local checkpoint synchronized to the verified remote commit.

These are controlled local deadline and synthetic recovery checks, alongside the existing real Unix-socket regressions. No production latency, availability, external execution truth, protected storage, independent transport or power-loss guarantee follows. All [external prerequisites](witness-trust-boundary-lifecycle.md) remain open; product dispatch, paid models, real effects, production connections, deployment and merging remain disabled.
