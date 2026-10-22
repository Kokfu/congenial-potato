# Guided local document fixture validation

Date: 2026-10-22. Branch: `mvp-guided-document-fixture`. Parent: draft [#151](https://github.com/Kokfu/congenial-potato/pull/151), `7112ca59577c40ee3923e3a83447bccf1bbb9ce4`.

## Change

Projects offers a source-notes form and owner walkthrough. `POST /api/document-fixtures` uses the existing owner/CSRF/origin checks, rejects unknown fields and blank/oversized input, and saves one project/brief, two fixed unpriced fixture configurations, two scoped execution grants and a backlog plan task in one transaction. No execution, outbox or approval is created. An audit/activity event records setup. No schema migration is added.

The UI selects the new project's planner. Plan dispatch, source review/admission, each reviewed draft request, exact artifact approval and task acceptance remain separate owner actions. The plan is predefined and the output is a deterministic cited quote fixture, not useful autonomous analysis. A form locks after submission, retains notes after failure and warns that a lost response can follow a committed setup. There is no cross-tab deduplication or automatic retry; a new setup creates new records.

## Actual checks

- `/workspace/witness-postgres-venv/bin/python /tmp/check-document-setup.py`: **87 focused PostgreSQL tests passed in 70.40s**, including three new setup cases. These verify fixed connections/configuration, preserved Unicode notes/revision, scoped grants, backlog-only state, zero executions/outbox/approvals, owner/CSRF/input rejection and full rollback on an injected post-flush failure. The other 84 cases cover the existing source/review/draft workflow and related foundation paths.
- The same ownership-scoped disposable PostgreSQL runner checked legacy-objective backfill, empty-table migration round trip, no metadata drift and populated draft-history downgrade refusal. Expected refusal retained history; cleanup removed only its own tmpfs container/internal network. No published database port or host data mount was used.
- All **9 Playwright tests passed in 29.3s** against the actual updated app on `http://localhost:52113`. The document flow now begins entirely through the guided setup form, verifies backlog state, explicitly runs the selected planner and completes source review/admission, old-source draft after a notes edit, exact approval, saved-artifact read and separate acceptance. One extra case intercepts only a setup failure response to verify notes retention, disabled repeat submission and the uncertain-response warning; that controlled case is not backend durability evidence.
- `npm run build` passed with 22 modules. The owned stack rebuilt via `BUILDX_CONFIG=/tmp/workforce-buildx python scripts/local_workspace.py start --build-ca /etc/ssl/certs/ca-certificates.crt`; TLS stayed enabled. API/database/web became healthy and the worker remained running. The existing project/port/data were retained.
- Scoped `scripts/egress_smoke.py` passed: API/worker could reach the database and were denied direct/socket/HTTP/proxy/CONNECT/web-forward access to a reachable synthetic sink. Only owned sink resources were removed.
- Three changed Python files compiled. Markdown targets and staged whitespace were checked before committing.
- Initial runner invocation used the default Python without Alembic and performed no tests; its owned disposable resources were removed. The first dependency-equipped run reached 85 passes and one test-client-hostname assertion failure. The test client was corrected to the app's allowed localhost origin; final 87-test results above supersede that run. An earlier eight-browser pass preceded the added failure case; counts are not combined.

## Limits and next increment

Cloud Linux validation does not prove Windows Docker Desktop startup, host ACL/key-store protection or physical durability. Production connections, paid models, real effects, public deployment and merges remain disabled. No native provider is registered by this change.

The owner selected Claude, OpenAI/ChatGPT, Gemini and DeepSeek for offline preparation. See the [readiness plan](../live-model-readiness-plan.md). Next reliability increment: force zero SDK automatic retries even when an offline native adapter receives a preconfigured injected client; ambiguous charges must remain a governed-call concern rather than hidden SDK resends.
