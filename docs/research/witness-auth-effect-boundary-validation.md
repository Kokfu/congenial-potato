# Witness authentication at the synthetic effect boundary: Phase 8.4v

Date: 2026-10-16. Branch: `phase-8-witness-auth-effect-boundary`. Parent: witness outage effect-boundary draft PR #93.

## Fixture and assertions

The test sends a reservation with an invalid caller MAC and verifies authentication denial. It then substitutes a response with an invalid response MAC at the client boundary. The reservation verifier rejects the response before it can build a consume request or proceed to control admission. The witness reservation table, control fixture admission table, and fake ledger records/attempts all remain empty.

The protocol and effect target are test-only local fixtures. This does not connect a remote caller or external service.

## Validation

```sh
cp backend/tests/test_durable_witness_fake_ledger_recovery.py /tmp/test_durable_witness_fake_ledger_recovery.py
PYTHONPATH=/tmp/phase84-python:backend/tests:backend/src python -m pytest -q -x -p no:cacheprovider /tmp/test_durable_witness_fake_ledger_recovery.py
python -m py_compile backend/tests/test_durable_witness_fake_ledger_recovery.py
PYTHONPATH=backend/tests python -m unittest -v test_synthetic_write_recovery_witness
git diff --check
```

Results: **8 passed in 0.21s** for the copied fake-ledger recovery module; Python compilation passed; all **9** in-memory witness regression tests passed; whitespace and local Markdown link checks passed. The copy stays outside the backend test tree to avoid its global PostgreSQL fixture requirement.

## Limits

This verifies the local client helper and witness method boundary in-process. It does not prove remote identity, network security, external key custody, transport confidentiality, replay protection beyond the existing protocol tests, protected execution or production infrastructure. The witness and fake ledger remain replaceable local fixture files. No protected-storage or physical-power-loss guarantee is claimed. Product execution remains disabled.
