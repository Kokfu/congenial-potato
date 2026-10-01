# ADR 002: Durable execution engine

Status: approved architecture direction; final selection subject to Phase 0.

## Context

Restarts, long approval waits and schedules require more than queue retry.

## Options Considered

DBOS; Temporal; Celery/BullMQ + checkpoints; LangGraph + job owner; Conductor; custom engine.

## Decision

DBOS/PostgreSQL for custom MVP, subject to restart/cancel/schedule/approval tests.

## Reasons

Durable queue/wait/recovery without separate orchestration server; avoids custom mechanics.

## Tradeoffs

Smaller ecosystem than Temporal; replay/versioning/external reconciliation; sensitive checkpoint retention.

## Future Migration Path

Application-owned records and WorkflowEngine interface. Later Temporal; drain DBOS histories. For Paperclip adoption assess existing owner before second scheduler.
