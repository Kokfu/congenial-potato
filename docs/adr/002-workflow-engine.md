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

## Phase 0 evidence (2026-10-07)

DBOS Python 3.2.0 on PostgreSQL 17.6 reused a completed fake model step after process restart, resumed a correlated wait, and deduplicated a stable workflow ID. A crash after an external ledger write caused two step attempts; a separate unique-key ledger produced one logical effect. A v2 worker left a pending v1 workflow untouched until a v1 worker returned. Scheduling produced unique occurrence keys but overlap and missed-run policy remain application work. Keep DBOS as the candidate engine, with application-owned idempotency/reconciliation, cancellation gates, version draining, and schedule admission. See [Phase 0 evidence](../research/phase-0-validation.md).
