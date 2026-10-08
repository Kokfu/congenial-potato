# Scheduled and delegated daily budget: Phase 6.4

Date: 2026-10-08. Branch: `phase-6-daily-budget-integration`. Parent: Phase 6.3 draft PR #32.

The existing priced fixture path already reserves the UTC daily account and
the execution root account immediately before a model call. A scheduled
occurrence creates its own root account; a delegated child points to its
parent's root account. Both then use the same `governed_generate` and
`reserve_shared_cost` path. This slice adds an end-to-end fixture through
schedule admission, owner-controlled delegation, DBOS dispatch and the
shared money ledger. No new spending mechanism or live provider is enabled.

The fixture prices each call with a synthetic upper bound of **$0.000756**
and sets the UTC daily cap to that amount. A Manager root completes an
unpriced fixture call. A scheduled specialist run and a delegated specialist
child then compete for the single priced allowance. Exactly one request
reaches the timeout fixture and becomes `unknown`; its full hold remains on
the daily account and its root. The other execution fails closed without a
priced reservation. The delegated child has no independent root account and
retains the Manager's root ID. Reserving against the next UTC day creates a
separate daily account while the unknown hold remains on the previous day.
An attempted unknown settlement still retains the hold. Earlier ledger tests
cover simultaneous reservation threads, duplicate keys, known settlement and
overrun behavior.

## Reproduce

```sh
PYTHONPATH=backend/src APP_DATABASE_URL=postgresql+psycopg://postgres:phase1fixture@127.0.0.1:55433/workforce_test INITIAL_ADMIN_PASSWORD_FILE=/tmp/test-secret SESSION_COOKIE_SECURE=false /tmp/foundation-venv/bin/pytest -q backend/tests/test_schedule_daily_budget.py
PYTHONPATH=backend/src APP_DATABASE_URL=postgresql+psycopg://postgres:phase1fixture@127.0.0.1:55433/workforce_test INITIAL_ADMIN_PASSWORD_FILE=/tmp/test-secret SESSION_COOKIE_SECURE=false /tmp/foundation-venv/bin/pytest -q backend/tests
```

The focused PostgreSQL/DBOS integration test passed; **101 backend tests**
passed in the full suite. The last image build, Compose migration/health check and
fixture smoke were completed in Phase 6.3; this slice changes only a test and
documentation. It does not enable a live provider, paid request or external
integration.

## Limits

The daily account is in USD and keyed by UTC date of call reservation, not
the schedule's local date. A charge can arrive after the day changes; its
original hold remains tied to the original UTC day until settled or manually
reconciled. The fixture proves shared admission, not provider-side billing
accuracy. A real charge still needs independently verified price classes,
credentials and receipt reconciliation before native activation.
