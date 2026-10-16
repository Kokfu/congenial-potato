# Lost consume reply across witness process restart

Phase 8.4q sends a consume request from a separate client process, closes the
client's response side immediately, and waits for the server's durable event.
The server is then stopped and reopened against the same synthetic witness
file. A fresh client retry for that invocation is denied, and the reservation
remains consumed with exactly one consume event. This exercises one-way
consume behavior after a lost RPC reply across server restart.

This is a local Unix-socket and SQLite process fixture. It does not simulate
protected infrastructure failure or physical power loss, and it does not
establish production filesystem durability. The witness file remains
replaceable and the local service is not an independent external trust
boundary. Data and keys are synthetic; product dispatch remains disabled.

## Checks

The focused suites were copied to `/tmp` to bypass the repository-wide
`conftest.py` Docker/PostgreSQL fixture. Command:

```text
PYTHONPATH=/tmp/phase84-python:backend/tests:backend/src python -m pytest -q -x -p no:cacheprovider /tmp/test_durable_local_recovery_witness.py /tmp/test_durable_witness_fake_ledger_recovery.py /tmp/test_durable_local_witness_transport.py
```

Result: **36 passed in 1.44s**. Sandbox permission for the local Unix socket
was enabled.
