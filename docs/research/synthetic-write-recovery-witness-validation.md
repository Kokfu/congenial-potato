# Simulated monotonic recovery witness: Phase 8.3g

Date: 2026-10-16. Branch: `phase-8-simulated-recovery-witness`. Parent: recovery continuity draft PR #68 (`4f3b415`).

## Fixture protocol

`backend/tests/synthetic_write_recovery_witness.py` is a process-local protocol simulator, not a durable recovery service. It issues a domain-separated HMAC ticket binding one generation, ledger UUID, invocation UUID, exact intent digest and fresh nonce. Consume revalidates the strict fields and signature, compares against the witness's current generation, and atomically consumes an invocation identity. Advancing a generation makes old tickets stale but retains consumed invocation history. Missing/unavailable witness, malformed key/generation/ticket, changed bindings, stale generation and duplicate consumption deny.

Six standard-library tests cover exact binding/single use, stale generations across epoch advancement, unavailable service on issue and consume, concurrent duplicate consumption, invalid generation values and invalid key length. The concurrency test issues two tickets for one identity and confirms exactly one wins.

## Validation

```sh
PYTHONPATH=backend/tests python -m unittest -v test_synthetic_write_recovery_witness
python -m py_compile backend/tests/synthetic_write_recovery_witness.py \
  backend/tests/test_synthetic_write_recovery_witness.py
```

Result: **6 passed in 0.003s**; Python compilation passed. The module is referenced only by its test, with no import from application modules.

## Limits and next task

This simulator's key, generation and consumed set are in process memory. Restarting it resets all three, so it cannot detect any real rollback and must never be described as a recovery control. It is only contract-shape evidence for a separate witness that is protected outside the application DB and fake ledger. There is no application DB/ledger binding, durable ticket history, external service, hardware counter, key custody, transport authentication, outage recovery or product dispatch.

Next bind this test-only ticket contract into a disposable admission/ledger recovery harness and repeat single-store and coordinated-restore cases while the simulated witness state survives the two local store rollbacks. Preserve the explicit limitation that all three local fixture states can still be reset together. No product path or production recovery infrastructure is authorized.
