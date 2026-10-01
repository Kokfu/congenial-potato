# Memory

Status: approved architecture direction.

## Scope/layers

MVP persistent memory is project-scoped. Identity/history are separate; never insert all history into every prompt.

| Layer | Purpose/storage |
|---|---|
| Working context | Current task/relevant messages; execution checkpoint |
| Rolling summary | Bounded work/open questions; versioned summary |
| Structured facts | Requirements/decisions/constraints/outcomes; PostgreSQL |
| Searchable records | Research/messages/excerpts; full-text search |
| Artifacts | Exact content/version; ArtifactStore |
| Semantic retrieval | Later measured improvement; pgvector |

Start with facts/summaries/full-text. Add embeddings only when retrieval evaluation shows need.

## Record/interface

Record ID/project/kind/content/sources/creator/trust/confidence/status/timestamps/validity/superseded record.

Distinguish human instructions, approved decisions, observed results, external claims and model inference. Summarization cannot promote external content to human authority.

MemoryStore supports scoped query, candidate write, supersede, provenance and deletion/tombstones. Artifact retrieval stays separate.

Authorize before retrieval; inaccessible titles/snippets must not leak.

## Context

Priority: current human requirements; applicable approved decisions; dependencies; verified facts; artifact excerpts; bounded recent messages/summaries.

Reserve output/tool capacity. Bound categories/total. Summaries cite originals; requirements remain traceable.

## Writes/conflicts

Agents propose facts/summaries, marked unverified. Human decisions/verified results have higher authority. Preserve contradictions and request resolution when material; no silent overwrite.

Stable IDs/provenance enable dedupe/correction. Task completion does not verify every claim.

## Embeddings/retention

Store embedding provider/model/dimensions/index version. Re-embed into new generation; derived data is rebuildable. Begin with exact vector search if corpus is small, add approximate indexes after measurement. Combine lexical/semantic with security filters.

Deleting source invalidates derived records/embeddings. Keep necessary audit tombstones while applying content retention. No raw credentials. Add other scopes only for real use cases.

Evaluate exact requirements, contradictory/stale facts and irrelevant conversations.
