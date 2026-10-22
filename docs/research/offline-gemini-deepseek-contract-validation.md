# Pure Gemini/DeepSeek text preparation contracts

Date: 2026-10-22. Branch: `preparation-gemini-deepseek-text-contracts`. Parent: draft [#155](https://github.com/Kokfu/congenial-potato/pull/155), `1df4975d7f684003e38f82977756da6ff996f43b`.

## Scope and official references

Pure functions construct bounded JSON bodies and inspect supplied JSON responses for the selected `gemini-3.8-flash` and `deepseek-flash` preparation targets. There is no HTTP/SDK client, endpoint dispatch, credential reader, discovery method, adapter class or registry entry. Product workers do not import this module. `OfflineTextResult` is distinct from `GenerationResponse` and always has `billing_ready: false`; it cannot be treated as validated settlement evidence.

Shape references reviewed on 2026-10-22: Google's [generateContent API and usage metadata](https://ai.google.dev/api/generate-content), [Gemini 3.8 Flash](https://ai.google.dev/gemini-api/docs/models/gemini-3.8-flash), DeepSeek's [Chat Completions API](https://api-docs.deepseek.com/api/create-chat-completion/) and [thinking-mode controls](https://api-docs.deepseek.com/guides/thinking_mode/). Public documentation reads did not invoke these APIs.

Requests permit only selected IDs, text roles, at most 1,024 requested output tokens and an 8,192-byte serialized body. Tool/structured-output flags, tool messages, non-human system instructions, expired/naive deadlines and synthetic document metadata are rejected. User source text remains data. Gemini preserves leading system parts and rejects later system messages rather than reordering them; it requests one candidate with low thinking. DeepSeek preserves message order, requests non-streaming text and explicitly disables thinking. These preparation bounds are not enforced provider billing limits.

Parsers require one completed text candidate and a recorded request/model identity. They reject unsupported tools, non-text/thinking parts, unrequested DeepSeek reasoning, Gemini grounding/tool-use usage or blocked output. Counter types must be nonnegative integers (booleans are rejected), cache counts cannot exceed input and supplied complete totals must agree. Gemini output includes candidate plus thinking tokens when both are supplied; missing thinking usage leaves output unknown. Missing usage remains unknown, with no fabricated zero/cost. Actual model versions are retained rather than rewritten into requested aliases.

## Actual checks

- `/workspace/witness-postgres-venv/bin/python /tmp/check-offline-contracts.py`: **75 tests passed in 9.78s**: 49 new pure contract cases and 26 existing native SDK cases. The shared backend fixture initializes PostgreSQL per test even though the new functions perform no I/O.
- Coverage includes hostile source remaining a user part, selected-model/body/deadline/capability boundaries, unsupported system/tool authority, role ordering, complete/unknown usage, thinking counts, actual version retention, malformed identities/types/totals/cache counts, unfinished/multiple/blocked candidates, non-text/effect metadata and continued registry denial for both providers. Errors are generic rather than echoing malformed payload data.
- The runner used a uniquely owned internal network and tmpfs PostgreSQL instance, with no published port/host data mount. Backfill, empty-table round trip and metadata drift preflight passed; cleanup removed only its own resources. There is no new schema.
- Two changed Python files compiled. Markdown targets and staged whitespace checked before commit. A prior 68-case pass preceded seven additional authority/thinking/effect-denial cases; counts are not combined.
- Browser/build/egress repeats were not required: no reachable application route, worker integration, network configuration or registered provider changed.

## Limits and next host checkpoint

No real provider response, account/model availability, delivery, charge, reasoning quality, cancellation, credential encryption or secret broker was validated. This narrow parser can intentionally reject otherwise legitimate richer responses. It is not a general provider schema, complete accounting contract, prompt-injection guarantee or live-capability declaration. Custom/unknown usage categories and current price truth still require separate review before any settlement integration.

Before owner-host credential work, obtain non-secret output from `py scripts/local_workspace.py doctor` on the owner's Windows Docker Desktop machine. This managed cloud session cannot reach that PC or verify its mounts, ACLs/key store, Linux-container isolation or free-port behavior. A fixture pass cannot replace that evidence. If no checkout exists, use the [Windows setup guide](../local-workspace-guide.md); never send generated password files or real API keys. The pending host check does not authorize paid/live registration, external effects, production connections, deployment or merging.

The owner subsequently confirmed permission to execute on the PC. Connection discovery still found only the managed Linux shell; `codex_app.read_thread_terminal` returned no attached terminal session. The executor reported Linux/x86_64, no Windows mount and no PowerShell executable. Authorization is present; a local-PC execution connection is missing. Attach a local session/checkout or provide non-secret doctor output; no further hosting permission is being requested.
