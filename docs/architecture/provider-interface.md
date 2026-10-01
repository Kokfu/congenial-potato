# Provider interface

Status: approved architecture direction; selected integrations require validation.

## Design

Agent binds to a provider connection and model identifier. Connection owns endpoint and secret reference. Core orchestration never branches on vendor names.

Application owns a narrow contract. Adapters can reuse official SDKs, Pydantic AI or optional normalization libraries.

| Operation | Contract |
|---|---|
| discoverModels | Cached/refreshable enumeration when supported |
| describeCapabilities | Modalities, tools, structured output, limits, usage support |
| generate | Normalized complete request/response |
| stream | Normalized events plus authoritative final response |
| estimateUsage | Conservative token/cost bound with uncertainty |
| cancel | Best-effort cancellation |
| health | Redacted diagnostics |

Embeddings and asynchronous media have separate contracts. Video generation is not forced into chat semantics.

## Data

Request: execution/request IDs, model/capabilities, ordered content blocks, tool schemas, response schema, output limits, deadline/sampling, secret reference resolved outside model-visible content.

Response: content, proposed tool calls, finish reason, usage including cached/reasoning where reported, provider request ID, actual model, optional retained raw-response reference. Unknown values stay unknown.

Preserve opaque continuation/signature blocks when required; do not turn them into ordinary text.

## Catalog

Use discovery/cache plus operator-entered IDs where enumeration is unavailable. Record origin, observed time and validation. No static required model list.

Probe unknown models. Listing does not prove reliable tool calling. Unsupported capability causes a clear error, not silent degradation.

## Adapters

MVP: OpenAI and Anthropic native formats. Next: compatible/local endpoints, then Google without orchestration changes.

OpenAI-compatible endpoints need probes; compatibility is not identical behavior.

Seedance/Ark-related media later supports submit/status/cancel where available/collect. Verify official access, region, pricing and job semantics.

## Switching/fallback

Identity/project memory survive switching. Provider-specific state may not; create a new attempt from canonical context/summary with provenance.

Fallback is explicit, capability-compatible, budgeted and bound by data-location/destination policy. No silent reroute of private data.

## Errors/costs

Normalize auth, unavailable model, rate limit, timeout, transient server failure, invalid request, capability mismatch, malformed response and cancellation.

Bound retries with provider advice and jitter. No automatic retry for auth or capability failures.

Version pricing observations. Separate estimate/reported/reconciled costs. Unknown usage is not zero; uncertain outcomes may cause duplicate charges.

Fixture contract tests are primary; live smoke checks are opt-in and capped.
