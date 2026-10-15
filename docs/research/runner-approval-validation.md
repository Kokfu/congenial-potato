# Exact staged runner approvals: Phase 8.2b.3

Date: 2026-10-15 (Asia/Kuala_Lumpur). Branch: `phase-8-runner-approval`. Parent: draft PR #56 (`90aa4a2`).

## Boundary

New runner proposals also snapshot the execution, agent and root IDs. Staging is an authenticated CSRF-protected owner operation on a `proposed` runner invocation. It locks the root and invocation, requires a succeeded uncancelled source, current project/agent policy, an active agent and the exact owner grant revision/pins, an uncancelled persisted root, and a root account with positive available balance. Older proposals lacking the new scope snapshot fail closed; their original rows are retained and require fresh fixture work to propose again.

Approval payload/hash bind canonical input/argument hash, definition/schema, project, execution, agent/root scope, fixed profile/revision/hash, immutable image ID, reviewed code digest and exact grant ID/revision. Expiry is no later than the grant expiry or one day. Pending staging replay rechecks current authority and invalidates stale approval/proposal pairs. Concurrent staging returns the same approval.

At owner decision, recompute the payload and canonical tool arguments, lock/recheck current policy/grant/agent/root/budget/cancellation, and check approval expiry again after authority lock waits. An owner approval persists only `approved_staged`. Owner rejection and cancellation remain durable. Already-decided replay returns the recorded decision metadata; it is not current permission to launch. A later attempt issuer must independently revalidate every condition and expiry, even when an approval says approved.

The shared staging implementation retains the web-specific route/action check. The product effect dispatcher still explicitly skips runner actions, including forged `admitted` status. No launcher import, Docker socket, service, runner attempt, manifest issuance, isolated execution, result provenance, automatic context or real external effect is introduced.

## Validation

The first focused run exposed a budget-boundary gap: **1 failed, 9 passed in 6.17s** because zero available balance was still accepted. Requiring strictly positive availability fixed it. The revised focused command passed **88 tests in 74.76s**. Two subsequently added PostgreSQL lock cases passed **2 tests, 37 deselected in 5.05s**: concurrent staging created one approval, and a real three-second expiry elapsed while decision waited on a policy row lock. The resumed decision invalidated the approval as expired; no fake clock or outbound transport was used.

Coverage includes exact input/pins/scope, wrong owner hash and CSRF, rejection/replay, changed grant revision/image/code/expiry/revocation, missing execution authority, inactive agent, policy deny, zero budget, cancellation/root/source changes, tampered schema/input/scope/approval, legacy scope snapshots, repeat pending staging, cancellation after approval, and the retained product-dispatch exclusion. Existing artifact/web-read approvals and fake effects passed in the focused command.

The final backend image built as `sha256:fddb3e74314fb24065258196eeb0e3f47f0742092d9b448f1045b0bb55aacb61`. A UID 10001/read-only/network-none probe verified the staged route and absence of fixture-job import. Source/OpenAPI checks, all 73 modified-document local links and whitespace checks passed. Fresh isolated Compose initialized both databases, ran non-root processes, passed authenticated fixture execution and independent API/worker egress denial, and verified resource cleanup.

The final full backend run passed **520 tests, 23 skipped in 498.99s (8:18)**. All 39 runner approval cases, including the two lock regressions, ran in this command. The 14 runner and nine broker Docker acceptance cases were skipped because `WORKFORCE_DOCKER_GATE` was not enabled. Historical Docker isolation acceptance remains in parent #54; no rerun or new isolated runner launch is claimed for this slice. Post-suite Alembic metadata check passed (`No new upgrade operations detected.`); this slice adds no schema change. Browser, reboot, power-loss and stale restore tests were not performed. Host tests use the locked dependencies on Python 3.12.14; the image uses Python 3.12.12. The image probe/startup is distinct from running the full suite inside the image.

```sh
PYTHONPATH=backend/src APP_DATABASE_URL=postgresql+psycopg://postgres:phase1fixture@127.0.0.1:55433/workforce_test /tmp/workforce-venv/bin/pytest -q -x backend/tests/test_runner_approval.py backend/tests/test_runner_proposals.py backend/tests/test_tool_approval.py backend/tests/test_tool_gateway.py backend/tests/test_tool_effects.py backend/tests/test_tool_gate.py
PYTHONPATH=backend/src APP_DATABASE_URL=postgresql+psycopg://postgres:phase1fixture@127.0.0.1:55433/workforce_test /tmp/workforce-venv/bin/pytest -q -x backend/tests/test_runner_approval.py -k 'concurrent or waiting'
PYTHONPATH=backend/src APP_DATABASE_URL=postgresql+psycopg://postgres:phase1fixture@127.0.0.1:55433/workforce_test /tmp/workforce-venv/bin/pytest -q backend/tests
BUILDX_CONFIG=/tmp/workforce-buildx docker build --secret id=proxy_ca,src="$CODEX_PROXY_CERT" -f docker/backend.Dockerfile -t workforce-backend:phase1 .
/tmp/workforce-venv/bin/python scripts/clean_compose_smoke.py
# From backend/, with the same APP_DATABASE_URL:
/tmp/workforce-venv/bin/alembic check
```

## Next gate and limits

Positive root balance here is a current authorization check, not a new resource reservation or a settled execution cost. Independent committed attempts must bind this exact approval plus fresh policy/grant/scope, commit admission before returning any launch capability, fence unknown/cold-journal replays, and validate authority again before accepting a result. No product dispatch should be enabled until this full boundary clears.

Source hashes/image IDs bind an owner-reviewed declaration, not independently authenticated execution evidence. Journal loss, stale database-plus-journal restore, physical power loss and product key/image lifecycle remain open. Arbitrary generated code, browser/shell, paid models, real outbound reads/writes, merge, public deployment and production integration remain disabled.
