# Data model

Status: approved logical model, not implemented migrations.

## Entities

| Entity | Key relationships/data |
|---|---|
| User | Provisioned owner; future identity |
| Workspace | Owner/settings/pause/daily cap |
| Agent | Workspace/stable identity/role/status |
| AgentConfigVersion | Agent/instructions/provider/model/tools/limits |
| ProviderConnection | Type/endpoint/secret ref |
| Project | Workspace/objective/context/status |
| AgentProjectGrant | Agent/project/scope |
| Objective | Project/request/success criteria |
| Task | Objective/project/parent/revision/status/acceptance |
| TaskAssignment | Task/agent/role/lifecycle |
| TaskDependency | Cycle-free prerequisite edges |
| AgentExecution | Task/config revision/root/parent/engine ID |
| ModelCall | Execution/provider/model/request metadata/usage/cost |
| Conversation | Project/task/participants |
| Message | Verified sender/order/reply refs |
| Delegation | Caller/child task/authority/correlation |
| ToolInvocation | Execution/definition/version/arguments/resources/outcome |
| ApprovalRequest | Invocation/hashes/preview/expiry/decision |
| PolicyRule/Revision | Subject/action/resource/conditions/effect |
| IntegrationConnection | Account/endpoint/bounds/encrypted secret ref |
| Artifact | Stable project identity |
| ArtifactVersion | Immutable bytes/digest/provenance |
| MemoryRecord | Project knowledge/trust/sources/validity |
| Schedule | Target/timezone/recurrence/overlap/misfire |
| BudgetLedger | Reservations/consumption/reconciliation |
| AuditEvent/Outbox | Durable actions/pending delivery |

Concepts can initially share storage without merging semantics. Carry workspace/project ownership and enforce relationships; prepare future users without enterprise tenancy.

## Task lifecycle

| State | Meaning |
|---|---|
| backlog | Not admitted |
| ready | Requirements/dependencies satisfied |
| queued | Durable dispatch accepted |
| running | Active execution |
| waiting | Suspended, typed reason |
| review | Result ready; acceptance pending |
| completed | Acceptance met |
| failed | Unsuccessful end |
| cancelled | Operator/platform cancelled |

Assignment is a relation. Wait reasons: approval, child, dependency, provider recovery, budget, reconciliation. Execution attempts separately queued/running/waiting/succeeded/failed/cancelled.

Blocked is a board projection. Retry creates attempt, not task copy. Engine state is not task state.

## Integrity

Server transitions, row/version concurrency, cycle rejection, immutable task/config binding, unique dispatch/invocation keys, ownership/FKs, UTC timestamps plus schedule timezone, exact decimal money/currency, explicit unknown usage/cost.

## Artifacts

Version records agent/human author, task/execution, timestamp, parent, digest, MIME, size and storage ref.

Stage bytes then mark metadata available; recover/clean abandoned staging. Publish success only after bytes available. Optimistic replace; immutable versions never overwritten.

Later code work uses isolated worktrees and commit/diff provenance, not shared arbitrary host writes.

## Indexes

Task board, pending approvals, timelines, conversation order, version lookup, schedule and scoped full-text indexes. Avoid speculative indexes or JSON where integrity requires relations. Validated tool arguments/versioned provider metadata may use JSON.
