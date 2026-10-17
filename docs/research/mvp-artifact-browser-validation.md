# Visible approved outputs and Windows handoff

Date: 2026-10-17. Branch: `mvp-artifact-browser`. Parent: draft PR [#143](https://github.com/Kokfu/congenial-potato/pull/143), commit `fc21ba2327a23081ca643052e0088a63b5416487`.

The approved artifact was previously observable through the API but had no dedicated UI reader. The new Artifacts tab lists versions for the selected project and reads their content through the existing authenticated, integrity-checked backend API. It shows version, SHA-256 digest, author and execution identity. Content is React-escaped plain text, with no HTML/Markdown execution. Project changes remount scoped state and abort outstanding reads; selected-version guards prevent stale detail display. Empty/loading/read-error states and a reload action complete the owner workflow.

## Actual validation

- `npm run build` passed with TypeScript and Vite (19 modules). The owned local web image was rebuilt and updated; application database/worker resources were retained.
- All **five Playwright cases passed in 12.9s** against the real fixture application on its selected cloud loopback port. The extended foundation flow creates an agent/project/task, grants fixture execution, waits for the worker, approves a real artifact, opens its text/version/digest in Artifacts, switches to an empty project and back, then switches provider fixtures.
- That flow also injects a 503 read response at the browser boundary, verifies stale content disappears and the error is visible, removes the injected failure, and reloads the actual saved output successfully. This is UI error/recovery evidence, not an actual disk-corruption drill.
- One additional browser case uses real authenticated project creation and **explicitly mocked artifact responses** to exercise hostile text and delayed cross-project delivery. Script/img markup remains literal text, creates no corresponding DOM elements and does not execute. A delayed project-B reply cannot replace project-A content after switching back. These controlled responses test rendering/scoping only; they do not establish backend integrity or external execution truth.
- The actual healthy application was captured at `/workspace/workforce-mvp-artifacts.png`, using a saved synthetic output rather than a mocked API. The screenshot is a local review artifact, not a public deployment.
- The prior increment's ten launcher checks, four-case browser checkpoint, isolated egress denial and stop/start retention are retained as [separate evidence](mvp-local-launch-validation.md); they are not added to the five-case count. No full backend or recovery-witness suite rerun is claimed for this frontend change.
- Changed-document links and `git diff --check` passed. Local launch status showed healthy API/database/web plus a running worker, with only `127.0.0.1:52113` published for web.

## Owner PC and remaining scope

The owner confirmed **Windows with Docker Desktop**. The [local guide](../local-workspace-guide.md) now includes concrete PowerShell clone/start commands on this branch, Linux-container requirements, automatic free-port selection, private owner-password location, the full approval-to-output walkthrough and data-preserving stop/restart commands. This managed cloud session has no connection to that PC: actual Windows hardware/port/startup validation remains an owner-side step, not completed hosting on the PC.

The [completion plan](../mvp-completion-plan.md) records the implemented local MVP milestones and remaining gates. Fixture execution is usable for exploring the workflow. Real AI work still requires the separately scoped protected-credential/pricing/cap/cancellation integration, and paid activation has not been authorized by permission to host locally. Real external effects, production connections, public deployment and merging remain disabled; protected recovery infrastructure remains unverified.
