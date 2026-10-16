# Local witness acceptance matrix: Phase 8.4bj

Date: 2026-10-17. Branch: `phase-8-witness-auth-postgres-checkpoint`. Parent: draft PR [#133](https://github.com/Kokfu/congenial-potato/pull/133), commit `8534de30226ef74294ec6dd0c92175f4a298c135`.

This is the current local synthetic checkpoint. The fixture protocol, same-host transport and fake-ledger drills do not constitute an independent recovery service or product activation. Expected rollback and caller-effect limitations are recorded separately below.

## Current command and recorded results

```sh
/tmp/witness-local-venv/bin/python scripts/check_local_witness.py
```

The [fixed local checker](witness-local-check-command.md) tests the checkout directly, isolates pytest options/plugins/configuration, excludes PostgreSQL conftest loading and compiles selected files to a temporary directory. Dependency setup is documented with that command.

The latest six-module local runtime check is Phase 8.4bi: **139 local cases passed in 5.63s**, **65 product Python files passed the static fixture-import guard**, and **15 files compiled**. Separately, Phase 8.4bd passed **6 PostgreSQL-backed witness restore-wrapper cases in 9.76s** (three direct and three Unix-RPC), after fresh application/workflow migrations; see [RPC cases and limits](witness-postgres-rpc-restore-validation.md) and [database setup](witness-postgres-restore-wrapper-validation.md). The local command was rerun after fixing missing-key/empty-MAC authentication; see [authentication fix](witness-missing-auth-key-denial-validation.md) and [guard coverage](witness-admission-import-guard-validation.md). Collection-only inspection verified the exact six-module, 139-case inventory; changed-document links plus `git diff --check` passed.

Phase 8.4be additionally passed the **complete 34-case admission file in 55.79s**, including those six restore cases and migration safeguards; see [admission regression checkpoint](witness-admission-regression-checkpoint.md). These counts overlap and must not be added together.

Phase 8.4bf adds an abandoned consume-reply case before PostgreSQL admission: **7 focused cases passed in 11.66s**, including the six restore regressions. PostgreSQL admission/control/audit and the fake-ledger file remain absent after denied retries, while witness consumption persists; see [abandoned reply evidence](witness-postgres-lost-consume-reply-validation.md). That increment did not rerun the full admission file.

The [repository PostgreSQL command](witness-postgres-check-command.md) now reproduces setup/migrations/checks/cleanup. Phase 8.4bg passed its default **7 cases in 15.55s** and full admission **35 cases in 72.76s**, with a 65-file static product import check for each, and verified cleanup on a controlled failure. These are historical PostgreSQL-backed results preceding the Phase 8.4bi authentication fix; The full admission file was not rerun after that fix. They include, rather than add to, earlier restore/admission counts.

Phase 8.4bj reran the default PostgreSQL command after the authentication fix: **7 passed, 28 deselected in 12.72s**, with 65 product-source checks, successful migrations and fixture cleanup. See [current focused PostgreSQL checkpoint](witness-auth-postgres-checkpoint.md). This updates the selected wrapper/RPC/lost-reply cases only; the 35-case whole-file result above remains historical.

| Collected module | Cases |
| --- | ---: |
| [Durable protocol](../../backend/tests/test_durable_local_recovery_witness.py) | 49 |
| [Fake-ledger recovery](../../backend/tests/test_durable_witness_fake_ledger_recovery.py) | 13 |
| [Local transport/process lifecycle](../../backend/tests/test_durable_local_witness_transport.py) | 43 |
| [Pending-snapshot audit rollback](../../backend/tests/test_witness_pending_snapshot_audit_rollback.py) | 1 |
| [Response parsing/binding/contracts](../../backend/tests/test_witness_rpc_response_validation.py) | 24 |
| [In-memory protocol regressions](../../backend/tests/test_synthetic_write_recovery_witness.py) | 9 |
| **Total** | **139** |

## Current fixture behavior and evidence

| Area | What the local checks exercise | Evidence |
| --- | --- | --- |
| Authentication failure | Missing key plus empty MAC and malformed MACs deny before mutation; valid authenticated calls still succeed | [Missing-key fix](witness-missing-auth-key-denial-validation.md) |
| Reservation/consumption | Exact binding, idempotent reserve retry, one-way consume, retained-state restart and concurrent winner | [Durable protocol](durable-local-recovery-witness-validation.md) |
| Generation/admin | Idempotent advance identity, stale-ticket denial, stable caller allowlist, typed unique admin configuration | [Advance retry](idempotent-witness-generation-advance-validation.md), [configuration](witness-server-config-validation.md) |
| Identity/key encoding | Canonical named caller/key/request fields under v2 request MAC domains; old delimiter format rejected; invalid UTF-8 names denied before setup while valid Unicode/audit identities are retained | [Canonical identities](witness-canonical-auth-identities-validation.md), [Unicode names](witness-unicode-identities-validation.md) |
| Key lifecycle | Caller/state-key overlap, retirement, missing pending-ticket key denial and retained consumed identity | [Lifecycle](witness-trust-boundary-lifecycle.md), [process state-key rotation](witness-state-process-key-rotation-validation.md) |
| Framing/decoding | Byte cap, duplicate fields, non-finite numeric rejection and decode-error normalization | [RPC JSON](witness-rpc-json-validation.md), [frame size](witness-oversize-frame-validation.md) |
| Response correlation | v2 signed request binding plus fresh authenticated exchange nonce; stale/mismatched replies reject | [Request binding](witness-rpc-response-binding-validation.md), [exchange freshness](witness-rpc-exchange-freshness-validation.md) |
| Response metadata | Exact operation fields/status, integer generation range, canonical IDs, echoed bindings and ticket/digest shape | [Body contracts](witness-response-body-contract-validation.md) |
| Endpoint startup | Active/uncertain socket refusal, stable stale-path inode check, authenticated process readiness | [Socket guard](witness-socket-liveness-guard-validation.md) |
| Local receive/load | Monotonic frame receive budget, 32 active-handler cap and slot recovery | [Receive deadline](witness-frame-receive-deadline-validation.md), [capacity](witness-connection-cap-validation.md) |
| Stop/drain | Late-frame denial, atomic stop/admission, counted synchronous method drain, explicit unknown on drain expiry | [Stop gate](witness-stop-dispatch-gate-validation.md), [dispatch drain](witness-dispatch-drain-validation.md) |
| Effect recovery | Real fake-ledger fixture records through retained-witness rollback/replacement, lost reply, outage and key changes | [Fake-ledger recovery](durable-witness-fake-ledger-recovery-validation.md), [lost reply](witness-lost-reply-effect-boundary-validation.md) |
| Product/source boundary | Named static fixture imports denied in product Python before tests; no product runtime imported by that scan | [Static guard](witness-product-import-boundary-validation.md), [admission/receipt coverage](witness-admission-import-guard-validation.md) |

These are scoped checks. HMAC/body validation authenticates fixture metadata, not execution truth or current authority. The client checks ticket-MAC shape without possessing the state signing key. A fresh exchange is not trusted time. The static import guard does not analyze dynamic loaders or prove the whole dispatch graph.

## Observed limitations that remain acceptance evidence

| Trigger | Observed local result | Evidence |
| --- | --- | --- |
| Restore prior witness generation file | Generation rewinds from 3 to 1 | [Generation rollback](witness-generation-rollback-boundary-validation.md) |
| Restore witness, control and fake-ledger files together | The same intent can create a second distinct fake event | [Coordinated rollback](witness-coordinated-full-rollback-effect-validation.md) |
| Restore a pending witness snapshot | The exact old consume ticket works again and recreates identical audit rows/response | [Pending audit rollback](witness-pending-snapshot-audit-rollback-validation.md) |
| Drain expires with admitted work paused | Close reports unknown; the operation can still commit later | [Dispatch drain](witness-dispatch-drain-validation.md) |
| Witness successfully drains after consume reply | The retained caller can still create one fake-ledger effect afterward | [Caller/effect boundary](witness-drain-caller-effect-boundary-validation.md) |

The last row is one post-drain effect, not replay. Successful drain concerns only synchronous protocol methods admitted through one server instance. It does not revoke direct witness calls, stop other processes, finish all response/frame handlers or quiesce caller/control/effect stores. Socket probes/inode checks are non-atomic and do not eliminate all startup/filesystem races.

## External prerequisites and disabled gate

The [lifecycle checklist](witness-trust-boundary-lifecycle.md) still requires a separately administered service, reviewed remote authenticated transport, independently protected anti-rollback generation/consumed state, separate restore authority, protected key lifecycle and independently retained tamper-evident audit evidence. Coordinated restore also needs independent admission/caller/effect fencing or quiescence, reconciliation of consumed-but-unapplied and unknown outcomes, and divergent-snapshot resolution before admission reopens.

Those controls require separately authorized infrastructure and operational/integration evidence. The six PostgreSQL-backed direct/RPC wrapper cases are local fixture evidence only. Actual effect adapters, protected storage/backups and production recovery remain unrun. No protected-infrastructure, physical power-loss or production-safety claim follows. Product dispatch, real external writes, paid models, deployment and production integration remain disabled.

## Historical checkpoints

The original Phase 8.4ai matrix recorded **46 pytest cases in 2.09s**, compilation and **9 separate in-memory regressions**. Its original commands/results remain available in the [immutable source checkpoint](https://github.com/Kokfu/congenial-potato/blob/8280b316c26fc0e04f242516f3f567011b549571/docs/research/witness-local-acceptance-matrix.md).

Later per-increment results remain in their dated notes and `progress.md`: [response JSON](witness-rpc-json-validation.md), [request binding](witness-rpc-response-binding-validation.md), [exchange freshness](witness-rpc-exchange-freshness-validation.md), and the linked lifecycle/recovery evidence above. Their older counts and stated gaps describe those historical source states; the current tables describe the parent of this refresh.
