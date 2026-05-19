# Audit Log Admin RBAC Design

## Context

Penguard already records audit events for authentication, FortiGate integration changes, workspace updates, and audit reads through the FastAPI BFF. The current audit endpoint is intentionally scoped to the authenticated user, which is enough for analyst self-audit but not enough for SOC administration or insider-threat review.

This cut promotes audit visibility to an administrator-only capability while keeping the existing browser-session model: Vue never receives Keycloak tokens, and FastAPI remains the only component that talks to Keycloak.

## Goals

- Provision a development administrator in Keycloak for PoC and demos.
- Read real Keycloak realm roles into the BFF session instead of hardcoding every user as `analyst`.
- Keep public registration restricted to `analyst`.
- Add an administrator-only cross-user audit endpoint.
- Preserve secret redaction for API keys, tokens, passwords, client secrets, and encrypted blobs.
- Make the new authorization path reusable for future admin routes.

## Non-Goals

- No public UI for assigning roles.
- No full user-management console inside Penguard yet.
- No destructive FortiGate actions.
- No multi-tenant admin hierarchy in this cut.

## Keycloak Model

The development realm keeps realm roles `analyst` and `admin`.

Seeded users:

- `analyst@example.com`: role `analyst`.
- `admin@example.com`: role `admin`.

New users created through `POST /api/auth/register` receive only `analyst`. Production administrators should be created or promoted through Keycloak administration, not through the public Penguard registration form.

## Backend Design

`KeycloakClient` will extract roles from Keycloak responses rather than returning a static role list. The source is the access token payload returned directly by Keycloak during BFF login/register, where realm roles are expected under `realm_access.roles`. This parsing is only for server-side session creation; the browser still never receives or validates JWTs. If the claim is unavailable, the BFF falls back to `analyst` rather than granting admin implicitly.

Add a shared dependency:

```txt
get_current_api_user -> require_admin_user
```

`require_admin_user` returns the authenticated user when `roles` contains `admin`; otherwise it raises `403`.

Endpoints:

- `GET /api/audit/events`: unchanged; returns only the current user's events.
- `GET /api/admin/audit/events`: admin-only; returns events across users.

Admin audit filters:

- `limit`: 1-100.
- `actorUserId`: optional exact user id.
- `action`: optional exact action.
- `outcome`: optional exact outcome.

Every successful admin read records `audit.events.viewed` with details including the applied filters and result limit. Failed admin access returns `403`; it should not expose cross-user audit data.

## API Shape

`GET /api/admin/audit/events?limit=50&action=login&outcome=success`

```json
{
  "items": [
    {
      "id": "audit_01",
      "actor": { "id": "usr_01", "email": "analyst@example.com" },
      "action": "login",
      "outcome": "success",
      "ipAddress": "192.0.2.10",
      "userAgent": "Mozilla/5.0",
      "details": {},
      "createdAt": "2026-04-29T14:30:00.000Z"
    }
  ]
}
```

## Frontend Contract

The frontend can keep the current audit client for self-audit. A later UI pass can add `scope: "mine" | "admin"` or a separate admin audit client. Admin navigation must be gated by `auth.user.roles.includes("admin")`, but the backend remains the source of authorization truth.

## Security Requirements

- Browser receives only user profile and roles, never Keycloak tokens.
- Admin role must come from Keycloak session data, not from a client-provided field.
- Unknown or missing roles default to least privilege.
- Audit details are sanitized on write and read.
- Tests must prove that admin audit output never includes API keys, tokens, passwords, or client secrets.

## Test Plan

- Unit test Keycloak role extraction from access-token realm roles.
- Unit test fallback to `analyst` when role claims are missing.
- Realm config test for seeded `admin@example.com`.
- API test: analyst receives `403` from `/api/admin/audit/events`.
- API test: admin can list cross-user events and apply filters.
- API test: admin read records `audit.events.viewed`.
- API test: secret fields remain redacted in admin audit responses.
