# Witness generation rollback boundary: Phase 8.4ag

Date: 2026-10-16. Branch: `phase-8-witness-generation-rollback-boundary`. Parent: state-key process rotation draft PR #104.

## Fixture and assertion

The durable local witness advances generation from 1 to 2 and then to 3. The test restores an earlier byte-for-byte copy of the SQLite witness database and observes generation 1 after reopening the witness. This shows that the protocol's generation is monotonic only while the local database history is retained; the file itself has no independent anti-rollback protection. It complements the consumed-invocation replacement test, which demonstrates that restoring a prior witness file can also reopen a consumed identity.

## Validation

```sh
cp backend/tests/test_durable_local_recovery_witness.py /tmp/test_durable_local_recovery_witness.py
PYTHONPATH=/tmp/phase84-python:backend/tests:backend/src python -m pytest -q -x -p no:cacheprovider /tmp/test_durable_local_recovery_witness.py
python -m py_compile backend/tests/durable_local_recovery_witness.py backend/tests/test_durable_local_recovery_witness.py
PYTHONPATH=backend/tests python -m unittest -v test_synthetic_write_recovery_witness
```

Results: **23 pytest cases passed in 0.16s**; Python compilation passed; **9 in-memory witness regressions passed**.

## Limits

This is a local file-copy fixture. It does not test physical power loss, protected storage, an independent monotonic counter, production transport, production key custody, or production guarantees. The trust boundary still needs independently protected durable state and a separately operated/authenticated service before product dispatch could be considered. Product dispatch remains disabled.
