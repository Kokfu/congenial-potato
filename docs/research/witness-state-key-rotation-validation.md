# Local witness state-key rotation validation

Phase 8.4f extends the test-only durable SQLite witness with versioned state
signing keys. Each reservation records the key ID that authenticated its
ticket. A caller retry for an existing reservation returns the historical
ticket; new reservations use the configured current key. During an overlap,
both old and new keys can be loaded. Removing a key required by an unconsumed
reservation makes consumption fail closed until that key is restored. Once an
invocation is consumed, its durable spent identity remains spent even after
the ticket-signing key is retired.

This is local synthetic fixture evidence only. Keys are injected as startup
configuration; the prototype does not provide a protected key store, a remote
key-delivery channel, operator identity verification, key generation or
destruction, hardware-backed custody, or a production rotation procedure.
Caller-authentication key rotation is also not covered here. The SQLite state
file remains replaceable, and a same-host socket is not an independent
external recovery authority. These tests do not establish safety under
physical power loss or protected infrastructure failure. Product dispatch
remains disabled.

## Checks

The focused fixture tests were copied to `/tmp` so the repository-wide
`conftest.py` would not require Docker/PostgreSQL. The test command was:

```text
PYTHONPATH=/tmp/phase84-python:backend/tests:backend/src python -m pytest -q -x -p no:cacheprovider /tmp/test_durable_local_recovery_witness.py /tmp/test_durable_witness_fake_ledger_recovery.py /tmp/test_durable_local_witness_transport.py
```

Result: **26 passed in 0.85s**. The run required the sandbox's local socket
permission for the separate-process Unix-socket fixture. These tests exercise
synthetic keys and data only. The PostgreSQL-backed wrapper and Docker
integration were not run because Docker is unavailable in this environment.
