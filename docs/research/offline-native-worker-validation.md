# Offline native SDK worker validation

Date: 2026-10-08. This is an **offline test injection**, not native activation. The application registry still starts with fake fixtures only. No real provider endpoint, production credential or paid model call was used.

## Environment and pinned APIs

- Python 3.12; `openai==3.26.0` (installed Apache-2.0 license expression), `anthropic==1.11.0` (installed MIT license and classifier), and `httpx2==2.13.1` (installed BSD-3-Clause license expression).
- The tests inject an `openai.OpenAI` or `anthropic.Anthropic` client with `httpx2.MockTransport`. The in-memory handler accepts only the expected `/v1/responses` or `/v1/messages` path and records request bodies. SDK retries are set to zero.
- API, provider config, governed call and worker resolve one application-owned registry module. The test replaces that registry only for its own process; production startup remains fixture-only.

## Reproduce

With disposable PostgreSQL `workforce_test` and `workforce_dbos_test` databases and a synthetic owner secret:

```sh
PYTHONPATH=backend/src APP_DATABASE_URL=postgresql+psycopg://postgres:<test-password>@127.0.0.1:55433/workforce_test INITIAL_ADMIN_PASSWORD_FILE=<synthetic-secret-file> SESSION_COOKIE_SECURE=false pytest -q backend/tests/test_offline_native_worker.py
PYTHONPATH=backend/src APP_DATABASE_URL=postgresql+psycopg://postgres:<test-password>@127.0.0.1:55433/workforce_test INITIAL_ADMIN_PASSWORD_FILE=<synthetic-secret-file> SESSION_COOKIE_SECURE=false pytest -q backend/tests
```

Each case creates the agent through the owner API, pins a second priced config revision, grants project execution, dispatches a task and runs the DBOS worker. OpenAI and Anthropic mock responses each produced one HTTP request and one persisted model call. Replay of the delivered outbox item produced no second HTTP request or model call. Both root and UTC daily accounts moved one calculated charge from reserved to spent; one artifact approval was proposed. The Anthropic result used `4 + 2 + 3 = 9` normalized input tokens, while OpenAI retained its inclusive input count of `4` with cache details.

A third OpenAI mock response returned `completed` with no text. The SDK adapter raised a malformed-response error. The workflow ended `unknown`, one HTTP request was observed, root/daily holds stayed reserved, no model call or artifact approval was created, and replay made no second request. The normalized error kind was retained in the audit record.

## Remaining activation gate

The mock model ID and prices are synthetic; no live catalog, current price class, invoice or provider charge was verified. The worker has no configured native registry, and encrypted credential storage and independent charge reconciliation remain unfinished. A workflow-code upgrade from older `application_version` values still needs a drain or migration procedure. Keep native execution disabled and paid tests out of this validation.

Result: **35 backend tests passed**. The non-root backend image built, the local Compose API/worker restarted, and `python scripts/smoke.py` passed with unauthorized dispatch denied, a successful fake execution, task review and an audit record. The three offline native integration cases each observed one in-memory HTTP request across dispatch and replay; none contacted a provider endpoint.
