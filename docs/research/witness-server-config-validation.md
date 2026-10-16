# Local witness server configuration validation

Phase 8.4k makes the local server reject duplicate JSON keys and unknown or
missing server configuration fields before it opens the socket. Caller and
state keyring forms require their matching current key IDs; alternate
single-key fields cannot be mixed with keyring configuration. The separate
client-process fixture configuration is no longer included in the server
configuration. A process test exercises rotation with distinct client and
server files: old and replacement caller keys overlap, the replacement key
serves requests, then restart with only the replacement rejects the retired
key and still denies the already consumed invocation.

Both files are synthetic fixture configuration with local mode-0600
permissions. This reduces configuration ambiguity in the prototype; it does
not provide protected config distribution, secret storage, external caller
identity, filesystem race protection, or production key rotation. The
transport is a same-host Unix socket and product dispatch remains disabled.

## Checks

The focused suites were copied to `/tmp` to bypass the repository-wide
`conftest.py` Docker/PostgreSQL fixture. Command:

```text
PYTHONPATH=/tmp/phase84-python:backend/tests:backend/src python -m pytest -q -x -p no:cacheprovider /tmp/test_durable_local_recovery_witness.py /tmp/test_durable_witness_fake_ledger_recovery.py /tmp/test_durable_local_witness_transport.py
```

Result: **30 passed in 0.92s**. Sandbox permission for the local Unix socket
was enabled. Keys, identities, and state were synthetic.

## Phase 8.4ap: typed recovery-admin allowlist

Date: 2026-10-16. Branch: `phase-8-witness-admin-config-types`. Parent: local check command draft PR #113.

The server previously converted `advance_callers` directly to a frozen set. With configured callers `a` and `b`, the malformed string `"ab"` became two administrator names; a disposable local probe confirmed caller `a` could advance generation to 2. A mapping of those names also reached server construction, and duplicate list entries were silently collapsed. These are configuration interpretation failures in the local fixture, not evidence about a deployed service.

The optional field now requires a JSON list containing unique, nonempty strings before conversion. Omission means an empty allowlist; explicit null, strings, objects, booleans, numbers, non-string/empty members and duplicates reject. The existing witness constructor continues to reject names absent from the caller key configuration.

Nine invalid-config cases verify denial before server construction, no socket creation and byte-identical witness state. Four valid cases (omitted, empty, one caller, two callers) load configuration without starting a server, then exercise actual generation authorization and confirm the exact resulting generation and audit caller history. All three newly tightened rejection cases failed on the parent and pass with this validation.

```sh
/tmp/witness-local-venv/bin/python scripts/check_local_witness.py
git diff --check
```

Result: **80 local cases passed in 2.33s** and **15 files compiled**, including all earlier protocol, fake-ledger, nonce and separate-process cases. Changed-document Markdown links and whitespace checks passed. The suite's Unix-socket fixtures used sandbox permission; the new configuration cases intercepted server construction and opened no socket. PostgreSQL/product integration remained unrun.

This change supplies type checking, not protected configuration delivery, key custody or independent recovery administration. The [external lifecycle prerequisites](witness-trust-boundary-lifecycle.md) remain unmet. Product dispatch, real external writes, paid models, deployment and production integration remain disabled; no protected-infrastructure or physical power-loss claim is made.
