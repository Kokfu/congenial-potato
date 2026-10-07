# Phase 0 validation — 2026-10-07

Status: bounded experiments executed; Paperclip adoption gate **not cleared**. Architecture direction was already approved. This report records what ran and what remains unknown. No application, production integration, paid model call, public service, deployment, or merge was made.

## Environment and pins

- Checkout: `Kokfu/congenial-potato`, documentation PR #1 head `f7e470220cac1bb65bfad0b66d43d7b2f0e07e26`; Phase 0 branch based on that commit. No `AGENTS.md` found. Documentation was read before implementation decisions.
- Linux x86_64 kernel 6.18.44; Python 3.12.14; Node 24.19.0; Docker Engine 28.4.0. Disposable PostgreSQL image `postgres:17.6`, pulled digest `sha256:00bc86618629af00d2937fdc5a5d63db3ff8450acf52f0636ec813c7f4902929` (PostgreSQL license). The container published only `127.0.0.1:55432` with synthetic credentials.
- Paperclip source commit `a9a20fb5c6c080884ced7ee0a4e3b04f9cbf3a6e`, MIT `LICENSE`, declared pnpm 9.15.4, Node >=24.11.0. The repository has no single root package version. Local clone was outside this repository. Its lockfile changed **locally** during install and was not used as a pristine frozen lock.
- DBOS Python 3.2.0 (MIT package metadata), installed in a disposable venv with transitive versions recorded in [requirements.lock](../../experiments/dbos/requirements.lock). PostgreSQL holds DBOS state; `fixture.events` and `fixture.effects` are separate synthetic ledgers. No optional outbound telemetry was configured.

## Reproduce

```sh
# Paperclip: use the pinned commit, no credentials or model calls.
git clone https://github.com/paperclipai/paperclip.git /tmp/phase0-paperclip
git -C /tmp/phase0-paperclip checkout a9a20fb5c6c080884ced7ee0a4e3b04f9cbf3a6e
cd /tmp/phase0-paperclip
export COREPACK_HOME=/tmp/phase0-corepack XDG_DATA_HOME=/tmp/phase0-xdg XDG_CACHE_HOME=/tmp/phase0-xdg-cache
corepack pnpm install --frozen-lockfile --ignore-scripts # fails: patchedDependencies mismatch
corepack pnpm install --no-frozen-lockfile --ignore-scripts
corepack pnpm --filter @paperclipai/plugin-sdk ensure-build-deps
corepack pnpm exec vitest run server/src/__tests__/tool-gateway-service.test.ts server/src/__tests__/budgets-service.test.ts server/src/services/native-runtime/assigned-mcp-tools.test.ts
corepack pnpm exec vitest run server/src/__tests__/agent-adapter-validation-routes.test.ts server/src/__tests__/heartbeat-referenced-projects.test.ts server/src/__tests__/company-artifacts-service.test.ts server/src/__tests__/issue-monitor-scheduler.test.ts
```

The first run of the second Vitest command failed to resolve `@paperclipai/plugin-sdk`; building that workspace package fixed the harness, and the rerun passed. These are Paperclip's existing fixture tests, not a full product deployment. Embedded PostgreSQL and scripted providers are used by relevant suites. This managed environment required access to its local process sockets for embedded PostgreSQL.

```sh
# DBOS: disposable local PostgreSQL, synthetic password and data.
docker run -d --name phase0-dbos-pg -e POSTGRES_PASSWORD=phase0fixture \
  -e POSTGRES_DB=phase0 -p 127.0.0.1:55432:5432 postgres:17.6
python -m venv /tmp/phase0-dbos-venv
/tmp/phase0-dbos-venv/bin/pip install -r experiments/dbos/requirements.lock
# From this repository's root; drops only the fixture database's dbos/fixture schemas.
./experiments/dbos/run.sh | tee experiments/dbos/evidence.log
```

`run.sh` expects a dedicated disposable database at `PHASE0_DB_URL` (default above) and resets its `dbos` and `fixture` schemas. It intentionally exits worker processes with codes 41/42/43/44 to emulate crashes. [Full run log](../../experiments/dbos/evidence.log) retains timestamps and state counts.

## Paperclip adoption evidence

The two clean fixture runs reported **67/67** and **70/70** tests passing. They exercise approved-call races, signed arguments, review delivery, budget service behavior, assigned MCP tools, adapter routes, project references, artifact service and a scheduler. The initial install and test-harness failures above were setup failures, not product invariant failures. Existing assertions do not automatically establish the broader Phase 0 cases.

| Case | Status for required scenario | Executed evidence and gap |
|---|---|---|
| P01 provider/runtime switching | Not executed | Adapter route fixture changed provider config and retained fields. No persistent agent ID/history was checked across two fake provider executions. |
| P02 project access | Not executed | Project-reference and artifact fixtures passed. No combined unauthorized task, memory and artifact probe with zero metadata leakage ran. Paperclip uses company and project scopes that need explicit mapping to the required agent grants. |
| P03 durable approval wait | Not executed | Gateway fixture includes a service-recreation review delivery test. No worker process restart during a real pending approval ran. |
| P04 approval integrity | Not executed | Gateway tests passed for signed arguments, stale/closed issue, and review races. Schema change and target-version mutation after approval were not exercised together against a live restart fixture. |
| P05 complete mediation | Unsupported | Paperclip's pinned `doc/MCP-ACCESS-GOVERNANCE.md`, line 135, explicitly says V1 cannot prevent/audit direct upstream MCP calls by unmanaged clients or hand-edited adapter config. Gateway fixtures do pass for **assigned** tools. No isolated native shell/filesystem/network bypass trial ran; complete mediation is unproven and the documented unmanaged path falls outside gateway enforcement. |
| P06 duplicate execution | Not executed | Gateway fixture passed the approved identical-argument race and one execution. Repeated task dispatch and process replay of a logical mutation were not tested. |
| P07 shared root budget | Not executed | Budget service fixtures passed, but there was no concurrent child reservation test against one root cap. |
| P08 tree cancellation | Not executed | No full delegated tree with pending approval/tool was cancelled. |
| P09 restart scheduling | Not executed | Scheduler fixture passed, but no process restart around one scheduled occurrence and bounded catch-up was measured. |
| P10 provenance | Not executed | Gateway fixtures populated call/review records. No task-agent-execution-tool-approval-artifact version chain was traced. |

No P-case is claimed as an end-to-end pass. Paperclip source and fixture tests show substantial reusable work, especially governance within its gateway. They do not establish the required containment outside the gateway or the complete project/root-budget model. A current Paperclip install with an OS-isolated runner, a single mediated tool route, project grant enforcement, and durable end-to-end fixtures would be needed to reverse this result.

### Extension scope and maintenance

Adoption would require a restrictive runner boundary for native shell/filesystem/network and alternate runtime paths, not just changes to tool prompts; app-level project authorization across tasks/memory/artifacts; atomic shared root reservations; approval/checkpoint behavior through process loss; scheduling semantics; and a full provenance graph. These changes touch runtime launch, gateway, persistence and lifecycle modules and must track a fast-moving upstream. The local frozen-lock mismatch and 36-workspace dependency build increase upkeep. This is core control-plane work, not a modest UI or adapter extension.

## DBOS recovery experiment

The [probe](../../experiments/dbos/probe.py) uses DBOS workflows/steps/waits, PostgreSQL and a separate effect table. The [run script](../../experiments/dbos/run.sh) controls crash/restart stages. Results below refer to the recorded clean run; all model responses and external effects are synthetic.

| Case | Result | Observed state and limit |
|---|---|---|
| D01 saved model step | Passed | Worker exited after `model` step; restart returned `fake-model-result`; `model` event count stayed 1. |
| D02 durable correlated wait | Passed | After restart, `send(workflow_id, {'request':'approval-1','decision':'approve'}, 'approval')` resumed the wait; `after_signal` count became 1. A wrong-topic/forged decision test was not run. The workflow checks the payload; a production approval ledger must decide authority. |
| D03 duplicate submission | Passed | Two `start_workflow` calls under `SetWorkflowID('phase0-dedupe')` returned `done`; logical `run` event count was 1. This does not test an app outbox. |
| D04 post-effect crash | Passed as limitation demonstration | First step attempt inserted one row into `fixture.effects`, then exited before checkpoint. Recovery ran the step again: attempt count 2, effect row count 1 only because the **separate ledger's unique key and `ON CONFLICT DO NOTHING`** reconciled it. Without that key, duplicate effects remain possible. Unknown real outcomes require inquiry/reconciliation, not blind retries. |
| D05 cancellation recheck | Passed for fixture | A persisted app cancellation flag was read after a wait and before the effect: result `stopped`, effect count 0. Separately, DBOS cancellation while waiting left status `CANCELLED`, effect count 0; it logged `DBOSAwaitedWorkflowCancelledError`. In-flight external effects cannot be undone. |
| D06 restart scheduling | Partially passed | One-second UTC schedule with `automatic_backfill=False` produced five unique occurrence keys across a ~3-second worker gap; no duplicate key was recorded. The log shows the exact timestamps and omitted occurrences. It did **not** test overlap, DST or bounded coalescing, so the application must define these rules. |
| D07 workflow version changes | Passed as limitation demonstration | A v1 workflow was `PENDING` at crash; restarting the same code with `application_version=2` left it `PENDING` and `version_finish` count 0. Restarting v1 and signaling completed it, count 1. DBOS recovery filters by application version (`dbos/_recovery.py`); compatible old workers must drain outstanding v1 histories. Changing workflow code within a version can break replay. No migration of an actual incompatible workflow body was attempted. |

DBOS is useful for checkpoints, waits, deduplication and schedules. It is not an authorization service, cancellation fence for all external effects, or exactly-once external effect engine. The custom architecture must own policy, approval ledger, idempotency keys, reconciliation, budgets and schedule admission.

## Recommendation and ADR disposition

**Proceed with the approved component-plus-small-control-layer architecture; do not adopt Paperclip as the product base at this gate.** Its gateway and UI remain reference implementations. The documented mediation limit and unproven root/project invariants make adoption a high-maintenance rewrite of core behavior. This is an evidence-bound decision, not a claim that Paperclip is generally insecure.

ADR 001 (custom Python/API and React stack), 003 (Pydantic AI behind a replaceable boundary), 004 (project-scoped PostgreSQL memory), and 005 (application-owned provider contract) remain proposed direction; none is asserted as runtime-validated by these experiments. ADR 002 gains bounded DBOS evidence, with explicit side-effect/version/schedule limitations. No ADR is superseded because the stack decision has not changed. Revisit dependency versions and licenses before foundation implementation.

## Smallest next foundation phase

Create only the persistence/control shell: PostgreSQL migrations for owner, project, agent/config revision, task/execution, policy/audit/outbox, budget reservation and immutable artifact metadata; API plus separate worker process; secure owner bootstrap; a versioned workflow boundary; and Docker/Compose/`.env.example` with health and restore instructions. Use fake providers and an artifact fixture, with no general shell/network tools.

Acceptance: clean Compose build/start and login; worker survives API/browser shutdown; restart reuses one fake model result; duplicate dispatch and concurrent child reservations cannot double spend; default-deny project access and exact approved artifact replacement remain enforced after restart/cancellation; one idempotent effect and unknown-outcome reconciliation path are demonstrated; persisted audit/provenance and backup/restore are verified. Foundation development starts only as the next task after this report.
