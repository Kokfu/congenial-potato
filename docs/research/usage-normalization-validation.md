# Native usage normalization and uncertain response cost

Date: 2026-10-08. This validation used pinned OpenAI Python `3.26.0`, Anthropic Python `1.11.0`, in-memory HTTP fixtures, fake providers and disposable PostgreSQL/DBOS databases. No provider endpoint or paid call was used.

## Observed SDK contracts

The installed OpenAI `ResponseUsage` has inclusive `input_tokens` and `output_tokens`, with input details for cached/cache-write tokens and output details for reasoning tokens. These details are recorded for provenance and **not added again** to the inclusive totals.

The installed Anthropic `Message` type explicitly states that total input is the sum of `input_tokens`, `cache_creation_input_tokens` and `cache_read_input_tokens`. The adapter now reports that sum as normalized `Usage.input_tokens` and preserves cache and thinking breakdowns. Anthropic `output_tokens` remains its inclusive output total. Offline mock responses exercised nonzero cache and reasoning fields: OpenAI input/output totals remained `4/2` with `1/1/1` cached/cache-write/reasoning details; Anthropic normalized input/output became `9/2` from `4+2+3` input classes, with one thinking token.

The cost ledger uses normalized inclusive totals with operator supplied price ceilings. Those ceilings must cover the highest applicable rate across token classes; this was **not** verified against a live price sheet or invoice. Unexpected service tiers, server tools, model changes and missing usage still need conservative policy before native activation.

## Post-dispatch errors

Any adapter `ProviderError` after the priced call has been admitted now keeps the root/daily hold as `unknown`. Even an authentication, rejection or malformed-response error does not prove the service did not process or bill the request. The normalized error kind is retained in the audit detail. A fake malformed response test observed an unknown execution, both holds reserved and no model result; it did not retry the call.

## Reproduce

```sh
PYTHONPATH=backend/src APP_DATABASE_URL=postgresql+psycopg://postgres:<test-password>@127.0.0.1:55433/workforce_test INITIAL_ADMIN_PASSWORD_FILE=<synthetic-secret-file> SESSION_COOKIE_SECURE=false pytest -q backend/tests
docker build -f docker/backend.Dockerfile -t workforce-backend:phase1 .
```

The managed cloud build supplies its session proxy CA as a BuildKit secret. Workflow code version is `usage-normalization-v1`; in-flight code upgrades still require a drain or migration plan. Native adapters remain unregistered.

Result: **32 backend tests passed**. The non-root backend image built, the local Compose API/worker restarted, and `python scripts/smoke.py` passed (unauthorized dispatch 403, synthetic execution succeeded, task review and audit present).
