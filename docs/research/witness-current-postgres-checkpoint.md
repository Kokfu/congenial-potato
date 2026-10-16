# Current PostgreSQL admission checkpoint: Phase 8.4bn

Date: 2026-10-17. Branch: `phase-8-witness-current-postgres-checkpoint`. Parent: draft PR [#137](https://github.com/Kokfu/congenial-potato/pull/137), commit `efabb03e6521254417f003d83a020d4a06b72324`.

The complete synthetic admission file was rerun after missing-key authentication, explicit boolean initialization and consume ticket MAC validation. This refreshes the older full-file result, which predated those changes, and includes the seven focused witness cases rather than adding their counts separately.

```sh
/workspace/witness-postgres-venv/bin/python scripts/check_local_witness_postgres.py --full-admission
```

The resumed workspace required a disposable venv installed from `backend/requirements-dev.lock` and an explicit pull of the command's pinned PostgreSQL digest `sha256:00bc86618629af00d2937fdc5a5d63db3ff8450acf52f0636ec813c7f4902929`. The managed local Docker daemon reported 28.4.0. The script used its fixed local Unix socket, a uniquely labeled internal network and an unpublished tmpfs PostgreSQL container with no host mounts. It overrode both test database URLs and removed inherited DBOS cloud and pytest selectors. No product services were started.

Result: **35 passed in 52.69s**, with **65 product-source static import checks passed** and successful fresh application/DBOS migrations. Coverage includes authority changes, intent substitution, concurrency, child-process loss, retained unknown outcomes, migration guards, the expected repeat-effect gap without a witness, six retained-witness direct/Unix-RPC simulated restore cases and the abandoned-consume-reply case.

The command reported removal of its exact label-verified container `witness-pg-1d7d19b09c6045a2b6ef29123d001d15` and network `witness-net-1d7d19b09c6045a2b6ef29123d001d15`. Subsequent container/network listings filtered by its exact invocation label returned no resources. The pulled immutable image remains cached. Changed-document local Markdown targets and `git diff --check` passed.

This increment changes Markdown only. The parent [153-case local result and 15 compilation checks](witness-ticket-mac-validation.md) remain separate, without rerun or aggregation. No full backend, actual backup restoration, protected service, physical power-loss or real effect-adapter check is claimed. PostgreSQL rollback cases model row/file deletion; they do not supply infrastructure guarantees.

## Next planned boundary

Phase 8.3j's deployment-boundary consolidation is already complete; its obsolete duplicate unchecked entry was removed from `progress.md`. Phase 8.4 external recovery activation remains closed under the current scope. Before integration, the owner would need to authorize a concrete protected environment and actual effect adapters, with separately administered anti-rollback generation/consumption storage and restore authority, reviewed remote authentication and enrollment, protected key lifecycle, independently retained tamper-evident audit, caller/effect fencing and reconciliation, and operational restore/replacement/outage drills. See the full [external lifecycle prerequisites](witness-trust-boundary-lifecycle.md).

Local fixture success cannot satisfy those prerequisites. Product dispatch, real effects, paid models, production connections, deployment and merging remain disabled. The pushed stack is a clean local reliability checkpoint for subsequent authorized work.
