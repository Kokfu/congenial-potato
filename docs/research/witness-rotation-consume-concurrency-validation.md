# Caller-key rotation consume concurrency validation

Phase 8.4m races two authenticated callers using `caller-v1` and `caller-v2`
against the same pending ticket during configured overlap. Both requests bind
the caller key ID into their MACs and share the same stable caller identity.
The SQLite transaction permits exactly one consume to commit; the competing
request receives a denial. The durable audit contains exactly one consume
event, identifying whichever key won.

This is a same-process concurrency fixture over the replaceable local SQLite
file. The test does not establish cross-host linearizability, protected
storage durability, behavior after physical power loss, or external recovery
authority. The audit row is not an independent trust anchor. All keys and
records are synthetic, and product dispatch remains disabled.

## Checks

The focused suites were copied to `/tmp` to bypass the repository-wide
`conftest.py` Docker/PostgreSQL fixture. Command:

```text
PYTHONPATH=/tmp/phase84-python:backend/tests:backend/src python -m pytest -q -x -p no:cacheprovider /tmp/test_durable_local_recovery_witness.py /tmp/test_durable_witness_fake_ledger_recovery.py /tmp/test_durable_local_witness_transport.py
```

Result: **32 passed in 1.01s**. Sandbox permission for the local Unix socket
was enabled.
