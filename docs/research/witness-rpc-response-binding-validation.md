# Authenticated witness response/request binding: Phase 8.4am

Date: 2026-10-16. Branch: `phase-8-witness-rpc-response-binding`. Parent: strict-response JSON draft PR #110.

## Reproduced gap and change

The temporary local Unix-socket peer previously could return an authenticated generation response to an advance request, or return ticket A's authenticated consume response while ticket B remained pending. Both new rejection tests failed on the parent implementation: the client checked response authenticity without checking which request it answered. No fake-ledger effect was attempted.

The test-only response envelope now includes the authenticated request MAC. Response HMAC domain `workforce.synthetic.write.witness.response.v2` covers the body and that request binding, as well as the response key ID. The request MAC already binds caller identity, caller key ID and the complete canonical request, so the client compares it to the exact outbound request MAC after response authentication. All successful generation, reserve, consume and advance responses use the new format, including idempotent historical replies. Old envelope shapes are rejected without fallback; the SQLite schema and reservation-ticket format are unchanged.

Direct fixture helpers now also check the expected request MAC when they have an outstanding request. `verify_response` still supports authentication-only inspection of a captured envelope when no expected request MAC is supplied; the RPC client always supplies one. The PostgreSQL fixture helper was updated and compiled, but its database-backed test was not run.

## Checks

The response fixture checks normal acceptance, mismatched operation, a different consumed ticket with the current ticket still pending, binding tampering, caller mismatch when fixture key bytes are reused, missing binding, and duplicate JSON fields (including the new binding field). Both original mismatch reproductions now reject.

```sh
cp backend/tests/test_durable_local_recovery_witness.py backend/tests/test_durable_witness_fake_ledger_recovery.py backend/tests/test_durable_local_witness_transport.py backend/tests/test_witness_pending_snapshot_audit_rollback.py backend/tests/test_witness_rpc_response_validation.py backend/tests/test_synthetic_write_recovery_witness.py /tmp/witness-local-checks/
PYTHONPATH=backend/tests:backend/src /tmp/witness-local-venv/bin/python -m pytest -q -x -p no:cacheprovider /tmp/witness-local-checks
python -m py_compile backend/tests/durable_local_recovery_witness.py backend/tests/durable_local_witness_transport.py backend/tests/test_durable_local_recovery_witness.py backend/tests/test_durable_witness_fake_ledger_recovery.py backend/tests/test_witness_pending_snapshot_audit_rollback.py backend/tests/test_witness_rpc_response_validation.py backend/tests/test_synthetic_write_admission.py
git diff --check
```

Result: **63 local cases passed in 1.94s** with pytest 8.4.2 and pydantic 2.13.5, including all existing durable/process and fake-ledger drills. Compilation, changed-document Markdown links and whitespace checks passed. Local Unix sockets used sandbox permission. The PostgreSQL wrapper and product integration remain unrun.

## Remaining boundary

Request correlation is not freshness. An identical request from the same caller/key has the same request MAC; a captured authentic response to that identical request can still match. This increment does not add a per-exchange nonce, protect replaceable witness storage, or fix the [pending-snapshot replay](witness-pending-snapshot-audit-rollback-validation.md). Independent anti-rollback storage, audit retention and restore reconciliation still need the [external prerequisites](witness-trust-boundary-lifecycle.md). No claim is made for protected infrastructure or physical power loss. Product dispatch, real writes, paid models, deployment and production integration remain disabled.
