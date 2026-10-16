# Witness trust-boundary lifecycle and prerequisites: Phase 8.4w

Date: 2026-10-16. Branch: `phase-8-witness-trust-boundary-lifecycle`. Parent: witness authentication effect-boundary draft PR #94.

This note consolidates what the local synthetic prototype exercises and the lifecycle an independently operated external witness would still need. The lifecycle below is a design checklist, not an implemented production procedure.

## Prototype lifecycle exercised in fixtures

1. **Load synthetic identities and keys.** A stable caller ID maps to a key ID and key bytes in local startup configuration. State signing keys have IDs and a configured current ID. Local fixture configuration is mode restricted; it is not a protected secret store.
2. **Overlap for rotation.** The fixture loads old and replacement caller keys for the same stable caller identity, and overlapping state keys. Tests verify authenticated requests/responses by key ID. Pending reservations fail closed if their recorded state key is missing; restoring overlap allows validation. The recovery-admin allowlist binds to stable caller identity.
3. **Switch and retire.** A configured current key ID signs new tickets; retired caller keys stop authenticating after restart. A state key needed for a pending ticket cannot be removed without denying consume. Consumed invocation identity remains spent after key retirement. No automated rotation agent or destruction workflow exists.
4. **Use same-host transport.** The Unix-socket fixture checks the local peer UID and HMAC-protected request/response bodies. It is same-host transport and does not authenticate a remote principal.
5. **Handle outage and recovery.** Missing or unavailable state fails closed and does not bootstrap a replacement database. Restoring the retained local witness fixture restores the state modeled by that file. That file can itself be replaced or rolled back; the drill does not prove backup or recovery controls.

## External prerequisites before any product activation

- A separately administered witness service and storage whose monotonic generation and consumed identities cannot be restored from the product control plane's backups or credentials.
- A reviewed remote authenticated transport and caller identity enrollment/revocation process, with explicit authorization boundaries for recovery administrators.
- Independent key generation, protected custody, delivery, rotation overlap, revocation, destruction, emergency compromise response, and audited operator procedures for caller and state keys.
- A defined availability and recovery design that fails closed, prevents silent reinitialization, reconciles unknown outcomes, and establishes how witness state is recovered without rollback.
- Independently retained, tamper-evident audit evidence and a reviewed retention/monitoring process.
- Integration evidence against the actual control database and authorized effect adapters, plus operational review of restore, replacement, concurrency, outage, and recovery drills in that protected environment.
- Separate owner authorization and review before enabling any product dispatch or external write path.

These prerequisites are not provided by this repository's fixtures. Docker/PostgreSQL integration remains unrun in the current environment. No claim is made about physical power loss, protected infrastructure, external execution truth, or production safety. Product execution, external writes, paid activation, and deployment remain disabled.

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
