# Governed synthetic model-call validation

Date: 2026-10-07. This exercise uses the registered fake adapters only. No native adapter, production credential or paid endpoint was used.

## Boundary and behavior

An agent config can contain an operator-supplied `price_envelope` matching its pinned provider connection and model. The envelope has a source, expiry, token ceilings and upper USD prices. `DAILY_CAP_USD` is required for this opt-in path; missing cap, expired/mismatched envelope, or exceeded token bound fails closed. Normal unpriced fixtures retain their existing fixed synthetic reservation.

The worker estimates tokens via the adapter, checks the envelope, locks the execution and project grant, then commits root and UTC daily holds before calling. A committed `calling` hold represents an uncertain external outcome after a crash. Replay changes it to `unknown` and never calls again. A response with reported usage settles a **calculated** charge in the same transaction that records the model result. This is not a provider invoice. A timeout leaves both holds reserved and execution `unknown`. Mismatched response model also remains unknown. Reconciliation of an unknown charge remains manual.

The workflow version is `governed-cost-v1`. Existing in-flight DBOS workflows require a versioned drain or migration plan before deployment; code-version recovery was not validated here. Native adapters remain unregistered, and the opt-in envelope is currently seeded directly in disposable tests rather than exposed in the owner UI or API.

## Reproduce

With disposable PostgreSQL databases `workforce_test` and `workforce_dbos_test`, and a synthetic owner secret:

```sh
PYTHONPATH=backend/src APP_DATABASE_URL=postgresql+psycopg://postgres:<test-password>@127.0.0.1:55433/workforce_test INITIAL_ADMIN_PASSWORD_FILE=<synthetic-secret-file> SESSION_COOKIE_SECURE=false pytest -q backend/tests
```

Result: **24 passed**. The priced alpha case recorded one `ModelCall`, a settled hold and equal root/daily spent balances with no reserved balance. Replayed dispatch left the logical model call and charge at one. The priced timeout case recorded no `ModelCall`, retained equal root/daily reservations and marked the execution unknown. A fixture seeded with a committed `calling` hold used an adapter method that raises if invoked; recovery returned unknown, retained the hold and never invoked that method.

The backend image rebuilt and the local Compose worker restarted. `python scripts/smoke.py` passed: unauthorized dispatch returned 403, the synthetic execution succeeded, the task entered review and an audit record existed. The first image run caught an unreadable new source file (`600` mode); after correcting it to `644` and rebuilding, the non-root worker imported the module and the smoke test passed.

## Remaining activation gate

Native adapters need explicit registration policy and credentials, a bounded request deadline, conservative treatment of cached/reasoning token classes and untrusted provider usage, cancellation checks around the call, reconciliation for unknown charges, operator entry and refresh of price envelopes, and end-to-end tests with controlled HTTP fixtures before any live opt-in. The daily cap here is process configuration and not yet a complete operator cost policy. No paid call or live pricing validation was performed.
