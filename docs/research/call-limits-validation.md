# Call deadline and cancellation fixture validation

Date: 2026-10-07. All model calls in this exercise used deterministic fake adapters or SDK mock transports. No paid endpoint or production integration was contacted.

The worker sets an aware UTC deadline using `MODEL_CALL_TIMEOUT_SECONDS` (default 20, valid 1–120). The fake adapter rejects an expired deadline. The unregistered OpenAI and Anthropic text adapters calculate remaining time and use their SDK `with_options(timeout=...)` APIs for each generation request. Offline HTTP fixtures exercised both methods with future deadlines and verified expired deadlines generated no HTTP request.

The governed path rechecks execution cancellation after committing its shared cost hold and immediately before invoking the adapter. If cancellation is already recorded, it settles the unused hold to zero. Cancellation during an in-flight call cannot erase the call or its potential charge. The response is accounted for; the next worker step sees cancellation and prevents the artifact proposal. The integration fixture paused the adapter, cancelled through the owner API, then resumed: the workflow ended `cancelled`, the calculated cost was settled once, and there was no approval or artifact version.

The DBOS workflow version is `call-limits-v1`. In-flight workflow upgrades still need a drain or migration plan. This validation does not prove transport interruption at the deadline, provider billing accuracy, or cancellation of a call already accepted by an external service. Native adapters remain unregistered.

## Reproduce

```sh
PYTHONPATH=backend/src APP_DATABASE_URL=postgresql+psycopg://postgres:<test-password>@127.0.0.1:55433/workforce_test INITIAL_ADMIN_PASSWORD_FILE=<synthetic-secret-file> SESSION_COOKIE_SECURE=false pytest -q backend/tests
```

See `backend/tests/test_governed_calls.py` and `backend/tests/test_native_providers.py` for the controlled call and HTTP fixtures.

Result: **27 passed** across PostgreSQL/DBOS and offline SDK tests. The backend image built, the local Compose API/worker restarted, and `python scripts/smoke.py` passed (unauthorized dispatch 403, execution succeeded, task review, audit present).
