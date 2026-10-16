# Separate-process recovery-admin race validation

Phase 8.4p starts two independent local client processes with the same
allowlisted caller identity and generation-advance operation ID. Both wait
behind a readiness barrier before submitting the authenticated RPC. Each
receives the same `advanced` response at generation 2; the durable generation,
operation row, and audit event each show one increment.

This is a same-host Unix-socket and SQLite fixture. It does not establish
independent recovery-admin identity verification, cross-host consensus,
network-partition behavior, protected storage durability, or physical
power-loss recovery. Keys and records are synthetic. Product dispatch remains
disabled.

## Checks

The focused suites were copied to `/tmp` to bypass the repository-wide
`conftest.py` Docker/PostgreSQL fixture. Command:

```text
PYTHONPATH=/tmp/phase84-python:backend/tests:backend/src python -m pytest -q -x -p no:cacheprovider /tmp/test_durable_local_recovery_witness.py /tmp/test_durable_witness_fake_ledger_recovery.py /tmp/test_durable_local_witness_transport.py
```

Result: **35 passed in 1.30s**. Sandbox permission for the local Unix socket
was enabled.
