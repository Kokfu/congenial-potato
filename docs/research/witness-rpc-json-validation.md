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
