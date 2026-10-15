# OS-isolated local runner fixture: Phase 8.2a

Date: 2026-10-15 (Asia/Kuala_Lumpur). Branch: `phase-8-isolated-runner`. Parent: draft PR #53 (`0ee2cb3`).

This is a fixed local synthetic job plus a **test-only host launcher**. Product API/worker code imports neither launcher nor job. No Docker socket, general command/image selection, arbitrary shell/browser, application effect route or external write integration is introduced. The worker/provider registry remains fixture-only; Phase 7 product reads remain disabled.

## Boundary

The normal job computes only the SHA-256 and UTF-8 byte count of bounded text. It verifies the pinned manifest and its own reviewed source digest; the host pins the immutable image ID containing that code and its imports. The host private journal commits manifest/image/job digests with an exclusive marker, file fsync and directory fsync **before any container-create request**. No input text is stored in the marker or receipt. Existing/partial markers are unknown and never reset or automatically repeated, including after manifest expiry. Identity inspection is separate from current-time authorization; a new expired manifest cannot launch.

The model-facing input still has only text. Host fixture configuration supplies the image, private journal, exact expected digest and trusted callbacks. Each callback must return exactly `True`: before creation, immediately before start, and before receipt acceptance. These callbacks use synthetic local authority, **not database approval, policy, grants, root budget or cancellation**. Phase 8.2b must establish that application boundary independently.

Before start, the launcher verifies UID/GID 10001, read-only root, no network, no mounts, private PID/IPC namespaces, dropped ALL capabilities, no new privileges, one CPU, 128 MiB memory/no swap and 32 PIDs. It explicitly empties proxy environment fields and allows only reviewed image metadata variables; no DB/owner/provider configuration or Docker socket is mounted. A non-root job runs directly as PID 1; the reviewed application secret-copy entrypoint is not used.

Host stdin writes and stdout/stderr reads use nonblocking bounded pipes. Text is at most 4096 UTF-8 bytes, the manifest wire bound is 32768 bytes, and stdout/stderr are capped at 1024 bytes each. Parent draining/startup is bounded by manifest expiry and a 30-second backstop; individual Docker control calls have 30-second timeouts. The job has an independent two-second explicit-exit watchdog once its main function starts, including blocked stdin. Trusted module-import startup remains inside the parent manifest deadline. Cleanup may outlast ticket expiry; that never grants more job authority. The parent verifies and persists an accepted metadata receipt while current, before slow container teardown.

Fixed reviewed resource probes separately exercise kernel limits and lifecycle behavior. They are test code, never model-selected jobs or accepted runner receipts. Probe work also has a two-second watchdog; the independent job-watchdog case disables the probe timer so only the actual job timer can terminate PID 1. Normal completion/failure/cancellation cleans known container IDs. Process death or an unconfirmed Docker-create timeout can leave a fixture resource for verified operator cleanup; a missing client response is not permission to repeat creation.

## Validation and regressions

The first unit/contract command passed 85 tests in 17.50 seconds, but it did not establish namespace PID 1 watchdog behavior. An initial container command was interrupted after **6 failures in 62.94 seconds**: pre-start environment validation rejected automatically injected proxy fields, and some 10-second create calls timed out. No normal job receipt was accepted. Three stopped, fixture-labeled containers with the expected image were inspected and removed explicitly. Proxy fields are now cleared and verified empty, and bounded Docker control timeouts allow startup separately from actual job work.

A dedicated test against the old image reproduced the watchdog gap: default SIGALRM disposition did not terminate namespace PID 1; blocked input returned after ten seconds and the process exited 2 rather than the required watchdog 124 (**1 failed in 36.33 seconds**). The job now installs an explicit `os._exit(124)` signal handler and does not extend an inherited earlier timer. The corrected unit/contract command passed **85 tests in 36.72 seconds**.

The subsequent focused container command passed **14 tests in 161.81 seconds**. It covered a real pinned job/receipt and duplicate fence; actual namespace/privilege/read-only/network/cgroup state; kernel OOM kill; PID exhaustion; a parallel CPU probe within the configured quota; stdout/stderr overflow; timed termination; independent PID 1 watchdog; cancellation after observing a running container; cancellation before start; changed code pin and post-result authority denial; and actual process exit/fresh-interpreter replay before creation and after computation. Known resources were removed, including explicit cleanup after the deliberate process-exit case.

After that command, five default-deny/unpinned-image cases and an expired-existing-fence case were added. The final guard command passed **6 tests, 85 deselected in 1.79 seconds**. It verifies no Docker contact or persistence when disabled/unpinned, and no launch for an expired request while preserving unknown identity on repeats. The final full run below covers this refinement together with all earlier cases.

The final single Docker-enabled backend run passed **456 tests in 989.47 seconds (16:29)** on the final source/image, including all 91 runner contract/job unit cases, all 14 runner container cases, and the nine earlier broker container cases. All Docker acceptance cases were enabled; this run includes the final default-deny and expired-duplicate refinements.

The final image built (`sha256:3a09b46dceae29d88ca027e2ee8d0b51af5d5c1a282dacf6e7892055e58ca584`). The earlier focused container proof used the preceding hardened build (`df684885...`); the final full command uses the final image. Alembic metadata check reported `No new upgrade operations detected.` No SQLAlchemy model or migration is added. After the full run, a fresh isolated Compose project initialized both databases, ran API/worker as UID 10001, passed authenticated fixture execution and independent egress-denial checks, then removed all fixture-owned resources. A separate fenced non-root resource probe confirmed the kernel `memory.swap.max` value was `0`, with its container removed. Product import/source and local documentation-link checks passed.

```sh
PYTHONPATH=backend/src APP_DATABASE_URL=postgresql+psycopg://postgres:phase1fixture@127.0.0.1:55433/workforce_test /tmp/workforce-venv/bin/pytest -q backend/tests/test_runner_fixture_job.py backend/tests/test_reviewed_runner_contract.py
WORKFORCE_DOCKER_GATE=1 PYTHONPATH=backend/src APP_DATABASE_URL=postgresql+psycopg://postgres:phase1fixture@127.0.0.1:55433/workforce_test /tmp/workforce-venv/bin/pytest -q -x backend/tests/test_runner_isolation_gate.py
WORKFORCE_DOCKER_GATE=1 PYTHONPATH=backend/src APP_DATABASE_URL=postgresql+psycopg://postgres:phase1fixture@127.0.0.1:55433/workforce_test /tmp/workforce-venv/bin/pytest -q -x backend/tests
BUILDX_CONFIG=/tmp/workforce-buildx docker build --secret id=proxy_ca,src="$CODEX_PROXY_CERT" -f docker/backend.Dockerfile -t workforce-backend:phase1 .
/tmp/workforce-venv/bin/python scripts/clean_compose_smoke.py
```

## Limits and next gate

This proves the reviewed job/local resource fixture, not safe arbitrary generated code, a VM boundary or product authorization. Containers share the host kernel. CPU quota/configuration and bounded observed demand are verified; reserved performance or adversarial kernel resistance is not claimed. Clock checks use the same host clock.

The journal must remain the same intact private operator-owned namespace. Lost/replaced/stale journals, profile/image lifecycle and stale DB-plus-journal recovery are not solved by this local fence. Before any product runner or external write, Phase 8.2b must derive exact image/code/input scope from committed authority, persist an independent database admission before launch, recheck current approval/policy/grants/root budget/cancellation, reject cold-journal repeats and accept a result only after post-effect authority. No application provenance or automatic model context is created here.

Only local isolated fixtures, synthetic authority and temporary private secrets were used. No browser, host reboot, power-loss/corruption/restore acceptance, real outbound read, paid call, merge, public deployment or production integration occurred.
