# Internal Service Authentication

This document covers service-to-service calls between `apps/api` and the Penguin tools: `siem_kowalski`, `soar_skipper` and `xdr_rico`.

## Current Cut

The current foundation uses Docker Compose service discovery on the local Docker network:

```txt
apps/api -> http://siem-kowalski:8000
apps/api -> http://soar-skipper:8000
apps/api -> http://xdr-rico:8000
```

There is no implemented service authentication yet between `apps/api` and the Penguin tools. Do not describe the current local network boundary as production security. It is only acceptable for local development and early demo scaffolding.

Current minimum controls:

- Penguin service URLs come from environment configuration, not browser input.
- Penguin services are not exposed as browser-facing APIs.
- Browser sessions, CSRF, RBAC and audit live at `apps/api`.
- No FortiGate API keys, Keycloak tokens or endpoint enrollment secrets should be sent to Penguin tools.
- Health endpoints return only service identity and status.

## Target Model

The target production model should add explicit service identity before any non-health internal endpoint is accepted.

Recommended staged approach:

1. Add signed service tokens for `apps/api -> Penguin service` calls.
2. Validate token issuer, audience, service name, expiry and key ID in every Penguin service.
3. Add request IDs and caller identity to every audit-worthy internal action.
4. Move to mTLS for service identity once deployment has certificate automation.
5. Keep network policy as defense in depth, not as the only authentication layer.

Token claims should be minimal:

```json
{
  "iss": "fortidashboard-api",
  "aud": "siem_kowalski",
  "sub": "apps/api",
  "scope": "soc.events:write soc.incidents:read",
  "iat": 1778241600,
  "exp": 1778241900,
  "jti": "req_01"
}
```

Do not put user email addresses, browser session IDs, Keycloak access tokens, FortiGate secrets or endpoint enrollment tokens in service tokens. If user context is needed for audit, send a stable internal user ID and role summary in a signed, bounded claim or structured header.

## Request Contract

Future internal calls should include:

```txt
Authorization: Bearer <short-lived-service-token>
X-Request-ID: req_01
X-FortiDashboard-Actor-ID: usr_01
X-FortiDashboard-Actor-Roles: analyst
```

`apps/api` should enforce browser RBAC before making an internal call. Penguin services should enforce service-token scopes and reject direct user tokens.

Example target flow:

```txt
Browser -> POST /api/soc/events
apps/api:
  - validates browser session and CSRF
  - checks role permission
  - writes or prepares audit context
  - mints a short-lived token for audience siem_kowalski
apps/api -> POST /internal/events on siem_kowalski
siem_kowalski:
  - validates token and scope
  - validates payload schema
  - stores event and emits incident candidates
apps/api -> returns normalized response
```

## Error Handling

Penguin services should return precise internal errors; `apps/api` should map them into stable external errors:

```txt
401 internal auth failed       -> 502 service unavailable to browser
403 internal scope denied      -> 502 service unavailable to browser and security audit
422 internal payload invalid   -> 400 validation error to browser
429 internal rate limited      -> 503 retryable service error to browser
5xx internal service failure   -> 502 service unavailable to browser
```

External responses must not leak internal token validation details, service secrets, stack traces or private network names.

## Key and Secret Handling

- Store signing keys and mTLS private keys outside source control.
- Rotate service-token signing keys with `kid` support.
- Keep token lifetimes short, preferably minutes.
- Log token IDs or request IDs, not token values.
- Redact `Authorization`, cookies, enrollment tokens and provider API keys from logs.
- Use separate audiences for `siem_kowalski`, `soar_skipper` and `xdr_rico`.

## Review Checklist

- [ ] Docs state clearly that current local Docker networking is not real service auth.
- [ ] All target examples use placeholder IDs and no secrets.
- [ ] Service tokens are short-lived and audience-scoped.
- [ ] Browser tokens and Keycloak tokens are never accepted by Penguin services.
- [ ] Internal auth failures do not leak details to browser responses.
- [ ] Audit context includes request ID, actor ID and service name.
- [ ] mTLS is treated as a target hardening step, not current behavior.
