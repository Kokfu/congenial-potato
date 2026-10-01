# Open-source landscape

Research date: 2026-10-01. Status: reviewed and approved as architecture direction; executable validation pending. This is not a security certification.

## Findings

The ecosystem contains four distinct categories:

1. Workforce platforms: persistent identities, tasks, budgets, schedules, and operator interfaces.
2. Agent frameworks and harnesses: model interactions, tools, delegation, and context management.
3. Durable execution engines: queues, waits, retries, schedules, and recovery.
4. Interoperability protocols: tool access and communication across independently deployed agents.

A framework's conversational persistence does not establish durable background execution. Tool approval support does not establish that every execution path passes through that approval mechanism.

Current-source discoveries affect the shortlist:

- AutoGen explicitly declares maintenance mode and directs new projects to Microsoft Agent Framework.
- Flowise's repository is archived.
- Letta directs active development to `letta-ai/letta-code`; its old API server is historical.
- OpenHands' current repository presents Agent Canvas, a developer control center supporting multiple backends.
- Paperclip documents a substantial MCP gateway, including resource policies, exact-argument approvals, and audit events.
- Automatos closely matches the workforce vision, but its execution source supports off, shadow, and partially enforced policy modes.
- The inspected OpenFang approval manager uses in-memory pending requests and bounded in-memory recent history.

## Method and evidence limits

Reviewed repository metadata, READMEs, selected licenses, releases, documentation, and selected implementation files. Broader searches covered persistent agents, AI workforce platforms, operating systems, and durable execution.

Activity dates below are repository `pushed_at` observations. They may include non-default branches and do not prove release quality or security maintenance. For finalists, default-branch commits and release metadata were also checked.

No candidates were installed or benchmarked. Documented features remain unverified behavior. Missing evidence is unknown rather than assumed absence. Revalidate time-sensitive claims and selected release licenses before implementation.

## Candidate architecture, licensing, and activity

| Candidate | Problem and architecture | License observation | Last repository push observed |
|---|---|---|---|
| [Paperclip](https://github.com/paperclipai/paperclip) | Node server, React UI, persistent work management, runtime adapters, governance | MIT | 2026-10-01 |
| [Automatos](https://github.com/AutomatosAI/automatos-ai) | FastAPI/Next.js workforce platform; PostgreSQL, pgvector, Redis, object storage | Apache-2.0 | 2026-09-30 |
| [Agno / AgentOS](https://github.com/agno-agi/agno) | Python agents, teams, workflows, API runtime and management UI | Apache-2.0 | 2026-10-01 |
| [OpenFang](https://github.com/RightNow-AI/openfang) | Rust kernel/runtime; SQLite memory, scheduling, tools, channels | MIT file and Apache license file present; verify package declarations | 2026-07-02 |
| [OpenClaw](https://github.com/openclaw/openclaw) | Persistent assistant gateway with replaceable harnesses, channels and tools | MIT; third-party notices apply | 2026-10-01 |
| [Hermes Agent](https://github.com/NousResearch/hermes-agent) | Python harness, memory, skills, subagents and scheduled work | MIT | 2026-10-01 |
| [Agent Zero](https://github.com/agent0ai/agent-zero) | Docker-oriented general-purpose workspace with browser and desktop | MIT | 2026-09-30 |
| [Letta Code](https://github.com/letta-ai/letta-code) | Stateful identities, memory, skills, subagents, local/server operation | Apache-2.0 | 2026-10-01 |
| [LangGraph](https://github.com/langchain-ai/langgraph) | Stateful graph execution, checkpoints, interrupts and stores | MIT | 2026-10-01 |
| [Deep Agents](https://github.com/langchain-ai/deepagents) | LangGraph-based planning, filesystem, context and subagent harness | MIT | 2026-10-01 |
| [Microsoft Agent Framework](https://github.com/microsoft/agent-framework) | Python/.NET agents, middleware and graph workflows | MIT | 2026-10-01 |
| [AutoGen](https://github.com/microsoft/autogen) | Message-driven agents and team collaboration | MIT code; CC-BY-4.0 documentation | 2026-04-15; maintenance mode |
| [CrewAI](https://github.com/crewAIInc/crewAI) | Role-based crews plus event-driven flows | MIT core; commercial control plane separate | 2026-10-01 |
| [Pydantic AI](https://github.com/pydantic/pydantic-ai) | Typed execution, model adapters, tools and durable-engine integrations | MIT | 2026-10-01 |
| [OpenAI Agents SDK](https://github.com/openai/openai-agents-python) | Agents, handoffs, agents as tools, sessions and approvals | MIT | 2026-10-01 |
| [Claude Agent SDK](https://github.com/anthropics/claude-agent-sdk-python) | Claude Code harness, tools, permissions and subagents | MIT SDK; underlying runtime/service terms separate | 2026-09-30 |
| [Google ADK](https://github.com/google/adk-python) | Model-agnostic agents, graph workflows and structured delegation | Apache-2.0 | 2026-10-01 |
| [OpenHands](https://github.com/OpenHands/OpenHands) | Agent Canvas for coding agents, backends and automations | MIT repository observation; audit selected runtime packages | 2026-10-01 |
| [Dify](https://github.com/langgenius/dify) | Application/workflow platform, agents, retrieval and provider plugins | Modified Apache license with additional conditions | 2026-10-01 |
| [Flowise](https://github.com/FlowiseAI/Flowise) | Visual agent and workflow builder | Apache-2.0 portions; commercial exceptions | 2026-08-13; archived |
| [n8n](https://github.com/n8n-io/n8n) | Integration workflows, triggers and agent-enabled automation | Sustainable Use License; enterprise exceptions | 2026-10-01 |
| [Activepieces](https://github.com/activepieces/activepieces) | TypeScript integration pieces, workflows and MCP exposure | Component-level license review required | 2026-10-01 |

n8n's Sustainable Use License and Dify's modified license are not unrestricted OSI open-source licenses. Personal/internal use can fit current needs while future distribution or SaaS changes require another review.

## Functional comparison

Native means documented within the project; integration means another component supplies it; application means the host must implement it. Findings are source review, not executed acceptance tests.

| Candidate | Providers | Communication/delegation | Memory | Tools/MCP | Scheduling/recovery | Human approval | Browser | Authentication/security |
|---|---|---|---|---|---|---|---|---|
| Paperclip | Runtime adapters; models follow runtime | Persistent tasks/comments and organizational delegation | Shared assets and memory surfaces; evaluate project scope | Plugins and governed MCP gateway | Heartbeats/routines/history; recovery needs tests | Organizational and exact-call gateway approvals | Runtime/integrations | Auth modes, scoped credentials; native-runtime bypass paths need tests |
| Automatos | Broad registry | Auto manager, missions, coordination | Retrieval/graph/memory | Native actions, plugins, MCP, optional Composio | Background services/schedules; recovery needs tests | Governance and staged policy plane | Workspace/integration; secure sessions unverified | Local edition has no login; hosted auth differs; enforcement mode matters |
| Agno | Multiple adapters | Teams and workflows | Database sessions/memory/knowledge | Toolkits, MCP/A2A | Schedules/background jobs; crash guarantees need tests | Run pauses/tool confirmation | Toolkit/integration | JWT/RBAC documented; app owns tool boundaries |
| OpenFang | Drivers/compatible endpoints | Workflows and agent/network communication | SQLite/retrieval/compaction | Native tools/MCP/A2A | Native scheduler; approval restart concern | Pending approvals held in memory in inspected manager | Playwright bridge | Capabilities/vault/sandbox documented; boundaries need tests |
| LangGraph / Deep Agents | Replaceable models | Graph routing/harness subagents | Checkpoints/stores/compaction | Functions/MCP | Checkpoints; scheduling/job ownership app-owned | Interrupts/approval middleware | Integration | Host auth and sandboxing |
| Microsoft Agent Framework | Multiple providers | Graphs/handoffs/collaboration | State/session; project memory app-owned | Tools/MCP/A2A | Checkpoints/durable extensions; deployment matters | Workflow human input | Integration | Middleware; app governance/isolation |
| CrewAI | Multiple providers | Crews/manager/direct delegation | Memory/knowledge | Functions/MCP/A2A | Flows/checkpoints; deployment governs jobs | Human input/review | Integration | Core app enforcement; AMP separate |
| Pydantic AI | Typed adapters | App/harness calls and subagents | Persistence/context; project ledger app-owned | Typed tools/toolsets/MCP | DBOS/Temporal integrations | Deferred tools/approvals | Integration | App policy/isolation |
| OpenAI Agents SDK | Provider-agnostic; parity varies | Handoffs/agents as tools | Sessions; project memory app-owned | Functions/MCP/hosted tools | Background engine app-owned | Human-in-loop support | Sandbox/tools | Guardrails do not replace infrastructure controls |
| Claude Agent SDK | Claude-centric runtime | Subagents/sessions | Harness context/files | Claude tools/MCP | External durable owner required | Callbacks/modes | Runtime integration | allowed_tools auto-approves; does not remove others |
| Google ADK | Model-agnostic; Gemini optimized | Hierarchies/Task API | Sessions/state; project memory app-owned | Functions/OpenAPI/MCP | Workflow runtime; background owner deployment-dependent | Tool confirmation | Integration | Host auth and resource/credential policies |
| OpenHands | Profiles/ACP runtimes | Coding automation/task workflows | Runtime/workspace; project memory needs evaluation | Backend-dependent tools | Schedules/webhooks/backend runs | Runtime-dependent | Runtime-dependent | Direct host mode exposes full filesystem |
| Letta Code | Replaceable models | Background subagents/agent calls | Stateful/versioned memory | Skills/hooks; exact MCP support needs version check | Crons/server | Permission modes | Runtime/tool-dependent | Local backend; some features require Letta sign-in |
| Dify | Provider plugins | Agent steps/workflows; workforce needs extension | RAG/knowledge | Plugins/MCP | Version-specific execution/recovery needs tests | Version-specific | Agent sandbox integration | Product auth; license/control review |
| n8n / Activepieces | AI integrations | Workflow routing; employee identity needs extension | Workflow data; project memory needs extension | Connectors/MCP paths | Schedules/triggers/workers | Workflow approvals | Integration | Product credentials/auth; effect policies need review |

OpenClaw, Hermes and Agent Zero are strong persistent-worker candidates, but assistant/harness features do not establish the desired project/task control plane. Scheduling, memory, tools and delegation are useful capabilities; host-tool access must be explicitly constrained.

## Durable execution shortlist

| Component | Architecture/license | Strength | Limitation |
|---|---|---|---|
| [DBOS Python](https://github.com/dbos-inc/dbos-transact-py) / [TypeScript](https://github.com/dbos-inc/dbos-transact-ts) | PostgreSQL-backed in-process workflows; MIT | Queues, waits, schedules, recovery without orchestration server | Replay compatibility and external-effect handling |
| [Temporal](https://github.com/temporalio/temporal) | Durable workflow service and SDK workers; MIT server | Mature long-running workflow ownership/operational tools | Extra service and concepts for one developer |
| [Celery](https://github.com/celery/celery) | Distributed queue; BSD-3-Clause code | Mature Python background processing | Approval/recovery needs app state machinery |
| [BullMQ](https://github.com/taskforcesh/bullmq) | Queue library; MIT core | TypeScript job processing | Queue retries are not durable business workflows |
| [Conductor](https://github.com/conductor-oss/conductor) | Workflow service; Apache-2.0 | Rich orchestration/integrations | Larger operational footprint |

External API effects are not exactly-once just because steps are persisted. A crash can happen after the external action succeeds but before recording it.

## Protocols and specialist components

- [MCP specification](https://github.com/modelcontextprotocol/modelcontextprotocol): tools/resources/prompts. Use the [Python SDK](https://github.com/modelcontextprotocol/python-sdk), checking selected package versions/licenses. Spec repository is transitioning from MIT to Apache with separate documentation licensing.
- [A2A](https://github.com/a2aproject/A2A): discovery/task/message/artifact exchange between opaque apps, Apache-2.0. Future external agents; no internal network hop needed in MVP.
- [browser-use](https://github.com/browser-use/browser-use): model-driven browser interaction, MIT; not a complete approval or credential boundary.
- [Playwright](https://github.com/microsoft/playwright): deterministic browser automation/traces, Apache-2.0; preferred browser foundation.
- [pgvector](https://github.com/pgvector/pgvector): PostgreSQL vector retrieval; no separate vector database.
- [Mem0](https://github.com/mem0ai/mem0): extraction/retrieval candidate; managed benchmarks do not prove identical open-source behavior.
- [LiteLLM](https://github.com/BerriAI/litellm): optional provider normalization/routing/cost adapter; MIT outside enterprise exceptions.
- [Volcengine SDK](https://github.com/volcengine/volcengine-python-sdk): official Ark integration starting point. Seedance access, regional endpoints and pricing need provider-specific validation.

## Critical primary evidence

- [Paperclip governance at inspected commit](https://github.com/paperclipai/paperclip/blob/0d3e7bf6ac69c6a41995e62e7a38ca99dcbc8dfd/doc/MCP-ACCESS-GOVERNANCE.md): exact argument/schema matching, audit and limitations. Its own MCP endpoint is outside gateway policy.
- [Paperclip connection threat model](https://github.com/paperclipai/paperclip/blob/master/doc/connections/SECURITY-THREAT-MODEL.md): brokered credentials/resource filters/execution checks.
- [Automatos execution at inspected commit](https://github.com/AutomatosAI/automatos-ai/blob/1bc4c07247ecc0f663e904c93b1c3f0474144d42/orchestrator/modules/tools/execution/unified_executor.py): off/shadow/destructive stages and conditional fail-open behavior.
- [OpenFang approvals at inspected commit](https://github.com/RightNow-AI/openfang/blob/acf2587e46be174c10200489c9a2d23a39a98aeb/crates/openfang-kernel/src/approval.rs): in-memory pending/recent records.
- [Pydantic AI DBOS at inspected commit](https://github.com/pydantic/pydantic-ai/blob/06ba88fd34ffd1b9de1e762b1e7235980ed693fe/docs/durable_execution/dbos.md): custom tools not automatically wrapped as durable steps.
- [AutoGen status](https://github.com/microsoft/autogen#readme), [Letta migration](https://github.com/letta-ai/letta#readme), [Flowise status](https://github.com/FlowiseAI/Flowise).

These findings identify risks; they do not establish that an entire project is insecure.

## Adopt, fork, combine, or build

| Option | Assessment |
|---|---|
| A: adopt unchanged | Fastest, but reviewed products do not yet demonstrate all enforcement/recovery invariants |
| B: extend Paperclip | Strongest alternative; coordination/UI could eliminate major work |
| B: extend Automatos | Closest visible fit; broader surface, local auth and policy-mode audit add evaluation effort |
| C: combine components | Recommended for workflows, models, retrieval, protocols/browser |
| D: build product over libraries | Preferred if adoption validation fails; app owns identity/task/policy/audit semantics |

Decision direction: C + D, with an adoption gate before substantial bespoke implementation.

Use fixtures, not company credentials, to evaluate Paperclip:

1. Swap provider without losing identity/history.
2. Enforce project access on memory/tasks/artifacts.
3. Preserve approval waits across restart.
4. Invalidate changed-argument approvals.
5. Prevent native shell/network bypass.
6. Deduplicate dispatch and mutations.
7. Enforce root budget across concurrent delegation.
8. Stop subsequent effects after cancellation.
9. Recover schedules without duplicate work.
10. Inspect task/agent/tool provenance.

If modest extensions pass these requirements, prefer B and revise ADRs. If core runtime/security lifecycle replacement is needed, proceed with C + D. The evaluation has not been executed.
