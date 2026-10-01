# Phase 0 validation: status and execution protocol

Status: NOT RUN. Architecture direction and bounded validation are authorized.

## Session capability

The documentation session can read/write through GitHub. It has no shell, local filesystem editor, Docker runner or PostgreSQL execution tool. Documentation inspection and repository publication do not count as runtime validation.

Do not report a pass/fail for unexecuted experiments.

## Run manifest

Record environment/OS/architecture, dependency versions, source commit, commands, start/end timestamps, logs, database state/effect counts, and result per case. Use immutable candidate commits and selected licenses. Revalidate current API docs against pinned dependencies.

Fixtures use synthetic projects/agents/data and fake provider responses. No paid models, company credentials or production integrations. Keep resource/time limits. Do not build application features as a side effect.

## Paperclip adoption cases

| ID | Experiment | Pass evidence |
|---|---|---|
| P01 | Same identity changes provider/runtime | ID/history unchanged; compatible task result |
| P02 | Cross-project retrieval/artifact/task access | Denied read/write; no leaked snippets |
| P03 | Approval wait, restart process, then decide | Request survives; correct continuation |
| P04 | Change args/schema/target after approval | No effect; new approval required |
| P05 | Native shell/network alternate paths | Cannot bypass configured authority |
| P06 | Duplicate dispatch/replay mutation | One logical effect, stable identity |
| P07 | Concurrent delegation and root cap | Atomic admission prevents overspend |
| P08 | Cancel tree with pending tool/approval | No subsequent effect; existing effect visible |
| P09 | Restart around schedule occurrence | At most one logical run; bounded catch-up |
| P10 | Review provenance | Actor/task/run/tool/artifact/approval connected |

Use existing fixtures where possible. Read implementation for bypass surfaces; source claims alone do not pass runtime cases. Mark unsupported experiments unknown, not failed.

## DBOS recovery cases

| ID | Experiment | Pass evidence |
|---|---|---|
| D01 | Successful fake model step, crash before next | Recorded result reused; successful step count one |
| D02 | Persist wait, terminate/restart, signal | Wait survives; correlated resume |
| D03 | Duplicate workflow submission | Stable workflow ID, one logical run |
| D04 | Fake external effect then crash before checkpoint | No blind duplicate; reconciliation requirement demonstrated |
| D05 | Cancel pending/active work | Checkpoints recheck cancel before new effect |
| D06 | Schedule restart/misfire | Document actual dedupe/overlap semantics |
| D07 | Versioned code update with in-flight work | Recovery/version limitations documented |

D04 must demonstrate why durable steps alone cannot guarantee external exactly-once behavior. Use a separate fixture effect ledger, not a real service.

## Decision gate

Adopt/extend Paperclip if requirements pass with modest documented extensions. Keep its stack rather than rewriting it. If core execution/security replacement is necessary, proceed with custom control plane + existing components.

Report extension scope, risks, license/version evidence, estimated maintenance burden and remaining unknowns. Supersede ADRs if the choice changes. No substantial implementation before report.

## Results

- Paperclip: not executed.
- DBOS: not executed.
- Live provider calls: none.
- Adoption recommendation: pending executable evidence.
- App implementation: not started.
