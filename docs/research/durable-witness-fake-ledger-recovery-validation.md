# Durable witness and fake-ledger restore drills: Phase 8.4b

Date: 2026-10-16. Branch: `phase-8-durable-witness-restore-drills`. Parent: durable local witness draft PR #73 (`9d39687`).

## Fixture design

`backend/tests/test_durable_witness_fake_ledger_recovery.py` drives the actual test-only `SyntheticWriteLedger.apply` with a separately persisted local witness. A small SQLite control-state fixture records a consumed admission marker. The control fixture, fake-ledger directory and witness file use separate paths and separate baseline snapshots. After a synthetic effect, the harness restores the control fixture, fake ledger, or both while retaining the witness file, reopens the witness object, and attempts the same invocation again. Every repeat is denied at reservation before writing control state or opening a new effect attempt.

The five checks cover control-only rollback, ledger-only rollback, coordinated rollback, replacing the ledger with an empty SQLite file, and a lost consume reply followed by a fresh witness object. The last case confirms fail-closed behavior burns an invocation even when the fake ledger was never entered. The drill uses synthetic content and no external writes.

## Validation

```sh
cp backend/tests/test_durable_witness_fake_ledger_recovery.py /tmp/test_durable_witness_fake_ledger_recovery.py
cp backend/tests/test_durable_local_recovery_witness.py /tmp/test_durable_local_recovery_witness.py
PYTHONPATH=/tmp/phase84-python:backend/tests:backend/src python -m pytest -q -x -p no:cacheprovider /tmp/test_durable_local_recovery_witness.py /tmp/test_durable_witness_fake_ledger_recovery.py
python -m py_compile backend/tests/durable_local_recovery_witness.py backend/tests/test_durable_local_recovery_witness.py backend/tests/test_durable_witness_fake_ledger_recovery.py backend/tests/test_synthetic_write_admission.py
PYTHONPATH=backend/tests python -m unittest -v test_synthetic_write_recovery_witness
git diff --check
```

Result: **15 pytest cases passed in 0.18s** across the new witness protocol and restore-drill suites; the existing in-memory protocol regression passed **9 tests**. Python compilation and whitespace check passed. Pytest 9.1.1 is in `/tmp/phase84-python`; both new suites were copied outside `backend/tests` to avoid the global `conftest.py` requirement for a disposable PostgreSQL database.

## Limits

The control database in this drill is a SQLite fixture, not the application's PostgreSQL database. These files share a local host and filesystem; separate directories do not create independent trust domains. This demonstrates the protocol behavior when witness state is retained while synthetic control/ledger files roll back. It does not establish actual PostgreSQL integration, independent backup systems, external execution truth, hardware monotonicity, filesystem or physical power-loss durability, protected host operation, or safety if the witness file itself is restored. The prior negative test explicitly shows that replacing the witness file with an old copy can reopen a consumed invocation.

The PostgreSQL admission plus SQLite fake-ledger integration wrapper remains unexecuted in this environment because the Docker daemon socket is inaccessible. Keep product dispatch disabled. A future protected service requires independent administration and storage, authenticated remote transport, reviewed key provisioning/rotation/revocation, externally auditable restore controls, and separate authorization. No production guarantee or physical power-loss claim follows from these local drills.
