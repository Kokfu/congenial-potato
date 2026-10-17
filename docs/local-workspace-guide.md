# Run the fixture workspace on your computer

This is a private local prototype, with synthetic model/tool execution only. You do not need to deploy publicly or connect production accounts. The cloud workspace used for development is a separate computer; a cloud localhost URL is not reachable as localhost on your PC.

## Prerequisites

- Python 3.10+ and Git.
- Docker Engine 28+ with Docker Compose and Linux containers. Windows/macOS normally use Docker Desktop. The application requires its existing Linux bridge isolation features; Windows/macOS hosting has not yet been validated on the owner's hardware.
- Free disk/memory for PostgreSQL, API, worker and web images. First build requires package/image downloads; no paid model is used.

Check out the branch containing this guide, not the repository's initial `main` README-only checkpoint. Use the current draft PR's head branch or GitHub's branch selector. Open a terminal in that checkout.

For the owner's confirmed Windows + Docker Desktop setup, start Docker Desktop and select **Linux containers** (the WSL 2 backend is suitable). Check `docker version` and `docker compose version` in PowerShell. If you do not have a checkout yet, use a new directory so your other project is left alone:

```powershell
git clone --branch mvp-project-briefs https://github.com/Kokfu/congenial-potato.git workforce-local
Set-Location workforce-local
py scripts/local_workspace.py doctor
py scripts/local_workspace.py start
```

The `mvp-project-briefs` branch includes this plan, launcher, artifact UI, readiness fixes and saved project briefs. If that directory already exists, use your existing checkout or choose a different new directory; do not overwrite another project. Actual startup on the owner's Windows machine remains a required owner check because the development session cannot access that PC.

`doctor` checks Python, a local Linux Docker Engine 28+, Docker Compose v2+, availability of a free loopback port, and any retained workspace files/resource labels. It does not initialize a workspace, start or stop containers, read password contents or print them. A successful diagnosis is a prerequisite check, not proof that your particular Windows networking/build/startup will succeed. You may share its non-secret status/error messages when troubleshooting; keep the password files private.

## Start without conflicting with another project

Windows:

```powershell
py scripts/local_workspace.py start
```

macOS/Linux:

```sh
python3 scripts/local_workspace.py start
```

The launcher builds project-specific image tags, creates a uniquely named Docker Compose project and persistent volumes, generates private local passwords, and chooses an unused loopback port. It prints your actual URL, such as `http://localhost:49152`, and the owner-password **file path**. Read that file locally to sign in; do not send or commit its contents. Files live under `.local/mvp/`, which Git ignores. On Windows, keep that directory restricted to your Windows account.

For a particular port, use `start --port 49152`. If occupied, startup refuses without stopping the other application. Port selection and Docker bind are separate operations; a race can still fail startup, but the launcher does not kill another process or bind publicly. Start again to select another free port.

Only web publishes a port, on `127.0.0.1`. Application/database/worker services remain on the isolated control network. A remote Docker context is refused. There is no owner-PC remote connection or public hosting configured by this repository.

## First useful walkthrough

1. Open the printed URL and sign in with your locally generated owner password.
2. On Projects, create a project with an optional brief (up to 20,000 characters). The saved brief appears below the project selector and survives reload. Briefs are owner reference only: fixture runs do not consume them. Existing briefs cannot yet be edited. This selects the project for the following grant.
3. On Agents, add an agent with a fixture provider/model, then choose **Grant project execution** for that agent.
4. Return to Projects, choose the agent, add a task, and choose **Run fixture**.
5. Refresh until the task reaches `review`. This is synthetic background execution, not a live AI answer.
6. On Approvals, inspect the exact proposed artifact content and approve it. Open **Artifacts**, select the project, and inspect the saved version, content, SHA-256 digest, author and execution identity. Use **Reload outputs** after a new approval. Errors are shown rather than substituting unverified content; artifact text is displayed literally rather than executed.
7. Inspect Activity and Collaboration for recorded events and proposal review. Settings identifies the fixture-only model mode.

Execution grants and approvals are separate: granting an agent does not approve arbitrary external actions. Paid models, real outbound effects, arbitrary shell/browser tools and production integration remain disabled.

## Stop, restart and inspect

```sh
python3 scripts/local_workspace.py status
python3 scripts/local_workspace.py stop
python3 scripts/local_workspace.py start --no-build
```

Use `py` instead of `python3` on Windows. Stop preserves containers, volumes, runtime metadata and passwords. A later start may print a different free port, while retaining the same project and data. If web is already running, start retains its port, reconciles the entire owned stack and waits for readiness; it can recover a stopped worker/API without creating a second copy. Plain `start` rebuilds images after source changes, even while running; `start --no-build` checks/reconciles using existing images. Readiness failures return a nonzero exit status. To change the port, stop this workspace first.

Do not delete `.local/mvp/` to reset a password: its generated password must stay paired with the existing initialized database. If a retained password file is missing, startup refuses to invent a replacement. Keep local credentials and both database/artifact backups together under your own protection. Actual backup/restore and protected-infrastructure guarantees are separate from a healthy restart.

## Browser checks on the chosen port

Install frontend dependencies with `npm ci` in `frontend`, then install a Playwright browser with `npx playwright install chromium` if needed. Set `WORKFORCE_BASE_URL` to the launcher's printed origin and `WORKFORCE_PASSWORD_FILE` to the absolute owner-password file path before `npm exec playwright test` in `frontend`.

`PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH` optionally selects an existing Chromium. `WORKFORCE_BROWSER_NO_SANDBOX=1` is only for an isolated test environment that requires it; normal PC runs should use the browser sandbox. Tests create synthetic projects, agents, tasks and approvals in the selected fixture workspace. Never aim them at a production system.

## Troubleshooting and scope

- Docker unavailable: start Docker Desktop/Engine and select a local Linux context. Remote endpoints are intentionally refused.
- Docker isolation/network feature unavailable: update to a supported Engine/Compose; do not remove the isolation settings to make it run.
- Build fails in a managed proxy environment: `--build-ca /path/to/public-ca-bundle.pem` supplies an optional build-time trust bundle without disabling TLS verification. This is not normally needed on a personal PC.
- Startup fails: data is preserved. Use `status` and the named project's Docker logs; do not prune Docker resources or delete another project's volumes.
- No real AI answer: expected. This milestone verifies the workflow using fixtures. Protected credentials, verified prices and capped live-provider activation remain a separate milestone.

See [the MVP completion plan](mvp-completion-plan.md) for current work and [progress.md](../progress.md) for recorded validation results and limitations.

For the intended source-notes → reviewed plan → cited draft path, see the [document workflow plan](document-workflow-plan.md). Only saved reference briefs and the synthetic review path are available now; useful real-model drafting remains gated.
