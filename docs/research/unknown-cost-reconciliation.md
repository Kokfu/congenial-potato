# Unknown synthetic charge reconciliation

Date: 2026-10-08. This slice uses fake providers and synthetic evidence references only. It does not enable native calls or verify a provider invoice.

## Behavior

An uncertain priced call remains `unknown` with its root and UTC daily holds reserved. An authenticated owner can inspect `GET /api/executions/{id}/cost-hold` and submit `POST /api/executions/{id}/cost-reconciliation` with the exact held amount, a calculated USD charge and a `synthetic:` evidence reference. The command requires CSRF protection. It moves the existing hold once from reserved to spent and writes one audit record containing the amount and evidence reference. An exact replay is idempotent; a changed amount or reference conflicts. A known settled result cannot be relabeled as a manual reconciliation. The model call is never retried.

The reference is an **owner attestation**, not a receipt verified by this service. Only `synthetic:` references are accepted in this slice. The endpoint does not establish a true external charge or permit native activation. A future live flow needs provider statement retrieval or another independently verifiable source before releasing an unknown hold.

## Reproduce

With disposable PostgreSQL `workforce_test` and `workforce_dbos_test` databases and a synthetic owner secret:

```sh
PYTHONPATH=backend/src APP_DATABASE_URL=postgresql+psycopg://postgres:<test-password>@127.0.0.1:55433/workforce_test INITIAL_ADMIN_PASSWORD_FILE=<synthetic-secret-file> SESSION_COOKIE_SECURE=false pytest -q backend/tests
```

The integration fixture dispatches a priced timeout, observes equal root/daily reservations and no model result, then records a synthetic charge. It checks one settled hold, one audit event and zero subsequent model calls. It also checks wrong hold amount, changed charge/reference, missing CSRF and a previously settled call.

Result: **29 backend tests passed**. The non-root backend image built, the local Compose API/worker restarted, and `python scripts/smoke.py` passed with unauthorized dispatch denied, a successful synthetic execution, task review and an audit record.

## Remaining limits

Unknown calls still require a human to find a trustworthy charge source. A fabricated reference could falsely free money; the present API is intentionally limited to synthetic references and native adapters remain unregistered. Provider cost categories and billed totals have not been reconciled against a real statement. No paid call was made.
