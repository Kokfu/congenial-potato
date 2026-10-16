# Local authenticated witness transport prototype: Phase 8.4c

Date: 2026-10-16. Branch: `phase-8-local-witness-transport`. Parent: durable witness restore-drill draft PR #74 (`0c98b33`).

## Local transport

Phase 8.4ar follow-up: the [socket liveness guard](witness-socket-liveness-guard-validation.md) refuses to unlink active endpoints, fails closed when probing is inconclusive and preserves an observed replacement inode. Process fixtures now wait for an authenticated reply without preemptively removing the path. These are non-atomic local checks, not an independent ownership or locking guarantee.

Phase 8.4an follow-up: [exchange freshness](witness-rpc-exchange-freshness-validation.md) adds a required authenticated per-exchange nonce to local RPC frames. A captured reply to an identical earlier request no longer matches the current client's outbound MAC; no durable nonce cache, remote transport or anti-rollback storage is added.

Phase 8.4am follow-up: [response/request binding](witness-rpc-response-binding-validation.md) replaces the test-only v1 response envelope with v2, authenticating the exact request MAC and requiring the client to compare it. The original Phase 8.4c behavior and results below are historical; response freshness for identical requests remains a separate gap.

`backend/tests/durable_local_witness_transport.py` adds a test-only JSON request/response transport over a Unix domain socket. The fixture server checks Linux `SO_PEERCRED` and requires the connecting process to run as the configured local UID (the current UID in this prototype). The socket directory must be an owned mode-0700 directory, and the socket is mode 0600. The client sends the caller identity and an HMAC over the canonical request. The witness checks that MAC; the client verifies the response MAC before using any returned status. Frames are newline-delimited and capped at 16 KiB. Unknown, malformed, oversized, unauthenticated and unavailable requests fail closed.

The server and caller run as separate local processes in the transport test. It exercises request authentication, response authentication, exact reservation retry, consume, caller-key denial, server outage, server replacement/restart, and persistence of a spent identity across that restart. The server uses the existing SQLite witness protocol state and does not import or connect to product dispatch.

## Key and transport lifecycle

Transport-test keys are generated as fixed synthetic byte strings in the test and copied into a mode-0600 fixture config solely so the child process can load them. The config file is in a private temporary directory and is removed with the test fixture. The server never accepts caller or witness keys in an RPC request. The caller key authenticates requests and responses; the distinct state key authenticates reservation tickets. This is a local proof of protocol wiring only. UID checks and filesystem socket permissions do not establish a separate administrative trust domain, and HMAC does not provide confidentiality. There is no TLS, remote certificate authority, secure enclave, secret manager, key rotation/revocation workflow, production audit sink, or production endpoint.

A production transport would require an independently administered remote service, mutually authenticated encrypted transport with reviewed peer identity, separate caller/state key custody, rotation overlap and revocation, monitored service identity changes, an auditable generation high-water mark, and a restore procedure that preserves consumed reservations. Those controls require separately authorized infrastructure and operational evidence.

## Validation

```sh
cp backend/tests/test_durable_local_recovery_witness.py /tmp/test_durable_local_recovery_witness.py
cp backend/tests/test_durable_witness_fake_ledger_recovery.py /tmp/test_durable_witness_fake_ledger_recovery.py
cp backend/tests/test_durable_local_witness_transport.py /tmp/test_durable_local_witness_transport.py
PYTHONPATH=/tmp/phase84-python:backend/tests:backend/src python -m pytest -q -x -p no:cacheprovider /tmp/test_durable_local_recovery_witness.py /tmp/test_durable_witness_fake_ledger_recovery.py /tmp/test_durable_local_witness_transport.py
python -m py_compile backend/tests/durable_local_recovery_witness.py backend/tests/durable_local_witness_transport.py backend/tests/run_durable_local_witness_server.py backend/tests/test_durable_local_recovery_witness.py backend/tests/test_durable_witness_fake_ledger_recovery.py backend/tests/test_durable_local_witness_transport.py backend/tests/test_synthetic_write_admission.py
PYTHONPATH=backend/tests python -m unittest -v test_synthetic_write_recovery_witness
git diff --check
```

Result: **19 pytest cases passed in 0.56s** across the durable state, fake-ledger restore, and local transport suites; the original process-local witness regression passed **9 tests**. Compilation, focused Markdown links, and whitespace checks passed. The Unix socket tests ran with the sandbox's local socket permission enabled; their code opens only filesystem Unix sockets and makes no network connection. New pytest suites were copied outside `backend/tests` because the repository `conftest.py` requires a disposable PostgreSQL database for all in-tree pytest collection. The transport suite also confirms an owned stale socket path is replaced and an insecure socket directory is rejected.

## Limits

This is same-host local transport evidence over Unix sockets, not a remote authenticated channel. It assumes Linux peer credentials and one local UID. The control-state restore harness uses SQLite, and the witness SQLite file itself remains replaceable. Tests do not establish protection from the host administrator, independent key custody, PostgreSQL integration, cross-host outage behavior, external execution truth, physical power-loss behavior, or production restore safety. Keep product dispatch disabled and do not treat these results as production authorization.
