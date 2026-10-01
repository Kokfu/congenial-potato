# AI Workforce: approved architecture

The human approved the research and architecture direction in the project conversation. Technology selection remains subject to the bounded Phase 0 adoption and recovery validation.

This branch contains documentation only. It contains no application, executable proof of concept, deployment, credentials, or claimed runtime test results.

## Read first

1. [Open-source landscape](research/open-source-landscape.md)
2. [System architecture](architecture/system-architecture.md)
3. [MVP and implementation phases](mvp-plan.md)
4. [Phase 0 validation status and protocol](research/phase-0-validation.md)

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

## Next coding task

The research and architecture are approved. Inspect repository instructions, then perform Phase 0 using local fixtures and fake providers. Evaluate Paperclip adoption and DBOS recovery, record reproducible commands and actual results in `docs/research/phase-0-validation.md`, and stop before substantial application implementation.

Do not request architecture approval again. Do not use paid model calls, real company credentials, or production integrations. Deliver the bounded validation changes through a pull request.

A repository-connected execution environment with a terminal and a supported PostgreSQL/test setup is required. GitHub connector access alone is sufficient to edit documentation, but cannot execute these experiments.
