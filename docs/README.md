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
38. [Persistent read destination grants](research/read-grant-validation.md)
39. [Inert web-read proposals](research/read-proposal-validation.md)
40. [Staged exact web-read approval](research/read-approval-validation.md)
41. [Mediated synthetic web-read effect](research/read-effect-validation.md)
42. [Phase 7 fixture gate and remaining limits](research/phase-7-fixture-gate.md)
43. [Local backend egress denial](research/egress-denial-validation.md)
44. [Bounded resolver and local TLS proof](research/transport-deadline-validation.md)
45. [Exact single-use broker contract](research/broker-contract-validation.md)
46. [Database-bound broker issuance](research/broker-issuer-validation.md)
47. [Authenticated broker results](research/broker-result-validation.md)
48. [Private broker RPC](research/broker-rpc-validation.md)
49. [Separate-container broker proof](research/isolated-broker-validation.md)
50. [Independent mediator admission](research/broker-admission-validation.md)
51. [Clean isolated Compose bootstrap](research/clean-bootstrap-validation.md)
52. [Phase 7 synthetic acceptance and closed product gate](research/phase-7-acceptance.md)
53. [Inert reviewed-runner contract](research/reviewed-runner-contract-validation.md)
54. [OS-isolated local runner fixture](research/isolated-runner-validation.md)
55. [Inert owner-pinned runner grants](research/runner-grant-validation.md)
56. [Inert typed runner proposals](research/runner-proposal-validation.md)
57. [Exact staged runner approvals](research/runner-approval-validation.md)
58. [Independent runner admission fixture](research/runner-admission-validation.md)
59. [Authenticated transient runner results](research/runner-result-contract-validation.md)
60. [Durable synthetic runner results](research/runner-result-acceptance-validation.md)
61. [Governed runner fixture acceptance](research/governed-runner-acceptance.md)

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

Follow [progress.md](../progress.md) task by task. Phase 7 local synthetic acceptance and the Phase 8 OS-isolated fixed-job fixture are complete; the latest full backend run passed 663 tests with 32 Docker cases skipped; the focused Docker-enabled runner run passed all 152 tests and fresh-volume Compose smoke passed. Product reads, runner dispatch and Phase 2 native activation remain closed. Owner-pinned runner grants are persisted as inert metadata. Typed fixed-job proposals now remain inert in owner review. Exact owner approvals now remain staged. Independent database admission now fences the test-only runner bridge. Transient result envelopes now authenticate one durable synthetic metadata result under fresh authority. Exact duplicates return historical metadata without execution; missing/rejected results retain unknown admission. The governed-runner fixture matrix is consolidated; next test precommit result loss and unavailable keys across fresh interpreters. Product key/transport/restore acceptance remains open. Keep arbitrary shell/browser execution, paid calls, real outbound effects and production credentials disabled.
