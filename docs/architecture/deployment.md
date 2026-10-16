# Deployment

Status: private synthetic Compose foundation implemented and locally verified. Product outbound reads, native paid activation and production integration remain gated. See [current Phase 7 acceptance](../research/phase-7-acceptance.md) for exact results and limits.

## Topology

Compose: web static UI/same-origin proxy; FastAPI api; same-image worker; one-shot migrate; PostgreSQL application/workflow databases. Local model optional later.

Only web binds the host, on loopback by default. Docker Engine 28+ with the Linux bridge driver is required: db/migrate/api/worker use an internal isolated control network without a host gateway or default route. Web also joins an ingress network and proxies the fixed API. Run the synthetic egress smoke after startup/network changes. No broker service, Redis or object-store service is configured.

## Required foundation files

- `docker/backend.Dockerfile`: locked dependency builder and API/worker code. The reviewed entrypoint starts as root to copy mounted Compose secrets into private tmpfs, drops supplementary groups/GID/UID, then execs application code as UID 10001. This is not a rootless entrypoint or a hostile-code sandbox. No secrets are baked into the image.
- `docker/web.Dockerfile`: Node static build, minimal non-root serving/proxy stage.
- `docker/postgres.Dockerfile`: pinned PostgreSQL 17.6 plus the reviewed init script owned by postgres, mode 0500. Avoids dependence on host bind-script permissions. Database PID 1 ran as UID 999 in the fresh-volume fixture.
- `docker-compose.yml`: health/dependencies/restarts/limits/volumes/one-shot migrations.
- `.env.example`: names/placeholders only.

Image tags/dependencies are pinned in these files and lockfiles; base-image digest pinning is still later supply-chain work. Builds and non-root process probes are recorded in evidence, not inferred from templates.

## Persistence/secrets

Volumes: PostgreSQL, immutable artifacts; separately encrypted browser profiles later.

Current mounted secrets: `.local/db_password` and `.local/initial_admin_password`. Keep their files private and outside Git. The bootstrap password initializes an absent owner; changing the file does not rotate an existing owner password. Provider keys, an encryption master key and encrypted credential rotation are future activation work, not implemented Compose secret services.

Current local configuration (`.env.example`):

```dotenv
PUBLIC_BASE_URL=http://localhost:8080
SESSION_COOKIE_SECURE=false
BIND_ADDR=127.0.0.1
PORT=8080
# Optional opt-in priced synthetic calls; Compose defaults to disabled (0):
# DAILY_CAP_USD=1.00
# MODEL_CALL_TIMEOUT_SECONDS=20
```

Compose fixes the database host/names and mounted secret paths for trusted API/worker/migration code. Direct `APP_DATABASE_URL` / `DBOS_SYSTEM_DATABASE_URL` settings support isolated development/testing; never put credentials in model context. Any future remote access requires separately authorized TLS, secure-cookie and private-network policy.

## Startup/health

API liveness/readiness and Compose database/web health checks are implemented. The worker has no separate Compose healthcheck; process state and successful fixture execution provide the local evidence here. Do not infer complete worker/queue observability from API health.

1. Validate secrets/config.
2. Start PostgreSQL and await health.
3. Run the one-shot application and DBOS migration service before dependent API/worker services.
4. Bootstrap owner only if none.
5. Start API/worker.
6. Start web.
7. Verify login/health/fixture.

Ordinary Compose dependencies serialize this local startup. Multi-host migration coordination is not established by that ordering. After building images, `scripts/clean_compose_smoke.py` proves fresh-volume startup in its own disposable namespace with synthetic secrets; it does not reset the regular application.

## Backup/update

Back up both application/workflow databases, artifact bytes and protected local secrets consistently; [README](../../README.md) documents the existing fixture backup/restore procedure. Future encrypted credentials additionally require the separately protected master key. The clean-startup slice did not repeat a restore drill.

Experimental broker attempts introduce a separate recovery boundary: restoring stale control DB plus broker key/journal copies may erase unknown external outcomes. No broker is deployed here, and the existing fixture backup procedure is not production broker recovery evidence. Quiescence, ticket invalidation/key lifecycle and external reconciliation must be verified before product reads.

Runner fixtures add the same recovery constraint: stale application DB restoration can erase consumed admission or accepted-result history even if a host journal/key survives. No runner service, Docker socket or result key is configured in Compose. Current process-exit/replay tests do not validate runner key rotation or restore; product runner execution stays closed. See [runner fixture acceptance](../research/governed-runner-acceptance.md).

Drain incompatible updates; retain old workflow code for active runs.

## Portability

Same images on VM/on-premise. BlobStore/SecretStore adapters allow managed services. AWS/Tencent optional, no core dependence. Add TLS/private networking/backups/egress controls. Kubernetes only when warranted.

Browser closure does not stop work; laptop sleep/shutdown does.

## Foundation acceptance

Recorded fixture evidence covers clean Compose startup, non-root application processes, secret-free images, migrations/bootstrap, authenticated fixture execution, prior restart/persistence/restore exercises and local egress denial. Production credential/key rotation, remote transport, full worker observability and broker recovery remain open. Use the linked progress/evidence instead of treating this architecture checklist as a passing test report.
