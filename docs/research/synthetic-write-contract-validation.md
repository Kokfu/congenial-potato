# Inert synthetic write receipts and reconciliation: Phase 8.3a

Date: 2026-10-16. Branch: `phase-8-write-receipt-contract`. Parent: draft PR #62 (`2c24cf9`).

## Boundary

One inert intent describes `synthetic.record.replace` in a UUID-identified synthetic ledger/record. It binds project, agent, root and logical invocation, expected revision, bounded content digest/size, exact approval-payload hash and policy-snapshot hash. Its canonical SHA-256 binds every field; canonical key ordering/UUID/time representation is deterministic. Inputs contain metadata only, with no arbitrary command, path, endpoint, credentials or raw content. An approval hash supplied to this parser is a claim to bind later, not evidence of database approval.

A strict applied receipt binds that intent digest, one event UUID, aware application timestamp, exact next revision and exact content digest/size. Signing requires an explicit fixture flag and a caller-held 32-byte key. Verification authenticates a key holder and matching metadata, not actual execution or external truth. The HMAC domain is distinct from runner/broker results and reconciliation replies. Historical applied metadata has no execution expiry/permission semantics; a future executor must separately check fresh authority and consumed admission.

Reconciliation queries bind the intent digest, caller-generated UUID nonce and aware issued time. Replies bind the exact query, observation timestamp and explicit `applied`, `not_applied` or `unknown`. Applied requires the matching receipt, with application time no later than observation; other outcomes require explicit absence of a receipt. Observation must follow query issuance and cannot be in the future. Changing the nonce, issue time or intent defeats replay into another query. Fresh unpredictable nonce generation belongs to the trusted future caller. No outcome carries retry permission: even a signed `not_applied` is fixture evidence only and cannot reset consumed admission or authorize another effect.

The strict parser bounds characters and UTF-8 bytes before JSON validation (8192); rejects duplicate keys, non-finite values, extra fields and primitive coercion; and revalidates copied models. Content is bounded at 4096 bytes; revisions use a bounded nonnegative precondition and exact successor. Key distribution/rotation, confidential transport, database approval/current grants/policy/budget/cancellation, executor admission, immutable accepted records, ledger storage and reconciliation policy are deliberately not implemented by this contract.

No tool registration, API/worker import, runner job change, ledger mutation, product dispatch, model context or real outbound effect is added. The existing fixed runner remains a digest-only job; these contracts do not turn it into a writer.

## Validation

The first focused file passed **57 tests in 8.85s**. After simplifying the shared strict version validator and adding query/boundary cases, the final combined contract command passed **212 tests, 1 skipped in 40.05s**. This includes all **64 new write-contract cases**, existing runner result/manifest contracts and the read-broker contract. The skip is the existing explicitly gated Docker signing bridge, previously verified in the parent runner evidence; it is not a new write integration.

Tests exercise all three reconciliation outcomes, exact canonical identity, empty/maximum content and revision bounds, each scope/resource/approval/policy/content/precondition substitution, invalid receipt shape and valid-MAC binding tampering, copied-model validation, unknown/extra/hostile fields, malformed keys, disabled-before-parsing signing, duplicate/non-finite/oversized/unsigned/cross-domain data, query nonce/time/intent transfer and impossible receipt/observation states. No test performs an external write.

The backend image built as `sha256:ec070f3ffeab1d5b6c9259158de050d595d99d5c621e503df563f13fa35961c5`. A UID 10001/read-only/network-none probe confirmed product imports omit the write-contract module and explicit metadata import succeeds. Alembic metadata reported `No new upgrade operations detected.` All 79 local links across modified documents resolved and `git diff --check` passed.

```sh
# Repository root, PYTHONPATH=backend/src and APP_DATABASE_URL points at
# an owned disposable workforce_test PostgreSQL fixture on loopback:
/tmp/workforce-venv/bin/python -m pytest -q -x backend/tests/test_synthetic_write_contract.py backend/tests/test_runner_result_contract.py backend/tests/test_reviewed_runner_contract.py backend/tests/test_read_broker_contract.py
BUILDX_CONFIG=/tmp/workforce-buildx docker build --secret id=proxy_ca,src="$CODEX_PROXY_CERT" -f docker/backend.Dockerfile -t workforce-backend:phase1 .
# backend/ with the same APP_DATABASE_URL:
/tmp/workforce-venv/bin/alembic check
```

The prior full backend run (663 passes, 32 Docker skips), 152-test Docker-enabled runner command and fresh isolated Compose proof remain historical. No schema/dependency/runtime wiring changes are made; full backend, browser, kernel-isolation, Compose recreation and restore tests were not repeated for this inert metadata module. Host contract tests use Python 3.12.14; image import uses Python 3.12.12.

## Next task and limits

Next exercise a private local fake ledger with these exact intent/receipt/reconciliation contracts. Preserve single logical effect identity across concurrent delivery and process loss, distinguish unknown from authoritative absence, reject changed intents/preconditions, and never use a status reply as launch permission. This remains separate from database-governed product effect admission/acceptance. Keep real writes, product runner/read dispatch, paid activation, merge, public deployment and production integration closed. Physical power loss, stale database/journal restore, hostile hosts and production key/transport lifecycle remain unverified.
