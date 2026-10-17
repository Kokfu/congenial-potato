# Saved project briefs and document workflow plan

Date: 2026-10-17 UTC. Branch: `mvp-project-briefs`. Parent: draft PR [#145](https://github.com/Kokfu/congenial-potato/pull/145), commit `34eb7eb3d0e2c86f0d2c9444558f6d93ac6100f0`. Earlier entries use the previous session's local date.

## Change

The backend already persisted a project objective, but the browser could only supply a name. Creation now accepts an optional brief (20,000-character browser limit matching the backend bound) and displays the selected project's saved objective as React-escaped plain text. Name length is bounded to the existing API limit of 160. Empty briefs remain valid; failed creation retains the draft. No schema, backend prompt, worker, provider registry or dispatch change was needed.

The [workflow plan](../document-workflow-plan.md) defines an initial source-notes → reviewed plan → cited Markdown draft path with separately reviewable source revision, context, planning, output and live-activation increments. It explicitly distinguishes currently saved owner-reference notes from future model input. The Windows guide now points to this branch and explains that limitation.

## Actual checks

- `npm run build` passed TypeScript and Vite, transforming 19 modules.
- Rebuilt only the owned local web image using `docker build --secret id=proxy_ca,src=/etc/ssl/certs/ca-certificates.crt -f docker/web.Dockerfile -t <owned-project>-web:local .`, with `BUILDX_CONFIG=/tmp/workforce-buildx`; scoped Compose `up -d --no-deps --no-build --wait web` passed. Only the owned web container was replaced. An initial `docker compose build --secret ... web` command was rejected because Compose has no such flag; it performed no build/update. TLS verification remained enabled.
- All **six Playwright cases passed in 15.9s** against the real isolated fixture application on cloud loopback port 52113. Existing activity, collaboration, tool review, artifact and foundation flows remained passing.
- The new brief case first injects a browser-boundary HTTP 503 on project creation and verifies that the entered name/notes remain available for retry. After removing the fault, real authenticated creation, reload and API readback preserve multiline text, Unicode and hostile HTML exactly. Script/img content creates no such DOM nodes and does not execute. Selecting an empty project removes the previous brief; selecting the original restores it. The mocked failure demonstrates UI retention, not actual database outage recovery.
- Actual application screenshot: `/workspace/workforce-mvp-project-brief.png`, from the persisted browser-test brief without mocked responses. It is a local review artifact.
- Markdown local targets and `git diff --check` passed before commit.

## Limits and next task

Briefs currently have no edit/revision history and are **not consumed by fixture or live model prompts**. There is no document extraction, generated plan or substantive draft result. Browser length limits use UTF-16 units; the server remains authoritative for its own character bound. This is a UI/planning increment, not a claim of factual quality, broad prompt-injection resistance or backend release acceptance.

No full backend, witness, egress or launcher suite rerun is claimed for unchanged backend/launcher code. Actual Windows Docker Desktop startup remains unverified because the session runs on a different cloud computer. Next implementation: source revision/digest pinning before any worker-context use. Protected credentials, verified pricing, caps, cancellation/unknown charges and separately authorized live activation remain prerequisites. Paid calls, product external dispatch, real effects, production connections, public deployment and merging stay disabled.
