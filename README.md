# Workforce control plane

A private, self-hosted foundation for persistent agents, projects, tasks and controlled execution. The current worker runs **synthetic fixture results only**. Read [progress.md](progress.md) for completed work and next tasks, and [the architecture](docs/README.md) for the approved design.

## Local Compose startup

Requires Docker Compose. Create local secret files outside Git, then start:

```sh
mkdir -p .local
chmod 700 .local
python - <<'PY'
import secrets
from pathlib import Path
Path('.local/db_password').write_text(secrets.token_urlsafe(32))
PY
# Set a strong, private owner password yourself in .local/initial_admin_password.
chmod 600 .local/db_password .local/initial_admin_password
cp .env.example .env
docker compose up --build -d
curl -fsS http://localhost:8080/health/ready
```

Open `http://localhost:8080` and sign in as the provisioned owner. Only the web service binds the host, on loopback. The initial password file is read on first bootstrap; changing it later does not rotate the stored password. The Compose migration service runs once per startup before API and worker. The database and artifact directories use named volumes. Fixture runs create an artifact proposal; review its exact content in Approvals. The separate worker writes an immutable version only after approval.

## Verify and restore

```sh
docker compose stop api worker web
docker compose ps
docker compose exec -T db pg_dump -U postgres -Fc workforce > workforce.dump
docker compose exec -T db pg_dump -U postgres -Fc workforce_dbos > workforce_dbos.dump
docker run --rm --entrypoint tar -v workforce_artifacts:/data:ro workforce-backend:phase1 -C /data -cf - . > artifacts.tar
docker compose start api worker web
```

Keep both dumps, `artifacts.tar`, and local secret files together under protected backup. On a fresh installation with the same secrets, start only the database, restore both dumps, restore the artifact archive into the named volume, then start the remaining services:

```sh
docker compose up -d db
docker compose exec -T db pg_restore -U postgres -d workforce --clean --if-exists < workforce.dump
docker compose exec -T db pg_restore -U postgres -d workforce_dbos --clean --if-exists < workforce_dbos.dump
docker run --rm -i --entrypoint tar -v workforce_artifacts:/data workforce-backend:phase1 -C /data -xf - < artifacts.tar
docker compose up -d --no-build
```

A full disposable Compose restore was tested on a separate loopback port: owner login, seven project IDs, three artifact versions and their content digests matched the source. Recovery after a workflow-code upgrade remains an operational check. Incompatible DBOS workflow versions must retain an old worker until outstanding histories drain.

## Development checks

Use PostgreSQL test databases and synthetic secrets. Apply migrations with `cd backend && APP_DATABASE_URL=... alembic -c alembic.ini upgrade head`. Run `PYTHONPATH=backend/src APP_DATABASE_URL=... INITIAL_ADMIN_PASSWORD_FILE=... pytest backend/tests` against a database named `workforce_test`. Build the UI with `cd frontend && npm ci && npm run build`. No paid provider or external tool is configured.
