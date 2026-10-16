# Local witness process key-rotation validation

Phase 8.4j exercises the caller-key lifecycle over separate local client and
server processes. The server starts with a synthetic keyring containing
`caller-v1` and `caller-v2`, selecting `caller-v2` for new requests. A request
signed by `caller-v1` is still accepted during overlap; the new client uses
`caller-v2` for reservation, retry, and consume. After stopping and restarting
the server with only `caller-v2`, the consumed identity remains denied and a
request signed by the retired `caller-v1` key is rejected.

The fixture transport is a private same-host Unix socket: the parent directory
is mode 0700, the socket is mode 0600, the server checks the peer UID, and
request and response MACs bind the caller key ID. The synthetic server config
is mode 0600 and supplies keys at process startup. This demonstrates fixture
configuration and process restart only. It is not a production key-management
procedure: real key generation, protected distribution, evidence that all
callers migrated, retirement approval, revocation propagation, and independent
recovery ownership are still prerequisites. The config and witness file are
local files; filesystem races, power loss, and protected infrastructure are
not covered. Product dispatch remains disabled.

## Checks

The three focused suites were copied to `/tmp` to bypass the repository-wide
`conftest.py` Docker/PostgreSQL fixture. Command:

```text
PYTHONPATH=/tmp/phase84-python:backend/tests:backend/src python -m pytest -q -x -p no:cacheprovider /tmp/test_durable_local_recovery_witness.py /tmp/test_durable_witness_fake_ledger_recovery.py /tmp/test_durable_local_witness_transport.py
```

Result: **29 passed in 1.24s**. Sandbox permission for the local Unix socket
was enabled. All keys, caller identities, and records were synthetic.
