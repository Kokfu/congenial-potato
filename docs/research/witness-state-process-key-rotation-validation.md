# Local witness state-key rotation across process restarts

Phase 8.4l exercises state-signing-key rotation using the separate local
server and client processes. The first server creates a reservation with
`state-v1`. After restart with only `state-v2`, consumption of the pending
`state-v1` ticket fails closed. Restoring an overlap config with both keys
allows that ticket to be consumed, while a new reservation uses `state-v2`.
After consuming, restarting with only `state-v2` still denies a new reservation
for the spent invocation.

The test uses synthetic key bytes, SQLite state, and a same-host Unix socket.
It verifies config loading and process restart behavior, not protected key
custody, remote delivery, physical power-loss safety, or production service
recovery. The pending old key must remain available until reservations signed
with it are resolved or intentionally denied under a separately reviewed
recovery policy; this fixture does not establish a production retirement
policy. Product dispatch remains disabled.

## Checks

The focused suites were copied to `/tmp` to bypass the repository-wide
`conftest.py` Docker/PostgreSQL fixture. Command:

```text
PYTHONPATH=/tmp/phase84-python:backend/tests:backend/src python -m pytest -q -x -p no:cacheprovider /tmp/test_durable_local_recovery_witness.py /tmp/test_durable_witness_fake_ledger_recovery.py /tmp/test_durable_local_witness_transport.py
```

Result: **31 passed in 1.07s**. Sandbox permission for the local Unix socket
was enabled. All keys and records were synthetic.
