# Document-to-plan-to-draft workflow

Status: versioned brief editing, run-source recording and bounded fixture-context preparation implemented; source-bound plan review implemented with fixture candidates; substantive generation, plan-bound draft execution and live activation remain planned. This is the first bounded workflow in [MVP milestone 5](mvp-completion-plan.md). Live calls require separate activation after the gates below pass.

## Intended useful result

An owner pastes a document or notes, specifies the reader and desired output, reviews a proposed plan, then reviews a cited draft before accepting a saved artifact. Initial target: turn meeting or research notes into a short action plan and Markdown draft. No external research, sending, publishing, shell execution or file-system browsing is needed.

## Available now

Projects accepts an optional brief of up to 20,000 characters when creating a project. It is persisted in the existing project objective field and shown literally when that project is selected, including after reload. An empty brief remains supported. A failed save keeps the entered name and brief for retry. Owners can edit the current brief, inspect prior revisions and their SHA-256 digests, and reload history. Edits require the expected current revision; a stale save keeps the draft and requires reviewing the latest text and explicitly choosing it as the draft base. History pages contain at most 50 metadata rows; older pages can be loaded. Attachments and document extraction are not implemented.

The worker uses the pinned brief as a bounded quoted source for reviewed fixture connections, separate from agent instructions, task title and eligible memory. A JSON message of at most 6,000 characters includes source identity, an exact text prefix and truncation metadata. The source is marked `external` trust and a fixed instruction describes its data-only role. **Fixture outputs remain synthetic placeholders**, not substantive generated drafts. Saving a brief grants no execution or tool permission. Keep credentials out of notes. The existing fixture task → exact approval → artifact path remains useful for practicing review, not for obtaining a substantive generated draft.

Suggested brief:

```text
Goal: Turn the notes below into an action plan and a short draft.
Reader: Who will use the result?
Output: Markdown; plan followed by a draft of at most 500 words.
Constraints: Identify missing facts. Do not invent owners, dates or citations.
Source notes:
[Paste non-secret text here.]
Acceptance: Each factual claim traces to the supplied notes or is marked unknown.
```

## Remaining bounded increments

| Increment | Behavior to implement | Acceptance evidence required |
| --- | --- | --- |
| Versioned brief and run pin (implemented) | Owners can revise source notes with a revision/digest. New root runs pin the current version at admission; delegated runs inherit the parent source. | PostgreSQL tests check edit/dispatch races, duplicate admission, schedule replay and source inheritance. Browser acceptance checks that approval and artifact reading retain the earlier source after a project edit. Prepared-context history records whether a bounded source message was prepared; it does not attest delivery or use. |
| Explicit context boundary (fixture implementation complete) | Prepare a bounded pinned source message, quote it as untrusted data, and preserve its exact serialized form/hash for replay. | Recording fixtures inspect actual worker requests, truncation, unchanged instructions/authority and approval-required output. Cancellation, revoked grants, missing/corrupt sources and unreviewed connections deny preparation. This is not a general prompt-injection guarantee. Product external dispatch stays disabled. |
| Reviewable plan (fixture contract implemented) | Reuse bounded Manager task plans; bind pinned brief and exact prepared-message identity into the owner-reviewed payload hash. | Model-supplied binding fields are rejected; the server derives them. Admission rechecks current brief, context, graph, project revision and grants. It creates associated backlog tasks only; server/UI keep document draft dispatch disabled until that path preserves the admitted source. |
| Cited draft | Generate a Markdown artifact proposal with references to the pinned source and clear unknowns. | A deterministic adapter proves source flow, cancellation and exact artifact approval; UI shows source/plan provenance. Fixture tests do not establish factual quality. |
| Protected live activation | Configure one provider/model only after encrypted credential storage, independently verified current pricing, enforced caps and cancellation/unknown-charge handling. | Separately authorized capped live trial; report actual quality, charges and limitations. Offline adapters or fixture ledgers alone do not satisfy this gate. |

## Owner acceptance and limits

Run the Windows [startup guide](local-workspace-guide.md), create a project using non-secret notes, reload and confirm the brief, then practice the synthetic approval/artifact walkthrough. Actual Windows Docker Desktop startup is still an owner-side check; cloud browser results do not establish PC compatibility.

No live activation, real external effect, protected recovery infrastructure, deployment or merge is authorized by this plan. Backend egress isolation stays in place. Source quoting is one input boundary and must not be represented as a general prompt-injection guarantee.

The [revision validation](research/mvp-brief-revisions-validation.md) records migration, concurrency and browser evidence. History is append-only through these application routes, not protected against privileged database replacement or rollback. Downgrade refuses to delete revised history.

Run-source recording is covered by [pin validation](research/mvp-run-brief-pins-validation.md). Older runs and their descendants stay explicitly unpinned; no current brief is substituted for unknown historical input. Artifacts can display the recorded source, and prepared-context metadata when present. A preparation record does not establish provider delivery, semantic use or answer quality. Next: carry the admitted plan/source binding into an explicitly requested fixture draft run, then verify cited output and approval before substantive drafting or live activation.

See [fixture-context evidence](research/mvp-brief-fixture-context-validation.md). Empty/unpinned sources add no source message; older runs are not retroactively marked prepared. The bound covers the serialized source message, not the entire prompt or real-model token usage.

The [source-bound plan evidence](research/mvp-source-bound-plan-validation.md) covers runtime fixture plan review and exact owner admission. Fixtures supply predefined candidate JSON; this is not substantive model-generated planning. Pending legacy candidates without an exact source binding are not silently rebound at decision time; use a new proposal. Generic empty/unpinned legacy plans keep their existing semantics.
