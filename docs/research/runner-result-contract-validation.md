# Authenticated transient runner results: Phase 8.2b.5a

Date: 2026-10-16 (Asia/Kuala_Lumpur). Branch: `phase-8-runner-result-contract`. Parent: draft PR #58 (`a0e8451`).

## Boundary

A strict, bounded envelope authenticates the fixed job's metadata receipt with an explicitly injected 32-byte host result key. That key must differ from the private admission capability and is never supplied to the job container. The HMAC uses a runner-result-specific domain, separate from broker results. Signatures bind exact project/agent/root/attempt, immutable image ID, admission capability hash, reviewed job/profile/input/manifest digests, input size and a host-observed completion timestamp inside the current manifest lifetime. Wire input is at most 8192 UTF-8 bytes; duplicate JSON keys, non-finite values, extra fields, primitive coercions, altered bindings and expired manifests fail closed. Signing is disabled unless explicitly enabled.

This is a pure transient contract: verification does not query the database or grant execution authority. A trusted caller must recheck database admission/authority independently. The test-only bridge checks fresh authority after the isolated receipt and around host signing. Its per-run result key is held outside container configuration, mounts and commands. The envelope includes metadata only, with no input text, raw private capability or signing key.

Authentication establishes that a holder of the trusted host result key signed the metadata. It is not a hardware/container execution attestation, proof of external truth or protection from a compromised host/key holder. Both signing and verification share trusted host clocks. There is no public RPC, key configuration/rotation/recovery integration, database result acceptance, new tool/API/worker route, context promotion or product dispatch.

## Validation

The first contract/manifest/job command passed **136 tests in 28.74s**. A Docker-enabled combined result/admission command passed **109 tests in 81.94s**: both real bridge cases ran, including host-only signing with a fresh per-run key, key absence from inspected container configuration, no mounts, no leftover runner container and retained unknown database state. This command also covered the existing admission mutation/concurrency/process-loss/rollback fences. It preceded the final early character-count refinement and three extra oversized/untyped signer cases.

The tests reject semantic alterations even with recomputed valid MACs: changed scope, image, private-capability hash, receipt input/profile/code/manifest metadata, sizes and timestamps; unsupported/coerced versions; wrong/weak/reused keys; extra fields; duplicate/non-finite/oversized/unsigned JSON; wrong HMAC domain; transfer to changed admission; and actual manifest expiry. The signer and verifier bound character count before UTF-8 encoding; the receipt's existing byte-size validator remains enforced.

The initial image `sha256:a5f02c03c99505ceb0fcaf070128d02bf58cc4295a9df4fffee21e013b83ee57` passed a UID 10001/read-only/network-none probe: product imports omitted result/job modules, and the explicit metadata contract imported successfully. All 75 modified-document local links and whitespace checks passed. The final image built as `sha256:dd00745cb70fea2a9d5892bc9c8f17e5894cd41aab545b0cedf4f9acd294898a`. On final source/image, all **49 result contract tests passed in 20.38s**, with the Docker host-signing case enabled and no skips. The final non-root/read-only/network-none import probe passed too. Post-run Alembic metadata check reported `No new upgrade operations detected.`

The parent #58 full run passed 582 tests with 24 Docker cases skipped; it is historical evidence and was not repeated for this inert contract. Full legacy kernel resource-isolation, browser, reboot, restore and fresh Compose tests were not repeated here. Parent #58 fresh Compose/egress proof remains distinct. No schema or production dispatch change is made.

```sh
# From repository root, with PYTHONPATH=backend/src and APP_DATABASE_URL pointing at workforce_test:
/tmp/workforce-venv/bin/pytest -q -x backend/tests/test_runner_result_contract.py backend/tests/test_reviewed_runner_contract.py backend/tests/test_runner_fixture_job.py
WORKFORCE_DOCKER_GATE=1 /tmp/workforce-venv/bin/pytest -q -x backend/tests/test_runner_result_contract.py backend/tests/test_runner_admission.py
WORKFORCE_DOCKER_GATE=1 /tmp/workforce-venv/bin/pytest -q -x backend/tests/test_runner_result_contract.py
BUILDX_CONFIG=/tmp/workforce-buildx docker build --secret id=proxy_ca,src="$CODEX_PROXY_CERT" -f docker/backend.Dockerfile -t workforce-backend:phase1 .
# From backend/, with the same APP_DATABASE_URL:
/tmp/workforce-venv/bin/alembic check
```

## Next gate

The database attempt remains `unknown` and the invocation remains `approved_staged`, including after a verified envelope. Next persist at most one exact accepted result from this envelope plus fresh database authority; handle duplicate/concurrent/lost results without another job launch; and verify grant/cancellation/expiry changes during computation and delivery. Keep a recorded historical result distinct from current permission to execute. Production key/image/transport lifecycle, stale restore, physical power loss, arbitrary generated code and all real outbound integrations remain open/disabled. No paid call, merge, public deployment or production integration is authorized.
