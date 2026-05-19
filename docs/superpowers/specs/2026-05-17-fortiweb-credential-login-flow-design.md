# FortiWeb Credential Login Flow Design

**Date:** 2026-05-17
**Status:** Approved direction, pending written spec review

## Goal

Replace the FortiWeb integration form that asks operators to paste an API token
with a normal dashboard-managed login flow. The operator enters FortiWeb
credentials once, Penguard turns them into the FortiWeb REST
`Authorization` value internally, probes the device, then stores only an
encrypted secret.

This keeps the product flow simple while preserving the existing FortiWeb block
orchestration boundary:

```txt
Vue integration drawer
  -> host, username, password, vdom, verifyTls
  -> apps/api builds FortiWeb Authorization header value
  -> apps/api probes /api/v2.0/monitor/system/status
  -> apps/api stores encrypted auth secret
  -> Vue receives sanitized provider status only
```

## Existing Problem

The current FortiWeb provider design and implementation expose `apiKey` in the
integration form. For FortiWeb management API calls, the practical token is an
opaque `Authorization` header value. In lab usage this often means a base64
encoded credential payload, which is awkward and easy for operators to mishandle.

The token is also not a product concept that should leak into the cockpit. It is
an implementation detail of the FortiWeb adapter.

## Non-Goals

- No iframe or embedded FortiWeb GUI inside Penguard.
- No browser redirect or SSO bridge to the FortiWeb management UI.
- No storage of plaintext FortiWeb passwords.
- No automatic creation of FortiWeb administrator accounts.
- No change to the governed block workflow, RBAC, preflight, approval, or audit
  boundary.
- No support for operator-pasted raw tokens in the primary UI.

## UX Contract

The FortiWeb card in the integrations drawer asks for:

```txt
Connection name
FortiWeb URL
Username
Password
VDOM/ADOM default root
Verify TLS certificate
Target server policy default lab-waf-policy
Managed IP list policy default PG_IP_BLOCKLIST
```

User-facing copy should say that this should be a dedicated FortiWeb automation
account. In lab mode, using `admin` is acceptable for quick validation, but the
production path should guide operators to restrict Trusted Host to the
Penguard API host or management subnet and grant only the permissions
needed for the enabled capabilities.

The UI never shows, exports, or logs the generated authorization value. After a
successful save, the card shows sanitized metadata:

```json
{
  "type": "fortiweb",
  "name": "Lab FortiWeb",
  "status": "connected",
  "host": "https://fortiweb.example",
  "auth": {
    "scheme": "fortiweb-v2-authorization",
    "username": "penguard-api",
    "vdom": "root"
  },
  "targetServerPolicy": "lab-waf-policy",
  "managedIpListPolicy": "PG_IP_BLOCKLIST"
}
```

The password is write-only. Re-authentication is done by editing the integration
and entering a new password.

## API Contract

Keep the existing provider endpoints and change their payload shape:

```txt
POST /api/integrations/fortiweb/test
POST /api/integrations/fortiweb
```

Test request:

```json
{
  "host": "https://10.10.20.30",
  "username": "penguard-api",
  "password": "redacted",
  "vdom": "root",
  "verifyTls": false
}
```

Create request:

```json
{
  "name": "Lab FortiWeb",
  "host": "https://10.10.20.30",
  "username": "penguard-api",
  "password": "redacted",
  "vdom": "root",
  "verifyTls": false,
  "targetServerPolicy": "lab-waf-policy",
  "managedIpListPolicy": "PG_IP_BLOCKLIST"
}
```

Responses must not include `password`, `authorization`, `authSecret`,
`apiKey`, or the generated base64 value.

## Backend Contract

Add a small auth helper under the FortiWeb integration boundary:

```txt
apps/api/app/integrations/fortiweb/auth.py
```

It owns the FortiWeb-specific transformation:

```txt
username + password + vdom
  -> compact JSON credential payload
  -> base64 token
  -> Authorization header value
```

`FortiWebApiClient` should keep receiving a generic `authorization` string and
should not know the plaintext password. All redaction, validation, and audit
rules sit above the client.

The store should move away from public `api_key` naming. The durable model
should express the secret as FortiWeb auth, not as an operator-managed API key:

```txt
fortiweb_integrations
  auth_secret_blob encrypted, contains authorization value and auth scheme
  auth_username nullable text
  auth_vdom text default root
  auth_scheme text default fortiweb-v2-authorization
```

If existing rows already use `api_key_blob`, migrate them without exposing the
secret:

```txt
api_key_blob -> auth_secret_blob
auth_scheme = raw-authorization
auth_vdom = root
auth_username = null
```

This preserves local/lab records while making new code use the correct domain
language.

## Security Boundary

- Treat the generated authorization value as equivalent to the FortiWeb
  password.
- Store the authorization value only through the existing encrypted secret
  cipher.
- Never return the secret to Vue, audit details, fixtures, logs, exported
  workspace manifests, or error responses.
- Audit create/test/update attempts with host, TLS mode, target policy, managed
  policy, username, and vdom; never audit password or generated authorization.
- Use dedicated FortiWeb accounts for real environments.
- Keep apply/remove block actions admin-only and CSRF-protected.
- If FortiWeb returns 401/403, show "credentials invalid or insufficient
  permissions" instead of token-oriented wording.

## Error Handling

Stable user-facing failures:

```txt
400 username, password, host, or vdom missing
401/403 FortiWeb credentials invalid or insufficient permissions
404 FortiWeb API endpoint unavailable on this firmware version
502 FortiWeb unreachable or returned an unexpected response
```

The backend should avoid logging raw request bodies for these endpoints because
they contain a password.

## Implementation Impact

Backend:

- Replace `apiKey` fields in FortiWeb create/test models with
  `username`, `password`, and `vdom`.
- Add FortiWeb auth helper and unit tests for token generation/redaction.
- Rename service/store vocabulary from `api_key` to `authorization` or
  `auth_secret`.
- Add an Alembic migration for FortiWeb auth columns.
- Update audit details and API errors to credential-oriented language.

Frontend:

- Replace the FortiWeb API key field with username, password, and VDOM fields.
- Keep password in component state only long enough to submit.
- Clear password after successful test/create and after failed submissions.
- Localize all new labels and errors in `pt-BR` and `en-US`.

Tests:

- FortiWeb create/test accepts credentials and rejects missing password.
- Generated authorization is passed to the client but never returned.
- Store encrypts auth secret and returns only public auth metadata.
- Audit records omit password and generated authorization.
- Frontend form does not render an API token field.

## Relationship To Existing FortiWeb Design

This spec supersedes the `apiKey` setup fields in
`docs/superpowers/specs/2026-05-17-fortiweb-provider-orchestration-design.md`.
The source-IP block workflow remains unchanged. Only provider connection and
secret handling change.
