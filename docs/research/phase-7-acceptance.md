# Phase 7 synthetic acceptance and product activation boundary

Date: 2026-10-15 (Asia/Kuala_Lumpur). Branch: `phase-7-fixture-acceptance`. Parent: draft PR #51 (`0db86e2`).

The Phase 7 **local synthetic acceptance** is complete. The **product outbound-read activation gate remains closed**. The application can record scoped proposals and exact staged approvals, but the worker cannot dispatch a read, contact the experimental broker or automatically consume fetched observations as context. This distinction does not authorize real reads, paid models or production integrations.

## Acceptance matrix

| Requirement | Verified implementation and evidence |
| --- | --- |
| Exact approval and current authority | Proposal, staging, decision, issuer and mediator recheck scope, exact payload/schema/policy, destination revision/expiry, root budget and cancellation. [Approval](read-approval-validation.md), [effect](read-effect-validation.md), [issuer](broker-issuer-validation.md), [results](broker-result-validation.md). |
| SSRF and destination binding | Strict HTTPS origin; all DNS answers must be public; re-resolution, numeric peer pinning and original-host TLS verification; redirect following denied. Fake DNS and mapped local origins only. [Network boundary](network-boundary-validation.md), [local TLS/deadlines](transport-deadline-validation.md). |
| Bounded resources | Shared absolute DNS/connect/TLS/read deadline, killed/reaped resolver child plus independent watchdog, bounded status/headers/chunks/body, bounded RPC frames and one active broker request. [Transport](transport-deadline-validation.md), [RPC](broker-rpc-validation.md). |
| Durable unknown outcomes | Attempt and exact ticket issuance committed before effect; broker fsynced marker before challenge; independent database permit consumption committed before authorization returns. Duplicate/concurrent/restarted attempts never blindly fetch again. Fresh empty broker replacement after fetch still sees one origin GET. [Contract](broker-contract-validation.md), [admission](broker-admission-validation.md). |
| Provenance after authority | Authenticated ticket-bound bounded reply; authority/expiry checks after lock waits and before commit; one immutable cited `external_claim`. Lost/unverified/disallowed results create no observation. [Observations](read-observation-validation.md), [results](broker-result-validation.md). |
| Hostile agent output | A deliberately compliant fake adapter sees the fetched claim through a test-only real-worker context seam. The real gateway denies secret/grant/scope/exfiltration attacks, retains exact approval for writes and leaves another same-host read inert. No model-resistance claim. [Worker injection](phase-7-fixture-gate.md), [separate containers](isolated-broker-validation.md). |
| Independent local isolation | API/worker lack a default route/host bridge gateway and cannot use direct sockets, HTTP, proxy, CONNECT or the web proxy to bypass mediation. Separate resource-bounded non-root broker cannot reach control DB and holds no DB/owner/provider configuration. [Egress](egress-denial-validation.md), [container proof](isolated-broker-validation.md). |
| Migration, images and startup | Data-bearing conservative admission migration, separate upgrade/downgrade/upgrade/metadata checks, non-root runtime probes, ordinary Compose smoke, and two fresh-volume isolated Compose startups with both databases, fixture execution, egress denial and owned-resource cleanup. [Admission](broker-admission-validation.md), [clean startup](clean-bootstrap-validation.md). |

The latest single full backend run was **351 passed in 936.84 seconds**, with `WORKFORCE_DOCKER_GATE=1`, on the admission slice (`3ca038b`). It includes nine separate-container cases. The following bootstrap slice changed only image initialization, Compose, fixture scripts and documentation; its two fresh-volume runs, negative namespace/origin probes, default smoke and Alembic metadata check passed. The full 351-case suite was not repeated after those changes. Exact commands, failed regressions, corrected verification probes and limitations are in the linked evidence.

This acceptance consolidation changes documentation only. Source/configuration inspection confirms: the fixed provider registry remains fake-only; `main.py`, `worker.py` and `tool_effects.py` do not import broker execution/issuance/mediation or the mediated-effect experiment; approved reads remain `approved_staged`, while ordinary tool effects select `admitted`; and Compose defines only db/migrate/api/worker/web. Shared validation/contracts are imported without a fetch route. The worker's normal context builder reads the memory ledger, not external read observations. These are bounded source observations, not a claim of a general sandbox against arbitrary future code changes.

Documentation-slice validation: a source AST inspection found no broker/effect imports or calls in the three product entrypoint/effect modules above; registry introspection confirmed every installed adapter is a fake adapter. `docker compose config --services` returned only the five listed services. All 100 local Markdown link targets across modified documents resolved, and `git diff --check` passed. No backend test, migration cycle, image build or Compose recreation was repeated for this documentation-only slice.

## Closed product activation gate

Before any product outbound path, a separate change must establish and verify:

- Protected broker identity/key provisioning, rotation/revocation and journal ownership/storage policy, with old tickets fenced throughout transition.
- Confidential authenticated remote transport and an explicit clock-skew/expiry policy. The present private RPC authenticates messages but does not encrypt them.
- Quiesced backup/restore and recovery policy for the control DB, broker key/journal and outstanding tickets. Restoring stale copies of both databases and journals can erase uncertainty; these fixtures cannot reconstruct external truth. No automatic unknown retry or invented reconciliation is acceptable.
- A narrowly configured deployed broker, product-facing authority/dispatch/context boundaries, and end-to-end isolation/incident-stop checks in that topology. The fixture subprocess/pipe authorizer is not a deployed API.
- Explicit owner authorization for any real destination or paid integration, plus its resource, retention and accounting policy. Current authorization excludes those actions.

No public resolver/destination read, browser test, host reboot, physical power-loss/corruption acceptance or production key/credential/restore validation is claimed here. Phase 2 native activation remains separately closed. Nothing in this document merges or deploys the stack.

## Next incremental work

Phase 8 starts with an **inert reviewed-runner contract** for a fixed synthetic job. Pin the reviewed profile/version and canonical bounded input; bind project/agent/root/attempt and expiry; reject model-selected commands, images, environment, host paths, mounts, network and credentials. Keep parsing/manifest construction separate from execution. No Docker socket or runner launch enters product API/worker code.

Later isolated fixture execution must prove non-root/read-only/no-network operation, dropped capabilities, CPU/memory/PID/time/output bounds, durable pre-launch attempts, cancellation and unknown-outcome behavior before any integration. Synthetic external-write receipts/reconciliation are a subsequent slice. General shell/browser execution and real external writes remain deferred.
