# Local MVP launch and first-use checkpoint

Date: 2026-10-17. Branch: `mvp-local-launch-workflow`. Parent: draft PR [#142](https://github.com/Kokfu/congenial-potato/pull/142), commit `b1f08c3fe747d5482e6b87ec1b6af4526b88602a`.

The owner authorized building and local hosting without reusing another project's port. This managed cloud session has no connection to the owner's PC. The [launcher](../../scripts/local_workspace.py) and [PC guide](../local-workspace-guide.md) prepare that workflow without claiming actual PC hosting. The [completion plan](../mvp-completion-plan.md) prioritizes a usable end-to-end product path over further recovery-prototype expansion.

The launcher selects a free `127.0.0.1` port, creates its own labeled Compose project, image tags and persistent volumes, and keeps generated credentials under ignored `.local/mvp/`. It refuses remote Docker endpoints, foreign project resources, occupied explicit ports and missing retained credential files. Stop preserves state; a later start can use a different port. Port selection/bind is non-atomic; a bind race can fail rather than evict another process. Local runtime file ownership/concurrent launcher coordination are not a hardened adversarial boundary.

Browser checks now accept `WORKFORCE_BASE_URL`, `WORKFORCE_PASSWORD_FILE` and optional browser selection rather than hardcoding port 8080, a Linux executable and the default project's password. Test HTTP Origin follows the selected origin. Ordinary PC browser checks retain their browser sandbox; the managed Linux test explicitly opted out as required by this environment.

## Actual results

- Ten standard-library launcher checks passed with sandbox network permission, including a real occupied sentinel listener that remained connectable, remote-daemon refusal, project label refusal, private exclusive secret creation, runtime validation and environment overrides. The initial sandbox-only run could not create sockets; the permission-enabled run passed.
- Backend, web and PostgreSQL images built with TLS verification and the managed proxy's public CA bundle as a build secret. The environment's read-only Docker buildx configuration required `BUILDX_CONFIG=/tmp/workforce-buildx`; Docker credentials/configuration were preserved. Project-specific builds then passed through the launcher.
- A fresh real Compose workspace started at cloud loopback port **47443**, with successful migrations, healthy database/API/web and a running worker. Only web published a loopback port; no production system or paid model was connected.
- `npm run build` passed. All **four Playwright browser cases passed in 9.4s** against the actual application at its selected port: project/agent/grant/task/approval and provider-fixture switching; runtime collaboration review; exact synthetic tool approval; and activity reconnect/cursor behavior. These used actual PostgreSQL/API/worker services, not the earlier screenshot's mocked GET API.
- The scoped `scripts/egress_smoke.py` passed: API and worker retained database access while direct/HTTP/proxy/CONNECT/arbitrary-web forwarding bypasses were denied. Its disposable synthetic sink was removed.
- Real launcher stop/start retained **4 projects, 4 agents and 1 artifact version**, the same Compose identity and owner password. Login and readiness succeeded after restart at cloud loopback port **52113**. While stopped, an explicit occupied-port start was refused without changing runtime metadata; the sentinel listener remained connectable. Normal restart then selected a free port.
- Help, browser collection (four cases), changed-document links and `git diff --check` passed. No new full backend or local-witness runtime rerun is claimed; the parent 174-case witness result remains historical.

## Limits and next increment

The owner PC's OS/Docker configuration and actual port availability remain unverified. Windows/macOS instructions are provided, but no Docker Desktop hardware/platform acceptance is claimed. The cloud URL is not a PC-accessible deployment. This checkpoint establishes a tested local fixture workflow, not real AI work, production readiness, backup restore or protected-infrastructure guarantees.

Next implement the plan's project-scoped artifact browser so an owner can inspect approved output directly in the UI. Live models, outbound tools, arbitrary shell/browser execution, production connections, public deployment and merging remain disabled. Protected credentials, verified pricing/caps, external recovery infrastructure and actual effect adapters remain separately gated.
