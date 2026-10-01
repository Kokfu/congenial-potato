# ADR 004: Project memory

Status: approved architecture direction; final selection subject to Phase 0.

## Context

Reliable scoped recall without full-history prompts or excess infrastructure.

## Options Considered

Full replay; PostgreSQL facts/summaries/full-text; immediate pgvector; Mem0; Letta; dedicated vector/graph DB.

## Decision

App-owned project facts/cited summaries/artifacts/full-text; pgvector after measured need.

## Reasons

Relational provenance/corrections/trust fit requirements. Small corpus needs no extra service.

## Tradeoffs

Less automatic semantic recall/personality; summaries can omit; retain originals; small knowledge ledger needed.

## Future Migration Path

Version MemoryStore/embedding metadata. Add semantic/library adapter with same scope/provenance/authority. Rebuild derived indexes.
