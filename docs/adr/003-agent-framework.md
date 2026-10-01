# ADR 003: Agent execution library

Status: approved architecture direction; final selection subject to Phase 0.

## Context

Typed model/tools and provider flexibility must not surrender identity/security semantics.

## Options Considered

Pydantic AI; LangGraph/Deep Agents; Microsoft Agent Framework; CrewAI; OpenAI SDK; Google ADK; Agno; custom loop.

## Decision

Pydantic AI behind application runtime/provider boundaries; core facilities, no broad autonomous defaults.

## Reasons

Typed tools/output, broad providers and DBOS integration. LangGraph alternative for complex graphs.

## Tradeoffs

Evolving APIs; custom tools need durability; subagents/hosted tools must use gateway.

## Future Migration Path

Canonical persisted messages/results and app records. Replace runtime adapter, drain/new attempts for in-flight migration.
