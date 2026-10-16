# Local witness acceptance matrix: Phase 8.4ba

Date: 2026-10-16. Branch: `phase-8-witness-acceptance-checkpoint-106`. Parent: response-body contract draft PR [#124](https://github.com/Kokfu/congenial-potato/pull/124), commit `214ac9bb252702561bade7850120ea65ba14a02a`.

This is the current local synthetic checkpoint. The fixture protocol, same-host transport and fake-ledger drills do not constitute an independent recovery service or product activation. Expected rollback and caller-effect limitations are recorded separately below.

## Current command and recorded results

```sh
/tmp/witness-local-venv/bin/python scripts/check_local_witness.py
```

The [fixed local checker](witness-local-check-command.md) tests the checkout directly, isolates pytest options/plugins/configuration, excludes PostgreSQL conftest loading and compiles selected files to a temporary directory. Dependency setup is documented with that command.

The latest executed runtime check is the Phase 8.4az parent: **106 local cases passed in 4.53s**, **65 product Python files passed the static fixture-import guard**, and **15 files compiled**. The PostgreSQL wrapper is compiled only. This documentation-only refresh did not rerun those test bodies; collection-only inspection verified the exact six-module, 106-case inventory, and changed-document links plus `git diff --check` passed.

| Collected module | Cases |
| --- | ---: |
| [Durable protocol](../../backend/tests/test_durable_local_recovery_witness.py) | 25 |
| [Fake-ledger recovery](../../backend/tests/test_durable_witness_fake_ledger_recovery.py) | 13 |
| [Local transport/process lifecycle](../../backend/tests/test_durable_local_witness_transport.py) | 37 |
| [Pending-snapshot audit rollback](../../backend/tests/test_witness_pending_snapshot_audit_rollback.py) | 1 |
| [Response parsing/binding/contracts](../../backend/tests/test_witness_rpc_response_validation.py) | 21 |
| [In-memory protocol regressions](../../backend/tests/test_synthetic_write_recovery_witness.py) | 9 |
| **Total** | **106** |

## Current fixture behavior and evidence

| Area | What the local checks exercise | Evidence |
| --- | --- | --- |
| Reservation/consumption | Exact binding, idempotent reserve retry, one-way consume, retained-state restart and concurrent winner | [Durable protocol](durable-local-recovery-witness-validation.md) |
| Generation/admin | Idempotent advance identity, stale-ticket denial, stable caller allowlist, typed unique admin configuration | [Advance retry](idempotent-witness-generation-advance-validation.md), [configuration](witness-server-config-validation.md) |
| Identity/key encoding | Canonical named caller/key/request fields under v2 request MAC domains; old delimiter format rejected | [Canonical identities](witness-canonical-auth-identities-validation.md) |
| Key lifecycle | Caller/state-key overlap, retirement, missing pending-ticket key denial and retained consumed identity | [Lifecycle](witness-trust-boundary-lifecycle.md), [process state-key rotation](witness-state-process-key-rotation-validation.md) |
| Framing/decoding | Byte cap, duplicate fields, non-finite numeric rejection and decode-error normalization | [RPC JSON](witness-rpc-json-validation.md), [frame size](witness-oversize-frame-validation.md) |
| Response correlation | v2 signed request binding plus fresh authenticated exchange nonce; stale/mismatched replies reject | [Request binding](witness-rpc-response-binding-validation.md), [exchange freshness](witness-rpc-exchange-freshness-validation.md) |
| Response metadata | Exact operation fields/status, integer generation range, canonical IDs, echoed bindings and ticket/digest shape | [Body contracts](witness-response-body-contract-validation.md) |
| Endpoint startup | Active/uncertain socket refusal, stable stale-path inode check, authenticated process readiness | [Socket guard](witness-socket-liveness-guard-validation.md) |
| Local receive/load | Monotonic frame receive budget, 32 active-handler cap and slot recovery | [Receive deadline](witness-frame-receive-deadline-validation.md), [capacity](witness-connection-cap-validation.md) |
| Stop/drain | Late-frame denial, atomic stop/admission, counted synchronous method drain, explicit unknown on drain expiry | [Stop gate](witness-stop-dispatch-gate-validation.md), [dispatch drain](witness-dispatch-drain-validation.md) |
| Effect recovery | Real fake-ledger fixture records through retained-witness rollback/replacement, lost reply, outage and key changes | [Fake-ledger recovery](durable-witness-fake-ledger-recovery-validation.md), [lost reply](witness-lost-reply-effect-boundary-validation.md) |
| Product/source boundary | Named static fixture imports denied in product Python before tests; no product runtime imported by that scan | [Static guard](witness-product-import-boundary-validation.md) |

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

Those controls require separately authorized infrastructure and operational/integration evidence. The PostgreSQL-backed wrapper, actual effect adapters, protected storage/backups and production recovery remain unrun. No protected-infrastructure, physical power-loss or production-safety claim follows. Product dispatch, real external writes, paid models, deployment and production integration remain disabled.

## Historical checkpoints

The original Phase 8.4ai matrix recorded **46 pytest cases in 2.09s**, compilation and **9 separate in-memory regressions**. Its original commands/results remain available in the [immutable source checkpoint](https://github.com/Kokfu/congenial-potato/blob/8280b316c26fc0e04f242516f3f567011b549571/docs/research/witness-local-acceptance-matrix.md).

Later per-increment results remain in their dated notes and `progress.md`: [response JSON](witness-rpc-json-validation.md), [request binding](witness-rpc-response-binding-validation.md), [exchange freshness](witness-rpc-exchange-freshness-validation.md), and the linked lifecycle/recovery evidence above. Their older counts and stated gaps describe those historical source states; the current tables describe the parent of this refresh.
