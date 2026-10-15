# Independent runner admission fixture: Phase 8.2b.4

Date: 2026-10-16 (Asia/Kuala_Lumpur). Branch: `phase-8-runner-admission`. Parent: draft PR #57 (`8ecc761`).

## Boundary

This explicit fixture service locks the persisted root, source, invocation and approval; rechecks exact staged approval, current policy/grant/image/code/scope, cancellation and a valid USD root account with positive available balance; and creates one `runner_attempts` row keyed by invocation. Presence of that row consumes admission. The row commits **before** returning a bounded canonical manifest and a private random 32-byte capability. Only the capability hash is stored; the returned object's representation excludes capability and input. Manifest expiry is at most 30 seconds and no later than approval/grant expiry. Input and pins derive solely from reviewed database authority.

A repeated or restarted admission is unknown, including when authority has since expired or its local journal is replaced. Lost delivery cannot recover the private capability or reissue a manifest. Ongoing private checks validate capability, manifest digest/input/scope/time, recorded image/code and full approval/policy binding against fresh authority. They never create another attempt or authorize a new bridge entry. Wrong capability does not burn legitimate ongoing authority. A denied ongoing check preserves the attempt's unknown outcome and invalidates the application authority; it does not assert that execution never happened.

The trusted **test-only** bridge admits before every launcher entry, compares reviewed host code, then uses the existing non-root/no-network fixed-job launcher with fresh checks before creation, before start and after computation. The launcher now passes `--pull never`, avoiding registry access for missing images. A private callback may be reused for checks inside that one ongoing run; it is not an untrusted transport or externally replayable launch API. This assumes the trusted host and capability remain private. Product API/worker code imports neither service nor bridge/job; there is no new API, Docker socket, runner service or product dispatch.

The database migration refuses to drop a nonempty admission table. Empty-table rollback remains supported, with parent approvals preserved. This protects ordinary schema rollback, not an administrator deleting rows, replacing/restoring the database, stealing a live capability or running arbitrary trusted-host code.

## Validation

The first admission/approval command passed **89 tests in 61.06s**. After adding guarded rollback and the bridge, admission/approval/manifest/job checks passed **181 tests, 1 skipped in 73.61s**; the skip was the explicitly gated Docker case. Additional account/status/capability cases and the actual bridge were then run with Docker enabled: **12 passed, 51 deselected in 20.99s**. That command ran one real pinned no-network digest container, verified the database fence before delivery, refused a second launcher entry with a replacement empty journal, and verified no runner container remained. A receipt was locally verified, but no application result was accepted.

The suite covers exact manifests/pins/capability, each changed approval/grant/policy/root/source/budget condition before and after admission, wrong capability without consuming valid ongoing authority, concurrent admission with one delivery, actual `os._exit` after commit and fresh-interpreter refusal, empty-table migration round trip preserving parent approvals, and refusal to downgrade a consumed admission. The first migration command used repository-root relative Alembic configuration and failed (`Path doesn't exist: migrations`); rerunning from `backend/` succeeded. The failed command is not validation.

Backend image `sha256:441e79ae8a1bb64df75305b1fd229a85ea3475162491d85526310c0c42f090d7` built and was used for the bridge proof. A UID 10001/read-only/network-none import probe confirmed absence of the admission service and job from product imports and no admission API. Fresh isolated Compose initialized both databases, ran non-root processes, passed authenticated fixture execution and independent API/worker egress denial, then removed its resources. All 74 modified-document local links and whitespace checks passed.

The final full backend run passed **582 tests, 24 skipped in 596.32s (9:56)**. The 24 skips were the 23 existing runner/broker Docker acceptance cases and this new bridge case; the latter passed in the separate 12-case Docker-enabled command above. Alembic metadata check passed with no new upgrade operations. Host tests use locked dependencies on Python 3.12.14; image import/startup and bridge proof use Python 3.12.12. Browser, full kernel resource-isolation rerun, host reboot, power loss and stale restore were not tested.

```sh
# Disposable synthetic PostgreSQL setup (no application stack is adopted):
docker run -d --name workforce-runner-attempt-test --label workforce.fixture=runner-attempt -p 127.0.0.1:55433:5432 -e POSTGRES_PASSWORD=phase1fixture -e POSTGRES_DB=workforce_test postgres:17.6
# From backend/, with APP_DATABASE_URL pointing at workforce_test:
/tmp/workforce-venv/bin/alembic upgrade head
# From repository root, with PYTHONPATH=backend/src and the same APP_DATABASE_URL:
/tmp/workforce-venv/bin/pytest -q -x backend/tests/test_runner_admission.py backend/tests/test_runner_approval.py backend/tests/test_reviewed_runner_contract.py backend/tests/test_runner_fixture_job.py
WORKFORCE_DOCKER_GATE=1 /tmp/workforce-venv/bin/pytest -q -x backend/tests/test_runner_admission.py -k 'isolated_job or invalid_root or staged_status or wrong_capability'
/tmp/workforce-venv/bin/pytest -q backend/tests
BUILDX_CONFIG=/tmp/workforce-buildx docker build --secret id=proxy_ca,src="$CODEX_PROXY_CERT" -f docker/backend.Dockerfile -t workforce-backend:phase1 .
/tmp/workforce-venv/bin/python scripts/clean_compose_smoke.py
```

## Limits and next task

Even a locally verified fixture receipt leaves the database attempt `unknown` and the invocation `approved_staged`. There is no application result/provenance/context promotion, settlement or external-write receipt. Current positive budget is an authorization check; no monetary cost or CPU quota reservation is invented. Containers share the host kernel; the historical full isolation evidence is distinct from the new admission integration proof.

Next derive one exact result record from the admitted manifest and authenticated/private runner result, recheck current authority before accepting it, and fence concurrent/duplicate/lost results. Exercise grant/cancellation/expiry changes during isolated computation. Keep product dispatch disabled through result/recovery acceptance. Stale database-plus-journal restore, physical power loss, hostile host/kernel, production image/key/transport lifecycle, arbitrary code/shell/browser and real outbound integrations remain unproved/disabled. No paid call, merge, public deployment or production integration is authorized.
