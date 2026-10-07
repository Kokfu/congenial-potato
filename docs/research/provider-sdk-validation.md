# Native provider SDK offline validation

Date: 2026-10-07. Scope: Python SDK API and response-shape verification through in-memory HTTP fixtures. No provider endpoint was contacted and no paid model call was made.

## Environment and versions

- Python 3.12; OpenAI SDK `openai==3.26.0` (installed package license expression Apache-2.0).
- Anthropic SDK `anthropic==1.11.0` (installed package license expression MIT).
- Both SDKs use `httpx2==2.13.1` in this lock (BSD-3-Clause). All direct and transitive versions are pinned in `backend/requirements.lock` and `backend/requirements-dev.lock`.
- Versions were selected from `python -m pip index versions openai` and `python -m pip index versions anthropic` on the date above, then checked with `importlib.metadata.version` and `License-Expression` from the installed wheels. These observations are for the tested releases; they do not establish future API compatibility.

## APIs exercised

| SDK | Tested call | Observed mapping |
|---|---|---|
| OpenAI 3.26.0 | `OpenAI(..., max_retries=0).models.list()` | `model.id` enumerates IDs. Listing does not validate capabilities. |
| OpenAI 3.26.0 | `client.responses.create(model=..., input=..., max_output_tokens=..., store=False)` | `output_text`, `model`, `id`, `status`, optional `usage.input_tokens` / `usage.output_tokens`. |
| Anthropic 1.11.0 | `Anthropic(..., max_retries=0).models.list()` | `model.id` enumerates IDs. Listing does not validate capabilities. |
| Anthropic 1.11.0 | `client.messages.create(model=..., messages=..., system=..., max_tokens=...)` | Text content blocks, `model`, `id`, `stop_reason`, input/output usage. |

The SDK constructors accept an injected `httpx2.Client`; tests used `httpx2.MockTransport` and synthetic JSON responses. The adapters normalize generic authentication and rate-limit failures without exposing the raw provider error. A generated response keeps reported usage when present; unreported money cost remains `null`.

## Reproduction

```sh
cd backend
UV_CACHE_DIR=/tmp/workforce-uv-cache uv pip compile requirements.in --python-version 3.12 -o requirements.lock
UV_CACHE_DIR=/tmp/workforce-uv-cache uv pip compile requirements-dev.in --python-version 3.12 -o requirements-dev.lock
cd ..
PYTHONPATH=backend/src APP_DATABASE_URL=postgresql+psycopg://<disposable-test-db>/workforce_test INITIAL_ADMIN_PASSWORD_FILE=<synthetic-secret-file> SESSION_COOKIE_SECURE=false pytest -q backend/tests
docker build -f docker/backend.Dockerfile -t workforce-backend:native-offline .
```

On the managed cloud environment, the Docker build additionally mounted the local proxy CA as a build secret. The backend image built, and a container import check reported `openai=3.26.0` and `anthropic=1.11.0`. The full PostgreSQL and offline SDK suite passed: **17 tests**.

## Current limits

- Native adapters are **not registered** in the worker or API. Agent selection still exposes only fake fixtures. This prevents live calls while cost bounds and activation policy remain incomplete.
- A provider model listing creates a catalog entry with unknown capabilities. Generation requires an operator-validated capability manifest for the exact model ID. No permanent model ID list is embedded.
- Adapters currently support complete text generation only. Tool calling, structured output and native streaming fail with a capability error. Embeddings and asynchronous media require separate interfaces.
- Credential input is an absolute private file reference, resolved into the SDK client outside prompts and artifacts. No real credential was used in tests. The existing budget reservation is a fixture amount and is not an enforceable live cost cap; native registration must wait for cost upper-bound and uncertain-outcome handling.
- Pagination, opaque continuation blocks, usage discrepancies, SDK behavior across later releases, and a real provider response remain unvalidated.
