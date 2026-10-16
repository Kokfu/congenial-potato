# Recovery-admin key rotation concurrency validation

Phase 8.4n races two overlapping caller keys for the same stable,
allowlisted recovery-admin identity against one generation-advance operation
ID. Both authenticated requests receive the same durable generation result.
The generation operation and audit log each contain one mutation, with the
audit row identifying the key that won the transaction.

The fixture uses a single local SQLite database and threads. It does not prove
distributed consensus, cross-host linearizability, independent admin identity
verification, or durable recovery under physical power loss. Keys and records
are synthetic; product dispatch remains disabled.

## Checks

The focused suites were copied to `/tmp` to bypass the repository-wide
`conftest.py` Docker/PostgreSQL fixture. Command:

```text
PYTHONPATH=/tmp/phase84-python:backend/tests:backend/src python -m pytest -q -x -p no:cacheprovider /tmp/test_durable_local_recovery_witness.py /tmp/test_durable_witness_fake_ledger_recovery.py /tmp/test_durable_local_witness_transport.py
```

Result: **33 passed in 1.16s**. Sandbox permission for the local Unix socket
was enabled.
