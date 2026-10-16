# Local witness oversized-frame validation

Phase 8.4s sends a frame larger than the configured limit directly to the
local Unix-socket server and half-closes the client write side. The server
returns only the generic denial response; the reservation table remains
empty. This exercises the server-side frame-size check independently of the
client's pre-send size check.

This is local transport fixture evidence only. It does not establish remote
transport behavior, network denial-of-service resistance, or protected
infrastructure guarantees. All state and keys are synthetic; product
dispatch remains disabled.

## Checks

The focused suites were copied to `/tmp` to bypass the repository-wide
`conftest.py` Docker/PostgreSQL fixture. Command:

```text
PYTHONPATH=/tmp/phase84-python:backend/tests:backend/src python -m pytest -q -x -p no:cacheprovider /tmp/test_durable_local_recovery_witness.py /tmp/test_durable_witness_fake_ledger_recovery.py /tmp/test_durable_local_witness_transport.py
```

Result: **38 passed in 1.92s**. Sandbox permission for the local Unix socket
was enabled.
