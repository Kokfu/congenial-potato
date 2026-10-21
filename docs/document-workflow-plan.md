# Document-to-plan-to-draft workflow

Status: versioned owner-reference editing and run-source recording implemented; model use and the remaining workflow are planned. This is the first bounded workflow in [MVP milestone 5](mvp-completion-plan.md). Live calls require separate activation after the gates below pass.

## Intended useful result

An owner pastes a document or notes, specifies the reader and desired output, reviews a proposed plan, then reviews a cited draft before accepting a saved artifact. Initial target: turn meeting or research notes into a short action plan and Markdown draft. No external research, sending, publishing, shell execution or file-system browsing is needed.

## Available now

Projects accepts an optional brief of up to 20,000 characters when creating a project. It is persisted in the existing project objective field and shown literally when that project is selected, including after reload. An empty brief remains supported. A failed save keeps the entered name and brief for retry. Owners can edit the current brief, inspect prior revisions and their SHA-256 digests, and reload history. Edits require the expected current revision; a stale save keeps the draft and requires reviewing the latest text and explicitly choosing it as the draft base. History pages contain at most 50 metadata rows; older pages can be loaded. Attachments and document extraction are not implemented.

This is an owner-reference record. Current worker prompts use the task title and eligible reviewed memory; **the project brief is not sent to a model**, and fixture outputs are synthetic placeholders. Saving a brief grants no execution or tool permission. Keep credentials out of notes. The existing fixture task → exact approval → artifact path remains useful for practicing review, not for obtaining a substantive generated draft.

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
| Versioned brief and run pin (implemented) | Owners can revise source notes with a revision/digest. New root runs pin the current version at admission; delegated runs inherit the parent source. | PostgreSQL tests check edit/dispatch races, duplicate admission, schedule replay and source inheritance. Browser acceptance checks that approval and artifact reading retain the earlier source after a project edit. Workers still do not consume briefs. |
| Explicit context boundary | Pass a bounded pinned brief to the worker as quoted untrusted source, distinct from agent instructions and grants. | Inspect actual generated messages with a recording fixture adapter; hostile notes cannot change policy, tool grants, budgets or approval requirements. Product external dispatch stays disabled. |
| Reviewable plan | Produce a bounded structured plan, record source identity and require explicit owner review before draft execution. | Malformed, cyclic, wrong-project and stale-source plans are rejected; retries do not duplicate execution. Existing collaboration admission rules must be reused or extended explicitly. |
| Cited draft | Generate a Markdown artifact proposal with references to the pinned source and clear unknowns. | A deterministic adapter proves source flow, cancellation and exact artifact approval; UI shows source/plan provenance. Fixture tests do not establish factual quality. |
| Protected live activation | Configure one provider/model only after encrypted credential storage, independently verified current pricing, enforced caps and cancellation/unknown-charge handling. | Separately authorized capped live trial; report actual quality, charges and limitations. Offline adapters or fixture ledgers alone do not satisfy this gate. |

## Owner acceptance and limits

Run the Windows [startup guide](local-workspace-guide.md), create a project using non-secret notes, reload and confirm the brief, then practice the synthetic approval/artifact walkthrough. Actual Windows Docker Desktop startup is still an owner-side check; cloud browser results do not establish PC compatibility.

No live activation, real external effect, protected recovery infrastructure, deployment or merge is authorized by this plan. Backend egress isolation stays in place. Source quoting is one input boundary and must not be represented as a general prompt-injection guarantee.

The [revision validation](research/mvp-brief-revisions-validation.md) records migration, concurrency and browser evidence. History is append-only through these application routes, not protected against privileged database replacement or rollback. Downgrade refuses to delete revised history.

Run-source recording is covered by [pin validation](research/mvp-run-brief-pins-validation.md). Older runs and their descendants stay explicitly unpinned; no current brief is substituted for unknown historical input. Artifacts can display the recorded source, but that is admission metadata and does not mean the fixture generated its answer from those notes. Next: explicit bounded untrusted-source context with a recording fixture adapter, before generated planning or live activation.
