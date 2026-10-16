# Local witness key audit trail validation

Phase 8.4h adds caller identity, caller key ID, and (when applicable) state
ticket key ID to each durable mutating witness event. Reservation, consume,
and generation-advance events write these fields in the same SQLite
transaction as their state mutation. A regression rotates the caller key,
consumes a ticket created under the previous state key, advances generation,
reopens the fixture, and checks that the event history records the expected
caller/key IDs.

This log is stored in the same replaceable local SQLite file as the witness
state. It is not tamper-evident or independently protected, and there is no
remote audit sink, signature chain, trusted timestamp, or log-retention
control. The test uses synthetic identities and keys only. It does not prove
physical power-loss behavior or protected infrastructure guarantees.
Product dispatch remains disabled.

## Checks

The three focused suites were copied to `/tmp` to bypass the repository-wide
`conftest.py` Docker/PostgreSQL fixture. Command:

```text
PYTHONPATH=/tmp/phase84-python:backend/tests:backend/src python -m pytest -q -x -p no:cacheprovider /tmp/test_durable_local_recovery_witness.py /tmp/test_durable_witness_fake_ledger_recovery.py /tmp/test_durable_local_witness_transport.py
```

Result: **27 passed in 0.69s**. The sandbox's local Unix-socket permission
was enabled for this run. All data and keys were synthetic.
