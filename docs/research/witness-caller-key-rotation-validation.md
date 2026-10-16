# Local witness caller-key rotation validation

Phase 8.4g adds versioned caller-authentication keys to the local witness
fixture. Requests identify a caller key ID and authenticate that ID with the
request body. Responses include the selected key ID and authenticate it with
the response body. During overlap, either configured key for the same stable
caller ID can authenticate a request; the fixture can select a new key for
the Unix-socket client. The recovery-admin allowlist remains attached to the
stable caller ID. Removing the old key rejects requests signed by it while
requests with the replacement key continue to work across reopening the
SQLite witness.

This remains test-only behavior using synthetic key bytes loaded from a local
startup config. It does not establish protected key custody, remote key
delivery, operator identity verification, key generation/destruction,
hardware-backed custody, revocation propagation, or a production rotation
procedure. The local socket is same-host only and the SQLite file remains
replaceable. No PostgreSQL-backed wrapper, protected infrastructure, physical
power-loss case, or production caller was exercised. Product dispatch remains
disabled.

## Checks

The three focused suites were copied to `/tmp` to bypass the repository-wide
`conftest.py` Docker/PostgreSQL fixture. Command:

```text
PYTHONPATH=/tmp/phase84-python:backend/tests:backend/src python -m pytest -q -x -p no:cacheprovider /tmp/test_durable_local_recovery_witness.py /tmp/test_durable_witness_fake_ledger_recovery.py /tmp/test_durable_local_witness_transport.py
```

Result: **27 passed in 0.96s**. Sandbox permission for the local Unix socket
was enabled for this run. Data and keys were synthetic fixtures only.
