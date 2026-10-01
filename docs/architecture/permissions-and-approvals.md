# Permissions and approvals

Status: approved architecture direction.

## Policy

Evaluate subject + action + resource + execution context into allow, require approval or deny.

Subject: human/agent. Resource: project/artifact version/repository ref/recipient/browser origin/account. Conditions may constrain connection, arguments, time, budget and expiry.

Example:

```json
{
  "subject": "agent:assistant",
  "action": "gmail.send",
  "resource": {
    "connection_id": "mail-primary",
    "recipient_domain": "example.com"
  },
  "effect": "require_approval"
}
```

Use validated policy grammar, not arbitrary policy code.

## Evaluation

Default deny; explicit deny wins; approval beats ordinary allow. Project/workspace ceilings bound grants. Empty grants mean none. Unknown classification or evaluation failure denies. Manager status never bypasses.

Delegation cannot transfer secrets or elevate grants. Child authority is bounded by its own grants, task authority, project ceiling and allowed delegation.

Prevent privilege laundering: an unauthorized caller cannot cause a privileged agent to act without separately permitted delegation.

Version/audit policy changes. Agents propose but cannot apply them.

## Approval

Persist requesting agent/task/execution; action/connection/canonical resource; exact payload or immutable encrypted ref; preview; payload/schema hashes; target version/preconditions; effect/risk; policy revision; expiry/decision history.

Preview actual email body/recipient/attachments, diff, branch/commit, deployment target or browser destination/fields. Do not substitute an agent summary.

Pending -> approved/rejected/expired/cancelled. Invocation execution is separate: awaiting approval/admitted/executing/succeeded/failed/outcome unknown. Approval is not success.

Before effect recheck unchanged payload/schema/resource, target preconditions, approval validity, current policy/connection, stop/cancel and budget. Change or stale target requires new approval.

## Replay

Bind approval to one logical invocation. Atomically admit with idempotency key. Recovery may continue that invocation, not authorize another effect. Unknown external result requires reconciliation.

MVP approve/reject only. Editing creates a new proposal. Standing grants/trust rules come later with scope and expiry.

## Boundary

Agents have no database credentials, integration tokens or host execution. Trusted code evaluates/executes; later runners get task resources and short-lived broker handles.

Schedules, retries, direct delegation, manual resume and MCP use identical checks.

Tests: altered/expired requests, concurrent consumption, revocation after approval, forged sender, delegation laundering and restart.
