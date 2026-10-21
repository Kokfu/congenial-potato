# Recorded run brief sources

Date: 2026-10-22. Branch: `mvp-run-brief-pins`. Parent: draft PR [#147](https://github.com/Kokfu/congenial-potato/pull/147), commit `1e958501266dbebf63d75ecab795a8717244a0ff`.

## Implementation

New manual roots and scheduled occurrences record a project brief revision and SHA-256 digest in the same transaction as execution/outbox admission. A composite foreign key scopes the referenced history row. Manual dispatch can optionally supply a strict `expected_brief_revision`; stale requests fail before admission. Clients omitting it record the version current at admission, not a claim that the owner reviewed that source. Project locking serializes source capture with brief edits. Manual dispatch now locks project before task/agent, matching the graph's project-before-task order, and refreshes the task after acquiring its lock so duplicate admission cannot use the earlier lookup's cached backlog state.

Delegated children inherit their parent's pin, including after project edits. Exact delegation retries return the existing child. Legacy runs and their descendants remain explicitly unpinned; today's brief is never substituted for missing historical context. Source reads recheck project scope, the historical bytes' digest and the separately recorded digest; a mismatch fails closed. No application route updates or deletes pins. The migration intentionally adds no historical source rows, and downgrade refuses to erase recorded sources.

The saved-output view can expand the run's recorded brief and digest. This is source identity recorded at admission, **not evidence that the fixture generated its answer from those notes**. Worker prompts and provider registry are unchanged; the source endpoint explicitly reports `used_in_model_context: false` for pins. Actual bounded untrusted-source context is the next increment.

## Focused PostgreSQL validation

A temporary runner, `/tmp/check-run-brief-pins.py`, used the pinned disposable PostgreSQL image and existing fixture helper. Its final run had a uniquely labeled internal network, tmpfs database data, no host mounts or published ports, and ownership-checked cleanup. No product database was used for pytest.

- Parent objective backfill and exact Unicode/trailing-space digest checks passed through the new head. Empty-source-table downgrade/upgrade and `alembic check` passed with no metadata drift.
- `pytest -q -x -p no:cacheprovider backend/tests/test_project_briefs.py backend/tests/test_foundation.py backend/tests/test_activity.py backend/tests/test_task_graph.py backend/tests/test_runtime_collaboration.py backend/tests/test_schedule_dispatch.py backend/tests/test_execution_briefs.py` passed **43 tests in 29.23s**.
- Nine new cases check queued-source retention after edits, duplicate and concurrent dispatch, stale expected-source rollback, empty source recording, edit/dispatch races with coherent text/revision/digest, delegated inheritance/retry, schedule replay, explicit legacy unpinned inheritance, missing current history, and denied reads for changed bytes/digest/project scope or unauthenticated callers. Direct database changes in the integrity cases are controlled corruption fixtures.
- A populated pin table caused the expected `Cannot erase recorded execution brief sources` downgrade refusal, and remained readable afterward. This expected refusal is separate from the pytest count. All temporary resources were removed. An earlier 41-case pass preceded adding the last two admission regressions; it is not added to the final count.

## Built application and browser evidence

- `npm run build` passed TypeScript/Vite with 21 modules. Owned backend/web Docker images built with the public CA bundle as a build secret, retaining TLS verification. The owned fixture stack migrated and restarted successfully on its retained loopback port 52113 via `python scripts/local_workspace.py start --no-build`.
- Before migration, 25 historical executions existed. After migration and before browser work, there were still 25 executions and **zero source pins**. This checks that existing history was not silently assigned today's source.
- All **seven Playwright cases passed in 21.2s** on the actual fixture app. The foundation case now creates source notes, admits a run, edits the project brief after the run reaches review, approves the exact artifact, then expands its recorded revision 1 and reads the original text. Existing project-edit/conflict/history, rendering/project-scope, activity, collaboration and tool cases remained passing. This is synthetic application flow evidence, not substantive drafting quality.
- Actual approved-output/source screenshot: `/workspace/workforce-mvp-run-source.png`, without mocked API responses. It is a local review artifact, not public hosting.
- Scoped `scripts/egress_smoke.py` passed: API and worker reached the database, while direct/socket/HTTP/proxy/CONNECT/web-forward bypasses to a reachable synthetic sink were denied. Only owned disposable sink resources were removed.
- Seven changed Python files compiled. Changed Markdown local targets and whitespace checks passed before commit.

## Limits

Pins and digests are application records in the same replaceable database, not independent attestation or rollback protection. They do not prove physical durability, protected recovery, factual correctness, or actual model use. Missing/corrupt current history denies new root admission; a scheduler transaction also fails closed instead of inventing a source. No worker-context consumption, generated plan or substantive drafting is introduced. No full backend/witness/launcher suite or actual Windows Docker Desktop validation is claimed. Paid/live activation, product external dispatch, real effects, production connections, public deployment and merges remain disabled.
