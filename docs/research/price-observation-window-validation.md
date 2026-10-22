# Price observation validity and recorded-outcome recovery

Date: 2026-10-22. Branch: `reliability-price-observation-window`. Parent: draft [#154](https://github.com/Kokfu/congenial-potato/pull/154), `c0a9b3d0455ef5bbbe7d7e5576062939ec55fce7`.

## Change

The flat synthetic price envelope previously checked expiry alone. A future observation or timezone-free observation could still admit a new priced call. `upper_bound()` now requires aware timestamps, observation strictly before expiry and observation no later than the current UTC instant. The owner configuration API returns a generic invalid-window/upper-price error without adding a config revision.

New-call validation remains before a cost hold or generation. Recorded ModelCall recovery and existing calling/unknown holds are resolved before new-call expiry validation: expiry blocks a new dispatch but does not erase recorded outcomes or obstruct unknown-charge replay. Historical settlement still uses pinned rates even if a request finishes after expiry. Offset-aware timestamps are compared as instants.

## Actual checks

- `/workspace/witness-postgres-venv/bin/python /tmp/check-price-window.py`: **32 tests passed in 22.36s** across shared budgets, scheduled/delegated daily budgets, governed calls and offline native worker integration. Fourteen cases were added: five invalid timestamp shapes at the envelope boundary, valid offset/historical settlement, five API rejections without revision creation, future pinned-price rejection before hold/provider and two expired-price settled/unknown recovery cases with one generation total.
- The ownership-scoped disposable PostgreSQL runner also checked objective backfill, empty-table migration round trip and metadata drift. It used an internal network and tmpfs, no published ports/host data mounts, and removed only its own resources. No schema changes were introduced.
- Six changed Python files compiled. Markdown targets and staged whitespace checked before commit. No browser/image/egress repeat was required for this price-boundary change; previous fixture checkpoint evidence remains separate.
- The initial focused run passed ten cases then reached a scheduled-budget test with a hardcoded workflow database port. That test now uses the configured workflow database, matching the earlier isolated-test corrections. An intermediate 30-case pass preceded the two new recorded-outcome recovery cases; counts are not combined.

## Limits and next increment

These checks validate temporal consistency, not independent pricing truth or freshness policy. Owner-declared expiry remains owner-declared; no maximum observation age or provider price feed is established. The flat two-rate envelope still cannot represent all selected providers' cache/thinking/tier/storage/tool categories. Recorded recovery retains existing request/model/capability checks and does not authorize arbitrary resends.

All provider transports in the native worker cases were in memory. No real credential, provider request, production connection, egress grant, live registration, deployment or merge occurred. Next: pure offline Gemini/DeepSeek text request/response contracts with explicit usage uncertainty, before any callable adapters or live accounting integration. Protected key custody and actual Windows hosting remain unverified.
