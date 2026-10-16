# Local RPC exchange freshness: Phase 8.4an

Date: 2026-10-16. Branch: `phase-8-witness-rpc-exchange-freshness`. Parent: response/request binding draft PR #111.

## Reproduction and change

The parent bound responses to a deterministic request MAC. A local peer could still replay an authentic generation-1 reply to the identical generation query after the witness had advanced to generation 2; the new rejection test failed before this change.

The Unix-socket client now generates a fresh random UUID for each exchange. The request frame carries `exchange_nonce`; a separate `workforce.synthetic.write.witness.exchange.request.v1` HMAC domain authenticates the canonical request and nonce together with caller and key ID. The witness verifies that context before protocol work. Its existing v2 response envelope signs this nonce-bound request MAC, and the client compares it to the current outbound MAC. The server requires the nonce field and rejects missing, null, malformed, noncanonical, changed or unauthenticated nonce context without legacy fallback.

The nonce is exchange context, not an invocation identity or reservation-ticket field. Exact reservation retries still return the same ticket body and create one reservation/audit row, while each exchange has a different request/response MAC. Direct in-process fixtures can still use the nonce-free protocol helper; the Unix-socket server cannot. No SQLite migration or durable nonce cache is added. Repeated commands retain their existing reservation/consume/advance identity semantics, and an unknown consume outcome still cannot authorize a blind retry or an effect.

## Checks

The local peer tests reject the stale identical-query reply and replay of an actual captured spent reply on a second exchange for the same consume. They verify that the witness still denies a real second consume and retains one consume audit event. Fresh-nonce reservation retries return identical ticket bodies. Seven invalid nonce-frame variants fail before any reservation or audit mutation. Existing mismatch and duplicate-response regressions now construct replies using the current exchange nonce, so they continue to test request binding and strict parsing rather than failing only because context is missing. The duplicate-request regression was also made otherwise valid for the current frame format.

```sh
cp backend/tests/test_durable_local_recovery_witness.py backend/tests/test_durable_witness_fake_ledger_recovery.py backend/tests/test_durable_local_witness_transport.py backend/tests/test_witness_pending_snapshot_audit_rollback.py backend/tests/test_witness_rpc_response_validation.py backend/tests/test_synthetic_write_recovery_witness.py /tmp/witness-local-checks/
PYTHONPATH=backend/tests:backend/src /tmp/witness-local-venv/bin/python -m pytest -q -x -p no:cacheprovider /tmp/witness-local-checks
python -m py_compile backend/tests/durable_local_recovery_witness.py backend/tests/durable_local_witness_transport.py backend/tests/test_durable_local_witness_transport.py backend/tests/test_witness_rpc_response_validation.py
git diff --check
```

Result: **67 local cases passed in 2.28s** with pytest 8.4.2 and pydantic 2.13.5. The combined set includes all earlier durable/process, fake-ledger, key-rotation and lost-reply drills. Compilation, changed-document Markdown links and whitespace checks passed. Unix-socket tests ran with sandbox permission. PostgreSQL and product integration were not run.

## Limits

Freshness here means that a captured response from a different random exchange does not satisfy the current client's expected binding. It does not provide trusted time, current-generation truth after a response was computed, nonce protection after compromise of the fixture key/randomness, or anti-rollback storage. The [pending-snapshot replay](witness-pending-snapshot-audit-rollback-validation.md) remains reproducible in the direct fixture: a witness restored to pending state can consume the same ticket again. Remote authentication, independent protected state/key/audit custody and restore reconciliation still require the [external lifecycle prerequisites](witness-trust-boundary-lifecycle.md). There is no protected-infrastructure or physical power-loss claim. Product dispatch, real external writes, paid models, deployment and production integration stay disabled.
