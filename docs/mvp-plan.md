# MVP plan

Status: architecture approved; Phase 0 execution is the next authorized task.

## Proof scenario

Human creates project/objective. Manager delegates research; specialist requests bounded review. Agents exchange verified messages and versioned Markdown.

Two native model providers. Fixture artifact replacement needs human approval. Restart during wait, approve, verify one logical effect. Human sees every step, intervenes/cancels and sees shared budget.

## Included

Secure owner login; persistent/versioned agents; two adapters; projects/objectives/tasks/subtasks; Manager/direct delegation; messages; minimal project facts/summaries/search; text artifacts; trusted tools; default-deny policy/durable approval; DBOS recovery/one daily schedule; activity/usage/root and daily caps; pause/cancel; Docker.

## Deferred

Global chat product, workflow editor, browser/shell, email/GitHub writes, rich media, default semantic memory, autonomous policy changes, marketplace, billing, organizations, enterprise RBAC.

Dashboard is work/approval overview, not analytics project.

## Phases

| Phase | Delivery | Acceptance |
|---|---|---|
| 0 | Paperclip fixture adoption comparison/DBOS restart experiment | Actual evidence, recommendation, ADR revisions if adoption wins |
| 1 | Compose/database/auth/UI shell | Clean startup/login/persistence/health |
| 2 | Worker/agents/two providers/limits | Switching, timeout/restart/cost fixtures |
| 3 | Plan validation/tasks/messages/delegation | Bounded collaboration/cycles/cancel |
| 4 | Memory/artifacts | Scope/provenance/version checks |
| 5 | Gateway/policy/approval | Denied never executes; restart/change/replay tests |
| 6 | Daily schedule/SSE/timeline/daily cap | Disconnect/misfire/reconnect tests |
| 7 | First external read | SSRF/bounds/provenance/injection tests |
| 8 | Isolated execution/external writes | Exact effects/isolation/reconciliation |

Migrations/security/audit start in phase 1. Durable execution precedes agents; enforcement precedes external tools.

## Tests

Unit transitions/policies/budgets/schemas; contracts providers/tools/stores; integration PostgreSQL/DBOS/approval/dedupe/artifact; security SSRF/injection/impersonation/bypass; E2E objective-through-review and cancel; fixed agent evals completion/cost/duplicates/retrieval.

Fake providers in CI; live checks opt-in/capped.

## Future structure

```text
backend/
  src/workforce/
    api/
    domain/
    agents/
    execution/
    providers/
    communication/
    tools/
    policies/
    approvals/
    memory/
    artifacts/
    observability/
  migrations/
  tests/
frontend/
docker/
docker-compose.yml
.env.example
README.md
```

Current docs include research, ten architecture files, this plan and five ADRs. Create app folders only after validation. Abstract differing dependency/security boundaries, not speculative consumers.

## Open questions

Paperclip fit after tests; first real daily workflow; accounts/caps; host architecture; data destinations/retention; first integration; later write approval strictness; licensing for distribution.

Repository destination is now Kokfu/congenial-potato.

## Stop

Approval authorizes bounded Phase 0, not unrestricted implementation/integrations. Report evidence before substantial app work.
