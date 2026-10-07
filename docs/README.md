# AI Workforce: approved architecture

The human approved the research and architecture direction in the project conversation. Phase 0 validation is recorded below. Implementation status and evidence are tracked in [project progress](../progress.md).

The repository now contains a fixture-only self-hosted foundation. Provider work remains synthetic in the running application; native SDK adapters have offline tests and are not registered for live execution.

## Read first

1. [Open-source landscape](research/open-source-landscape.md)
2. [System architecture](architecture/system-architecture.md)
3. [MVP and implementation phases](mvp-plan.md)
4. [Phase 0 validation status and protocol](research/phase-0-validation.md)
5. [Provider SDK offline validation](research/provider-sdk-validation.md)

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

Follow [progress.md](../progress.md) task by task. Complete Phase 2's native provider boundary with verified capability manifests, budget enforcement, and explicit live activation before any real request. Keep paid calls and production credentials disabled during offline validation.
