# Durable local recovery-witness prototype: Phase 8.4a

Date: 2026-10-16. Branch: `phase-8-durable-local-recovery-witness`. Parent: recovery-gate draft PR #72 (`1f41251`).

## Implemented boundary

`backend/tests/durable_local_recovery_witness.py` is a test-only protocol prototype. It keeps a monotonic generation, idempotent reservation rows, consumed invocation identities and a small append-only event sequence in a dedicated SQLite file. `BEGIN IMMEDIATE` serializes reservation, generation-advance and consume transitions. A reservation binds a caller request UUID to one caller, ledger UUID, invocation UUID, intent digest, generation and nonce. Exact issue retries return the same reservation; conflicting retries and alternate reservations for the invocation fail closed.

Consume verifies the durable reservation, state-key ticket MAC, exact binding and current generation before atomically marking it spent. A lost consume response leaves the invocation spent; a retry receives a denial and cannot mint another reservation. A consumed invocation remains spent after generation advance. Missing or corrupt witness state, unavailable service state, invalid caller authentication, malformed bindings, stale tickets, conflicts and invalid response MACs fail closed. Responses are separately authenticated and the fixture caller verifies them before reading status.

The fixture remains under `backend/tests`; no product module, worker, dispatcher, database admission service or fake-ledger production path imports it. The transport is a direct in-process test call: there is no socket listener, TLS, remote identity provider, hardware key, independently administered host, or production service. The SQLite file is only a protocol-state stand-in. Its storage can be replaced or rolled back, as a negative test demonstrates. A third file on the same host is not a protected external trust domain.

## Key and transport lifecycle

Tests inject synthetic 32-byte keys directly. The caller authentication key signs canonical operation requests; a distinct witness state key signs reservation tickets; the caller key also authenticates canonical responses. No key is generated, persisted, provisioned, rotated, revoked or recovered by this prototype, and no secret is included in fixture request bodies or logs. Production prerequisites remain an independently administered witness identity, protected key custody with separation of caller/state/response roles, authenticated encrypted transport (for example mutually authenticated TLS with explicit peer identity and rotation), overlap/revocation rules, audited key backup/recovery, and a tested generation-preserving restore procedure. Rotation must not erase reservations or consumed identities. Outage restore must not silently bootstrap a missing state file or reset a generation.

## Fixture checks

The standalone protocol tests cover exact idempotent reserve retry, conflicting reservation identity, lost reserve and consume replies, durable process restart in a fresh interpreter, generation advancement and stale-ticket denial, concurrent single-winner consume, request and response authentication, fail-closed outage, missing/corrupt state, and explicit witness-file rollback weakness. A related integration case in `test_synthetic_write_admission.py` now uses this prototype around the actual test-only governed fake-write bridge and checks control-row deletion, ledger-file deletion and coordinated rollback after reopening the witness object.

Commands run:

```sh
cp backend/tests/test_durable_local_recovery_witness.py /tmp/test_durable_local_recovery_witness.py
PYTHONPATH=/tmp/phase84-python:backend/tests python -m pytest -q -x -p no:cacheprovider /tmp/test_durable_local_recovery_witness.py
python -m py_compile backend/tests/durable_local_recovery_witness.py backend/tests/test_durable_local_recovery_witness.py
python -m py_compile backend/tests/test_synthetic_write_admission.py
git diff --check
```

Result: **10 passed in 0.11s**; both compilation commands and whitespace check passed. Pytest 9.1.1 was installed under `/tmp/phase84-python` because the runtime package directory is read-only. The test file was copied to `/tmp` to bypass the repository-wide `conftest.py`, which enforces a disposable PostgreSQL database even for this standard-library-only module.

The database/ledger integration test was not executed in this container. `docker ps` failed with permission denied on `/var/run/docker.sock`; this environment has no available disposable PostgreSQL fixture. Earlier PR evidence covers the pre-existing PostgreSQL/SQLite wrapper using the in-memory simulator, but does not validate this new durable prototype's integration wrapper. It remains a required next local fixture check.

## Evidence limits and next gate

These are synthetic protocol and local filesystem results only. Tests demonstrate state across a fresh interpreter while the same file remains present, not physical power-loss durability, filesystem/fsync guarantees, database backup consistency, service replacement safety, protection from an administrator, or recovery from restoring the witness file itself. A negative test copies an old witness SQLite file back and shows that the invocation can be reopened. Coordinated application-control/fake-ledger rollback is blocked only while the witness state is retained. No safety claim is made for protected infrastructure or real external effects.

Keep product execution disabled. Next, run the actual PostgreSQL plus fake-ledger rollback wrapper against this prototype in an isolated fixture, including replacement and outage restore cases, then review an authenticated local transport prototype separately. Production use requires independently protected infrastructure, a real authenticated transport and key lifecycle, external audit/restore controls, threat review, and explicit separate authorization. No physical power-loss guarantee has been tested.
