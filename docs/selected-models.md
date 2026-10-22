# Initial API model choices — disabled preparation

Observed: 2026-10-22. The owner asked the implementer to choose initial models from official documentation. These are preparation targets, not registered connections, approved prices, account availability checks or live activation. Selection favors a manageable text workflow and cost-aware comparisons; no project-specific quality evaluation has been run.

| Family | Selected API ID | Reason for starting here | Official evidence |
| --- | --- | --- | --- |
| Claude | `claude-sonnet-5-5` | General drafting/planning comparison with a current Sonnet model. | [Model/ID](https://platform.claude.com/docs/en/models/sonnet-5-5/overview), [pricing](https://platform.claude.com/docs/en/about-claude/pricing) |
| OpenAI / ChatGPT | `gpt-6-luna` | Cost-sensitive first text comparison; use the Responses API. ChatGPT is not the API model ID. | [Model, API and pricing](https://developers.openai.com/api/docs/models/gpt-6-luna) |
| Gemini | `gemini-3.8-flash` | Stable Flash text target rather than a preview or Live/audio endpoint. | [Model/ID](https://ai.google.dev/gemini-api/docs/models/gemini-3.8-flash), [pricing](https://ai.google.dev/gemini-api/docs/pricing) |
| DeepSeek | `deepseek-flash` | Official current Flash API name for a cost-aware comparison. | [API name](https://api-docs.deepseek.com/quick_start/pricing), [pricing and current backing model](https://api-docs.deepseek.com/quick_start/pricing/) |

## Observed price notes

USD per one million text tokens, standard direct-provider service only. These are observations, not executable price envelopes. Recheck before any trial; discounts, regional modes, tools and long-context tiers are not interchangeable.

| Selected model | Base input | Cached read | Cache write | Output | Important boundary |
| --- | --- | --- | --- | --- | --- |
| Sonnet 5.5 | 2.00 | 0.10 | 2.50 / 5 minutes; 4.00 / 1 hour | 10.00 | Adaptive thinking defaults on; the current text-only adapter rejects non-text blocks. US-only inference adds a multiplier. |
| GPT-6 Luna | 0.10 | 0.01 | 0.125 | 0.50 | Above 272K input tokens, input/cache rates double and output becomes 1.5x for the full request. Regional and fast processing add premiums. |
| Gemini 3.8 Flash | 0.75 | 0.075 | Separate explicit-cache storage: 0.50 per million tokens/hour | 3.75, including thinking | Introductory rates through 2026-12-31; documented input/output/cache/storage rates double on 2027-01-01. Free tier is not selected as a spending assumption. |
| DeepSeek Flash, peak | 0.30 cache miss | 0.006 | Not separately established here | 1.20 | Off-peak input/cache/output: 0.15 / 0.003 / 0.60. Bound future holds using peak prices, not a local scheduling guess. |

DeepSeek documents weekday peak windows with Chinese public-holiday exceptions. No holiday calendar or provider billing clock was validated. `deepseek-flash` is currently served by `DeepSeek-V4.1-Flash-1017`; it is not an immutable snapshot guarantee. Retired Flash aliases must not silently become additional approved models. The trailing-slash pricing URL returns the actual pricing table; the non-slash route returned the introductory API page during this review. No mirror/third-party pricing source was used.

## What still blocks live use

The [preparation manifest](model-preparation.json) records disabled targets only. The [provider matrix](provider-preparation-matrix.md) records implementation gaps: OpenAI/Anthropic text adapters are offline and unregistered; Gemini/DeepSeek adapters remain absent. Provider-advertised structured output/tools/streaming do not grant those capabilities to this application. Existing document fixture admission still rejects native connections.

The current `PriceEnvelope` has only two flat rates. It cannot accurately settle all cache-write, reasoning, time/tier, storage and tool categories from these observations. Do not paste these rows into agent configuration or mark them independently attested billing evidence. Protected credentials/key custody, current complete accounting, source/plan integration, cancellation/unknown-charge handling, account/model availability and a separately authorized capped trial remain prerequisites. No credential, network grant, model registration or paid request was created.

Price-envelope observation validity and recorded-outcome recovery now have [focused evidence](research/price-observation-window-validation.md). Next offline task: pure Gemini/DeepSeek text contracts, then complete category-aware accounting before callable adapter integration. Actual Windows hosting/key protection still requires owner-host evidence.
