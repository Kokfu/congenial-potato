# Versioned owner-reference brief editing

Date: 2026-10-21. Branch: `mvp-brief-revisions`. Parent: draft PR [#146](https://github.com/Kokfu/congenial-potato/pull/146), commit `a8df5870f0dc36d3a30ed6020004ffcc2db4985f`.

## Behavior and boundary

Owners can edit the current brief, read earlier revisions and inspect SHA-256 digests. Each successful create/update appends a project-scoped history row containing exact text, revision, digest, actor and timestamp. The current objective remains available to existing readers. The update locks the project and compares a strict expected revision; concurrent/stale saves receive 409 rather than overwriting newer notes. Audit/activity record scope/revision metadata without copying the source text. History lists at most 50 metadata rows per page; individual reads return one exact revision.

The editor retains a rejected draft. Reloading history lets the owner inspect the latest saved text, then explicitly choose that revision as the retained draft's base. Old revisions cannot be edited through these routes. Project changes remount the editor; aborted detail reads and generation checks discard superseded history replies.

Migration `e6b8d130a9f2` preserves every existing objective as revision 1, labels its actor `migration:existing-objective`, and hashes the exact UTF-8 text. Newly created versions identify the owner. Downgrade refuses to erase any revised history; it can round-trip before revisions are added.

This is application append-only history, not privileged-database tamper protection. There is **no execution source pinning or worker-context change yet**. Briefs remain owner reference only, including for queued/approved fixture runs. Run pinning must precede model-context integration.

## Actual validation

- `npm run build` passed TypeScript/Vite with 20 modules. Owned backend and web Docker image builds passed with the public CA bundle supplied as a build secret and TLS verification enabled.
- A temporary local runner (`/tmp/check-brief-revisions.py`) used the existing pinned PostgreSQL fixture image, a uniquely labeled internal network, tmpfs data, no host mounts and no published ports in the final run. All created resources were removed by ownership-checked cleanup. It ran migration to the parent, inserted a legacy Unicode/multiline/trailing-space objective, upgraded, checked exact text/digest/actor/revision, downgraded/upgraded before edits, and ran `alembic check`: no new upgrade operations detected.
- Against that disposable database, `pytest -q -x -p no:cacheprovider backend/tests/test_project_briefs.py backend/tests/test_foundation.py backend/tests/test_activity.py backend/tests/test_task_graph.py backend/tests/test_runtime_collaboration.py` passed **31 tests in 24.78s**. The nine new brief cases cover concurrent edits with one winner, stale/lost-response retry denial, prior-row preservation, metadata/scoping, 53 revisions and pagination, empty content, strict input limits, auth/CSRF and missing resources.
- After those tests, the runner inserted a revised-history fixture, attempted downgrade and observed the intentional `Cannot erase revised project brief history` failure. The revised row remained readable. This expected refusal was checked separately from the passing pytest count.
- Initial broader attempts exposed three regression files hard-coding a DBOS workflow URL at port 55433. Those tests now use `get_settings().workflow_url`; assertions are unchanged. An attempted temporary loopback mapping did not make that assumption work in this environment and was cleaned up. A separate intermediate migration attempt exposed connection-wide streaming affecting inserts; streaming is now confined to the SELECT statement. The final successful runner used the corrected code and no published database port.
- `python scripts/local_workspace.py start --no-build` updated only this retained fixture stack after the builds; migration succeeded and API/database/web became healthy with the worker running. The project and loopback port 52113 were retained. No owner-PC hosting result is inferred.
- All **seven Playwright cases passed in 18.0s** against that real app. The new two-tab case saves revision 2, rejects the stale tab with 409, preserves its draft through history reload, explicitly rebases and saves revision 3, reloads, and reads unchanged revisions 1 and 2 plus a digest. Existing foundation/artifact/activity/collaboration/tool cases remain passing. The initial browser run had six passes and a selector-label timeout; adding an explicit accessible name fixed the new revision selector before the final full browser rerun.
- Scoped `scripts/egress_smoke.py` passed: API/worker could reach the database, while direct HTTP/socket/proxy/CONNECT/web-forward attempts to the reachable synthetic sink were denied. The sink was local synthetic infrastructure; no production endpoint was contacted.
- Eight changed Python files compiled. Changed-document local targets and `git diff --check` passed before commit.

## Remaining work

Pin a brief revision/digest to a run before passing source notes into any prompt. Test pinned text across edits, queueing, retries and approval; this increment does not claim those guarantees. Attachments, extraction, generated plans/cited drafts and factual-quality acceptance remain future work. No full backend/witness/launcher suite or actual Windows Docker Desktop acceptance is claimed. Paid/live providers, product external dispatch, real effects, production connections, public deployment and merges remain disabled.
