# Caller-key rotation at the synthetic effect boundary: Phase 8.4x

Date: 2026-10-16. Branch: `phase-8-witness-rotation-effect-boundary`. Parent: witness trust-boundary lifecycle draft PR #95.

## Fixture and assertions

The test reserves a ticket with `caller-v1`, reopens the witness with old and replacement caller keys configured and `caller-v2` selected, then authenticates consumption and response verification with `caller-v2`. Only after verified consume does the test add the synthetic control admission marker and apply one test-only fake-ledger write. It then restarts with only `caller-v2` configured; replay of the same reservation is denied as consumed and the fake ledger retains exactly one record and one attempt.

The scenario confirms the stable caller identity can overlap keys while a ticket is pending, and that caller-key retirement does not reopen consumed identity. It uses only local synthetic keys and fixture data.

## Validation

```sh
cp backend/tests/test_durable_witness_fake_ledger_recovery.py /tmp/test_durable_witness_fake_ledger_recovery.py
PYTHONPATH=/tmp/phase84-python:backend/tests:backend/src python -m pytest -q -x -p no:cacheprovider /tmp/test_durable_witness_fake_ledger_recovery.py
python -m py_compile backend/tests/test_durable_witness_fake_ledger_recovery.py
PYTHONPATH=backend/tests python -m unittest -v test_synthetic_write_recovery_witness
git diff --check
```

Final result: **9 passed in 0.13s** for the copied fake-ledger recovery module; Python compilation passed; all **9** in-memory witness tests passed; Markdown local-link and whitespace checks passed. An initial run exposed that the fixture's current caller key ID must be set to `caller-v2` when selecting the replacement key; the test configuration was corrected and the full focused module rerun successfully. Tests are copied outside the backend tree to avoid the repository-wide PostgreSQL fixture requirement.

## Limits

This exercises in-process configuration reload using the local SQLite witness and test fake ledger. It does not verify protected key custody, remote caller identity, remote transport, operator rotation procedures, production storage, the PostgreSQL-backed wrapper, physical power loss or production guarantees. No product dispatch or external write was enabled.
