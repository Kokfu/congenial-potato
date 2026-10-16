# Local witness server configuration validation

Phase 8.4k makes the local server reject duplicate JSON keys and unknown or
missing server configuration fields before it opens the socket. Caller and
state keyring forms require their matching current key IDs; alternate
single-key fields cannot be mixed with keyring configuration. The separate
client-process fixture configuration is no longer included in the server
configuration. A process test exercises rotation with distinct client and
server files: old and replacement caller keys overlap, the replacement key
serves requests, then restart with only the replacement rejects the retired
key and still denies the already consumed invocation.

Both files are synthetic fixture configuration with local mode-0600
permissions. This reduces configuration ambiguity in the prototype; it does
not provide protected config distribution, secret storage, external caller
identity, filesystem race protection, or production key rotation. The
transport is a same-host Unix socket and product dispatch remains disabled.

## Checks

The focused suites were copied to `/tmp` to bypass the repository-wide
`conftest.py` Docker/PostgreSQL fixture. Command:

```text
PYTHONPATH=/tmp/phase84-python:backend/tests:backend/src python -m pytest -q -x -p no:cacheprovider /tmp/test_durable_local_recovery_witness.py /tmp/test_durable_witness_fake_ledger_recovery.py /tmp/test_durable_local_witness_transport.py
```

Result: **30 passed in 0.92s**. Sandbox permission for the local Unix socket
was enabled. Keys, identities, and state were synthetic.
