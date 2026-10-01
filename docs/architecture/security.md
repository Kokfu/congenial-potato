# Security

Status: approved architecture direction; controls must be implemented and tested.

## Trust

Human and reviewed backend are trusted. Models, messages, websites/email/uploads, remote tools and discovered schemas are untrusted.

Prompts describe behavior; deterministic services/infrastructure constrain authority. Single-user/localhost still needs authentication and browser-origin defenses.

## Authentication

One provisioned owner; no signup. Mature password/session implementation; Argon2id, opaque server-side sessions, HttpOnly cookies, CSRF, rotation and login rate limits.

Secure cookies over HTTPS; explicit loopback HTTP development mode only. Validate host/origin, no wildcard CORS. Remote use requires TLS/auth; private network/VPN initially preferred.

## Secrets

Encrypted credentials/refs in database with authenticated encryption/key IDs/rotation. Master key outside database/image: secret mount locally, replaceable secret manager later. Separate protected key backup.

Resolve credentials only in trusted adapters; scrub headers/logs/errors/artifacts. No keys/passwords/refresh tokens in prompts.

SDKs use keys in trusted process memory. Model-generated code cannot share that environment.

## Prompt injection

Attack example: invoice email asks agent to retrieve a key and post it to attacker URL.

Treat content as cited data; separate trusted instructions; deny secret-reading tools; authorize action/destination independently; restrict egress/resources; exact-effect approval for sensitive outbound actions; no external policy/install authority; preserve trust through summaries; bound output.

Detection/defensive prompts reduce risk but cannot guarantee prevention. Granted read-and-send can still exfiltrate, so destination limits/approval matter.

## SSRF/network

Validate scheme/hostname/port/resolved IP; deny metadata/link-local/private/reserved by default. Recheck redirects/socket peer and DNS rebinding.

Private model/service exceptions are narrow connection allowlists, not general private fetch access. Bound redirects/downloads/decompression/duration. Apply policy to browsers/fetch/artifact imports.

Compose networks are not outbound firewalls. Enforce/test proxy/firewall controls before broad network tools.

## Isolation

MVP only reviewed backend functions. Later runners: non-root, read-only base, dropped capabilities, seccomp, CPU/memory/PID bounds, task mounts and restricted egress. No Docker socket/host home/app secrets.

Containers share a kernel; higher-risk code may need VM/stronger sandbox. Shell allowlists do not securely constrain arbitrary code.

Browsers: dedicated worker/network policy and separated account/task profiles. Browser contexts alone are not hostile-code security boundaries.

## Browser credentials

Operator login in managed isolation or adapter OAuth. Encrypt session state/cookies; no tools reading raw cookies/storage. Broker credential fill and redact traces/screenshots.

MFA/CAPTCHA may require human; do not promise bypass. Quarantine downloads; upload exact approved artifacts. Preview submissions; changed page can invalidate approval.

## Other controls

Validate bounded input/output; sanitize Markdown/HTML; risky files as attachments; path/symlink/archive defenses; pinned dependencies/images, SBOM/scans; webhook signature/replay checks; rotation/secret audit; login/model/tool/schedule limits; disable optional telemetry.

Fail closed if required policy/audit persistence fails. Ordinary roles cannot update audit, but DB administrators can; strong tamper evidence needs later signed/off-host export.

Acceptance covers exfiltration, approval bypass, SSRF, impersonation, resource isolation, secret leakage and emergency stop.
