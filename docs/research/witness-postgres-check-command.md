# Reproducible disposable PostgreSQL check: Phase 8.4bg

Date: 2026-10-16. Branch: `phase-8-witness-postgres-check-command`. Parent: draft PR [#130](https://github.com/Kokfu/congenial-potato/pull/130), commit `33a56137ee140c71523c63bacb334ecfa2ad759f`.

The earlier PostgreSQL checks used a temporary setup script. The repository now has [a bounded command](../../scripts/check_local_witness_postgres.py) that creates fresh disposable databases, runs migrations and the selected witness cases, and cleans up its own exact resources. The existing [database-free command](witness-local-check-command.md) remains separate.

## Prerequisites and invocation

Use Linux with peer-credential Unix sockets, access to the local Docker Unix socket, and host routing to a Docker internal bridge address. This command does not support a remote Docker daemon or an existing database URL. Install `backend/requirements-dev.lock` in a disposable virtual environment and explicitly provision the pinned PostgreSQL image first; the script itself never pulls images:

```sh
python -m venv /tmp/witness-postgres-venv
/tmp/witness-postgres-venv/bin/python -m pip install -r backend/requirements-dev.lock
env -u DOCKER_HOST -u DOCKER_CONTEXT -u DOCKER_TLS -u DOCKER_TLS_VERIFY -u DOCKER_CERT_PATH \
  docker --host=unix:///var/run/docker.sock pull \
  postgres@sha256:00bc86618629af00d2937fdc5a5d63db3ff8450acf52f0636ec813c7f4902929
/tmp/witness-postgres-venv/bin/python scripts/check_local_witness_postgres.py
# Optional: all synthetic admission cases, including migration safeguards:
/tmp/witness-postgres-venv/bin/python scripts/check_local_witness_postgres.py --full-admission
```

The command statically checks the product/fixture import boundary, verifies the image is present, then creates a uniquely named/labeled internal network and a PostgreSQL 17.6 container with no published ports or host mounts. It inspects the internal-network, port, mount and tmpfs configuration before startup. Database data lives in tmpfs; resource limits are 512 MiB, one CPU and 128 PIDs. Trust authentication is confined to this unpublished local fixture. A TCP readiness check avoids the image's temporary initialization server; the command creates separate fresh application and DBOS test databases.

Child environment values always override application/workflow database URLs with the inspected private fixture address and set a zero daily cap. Inherited `DBOS__*`, `PYTEST_ADDOPTS` and `PYTEST_PLUGINS` selectors are removed; pytest plugin autoload is disabled. Docker context/host/TLS selectors are removed while Docker proxy/registry configuration remains available. No environment values or credentials are dumped.

Application/workflow migrations precede either the fixed seven-case witness selection or the fixed full admission file. No arbitrary pytest target or existing database is accepted. Each subprocess has a timeout. Cleanup runs on success and ordinary failure, verifies exact names and this invocation's unique label, attempts both removals and reports any cleanup failure. It never prunes shared resources. Forced interpreter/host termination can prevent cleanup; this is not a resource-lifecycle guarantee.

## Recorded checks

- Default command: **7 passed, 28 deselected in 15.55s**; both migrations and the 65-file product import check passed; own container/network removed.
- Full admission command: **35 passed in 72.76s**; both migrations and the 65-file product import check passed; own container/network removed.
- Controlled failure after database setup and before migrations propagated the injected error after removing both own resources.
- Inert environment probes verified that sentinel existing URLs/cloud/pytest/Docker-host selectors are overridden or removed and Docker configuration is preserved, without connecting to the sentinel destinations. The script compiled to temporary bytecode and `--help` passed without Docker operations.
- A development run initially rejected a pre-start inspection representation; its container/network were removed. The final check uses the daemon's configured tmpfs map before startup.

Changed-document local links and `git diff --check` passed. The separate 120-case database-free suite was not rerun for this command increment.

## Evidence boundary

These commands exercise PostgreSQL admission, local witness protocol/RPC and the fake ledger with synthetic data. Full admission includes the expected no-witness joint-rollback gap, and success does not repair it. They do not start standalone product services or enable live providers. No actual backup restore, independently protected infrastructure, remote transport, real effect adapter or physical power-loss guarantee is established. Product dispatch and all real-write, paid-model, deployment, merge and production gates remain disabled under the [external prerequisites](witness-trust-boundary-lifecycle.md).
