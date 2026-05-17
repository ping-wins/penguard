# Roles & Permissions Manager — Design

**Status:** Draft (awaiting user approval)
**Date:** 2026-05-17
**Owner:** luskotav-cloud
**Related:** [`docs/superpowers/specs/2026-04-29-audit-admin-rbac-design.md`](2026-04-29-audit-admin-rbac-design.md)

## Goal

Discord-style role/permission manager inside Settings. Admins create roles, assign permissions per role, and grant roles to users. Backend endpoints currently gated by `require_admin_user` (single hard-coded `"admin"` claim) become gated by named permissions checked against the user's effective permission set.

## Non-goals

- Multi-tenant / per-org scoping. Single org for now.
- Role hierarchy / position ordering (Discord priority). Flat union of permissions.
- Custom permission scopes per resource instance (e.g. "edit only widgets X,Y"). Permissions are app-wide.
- Editing the Keycloak realm. Roles live in the app DB; Keycloak only authenticates.
- OAuth scope re-mapping. Session payload keeps `roles` as-is from Keycloak for compatibility; new `permissions` field is added alongside.

## Source of truth

App DB (Postgres). Keycloak (or `mock_mode` fixture) authenticates the user and supplies their `user_id`/`email`/`roles` claim. The app maps that identity to in-app role assignments and resolves the effective permission set per request.

## Permission catalog (v1)

Flat string slugs. Stored in code as a frozen enum; admins pick from this list when editing a role. Slugs are stable identifiers — UI labels are i18n keys.

| Slug | Gates |
|---|---|
| `integrations.write` | POST/DELETE `/api/integrations/*` (add or remove FortiGate / Penguin provider) |
| `audit.read` | GET `/api/audit/*` (view audit feed; admin scope) |
| `roles.manage` | All new `/api/roles/*` endpoints (CRUD roles, assign members, edit perms) |
| `marketplace.install` | POST `/api/marketplace/install` + `/uninstall` |
| `workspaces.share` | POST `/api/workspaces/*/share` (publish workspace to org) |
| `playbooks.execute` | POST `/api/playbooks/*/run` (SOAR dry-run / live) |
| `tickets.manage` | POST/PATCH/DELETE `/api/tickets/*` (close, reassign, bulk) |

Two implicit perms not in the catalog:
- `*` — wildcard, granted only by the built-in `super_admin` role.
- (empty) — default for any user with no role assignments. Can still read non-gated endpoints (dashboard, own profile, AI chat).

Adding a perm later = append to enum + add `Depends(require_permission("slug"))` on the router. No migration.

## Data model

Three new tables. All use `created_at` / `updated_at` per existing convention.

### `roles`

| Column | Type | Notes |
|---|---|---|
| `id` | `String(64)` PK | ULID |
| `name` | `String(64)` unique | Human label, e.g. "SOC Analyst" |
| `description` | `Text` nullable | |
| `color` | `String(7)` nullable | Hex like `#5865F2`, Discord-style badge color |
| `is_system` | `Boolean` default `false` | `true` for built-in `super_admin`; blocks delete/rename |
| `created_at`/`updated_at` | `DateTime` | |

Built-in row seeded by migration:
- `id="role_super_admin"`, `name="super_admin"`, `is_system=true`. Granted `*` via permissions table.

### `role_permissions`

| Column | Type | Notes |
|---|---|---|
| `role_id` | FK → `roles.id` ON DELETE CASCADE | |
| `permission` | `String(64)` | Slug from catalog, or `"*"` |
| (PK) | `(role_id, permission)` | |

### `user_roles`

| Column | Type | Notes |
|---|---|---|
| `user_id` | `String(255)` | Keycloak `sub` (matches `AuthSessionModel.user_id`) |
| `role_id` | FK → `roles.id` ON DELETE CASCADE | |
| `granted_by_user_id` | `String(255)` nullable | Auditing |
| `granted_at` | `DateTime` | |
| (PK) | `(user_id, role_id)` | |

`user_roles` does NOT FK to a `users` table — there isn't one. Membership rows are created on-demand when an admin grants a role; users are identified by Keycloak `sub` (which the app already sees via the session). A user's display name/email are pulled from `auth_sessions` (most recent row per `user_id`) when listing.

### User directory (for the "Users" tab)

No standalone users table exists today. To populate the user-picker, we add an endpoint that aggregates from two sources:
1. `auth_sessions` (anyone who has logged in at least once).
2. `user_roles` (anyone who has ever been granted a role, even if never logged in — fallback).

Listing returns `{ userId, email, displayName, roles: [...] }`. No new table.

## Permission resolution

Per request, after `get_current_api_user` resolves the session user:

```
effective_perms(user) =
    union over user_roles where user_roles.user_id = user.user_id
        of role_permissions.permission
```

If the set contains `"*"`, all permission checks pass.

Bootstrap rule: if `current_user.roles` (the Keycloak claim) contains `"admin"`, the user is treated as `super_admin` regardless of `user_roles`. This guarantees the IdP admin can always recover access if the role manager itself is misconfigured.

### New dependency

```python
def require_permission(slug: str):
    def _dep(current_user = CURRENT_API_USER_DEP, db = DB_DEP):
        if "admin" in (current_user.get("roles") or []):
            return current_user                       # keycloak bootstrap
        perms = effective_permissions(db, current_user["user_id"])
        if slug not in perms and "*" not in perms:
            raise HTTPException(403, f"Permission required: {slug}")
        return current_user
    return _dep
```

`require_admin_user` stays as-is for backwards compatibility. New routers use `require_permission(...)`. Existing admin-gated routers migrate one-by-one (see Migration section).

Effective perms are cached per request (FastAPI dep already memoized within a request).

## API surface (new)

All under `/api/roles`, gated by `require_permission("roles.manage")` unless noted.

| Method | Path | Body / Returns |
|---|---|---|
| `GET` | `/api/roles` | `[{ id, name, description, color, isSystem, permissions: [...], memberCount }]` |
| `POST` | `/api/roles` | `{ name, description?, color?, permissions: [...] }` → role |
| `PATCH` | `/api/roles/{id}` | partial; rejects `name` change on `is_system` |
| `DELETE` | `/api/roles/{id}` | 409 if `is_system`. Cascades members + perms. |
| `GET` | `/api/roles/{id}/members` | `[{ userId, email, displayName, grantedAt, grantedBy }]` |
| `POST` | `/api/roles/{id}/members` | `{ userId }` (or `{ email }` resolved server-side) |
| `DELETE` | `/api/roles/{id}/members/{userId}` | |
| `GET` | `/api/roles/permissions/catalog` | `[{ slug, labelKey, descriptionKey, category }]` — frontend renders checkboxes |
| `GET` | `/api/users` | `[{ userId, email, displayName, roles: [{ id, name, color }] }]` (q-param search, paginated) |
| `PATCH` | `/api/users/{userId}/roles` | `{ add: [...], remove: [...] }` — bulk role toggle for one user |
| `GET` | `/api/users/me/permissions` | `{ permissions: [...] }` — frontend uses this to hide UI a user can't action |

All mutations emit `auth_audit_events` with `action="roles.role.create"` etc. so the existing audit feed surfaces them.

### Session payload change

`/api/auth/me` and login responses gain `permissions: string[]` alongside existing `roles: string[]`. Frontend `AuthUser` type extends. This decouples per-permission UI gating from the legacy `roles.includes('admin')` check.

## Frontend

### Settings modal — new tab "Roles & Members"

`SettingsModal.vue` already renders tab list from `tabs` computed. Add a sixth tab, visible only when `permissions.includes('roles.manage')` (or legacy `admin` role). Icon: `ShieldCheck` (already imported) or `Users`.

New component `RolesManagerPanel.vue` is loaded at `-mx-5 -my-5 h-[60vh]` like marketplace.

### Panel layout

Discord-inspired two-pane:

```
┌────────────────┬────────────────────────────────────────┐
│ Roles      [+] │ Role: SOC Analyst       [Save] [Del]   │
│                │ ─────────────────────────────────────  │
│ • super_admin  │ [Display] [Permissions] [Members]      │  ← sub-tabs
│ • SOC Analyst  │                                        │
│ • Read-only    │  (sub-tab content)                     │
│                │                                        │
│ ─── Users ──── │                                        │
│ [Open Users]   │                                        │
└────────────────┴────────────────────────────────────────┘
```

- **Left column**: role list with color dot + name + member count badge. "+" creates a new role (modal with name/color/description).
- **Right column** with three sub-tabs:
  - **Display**: name, description, color picker.
  - **Permissions**: grouped checkbox list of catalog perms (categories: Integrations, Audit, Roles, Marketplace, Workspaces, Playbooks, Tickets). `super_admin` row is read-only ("All permissions").
  - **Members**: searchable list of users in this role; "+ Add member" opens a user picker.
- **Users sub-mode** (toggled at top of left column or via a switcher): replaces role list with a paginated user list. Each row shows user + colored role pills + "+ Manage roles" dropdown. Implements the per-user toggle flow.

State managed by new Pinia store `useRolesStore`:
- `roles`, `catalog`, `usersIndex`, `isLoading`
- Actions: `fetchRoles`, `fetchCatalog`, `fetchUsers(query)`, `createRole`, `updateRole`, `deleteRole`, `setMembers`, `setUserRoles`
- After each mutation, re-fetch (no optimistic updates v1).

### Permission-aware UI hiding

`useAuthStore` exposes `hasPermission(slug: string)` derived from `user.permissions`. Existing `isAdmin` checks gradually migrate:

| Today | After |
|---|---|
| `isAdmin → show Integrations form` | `hasPermission('integrations.write')` |
| `isAdmin → audit scope='admin'` | `hasPermission('audit.read')` |
| (no current check) Marketplace install button | `hasPermission('marketplace.install')` |

`isAdmin` stays as a fallback while migration is in flight.

### i18n

New keys in `apps/web/src/i18n/messages/{en-US,pt-BR}.ts`:

```
settings.tabs.roles, settings.roles.title, settings.roles.subtitle
settings.roles.empty, settings.roles.create, settings.roles.delete.confirm
settings.roles.tabs.display|permissions|members
settings.roles.permission.<slug>.label, settings.roles.permission.<slug>.description
settings.roles.permission.category.<name>
settings.roles.members.add, settings.roles.members.search
settings.users.title, settings.users.searchPlaceholder
errors.permission.required
```

## Migration of existing admin gates

Done in a follow-up PR, not part of this feature's MVP. Mapping documented here so it's not lost:

| Current `Depends(require_admin_user)` | Replacement |
|---|---|
| `routers/audit.py` list | `require_permission("audit.read")` |
| `routers/integrations.py` admin endpoints | `require_permission("integrations.write")` |
| `routers/marketplace.py` install/uninstall | `require_permission("marketplace.install")` |
| `routers/soc.py` admin ingest | keep `require_admin_user` for now (out of scope) |

MVP keeps both checks alive: `require_admin_user` (Keycloak claim) AND `require_permission(...)` (DB lookup). Both pass = user is admin OR has perm. This guarantees no current admin loses access while we roll out.

## Database migration

New Alembic revision `20260517_0010_roles_and_permissions.py`:
1. Create `roles`, `role_permissions`, `user_roles` (schemas above).
2. Seed `super_admin` row + `('role_super_admin', '*')` in `role_permissions`.
3. Backfill: for every distinct `auth_sessions.user_id` whose stored `roles` JSON contains `"admin"`, insert `(user_id, 'role_super_admin')` into `user_roles`. Idempotent.

Downgrade drops the three tables.

## Audit events

`auth_audit_events.action` values added (no schema change, `action` is a string):

- `roles.role.create | update | delete`
- `roles.member.grant | revoke`
- `roles.permissions.update`
- `roles.permission.denied` (emitted by `require_permission` on 403)

`details` JSON carries `{role_id, role_name, permissions, target_user_id}` as relevant.

## Error handling

| Case | Status | Body |
|---|---|---|
| Non-admin hits `/api/roles/*` | 403 | `{"detail": "Permission required: roles.manage"}` |
| Delete `is_system` role | 409 | `{"detail": "System roles cannot be deleted"}` |
| Duplicate role name | 409 | `{"detail": "Role name already exists"}` |
| Unknown permission slug on PATCH | 422 | Pydantic validation error |
| Member grant with unknown `userId` | 404 | `{"detail": "User not found"}` |

Frontend toasts on 4xx; falls back to existing error banner pattern in SettingsModal.

## Testing

Backend (`apps/api/tests/`):
- `test_roles_endpoints.py` — CRUD, member assignment, system-role guards, permission catalog endpoint.
- `test_permission_dependency.py` — `require_permission` allows holder, denies non-holder, allows `*`, allows Keycloak `admin` bootstrap.
- `test_roles_migration.py` — backfill creates `super_admin` membership for existing admins.
- Update `test_audit_log.py` to assert `roles.*` actions appear.

Frontend (`apps/web/tests/unit/`):
- `rolesStore.test.ts` — fetch / create / update / delete flows against mocked client.
- `rolesManagerPanel.test.ts` — renders empty state, opens create modal, toggles permission checkbox, switches to Users sub-mode.
- `permissionGate.test.ts` — `hasPermission` reactivity; UI elements hide when perm missing.

Smoke: existing `apps/api/tests/test_smoke_flows.py` gets one extra step: log in as bootstrap admin, create role "Tester" with `audit.read`, grant to second user, second user can GET `/api/audit`.

## Open questions / deferred

- **Role priority / hierarchy:** Deferred. Today all granted perms union.
- **Per-resource scoping** (e.g., "can manage only this integration"): Deferred; out of scope.
- **External IdP role sync** (Keycloak group → app role auto-mapping): Deferred. For now Keycloak `admin` claim is the only auto-mapping.
- **Bulk import** of role assignments (CSV): Deferred.
- **Soft delete** of roles: Not in v1 — hard delete with confirmation modal.

## Rollout

1. Ship migration + new tables + endpoints behind `roles.manage` (super_admin only). No UI yet.
2. Ship Settings → Roles tab. Bootstrap admin uses it to create real roles.
3. Migrate one router at a time to `require_permission`. Each PR migrates one slug, runs full test suite.
4. Once all admin-gated routes migrated, deprecate `require_admin_user` (keep symbol for tests).
