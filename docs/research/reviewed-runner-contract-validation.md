# Inert reviewed-runner contract: Phase 8.1

Date: 2026-10-15 (Asia/Kuala_Lumpur). Branch: `phase-8-runner-contract`. Parent: draft PR #52 (`f8cfd9c`).

The first runner slice constructs data only. It adds no launcher, Docker access, API/tool registration, database attempt or worker dispatch. Phase 7 product reads remain disabled and native providers remain unregistered. General shell/browser execution and external writes remain deferred.

The model-facing proposal has exactly one field: bounded text. Unknown fields, including command, image, environment, credentials, scope, network, path and mount choices, are rejected. Text that looks like a command remains text; these parser tests do not claim arbitrary-code containment.

Trusted fixture code supplies project/agent/root/attempt UUIDs and aware timestamps. A strict frozen manifest binds these to the exact UTF-8 input size/digest, a fixed reviewed profile ID/revision/digest, and a lifetime of at most 30 seconds. Canonical serialization normalizes JSON representation and timestamps to UTC. Duplicate keys (including escaped equivalents), non-finite JSON, oversized wire/input data, invalid versions and copied-model validation bypasses are rejected. A verifier requires the expected canonical digest and a current time; exact expiry is denied. Validation errors suppress input-bearing exception context.

The one profile declares `synthetic.text-digest` revision 1: SHA-256 plus UTF-8 byte count, untrusted data input, UID/GID 10001, read-only/no-network, all capabilities dropped, no new privileges, one CPU, 128 MiB memory, 32 PIDs, two seconds of job time, 4096 input bytes and 1024 stdout/stderr bytes each, no host mounts or credential access. **These are declarations, not enforced runner acceptance.** A later executor must bind actual reviewed code and an immutable image identity before any launch; this manifest intentionally contains no caller-selected executable/image.

A manifest digest is not authentication, human approval, scope authorization or evidence that a process ran. Its trusted expected value must eventually come from a committed attempt and fresh database policy. The contract cannot independently discover changed grants, cancellation or budgets; Phase 8.2 must establish pre-launch/post-result authority and unknown-outcome handling outside product dispatch.

## Validation

The new contract suite passed **57 tests in 6.91 seconds**. It covers canonical/escaped Unicode and timezone forms; model execution-field smuggling; malformed, ambiguous and deeply nested JSON; UTF-8/wire limits; changed scope/input/expiry; invalid profile/digest/size/version values even with a recomputed hash; missing/duplicate manifest fields; exact issuance/expiry boundaries; invalid/naive/overflowing dates; copied-model revalidation; redacted error traces; and invalid expected digests.

Alembic metadata check on the separate migrated database reported `No new upgrade operations detected.` This slice adds no database model or migration. The parent Phase 7 full run passed 351 tests; a full 408-case backend run is not claimed. The focused suite is the backend validation for this new, isolated pure contract.

The backend image built: `sha256:fb55cff466eeefbe182ab97e9344224dbf4bc2122a095c7c52376fd6e50d5ea6`. A UID 10001, read-only/network-none container imported the contract and built/verified a synthetic manifest. That is an image compatibility probe, not execution of a runner job. A fresh isolated Compose project then migrated both databases, passed authenticated fixture execution and API/worker egress-denial checks, and removed all fixture-owned resources. After an environment reattachment, the preserved logs and exact image ID were reverified; those completed checks were not invented or rerun.

```sh
PYTHONPATH=backend/src APP_DATABASE_URL=postgresql+psycopg://postgres:phase1fixture@127.0.0.1:55433/workforce_test /tmp/workforce-venv/bin/pytest -q backend/tests/test_reviewed_runner_contract.py
# From backend with APP_DATABASE_URL selecting workforce_migration_check:
/tmp/workforce-venv/bin/alembic -c alembic.ini check
# From repository root, managed proxy CA build secret:
BUILDX_CONFIG=/tmp/workforce-buildx docker build --secret id=proxy_ca,src="$CODEX_PROXY_CERT" -f docker/backend.Dockerfile -t workforce-backend:phase1 .
/tmp/workforce-venv/bin/python scripts/clean_compose_smoke.py
```

Only synthetic local fixtures and private temporary secrets were used. This slice does not prove runner CPU/memory/PID/output/time enforcement, process cancellation/restart, signed receipts, reconciliation or hostile-code isolation. No browser, reboot, restore, public deployment, merge, paid call, real outbound read or production integration occurred.
