# Witness trust-boundary lifecycle and prerequisites: Phase 8.4aj

Date: 2026-10-16. Branch: `phase-8-witness-lifecycle-coordinated-rollback`. Parent: acceptance-matrix refresh draft PR #107.

This note consolidates what the local synthetic prototype exercises and the lifecycle an independently operated external witness would still need. The lifecycle below is a design checklist, not an implemented production procedure.

## Prototype lifecycle exercised in fixtures

1. **Load synthetic identities and keys.** A stable caller ID maps to a key ID and key bytes in local startup configuration. State signing keys have IDs and a configured current ID. Local fixture configuration is mode restricted; it is not a protected secret store.
2. **Overlap for rotation.** The fixture loads old and replacement caller keys for the same stable caller identity, and overlapping state keys. Tests verify authenticated requests/responses by key ID. Pending reservations fail closed if their recorded state key is missing; restoring overlap allows validation. The recovery-admin allowlist binds to stable caller identity.
3. **Switch and retire.** A configured current key ID signs new tickets; retired caller keys stop authenticating after restart. A state key needed for a pending ticket cannot be removed without denying consume. Consumed invocation identity remains spent after key retirement. No automated rotation agent or destruction workflow exists.
4. **Use same-host transport.** The Unix-socket fixture checks the local peer UID and HMAC-protected request/response bodies. It is same-host transport and does not authenticate a remote principal.
5. **Handle outage and recovery.** Missing or unavailable state fails closed and does not bootstrap a replacement database. Restoring the retained local witness fixture restores the state modeled by that file. That file can itself be replaced or rolled back: restoring a prior copy rewinds generation, and restoring prior witness, control, and fake-ledger copies together permits the same synthetic intent to produce a second event. See [the generation rollback drill](witness-generation-rollback-boundary-validation.md) and [the coordinated rollback drill](witness-coordinated-full-rollback-effect-validation.md). These fixtures do not prove protected backup or recovery controls.

## External prerequisites before any product activation

- A separately administered witness service with independently protected anti-rollback state for monotonic generation and consumed identities. Its backup, snapshot, and restore authority must be isolated from product control/effect restore authority, and recovery must detect and resolve divergent witness/control/effect snapshots before reopening admission.
- A reviewed remote authenticated transport and caller identity enrollment/revocation process, with explicit authorization boundaries for recovery administrators.
- Independent key generation, protected custody, delivery, rotation overlap, revocation, destruction, emergency compromise response, and audited operator procedures for caller and state keys.
- A defined availability and recovery design that fails closed, prevents silent reinitialization, reconciles unknown outcomes, and establishes how witness state is recovered without rollback. Restore controls must also stop new admission and independently fence or quiesce outstanding caller/effect work, reconcile consumed-but-unapplied outcomes and resolve divergent snapshots before reopening admission. The [caller-effect-after-drain drill](witness-drain-caller-effect-boundary-validation.md) demonstrates why successful witness-method drain alone is insufficient.
- Independently retained, tamper-evident audit evidence and a reviewed retention/monitoring process. The [pending-snapshot audit rollback drill](witness-pending-snapshot-audit-rollback-validation.md) shows that restoring a pending local witness snapshot allows the exact old consume ticket to succeed again and recreates identical final audit rows; the in-file audit cannot establish rollback detection.
- Integration evidence against the actual control database and authorized effect adapters, plus operational review of restore, replacement, concurrency, outage, and recovery drills in that protected environment.
- Separate owner authorization and review before enabling any product dispatch or external write path.

These prerequisites are not provided by this repository's fixtures. The [Phase 8.4bc local PostgreSQL wrapper check](witness-postgres-restore-wrapper-validation.md) passed three simulated control/ledger rollback cases against a disposable database; this does not provide protected-service, actual backup restore or external adapter integration evidence. No claim is made about physical power loss, protected infrastructure, external execution truth, or production safety. Product execution, external writes, paid activation, and deployment remain disabled.

## Validation

This is a documentation-only increment. Checks:

```sh
python - <<'PY'
from pathlib import Path
import re
files = [Path('progress.md'), Path('docs/README.md'), Path('docs/research/witness-trust-boundary-lifecycle.md')]
missing = []
for file in files:
    for target in re.findall(r'\[[^]]+\]\(([^)]+)\)', file.read_text()):
        if target.startswith(('http://', 'https://', '#', 'mailto:')):
            continue
        if not (file.parent / target.split('#', 1)[0]).resolve().exists():
            missing.append((str(file), target))
if missing:
    raise SystemExit(str(missing))
print(f'markdown links: {len(files)} files checked, all local targets exist')
PY
git diff --check
```

Result: all local Markdown targets exist and `git diff --check` passed. No runtime or production guarantee was tested in this documentation increment.
