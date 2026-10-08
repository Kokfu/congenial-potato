# AI Workforce: approved architecture

The human approved the research and architecture direction in the project conversation. Phase 0 validation is recorded below. Implementation status and evidence are tracked in [project progress](../progress.md).

The repository now contains a fixture-only self-hosted foundation. Provider work remains synthetic in the running application; native SDK adapters have offline tests and are not registered for live execution.

## Read first

1. [Open-source landscape](research/open-source-landscape.md)
2. [System architecture](architecture/system-architecture.md)
3. [MVP and implementation phases](mvp-plan.md)
4. [Phase 0 validation status and protocol](research/phase-0-validation.md)
5. [Provider SDK offline validation](research/provider-sdk-validation.md)
6. [Shared cost ledger fixture validation](research/shared-cost-ledger-validation.md)
7. [Governed synthetic calls](research/governed-call-validation.md)
8. [Call deadlines and cancellation](research/call-limits-validation.md)
9. [Owner price configuration](research/price-config-validation.md)
10. [Unknown synthetic charge reconciliation](research/unknown-cost-reconciliation.md)
11. [Credential file validation](research/credential-file-validation.md)
12. [Usage normalization and uncertain response cost](research/usage-normalization-validation.md)
13. [Offline native SDK worker validation](research/offline-native-worker-validation.md)
14. [Phase 3 task graph foundation](research/task-graph-validation.md)
15. [Task acceptance and assignment](research/task-acceptance-validation.md)
16. [Manager plan validation](research/manager-plan-validation.md)
17. [Bounded delegation](research/delegation-validation.md)
18. [Messages and cancellation](research/messages-cancellation-validation.md)
19. [Runtime collaboration gate](research/runtime-collaboration-validation.md)
20. [Scoped knowledge ledger](research/memory-ledger-validation.md)
21. [Reviewed memory writes](research/reviewed-memory-validation.md)
22. [Lexical memory retrieval](research/lexical-memory-validation.md)
23. [Cited context](research/cited-context-validation.md)
24. [Phase 4 artifact and memory gate](research/phase-4-gate.md)
25. [Typed tool gateway](research/tool-gateway-validation.md)
26. [Tool resource policy](research/tool-policy-validation.md)
27. [Durable tool approval](research/tool-approval-validation.md)
28. [Synthetic tool effects](research/tool-effect-validation.md)
29. [Phase 5 governed tool fixture gate](research/phase-5-gate.md)
30. [Daily schedule contract](research/daily-schedule-contract.md)
31. [Durable schedule dispatch](research/schedule-dispatch-validation.md)
32. [Project activity and SSE](research/activity-sse-validation.md)
33. [Scheduled and delegated daily budget](research/scheduled-daily-budget-validation.md)
34. [Phase 6 fixture gate](research/phase-6-gate.md)
35. [Local external-read contract](research/local-read-contract-validation.md)
36. [Pinned destination boundary](research/network-boundary-validation.md)
37. [External read observations](research/read-observation-validation.md)

## Architecture

- [Agent runtime](architecture/agent-runtime.md)
- [Provider interface](architecture/provider-interface.md)
- [Tool system](architecture/tool-system.md)
- [Permissions and approvals](architecture/permissions-and-approvals.md)
- [Memory](architecture/memory.md)
- [Security](architecture/security.md)
- [Data model](architecture/data-model.md)
- [Background execution](architecture/background-execution.md)
- [Deployment](architecture/deployment.md)

## Decisions

- [001: Backend stack](adr/001-backend-stack.md)
- [002: Workflow engine](adr/002-workflow-engine.md)
- [003: Agent framework](adr/003-agent-framework.md)
- [004: Memory strategy](adr/004-memory-strategy.md)
- [005: Provider abstraction](adr/005-provider-abstraction.md)

## Current coding task

Follow [progress.md](../progress.md) task by task. Phase 7.3 persisted scoped external claims; the complete gateway gate remains before any product outbound read. The Phase 2 live activation gate remains open; keep paid calls and production credentials disabled during fixture validation.
