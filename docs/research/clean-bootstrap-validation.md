# Clean private-checkout Compose bootstrap: Phase 7.4n

Date: 2026-10-15 (Asia/Kuala_Lumpur). Branch: `phase-7-clean-bootstrap`. Parent: draft PR #50 (`3ca038b`).

Previous effect/isolation evidence reused repaired application volumes. A new disposable PostgreSQL volume reproduced the original bootstrap failure: the official entrypoint dropped to the database user and could not run the private checkout's bind-mounted `docker/init-db.sh` (`Permission denied`, exit 1). The source script and its directory are mode 0700 in this environment. That failed run and its owned container/volume were removed; it is not passing startup evidence.

The database image now copies the fixed reviewed initialization script with `postgres` ownership and mode 0500. Compose uses that image instead of bind-mounting the host script. PostgreSQL remains at the existing pinned 17.6 version. No host checkout or secret permissions were widened, and no existing database volume was reset.

`scripts/clean_compose_smoke.py` creates a unique Compose project, refuses pre-existing resources in its namespace, supplies synthetic mode-0600 secrets in a private temporary directory, and binds a temporary loopback port. It requires already-built reviewed images. It checks both databases, empty initial project state, actual PID 1 UIDs, authenticated fixture execution and independent egress denial. Its cleanup removes only its own project's containers, networks and volumes and verifies their absence. An occupied port fails startup and enters cleanup; there is no alternate public bind. `scripts/smoke.py` now accepts an explicit loopback origin/password path while preserving its original defaults.

## Validation

A separate collision probe supplied an existing fixture-labeled sentinel volume. The script refused the namespace before creating containers/networks or entering cleanup; the sentinel remained present until the probe removed it. An image probe as UID 999 confirmed script ownership `999:999` and mode `0500`; host script/directory modes remained 0700 and host secret files 0600.

The database image built successfully: `sha256:19f3454b9233dde8517b0330150b6aa15d964b35103c079ba791c92ae6e31ddd`.

The initial fresh Compose run passed: both `workforce` and `workforce_dbos` were created without manual SQL; database PID 1 ran as UID 999, API/worker PID 1 as UID 10001. The owner/CSRF/project/grant/task/worker fixture passed (`unauthorized_dispatch=403; execution=succeeded; task=review; audit=present`). API and worker had isolated routes and could reach the database, while direct HTTP/socket, proxy, CONNECT and web-forward bypasses to the reachable synthetic sink were denied. Fixture-owned resources were removed.

The final script, including namespace-collision refusal and cleanup verification, passed again on another fresh project. Its fixture smoke and API/worker egress checks passed, and all fixture resources were removed. A preservation check initially compared Docker’s unordered mount list as a sequence and failed on order alone; comparison of mount sets confirmed the same five original container IDs, mounts and network sets. The regular-stack default smoke then passed separately with unauthorized dispatch denied (403), successful fixture execution, task review and audit present.

Final script syntax checks passed. Four invalid smoke origins (HTTPS remote, HTTP remote, userinfo redirecting the host, and a loopback URL with a path) were rejected with exit 2 before attempting to read a deliberately nonexistent secret file. Alembic metadata check against the separate migrated database reported `No new upgrade operations detected.`

```sh
BUILDX_CONFIG=/tmp/workforce-buildx docker build -f docker/postgres.Dockerfile -t workforce-postgres:phase1 .
/tmp/workforce-venv/bin/python scripts/clean_compose_smoke.py
# Existing regular stack, unchanged defaults:
/tmp/workforce-venv/bin/python scripts/smoke.py
# From backend, separate disposable migration database:
APP_DATABASE_URL=postgresql+psycopg://postgres:phase1fixture@127.0.0.1:55433/workforce_migration_check /tmp/workforce-venv/bin/alembic -c alembic.ini check
```

This slice changes container initialization and fixture scripts, not backend application logic or schema. The parent's full Docker-enabled backend run passed 351 tests; that full suite was not repeated for these startup/script changes. The backend image is the verified admission build (`c6d12fa...`), and the web image is unchanged. No browser test, host reboot, restore drill, power-loss test or production filesystem/credential validation was run. The disposable database was a real empty named volume; this is not a claim about upgrading existing database contents or rotating stored owner passwords.

Only isolated local fixtures and synthetic secrets were used. Product read dispatch and automatic external context consumption remain disabled. Production broker key/confidentiality/clock-skew/restore policy, native paid activation and production integration remain separate gates. No merge or public deployment occurred.
