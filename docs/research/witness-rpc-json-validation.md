# Local witness RPC JSON framing validation

Phase 8.4r rejects duplicate JSON object fields in an authenticated RPC frame.
A synthetic reserve request with a duplicated `caller_id` field receives the
generic denial response, and the reservation table remains empty. This keeps
the local decoder's interpretation unambiguous before caller authentication
and protocol dispatch.

This is a local Unix-socket parser fixture. It does not establish remote
transport security, cross-implementation canonicalization, or protected
infrastructure behavior. The request, key, and state are synthetic; product
dispatch remains disabled.

## Checks

The focused suites were copied to `/tmp` to bypass the repository-wide
`conftest.py` Docker/PostgreSQL fixture. Command:

```text
PYTHONPATH=/tmp/phase84-python:backend/tests:backend/src python -m pytest -q -x -p no:cacheprovider /tmp/test_durable_local_recovery_witness.py /tmp/test_durable_witness_fake_ledger_recovery.py /tmp/test_durable_local_witness_transport.py
```

Result: **37 passed in 1.60s**. Sandbox permission for the local Unix socket
was enabled.

## Phase 8.4al: strict response JSON

Date: 2026-10-16. Branch: `phase-8-witness-rpc-strict-response-json`. Parent: pending-snapshot audit rollback draft PR #109.

The client now applies the same duplicate-field rejection when decoding responses. A temporary Unix-socket peer serves an actual authenticated generation response with a duplicated `body`, `key_id`, `mac`, or nested `generation` field. In each case the final duplicate value would produce a valid HMAC under Python's default last-value parser. Before the fix all four malformed responses were accepted; afterward all four are denied before response authentication, while the unambiguous signed response remains accepted. The peer and keys are local synthetic fixtures.

Validation uses a complete checkout and a temporary virtual environment with the repository-pinned pytest 8.4.2 and pydantic 2.13.5. The six local modules are copied out of the repository test directory to avoid its PostgreSQL `conftest.py`:

```sh
mkdir -p /tmp/witness-local-checks
cp backend/tests/test_durable_local_recovery_witness.py backend/tests/test_durable_witness_fake_ledger_recovery.py backend/tests/test_durable_local_witness_transport.py backend/tests/test_witness_pending_snapshot_audit_rollback.py backend/tests/test_witness_rpc_response_validation.py backend/tests/test_synthetic_write_recovery_witness.py /tmp/witness-local-checks/
PYTHONPATH=backend/tests:backend/src /tmp/witness-local-venv/bin/python -m pytest -q -x -p no:cacheprovider /tmp/witness-local-checks
python -m py_compile backend/tests/durable_local_witness_transport.py backend/tests/test_witness_rpc_response_validation.py
git diff --check
```

Result: **58 cases passed in 2.73s**, including the previous 46 durable/protocol/process cases, nine in-memory regressions, the pending-snapshot audit drill and two response-parser tests (one with four duplicate-field subcases). Compilation, local Markdown link checks and whitespace checks passed. Local socket tests ran with sandbox permission; no TCP/IP effect service, product dispatch or production integration was started.

Strict parsing removes ambiguous response interpretation. It does not add response freshness or request correlation, independent anti-rollback state, protected audit retention, remote authentication, protected infrastructure or physical power-loss evidence. These remain separate concerns; product dispatch stays disabled.
