# Four-provider preparation matrix

Date: 2026-10-22. Owner selection: Claude, ChatGPT, Gemini and DeepSeek. This inventories local code and missing work; it is not a verified current provider capability or price catalog.

| Requested family | API identity to prepare | Current local implementation | Remaining provider-specific evidence |
| --- | --- | --- | --- |
| Claude | Anthropic; exact API model ID pending | Unregistered text Messages SDK adapter with injected-transport contract and worker tests. | Current model/capability validation, all billable cache/thinking categories, protected credential reference and source/plan/structured-output contract. |
| ChatGPT | OpenAI API; exact model ID pending | Unregistered text Responses SDK adapter with injected-transport contract and worker tests. | Current model/capability validation, complete cached/reasoning usage coverage, protected credential reference and source/plan/structured-output contract. ChatGPT product access/subscription does not establish API access or credit. |
| Gemini | Google Gemini API; exact model ID pending | No native adapter or registered connection. | Review the selected API/SDK, authentication and any project/location requirements; implement offline request/response/error/usage contracts before claiming support. Validate thinking/cache billing and cancellation semantics for that exact API/model. |
| DeepSeek | DeepSeek API; exact model ID pending | No native adapter or registered connection. | Review the selected API; implement offline request/response/error/usage contracts and validated capabilities. Do not assume compatibility with the existing OpenAI Responses adapter; matching SDK conventions do not establish matching endpoints, cache/reasoning billing or cancellation behavior. |

## Common requirements

All four require the [protected-model readiness sequence](live-model-readiness-plan.md): encryption/key custody outside replaceable application state, immutable scoped references, current independently checked official prices, conservative token/cost bounds, local caps, cancellation and unknown-charge reconciliation. Native streaming, tools and structured output are not validated by the two text adapters. The existing source-bound document path explicitly allows only fixture connections; it cannot become a native workflow by changing a dropdown.

Existing native adapters force SDK automatic retries to zero at each generation/catalog call, including injected clients. Their `cancel()` returns false; local cancellation is not provider cancellation. A durable governed call treats post-dispatch exceptions as unknown and does not resend on replay. In-memory tests establish behavior only for the tested SDK/transport path; they do not prove one provider charge, acceptance, cancellation, billing or network delivery. Client-supplied transport/proxy retries are not governed by an SDK retry override.

Before model-specific price/capability preparation, confirm exact API model IDs or ask the implementer to propose initial IDs from current official documentation. Do not provide real credentials in chat. No exact ID, numerical price, provider request, production binding, new egress access or paid execution is introduced by this matrix.

The Windows launcher/guide remain usable for fixtures. Actual Windows Docker Desktop startup and host key protection require owner-host evidence; this cloud workspace has no PC connection. Keep local fixture acceptance distinct from that infrastructure validation.
