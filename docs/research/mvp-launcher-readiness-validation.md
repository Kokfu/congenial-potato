# Local launcher readiness and Windows diagnosis

Date: 2026-10-18. Branch: `mvp-launcher-readiness`. Parent: draft PR [#144](https://github.com/Kokfu/congenial-potato/pull/144), commit `bac869af4a6c79433106454934f42964fe466715`.

The launcher previously returned success as soon as it found a running owned web container. It skipped requested builds and Compose readiness reconciliation, so a stopped API/worker could remain unavailable and the guide's rebuild instruction was ineffective. Two regression methods reproduced the parent behavior: both build/no-build subcases skipped reconciliation, and a simulated Compose readiness failure was never reached or propagated.

Running start now preserves the owned port and continues through the normal startup path. Plain start requests a build; `--no-build` retains existing images. Both reconcile all services and use Compose's bounded readiness wait. A failed Compose command remains a nonzero CLI result. Changing a running workspace's port still refuses and requires an explicit stop.

The new `doctor` action checks Python 3.10+, the existing local-only Linux Docker Engine 28+ requirement, Compose v2+, free loopback-port availability, and retained configuration/resource ownership when present. It validates Compose configuration quietly without starting/stopping containers or initializing a new workspace. It only checks password-file existence; it does not read or print their contents. Non-object runtime JSON now denies with a normal validation error. The [Windows guide](../local-workspace-guide.md) includes the new preflight and correct running-start behavior.

## Actual validation

```sh
python -m unittest discover -s scripts/tests -p test_local_workspace.py -v
python scripts/local_workspace.py doctor
python scripts/local_workspace.py start --no-build
```

- **17 launcher checks passed in 0.013s**, with sandbox network permission for the real port tests. They include the ten prior checks plus running-start/build/no-build/readiness failure regressions, fresh/retained/missing-file doctor behavior, legacy Compose denial and malformed runtime JSON. Guarded reads verify doctor never opens either password file; temporary-directory tests verify no initialization or password replacement.
- Real doctor passed for a nonexistent temporary state directory and the retained managed-Linux workspace: Python 3.12, Docker 28.4.0, Compose 2.40.3. The nonexistent state directory stayed absent. Exact owned Docker resource sets and retained file sizes/mtimes were unchanged.
- Deliberately stopped **only the owned worker**, leaving web running. Real `start --no-build` recovered the worker, waited for the existing stack, retained the same project and loopback port **52113**, and preserved **11 projects, 8 agents and 2 artifact versions**. This is a running-service recovery check, not backup restoration or Windows acceptance.
- Help, two Python compilations, changed-document links and whitespace checks passed. No new frontend/full-backend/recovery-witness runtime result is claimed; the previous five-case browser run remains [separate evidence](mvp-artifact-browser-validation.md).

The managed cloud session still has no connection to the owner's Windows PC. Doctor passing is not proof of Docker Desktop network isolation, image builds, application startup or service availability on that hardware. Port selection remains non-atomic and concurrent launcher/file manipulation is not a hardened boundary. Paid models, real external effects, production connections, public deployment and merging remain disabled.
