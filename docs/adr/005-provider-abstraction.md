# ADR 005: Provider-independent intelligence

Status: approved architecture direction; final selection subject to Phase 0.

## Context

Persistent identity must survive provider switching; capabilities/cost/media differ.

## Options Considered

Vendor calls in orchestration; all OpenAI-compatible; mandatory LiteLLM; framework objects canonical; app-owned contract.

## Decision

Typed ProviderAdapter; OpenAI/Anthropic first, compatible/local/Google later; separate embeddings/media.

## Reasons

Core uses capabilities/results; adapters reuse SDK/framework implementations without domain coupling.

## Tradeoffs

Preserve opaque continuation; no guaranteed parity; changing catalog/pricing uncertainty.

## Future Migration Path

Add/change adapters without core changes; optional LiteLLM. New attempt if incompatible state; explicit governed fallback.
