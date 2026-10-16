# Simulated witness reply ordering: Phase 8.3i

Date: 2026-10-16. Branch: `phase-8-witness-reply-ordering`. Parent: witness-bound restore draft PR #70 (`a9febed`).

## Ordering rules captured by the fixture

The in-memory witness now treats the invocation UUID as an issue idempotency key for one exact `(ledger, intent digest)` binding. Repeating issue before consumption returns the identical ticket, so losing an issue response can safely retry that reservation. A changed binding for that invocation is rejected.

Consume is a one-way transition. If its reply is lost, the caller cannot infer whether any later effect ran; the invocation remains consumed/unknown and the simulator refuses a new ticket. This favors safety over liveness and can burn an invocation even if the caller crashed before calling the fake ledger. A restart of this in-memory simulator loses that consumed state and the same key/generation can consume the invocation again; the test deliberately demonstrates why the simulator itself is not a trust anchor.

Nine standard-library tests cover binding/single-use, generation advance, unavailable witness, concurrent single-winner consumption, invalid keys/generations, idempotent issue retry, lost consume reply refusal, and state loss after simulator restart.

## Validation

```sh
PYTHONPATH=backend/tests python -m unittest -v test_synthetic_write_recovery_witness
python -m py_compile backend/tests/synthetic_write_recovery_witness.py \
  backend/tests/test_synthetic_write_recovery_witness.py
```

Result: **9 passed in 0.003s**; compilation and `git diff --check` passed. All **87 local Markdown links** across updated progress/docs/evidence resolved. The standard-library fixture has no database or network dependency.

## External protocol requirements and limits

A real independent witness must durably key reservation retries by a caller-generated operation identity and exact binding; lost issue replies must return the same reservation. Consume must have a durable single-use transition; a lost consume reply must return only spent/unknown status, never another fresh effect permit. Its consumed history and generation high-water mark must survive process restart and restoration of both local stores. The real witness needs an authenticated transport and protected signing/state keys outside both restore domains.

This contract remains an in-memory simulator with no product imports, no application DB/ledger integration, no authenticated RPC or independently protected state. It does not validate witness availability, durability, key custody, power-loss behavior or product recovery. No retry after consume is allowed by this fixture.
