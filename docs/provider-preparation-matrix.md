# Four-provider preparation matrix

Date: 2026-10-22. Owner selection: Claude, ChatGPT, Gemini and DeepSeek. This inventories local code and missing work. The owner authorized model selection; [selected targets and official price observations](selected-models.md) now record initial IDs. This is not an executable provider capability or price catalog.

| Requested family | API identity to prepare | Current local implementation | Remaining provider-specific evidence |
| --- | --- | --- | --- |
| Claude | Anthropic; `claude-sonnet-5-5` preparation target | Unregistered text Messages SDK adapter with injected-transport contract and worker tests. | Current model/capability validation, all billable cache/thinking categories, protected credential reference and source/plan/structured-output contract. |
| ChatGPT | OpenAI API; `gpt-6-luna` preparation target | Unregistered text Responses SDK adapter with injected-transport contract and worker tests. | Current model/capability validation, complete cached/reasoning usage coverage, protected credential reference and source/plan/structured-output contract. ChatGPT product access/subscription does not establish API access or credit. |
| Gemini | Google Gemini API; `gemini-3.8-flash` preparation target | Pure bounded JSON text contract only; no native adapter or registered connection. | A narrow pure text request/response contract has [offline evidence](research/offline-gemini-deepseek-contract-validation.md); client/authentication, error transport and project/location requirements remain unimplemented. Validate thinking/cache billing and cancellation semantics for that exact API/model. |
| DeepSeek | DeepSeek API; `deepseek-flash` preparation target | Pure bounded JSON text contract only; no native adapter or registered connection. | A narrow pure text request/response contract has [offline evidence](research/offline-gemini-deepseek-contract-validation.md); transport/authentication, validated capabilities and callable integration remain unimplemented. Do not assume compatibility with the existing OpenAI Responses adapter; matching SDK conventions do not establish matching endpoints, cache/reasoning billing or cancellation behavior. |

## Common requirements

All four require the [protected-model readiness sequence](live-model-readiness-plan.md): encryption/key custody outside replaceable application state, immutable scoped references, current independently checked official prices, conservative token/cost bounds, local caps, cancellation and unknown-charge reconciliation. Native streaming, tools and structured output are not validated by the two text adapters. The existing source-bound document path explicitly allows only fixture connections; it cannot become a native workflow by changing a dropdown.

Existing native adapters force SDK automatic retries to zero at each generation/catalog call, including injected clients. Their `cancel()` returns false; local cancellation is not provider cancellation. A durable governed call treats post-dispatch exceptions as unknown and does not resend on replay. In-memory tests establish behavior only for the tested SDK/transport path; they do not prove one provider charge, acceptance, cancellation, billing or network delivery. Client-supplied transport/proxy retries are not governed by an SDK retry override.

Initial IDs and standard-price observations are recorded in the linked selection evidence, following the owner's request to choose them. They are disabled preparation targets, not runtime enrollment or complete billing validation. Do not provide real credentials in chat. No provider request, production binding, new egress access or paid execution is introduced by this matrix.

The Windows launcher/guide remain usable for fixtures. Actual Windows Docker Desktop startup and host key protection require owner-host evidence; this cloud workspace has no PC connection. Keep local fixture acceptance distinct from that infrastructure validation.
