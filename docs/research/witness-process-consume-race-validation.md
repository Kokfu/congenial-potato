# Separate-process witness consume race validation

Phase 8.4o starts two independent client processes, waits until both are
ready, then releases them to consume the same pending ticket over the private
Unix socket. One receives `spent`, the other receives a denial, and the
SQLite event log contains one consume event. This exercises competing client
processes and independent SQLite connections against one local server process.

This is fixture evidence for local process concurrency only. It does not prove
cross-host consensus, behavior under network partitions, protected storage
durability, or safe physical power-loss recovery. The local SQLite file and
server are not an independent production trust boundary. All state and keys
are synthetic; product dispatch remains disabled.

## Checks

The focused suites were copied to `/tmp` to bypass the repository-wide
`conftest.py` Docker/PostgreSQL fixture. Command:

```text
PYTHONPATH=/tmp/phase84-python:backend/tests:backend/src python -m pytest -q -x -p no:cacheprovider /tmp/test_durable_local_recovery_witness.py /tmp/test_durable_witness_fake_ledger_recovery.py /tmp/test_durable_local_witness_transport.py
```

Result: **34 passed in 1.12s**. Sandbox permission for the local Unix socket
was enabled.
