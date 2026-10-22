# Next checkpoint: protected model preparation

Date: 2026-10-22. This is a preparation plan, not permission to register a native adapter or call a provider. The guided document fixture remains usable locally.

## Decisions needed before provider-specific work

The owner selected Claude (Anthropic), ChatGPT (OpenAI API), Gemini (Google) and DeepSeek. The owner then authorized initial model selection; [chosen API IDs and evidence](selected-models.md) are now recorded. ChatGPT subscriptions do not identify an API model or establish API billing access. Names only: do not send credentials in chat, project notes, agent instructions or a pull request. This determines the supported API/SDK, token accounting, official pricing source, charge ambiguity and cancellation semantics. Provider families and initial preparation IDs are selected; live activation is not.

The owner confirmed Windows with Docker Desktop. Actual host startup and secret protection still need host evidence; this managed Linux workspace cannot inspect Windows ACLs, a host key store, or Desktop mount behavior. A cloud tmpfs/file-mode fixture cannot establish those properties. The [Windows guide](local-workspace-guide.md) provides the existing local launcher and doctor commands, which choose a free loopback port.

## Preparation sequence after selection

| Increment | Existing foundation | Required next evidence |
| --- | --- | --- |
| Credential reference and protection design | Offline unregistered adapters accept descriptor-checked private files; [recorded limits](research/credential-file-validation.md). | Choose a trusted key custodian outside the application database and ciphertext backups. Define key IDs, encryption, rotation/revocation, broker permissions and failure behavior. Validate Windows mount/ACL behavior on the intended host; never infer it from Linux mode bits. No real key is needed for offline design/tests. |
| Provider accounting contract | Owner-configured immutable price envelopes and synthetic governed calls; [recorded limits](research/price-config-validation.md). | Pin exact model/API, official source and verification time; cover all billable input/output/cached/reasoning/tool categories or reject unsupported usage. Fail closed on stale/missing prices and uncertain bounds. Self-declared fixture prices are not independent verification. |
| Failure and cancellation contract | Local reservation, timeout and cancellation paths exist. | Test request-not-sent, response-lost, accepted-but-timed-out, cancellation-after-send and restart/replay with an injected transport. Preserve reservations/unknown-charge state until reconciliation. A local timeout does not establish provider cancellation or zero charge. |
| Disabled integration review | Native adapters remain unregistered; backend egress isolation and zero daily cap remain in place. | Offline integration can verify secret redaction, strict connection/model allowlists, source/context bindings, budget and owner approvals. Do not alter the registry, open egress, add production bindings or enable paid dispatch under this plan. |
| Separately authorized trial | No trial authorized or executed. | Only after the preceding evidence: review an explicit provider/model, protected credential reference, maximum spend, allowed destination, cancellation/reconciliation procedure and exact trial input. Any activation requires separate authorization. Record actual charges/quality; no fixture result substitutes for this trial. |

## Durable stopping point

The [four-provider inventory](provider-preparation-matrix.md) records the existing two offline adapters and pure Gemini/DeepSeek text contracts without callable adapters. Initial IDs were selected from official documentation; complete category-aware pricing, protected credentials and source/plan integration remain incomplete. Production connections, public hosting, merging and paid calls remain outside scope. Local fixture operation needs no live provider. Any future infrastructure request must identify the specific missing key custodian, host access or network authorization and preserve the current clean checkpoint.
