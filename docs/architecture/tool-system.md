# Tool system

Status: approved architecture direction.

## Vocabulary

ToolDefinition declares action/version/schemas/effects. Integration supplies adapter code. Connection supplies account/endpoint/resource bounds/secret ref. ToolInvocation is the immutable proposal and execution record.

Agents receive eligibility, never connector credentials.

## Definition

Declare capability/action, canonical resource extraction, input/output schema, read/write/destructive/external effect, sensitive-field redaction, timeout/size/rate limits, idempotency/reconciliation, approval preview and execution environment.

Reviewed configuration determines risk. Remote descriptions/annotations do not set policy.

## Flow

1. Validate model arguments.
2. Canonicalize connection/resources.
3. Check project/agent/run/connection policy.
4. Persist intent and policy decision.
5. Persist approval/suspend if required.
6. Revalidate after approval.
7. Execute trusted adapter or isolated runner.
8. Validate and bound output.
9. Record result/audit/artifacts.

Provider-hosted tools or framework/MCP execution cannot bypass this path unless an equivalent enforceable boundary is explicitly accepted.

## MCP

One transport alongside native functions and later OpenAPI adapters. Use official SDK; negotiate/pin protocol versions.

Prefer Streamable HTTP. Stdio requires reviewed commands and explicitly isolated environments; agents cannot install packages or supply commands.

Catalog is connection-scoped; pin configuration/schema hashes. New/changed tools enter quarantine. Metadata/output are untrusted.

Disable server-initiated sampling/expanded capabilities unless mediated. Validate OAuth state/PKCE/redirects/audience; never pass platform bearer tokens indiscriminately upstream.

## MVP

Project memory query, authorized artifact read/create, agent message, bounded delegation and task review. Local fixture approval-gates an existing text artifact replacement.

Web read/search follows SSRF/output controls. Filesystem means artifact service, not arbitrary paths. Shell, browser, email and unrestricted HTTP are deferred.

## Outputs/plugins

Bound bytes/tokens/MIME. Large output becomes artifact plus excerpt/ref. Sanitize rendered content. Returned URLs require validation before fetch.

Plugin code is trusted deployed software; plugin interfaces are not sandboxes. Human-reviewed installation remains required.
