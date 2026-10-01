# Deployment

Status: approved design. No deployable application/Docker build exists yet.

## Topology

Compose: web static UI/same-origin proxy; FastAPI api; same-image worker; one-shot migrate; PostgreSQL application/workflow databases. Local model optional later.

Only web binds host, loopback by default. Internals/private health remain private. No Redis/object-store service needed initially.

## Required foundation files

- `docker/backend.Dockerfile`: locked dependency builder, minimal non-root runtime, API/worker code, no secrets.
- `docker/web.Dockerfile`: Node static build, minimal non-root serving/proxy stage.
- `docker-compose.yml`: health/dependencies/restarts/limits/volumes/one-shot migrations.
- `.env.example`: names/placeholders only.

Pin supported dependency/image versions/digests after validation. Unbuilt templates must not be claimed tested deployment artifacts.

## Persistence/secrets

Volumes: PostgreSQL, immutable artifacts; separately encrypted browser profiles later.

Mounted secrets: database credentials, encryption master key, bootstrap account material. Provider keys added securely and encrypted, never image-baked.

Configuration inventory:

```dotenv
PUBLIC_BASE_URL=http://localhost:8080
APP_DATABASE_URL=
DBOS_SYSTEM_DATABASE_URL=
CREDENTIAL_KEY_FILE=/run/secrets/credential_key
INITIAL_ADMIN_PASSWORD_FILE=/run/secrets/admin_password
ARTIFACT_ROOT=/var/lib/workforce/artifacts
DEFAULT_TIMEZONE=Etc/UTC
MODEL_CONCURRENCY=2
DAILY_BUDGET_AMOUNT=
DAILY_BUDGET_CURRENCY=USD
LOG_LEVEL=INFO
```

This is design inventory, not working deployment. Actual secret wiring/bootstrap follows in foundation. Production HTTPS/cookie settings required.

## Startup/health

API liveness: process. Readiness: DB/schema dependencies. Worker health: process/heartbeat/queue/recovery. Optional provider outage is separate health, not API unreadiness.

1. Validate secrets/config.
2. Start PostgreSQL and await health.
3. Migrate once under lock.
4. Bootstrap owner only if none.
5. Start API/worker.
6. Start web.
7. Verify login/health/fixture.

No racing migrations on ordinary startup.

## Backup/update

Consistent app/workflow database backups, artifact bytes and separately protected master key. Document restore order/permissions/schema/recovery checks. DB backup without key cannot restore credentials.

Drain incompatible updates; retain old workflow code for active runs.

## Portability

Same images on VM/on-premise. BlobStore/SecretStore adapters allow managed services. AWS/Tencent optional, no core dependence. Add TLS/private networking/backups/egress controls. Kubernetes only when warranted.

Browser closure does not stop work; laptop sleep/shutdown does.

## Foundation acceptance

Clean Compose startup; non-root/no secrets; migrations/secure bootstrap; health/restart recovery; artifacts/history persist across replacement; backup/restore documented; key rotation.
