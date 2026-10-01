# Agent runtime

Status: approved architecture direction; executable validation pending.

## Identity/configuration

Separate stable Agent identity, immutable AgentConfigVersion, and AgentExecution attempts. Config includes instructions, provider/model, tools, limits and memory scope.

Changing provider updates future runs without recreating the agent. In-flight runs retain recorded configuration unless explicitly restarted as a new attempt. Current permission revocations, credential state and global stop override snapshots.

## Boundary

Application owns start/resume/cancel/inspect operations. Framework objects/provider messages are not canonical domain records.

Initially reuse Pydantic AI typed execution and tool proposals. Broad coding/subagent harnesses remain disabled until all paths use the governed gateway.

## Turn

1. Recheck status, deadline and shared remaining budget.
2. Assemble bounded task/summary/message/memory/artifact context.
3. Offer eligible tools.
4. Reserve model budget and request a typed next action.
5. Record durable response and usage.
6. Validate action.
7. Gateway-execute, delegate through task service, wait or finish.

Filtering tools improves behavior; execution-time authorization enforces it. Model output is untrusted. Validate plans, IDs, arguments and completion. A completion claim is not proof of external effect.

## Collaboration

Manager and specialists use one delegation service. Direct delegation creates a child task/execution. Messages create auditable records, not unlimited automatic model responses.

Wake requires authorized activation and remaining budget. Correlation IDs connect requests/results. Backend determines sender identity; message text cannot impersonate the human or grant authority.

## Limits

| Control | Starting default |
|---|---|
| Delegation depth | 3 |
| Children per root | 12 |
| Model calls per root | 40 including repairs/retries |
| Active runtime | 20 minutes |
| Human wait expiry | 24 hours |
| Concurrent model calls | 2 |
| Unproductive equivalent action | Block after 3 attempts |
| Transient provider retries | At most 3 within root budget |
| Root money cap | Required user-configured value |

Tune through evaluation. Track active runtime and elapsed deadline separately. Human wait consumes no active time but expires.

Children share root limits, not fresh budgets. Track ancestors, dependencies, depth and normalized work fingerprints. Reject delegation/dependency cycles. Similarity dedupe is advisory; exact idempotency keys enforce dispatch dedupe.

QA corrections create bounded task revisions, not indefinite recursion.

## Concurrency/cancellation

Lock or version execution mutations. Independent tasks may run concurrently; same-artifact writes use version preconditions.

Cancel the delegation tree. Recheck before every new model call/effect, abort supported requests and kill later isolated process trees.

Cancellation cannot undo completed external effects. Preserve them; propose separately authorized compensation where useful.

## Durability

Persist successful model responses/plans/waits/checkpoints. Replay must reuse recorded responses.

Put nondeterministic operations in explicit durable steps. Pydantic AI's DBOS integration does not automatically wrap arbitrary custom tools.

Tests: bounded delegation, duplicate dispatch, provider switching, restart in approval, cancellation and provider failure.
