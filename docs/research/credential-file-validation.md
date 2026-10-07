# Native adapter credential-file validation

Date: 2026-10-08. The native adapters are unregistered. Only synthetic keys were used; no provider request was made.

The offline adapters accept a secret through an absolute private file path or an injected test client. The file reader now opens the final path with `O_NOFOLLOW`, `O_CLOEXEC` and `O_NONBLOCK`, checks the opened descriptor is a regular file owned by root or the current process user, rejects any group/world permission, bounds input to 8192 bytes, and accepts one nonempty UTF-8 line. It reads from the checked descriptor and returns generic errors without including file contents. Tests reject final-component symlinks, directories, FIFOs, oversized or multiline values and invalid UTF-8; a private `0400` file succeeds.

The parent directories of the path must be a trusted secret mount; this reader does not defend against an attacker who can replace parent path components. The key still lives in trusted adapter process memory. Encrypted credential storage, key IDs/rotation, and brokered references from the approved security architecture are not implemented. This file check alone does not authorize native adapter registration.

## Reproduce

```sh
PYTHONPATH=backend/src APP_DATABASE_URL=postgresql+psycopg://postgres:<test-password>@127.0.0.1:55433/workforce_test INITIAL_ADMIN_PASSWORD_FILE=<synthetic-secret-file> SESSION_COOKIE_SECURE=false pytest -q backend/tests
docker build -f docker/backend.Dockerfile -t workforce-backend:phase1 .
```

The managed cloud build supplies its session proxy CA as a BuildKit secret. No credential file is copied into the image.

Result: **31 backend tests passed**. The backend image built. A separate `docker run` with network disabled, a read-only root filesystem and UID/GID `10001` created a synthetic `0400` key in a private tmpfs and constructed both offline adapters successfully (`private_secret_nonroot=passed`). It did not invoke a provider method or contact a network endpoint.
