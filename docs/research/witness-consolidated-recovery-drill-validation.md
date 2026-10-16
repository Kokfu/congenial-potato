# Consolidated local witness recovery drill: Phase 8.4t

Date: 2026-10-16. Branch: `phase-8-witness-consolidated-recovery-drill`. Parent: local witness oversized-frame draft PR #91.

## Fixture and assertions

The new test composes the earlier local synthetic checks into one scenario. It creates an idempotent reservation retry and asserts the ticket response is identical, then consumes the ticket while deliberately dropping the reply. It restores both the control SQLite fixture and fake-ledger SQLite fixture to their initial snapshots, restarts the witness object with overlapping caller and state keys, and retries reservation and consume. Both are denied as consumed. The current generation remains 1; restored control and ledger fixtures remain empty; the separate witness fixture retains exactly one consumed reservation, one `reserved` audit event, and one `consumed` audit event.

No product dispatch or external service is used. All payloads, keys, database files, and effects are test fixtures.

## Validation

Commands run from the repository root:

```sh
cp backend/tests/test_durable_witness_fake_ledger_recovery.py /tmp/test_durable_witness_fake_ledger_recovery.py
PYTHONPATH=/tmp/phase84-python:backend/tests:backend/src python -m pytest -q -x -p no:cacheprovider /tmp/test_durable_witness_fake_ledger_recovery.py
python -m py_compile backend/tests/test_durable_witness_fake_ledger_recovery.py
PYTHONPATH=backend/tests python -m unittest -v test_synthetic_write_recovery_witness
```

Results: **6 passed in 0.11s** for the copied fake-ledger recovery module; Python compilation passed; the pre-existing in-memory witness regression suite passed **9 tests**. The copy runs outside `backend/tests` to avoid the repository-wide `conftest.py` PostgreSQL requirement. Additional repository checks: `git diff --check` and local Markdown link validation passed.

## Limits and remaining prerequisites

These tests establish behavior only for this local Python/SQLite fixture and the test-only fake ledger. The control and ledger stores are replaceable local files, and the witness file is also replaceable; retaining it in this drill is an explicit fixture condition. Key overlap is configured in process and is not evidence of protected key custody. The test does not establish PostgreSQL integration, independent administration or storage, remote authenticated transport, external effect truth, tamper resistance, physical power-loss durability, protected infrastructure recovery, or production safety. No physical power-loss claim is made. Product execution remains disabled pending separately authorized external prerequisites and review.
