# Shared cost ledger fixture validation

Date: 2026-10-07. All values are synthetic USD amounts; no provider charge or production integration was used.

## Contract

`PriceEnvelope` records an operator source, observed/expiry time, exact provider/model ID, validated input/output token maxima and conservative USD prices per million tokens. An expired or zero-cost envelope cannot produce an upper bound. Provider model listings alone do not create an envelope.

The PostgreSQL ledger has a root account, one UTC daily account per day, and an idempotent invocation hold. Reservations lock the daily account before the root account. A duplicate key cannot reserve again. A model outcome with unknown charge keeps both holds reserved until reconciliation. A confirmed amount moves the hold to spent in both accounts. An amount above its hold is recorded as an overrun; later reservations fail against the resulting spent balance. This records an external overrun rather than implying that the cap retroactively prevented it.

The new ledger is separate from the existing fixture worker budget path. No native adapter is registered, and the ledger does not yet permit live calls.

## Reproduction and observations

```sh
cd backend
APP_DATABASE_URL=postgresql+psycopg://<disposable-test-db>/workforce_test alembic -c alembic.ini upgrade head
cd ..
PYTHONPATH=backend/src APP_DATABASE_URL=postgresql+psycopg://<disposable-test-db>/workforce_test INITIAL_ADMIN_PASSWORD_FILE=<synthetic-secret-file> SESSION_COOKIE_SECURE=false pytest -q backend/tests
docker build -f docker/backend.Dockerfile -t workforce-backend:phase1 .
docker compose up -d --no-build --force-recreate migrate api worker
python scripts/smoke.py
```

The full suite passed **21 tests**. PostgreSQL concurrency fixtures proved one of two roots could reserve `0.700000` against a `1.000000` daily cap; two requests with one invocation key produced one hold. Unknown settlement retained `0.700000` reserved until a reported `0.500000` charge was reconciled. A synthetic `1.200000` charge against a `0.700000` hold was marked `settled_overrun` and blocked another reservation. Compose migration reached `c391e5bc912a`; API, database and web were healthy, and the fixture dispatch smoke test passed. In the managed environment, Docker build used the session proxy CA build secret.

## Remaining gate

The worker still uses a fixture hold of `0.010000` and releases it after a free synthetic result. Before a native adapter is registered, the worker must use a validated and unexpired price envelope, reserve both root and daily upper bounds, enforce a bounded request deadline and token limits, then settle or hold the result according to reported usage and outcome certainty. Provider pricing, cached/reasoning token categories and uncertain charges need an explicit conservative policy. There is no live cost proof and no paid smoke result.
