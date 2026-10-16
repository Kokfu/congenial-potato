# Local witness storage-path guard validation

Phase 8.4i makes the local witness reject a state path whose parent is not an
owned mode-0700 directory or whose database is not an owned regular
mode-0600 file. This rejects symlinks and other file types. Startup checks
that the durable generation is in range and that the expected event,
reservation, and generation-operation tables are present. The same path checks
run before each SQLite connection. Tests cover symlink and permission
rejection, incomplete schema rejection, and successful recovery after restoring
the expected fixture permissions.

These checks are local process/filesystem fixture evidence. They do not remove
time-of-check/time-of-use races, defend against privileged host or kernel
actors, verify SQLite physical durability after power loss, or make the
directory or database independently protected. No protected infrastructure
or production data was used. Product dispatch remains disabled.

## Checks

The focused suites were copied to `/tmp` to bypass the repository-wide
`conftest.py` Docker/PostgreSQL fixture. Command:

```text
PYTHONPATH=/tmp/phase84-python:backend/tests:backend/src python -m pytest -q -x -p no:cacheprovider /tmp/test_durable_local_recovery_witness.py /tmp/test_durable_witness_fake_ledger_recovery.py /tmp/test_durable_local_witness_transport.py
```

Result: **29 passed in 1.21s**. Sandbox permission for the local Unix socket
was enabled. All records and keys were synthetic.
