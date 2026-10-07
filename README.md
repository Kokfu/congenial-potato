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

Open `http://localhost:8080` and sign in as the provisioned owner. Only the web service binds the host, on loopback. The initial password file is read on first bootstrap; changing it later does not rotate the stored password. The Compose migration service runs once per startup before API and worker. The database and artifact directories use named volumes.

## Verify and restore

```sh
docker compose ps
docker compose logs --tail=100 api worker
docker compose exec db pg_dump -U postgres -Fc workforce > workforce.dump
docker compose exec db pg_dump -U postgres -Fc workforce_dbos > workforce_dbos.dump
```

Keep both dumps, the `artifacts` volume, and local secret files together under protected backup. To restore to a fresh installation, stop API/worker, restore both databases with `pg_restore -U postgres -d <database> --clean --if-exists`, restore artifact files and secrets, then run migrations and start services. Test a restore on a disposable installation before relying on it. Incompatible DBOS workflow versions must retain an old worker until outstanding histories drain.

## Development checks

Use PostgreSQL test databases and synthetic secrets. Apply migrations with `cd backend && APP_DATABASE_URL=... alembic -c alembic.ini upgrade head`. Run `PYTHONPATH=backend/src APP_DATABASE_URL=... INITIAL_ADMIN_PASSWORD_FILE=... pytest backend/tests` against a database named `workforce_test`. Build the UI with `cd frontend && npm ci && npm run build`. No paid provider or external tool is configured.
