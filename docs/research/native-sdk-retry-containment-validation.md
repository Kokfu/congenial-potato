# Native SDK automatic retry containment

Date: 2026-10-22. Branch: `reliability-native-sdk-retry-containment`. Parent: draft [#152](https://github.com/Kokfu/congenial-potato/pull/152), `f2cf74f04e2ee6e37de1ff7571baa3a44ae9ee7e`.

## Problem and change

The unregistered OpenAI/Anthropic text adapters constructed their own clients with zero retries, but accepted injected clients with arbitrary SDK retry defaults. Generation without a deadline reused those defaults; generation with a deadline copied the timeout while preserving retry settings. A rate limit, service failure or lost response could therefore trigger multiple hidden SDK transport requests below one governed cost hold.

Both generation paths now copy the client with `max_retries=0`, retaining the explicit remaining deadline when provided. Catalog requests apply the same override. The caller's original client is not mutated. Existing error normalization remains generic, and the registry still contains fixtures only. No Gemini or DeepSeek adapter is implemented by this change.

## Actual checks

- `/workspace/witness-postgres-venv/bin/python /tmp/check-native-retries.py` ran against a uniquely owned disposable internal-network/tmpfs PostgreSQL instance with no published port or host data mount. **39 tests passed in 18.95s**: 26 native SDK cases, 8 governed-call cases and 5 actual API/DBOS-worker cases with in-memory provider transports. Cleanup removed only that instance/network.
- Eighteen new adapter cases use injected clients configured for two SDK retries. Sixteen generation cases cover OpenAI/Anthropic, deadline/no deadline, rate limit/service failure/read timeout/connection error. Every case observes exactly one intercepted transport request, unchanged original client retry settings and redacted errors. Two catalog service-failure cases also observe one request.
- Two new worker cases inject OpenAI/Anthropic service failures with SDK retries enabled on the supplied client. Actual API configuration/dispatch and DBOS replay produce one intercepted request, unknown execution/hold status, retained root/daily reservations, no ModelCall or approval and no extra dispatch on replay. Synthetic SDK successes/malformed output and existing budget/reconciliation/cancellation cases also passed.
- The isolated first runs passed 27 cases before an older governed test tried hardcoded localhost port 55433. Both affected test modules now use `get_settings().workflow_url`, so isolated runs use their disposable database instead of depending on another test's earlier global DBOS configuration. The final count supersedes those failures.
- Existing-objective backfill, empty-table downgrade/upgrade and `alembic check` passed as runner preflight. No model/schema changes are introduced. Four changed Python files compiled; Markdown targets and staged whitespace checked before commit.

## Limits and next decision

Every SDK request was intercepted in memory; no real credential or provider endpoint was used. Zero SDK retries does not control an injected transport/proxy's own retry behavior, prove one provider charge, or establish cancellation. Post-dispatch uncertainty retains the governed hold. The adapters' cancellation remains unsupported. Browser/application deployment and egress checks were not repeated for this unregistered-module change; the preceding fixture checkpoint records its separate browser/build/egress results.

The [four-provider matrix](../provider-preparation-matrix.md) inventories Claude, OpenAI/ChatGPT, Gemini and DeepSeek. Exact API model IDs remain unspecified; an owner question asks whether to propose initial models from current official documentation or use owner-provided IDs. That decision is needed before model-specific capability/pricing work. Protected key custody and actual Windows hosting also remain unverified. Paid calls, live registration, product external dispatch, production connections, public deployment and merges remain disabled.
