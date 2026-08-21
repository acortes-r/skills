---
name: security
description: Security pass for `review-changes`.
---

# Security

Use this profile only inside `review-changes`. Activate when the diff touches
authentication, authorization, session handling, API request parsing,
configuration or secret handling, deserialization, file upload or download,
cryptography, or dependency manifests.

Do not run it on every diff.

## Scope

**Authorization**
- A new endpoint, action, or query path with no ownership or scope check
- An object looked up by an identifier from the request with no tenancy or
  ownership filter
- A permission check performed in one place and the privileged action in
  another, where the two can diverge
- A check on the client where the server does not repeat it

**Injection**
- SQL, shell, template, or path built by concatenating or interpolating
  untrusted input
- Dynamic execution: `eval`, `exec`, `system`, `send` with a name from input
- Path traversal in a filename derived from a request

**Untrusted data**
- Deserialization of untrusted input: `pickle`, `Marshal`, unsafe YAML,
  `JSON.parse` on stored client data used for control flow
- A webhook or callback handler that skips signature verification
- Input validation weakened or removed on a path the diff touches

**Secrets and exposure**
- A credential, key, or token literal in code, configuration, or fixtures
- A secret written to logs, error responses, or telemetry
- An overly broad CORS origin, cookie scope, or token lifetime introduced here

**Dependencies**
- A dependency added or bumped to a version with a known advisory
- A lockfile change with no manifest change, or the reverse

## Rules

- Tie every finding to an exploit path, a privilege boundary, or data exposure.
  A mechanism with no reachable path is not a finding.
- Cite the exact file, line, and the untrusted source the value comes from.
- Skip pre-existing issues unless the diff introduces or worsens them.
- Do not report theoretical weaknesses with no evidence in the changed code.

## Severity guidance

| Level | Condition |
|---|---|
| critical | unauthenticated or cross-tenant access, remote execution, credential exposure |
| important | authorization gap behind authentication, injection reachable by an authenticated user, weakened validation |
| suggestion | hardening with limited reachable impact |

## Output

Per finding: `path`, `line`, `severity`, `category`
(`authz | injection | untrusted-data | secrets | dependency`), `untrusted_source`,
`exploit_path`, `impact`, `fix`, `confidence`.
