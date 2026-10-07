# ADR 001: Backend and application stack

Status: approved architecture direction; final selection subject to Phase 0.

## Context

One developer needs portable typed APIs, async tools/models, durable work and a private UI.

## Options Considered

Extend Paperclip TypeScript/React; Python/FastAPI + React; full-stack Node; Next.js backend; microservices.

## Decision

For custom architecture: Python/FastAPI/Pydantic, PostgreSQL/SQLAlchemy/Alembic, React/TypeScript/Vite; separate API/worker from one codebase. Run Paperclip adoption gate first.

## Reasons

Typed agent/durable integrations; static UI; transactional durable data; separate workers without microservices.

## Tradeoffs

Two languages; generate API types. Async/connection discipline. Existing platform may cost less than custom.

## Future Migration Path

Version API/events. Extract modules only when justified. If Paperclip wins, supersede ADR and keep its stack.

## Phase 0 disposition (2026-10-07)

The Paperclip adoption gate did not clear. Fixture suites passed, but its documented unmanaged MCP path is outside gateway enforcement and the required project/root-budget/restart invariants remain unproven end to end. Proceed with this ADR's custom control layer for the next foundation phase. Reassess Paperclip if an isolated, fully mediated runtime and the missing fixtures become available. See [Phase 0 evidence](../research/phase-0-validation.md).
