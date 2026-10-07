# Owner price envelope configuration validation

Date: 2026-10-07. Synthetic fixtures only; native adapters remain unregistered.

An authenticated owner can submit a `price_envelope` while creating a new immutable agent config revision with `PUT /api/agents/{id}/config`. The API checks the expected version, selected registered connection/model, exact envelope connection/model, validated capability bounds, a minimum 128 output tokens for the current worker request, a fresh positive upper price and a configured daily cap at least as large as that upper bound. The read API exposes the envelope with its version. Omitting it in a later revision clears priced mode. The envelope contains no credential.

The Compose backend environment now passes `DAILY_CAP_USD` to both API and worker with a disabled default of zero, plus `MODEL_CALL_TIMEOUT_SECONDS` (default 20). Set a positive daily cap deliberately for synthetic priced fixtures. No native provider is selectable through the registry, so this API cannot authorize a paid call.

The governed call integration tests now configure pricing through the owner API rather than directly changing the config row. They verify version history and reject missing cap, mismatched model, expired envelope and stale config revision. Operator price sources remain self-declared; there is no automatic live price verification. Native activation still requires credential policy, accurate token/charge coverage and controlled end-to-end tests before opt-in.

Result: **28 backend tests passed**. The non-root backend image built, Compose API/worker restarted, and `python scripts/smoke.py` passed. `docker compose config` showed identical disabled defaults on API and worker: daily cap `0`, timeout `20` seconds.

Reproduce with disposable `workforce_test` and `workforce_dbos_test` PostgreSQL databases and a synthetic owner secret:

```sh
PYTHONPATH=backend/src APP_DATABASE_URL=postgresql+psycopg://postgres:<test-password>@127.0.0.1:55433/workforce_test INITIAL_ADMIN_PASSWORD_FILE=<synthetic-secret-file> SESSION_COOKIE_SECURE=false pytest -q backend/tests
docker build -f docker/backend.Dockerfile -t workforce-backend:phase1 .
docker compose up -d --no-build --force-recreate api worker
docker compose config
python scripts/smoke.py
```
