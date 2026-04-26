# API Contracts

The initial API contract lives in `AGENTS.md` and is backed by JSON fixtures in `packages/contracts/fixtures`.

When `apps/api` is running, FastAPI publishes the generated OpenAPI document at:

```txt
http://localhost:8000/openapi.json
```

Contract changes must update:

- Pydantic request/response models in `apps/api`.
- Shared fixtures in `packages/contracts/fixtures`.
- Backend tests in `apps/api/tests`.
- Consumer-facing notes in `AGENTS.md` when payload shapes change.

## Auth Session Contract

Frontend login/register pages call FastAPI auth endpoints. The backend response body contains user/session context only; access and refresh tokens must never be returned to the browser.

The backend owns the `Set-Cookie` behavior for `fortidashboard_session`. Frontend code should use `GET /api/auth/me` to hydrate the current user after page reloads.

In live mode (`FORTIDASHBOARD_MOCK_MODE=false`), FastAPI authenticates against Keycloak and persists the browser session in Postgres. Keycloak tokens are stored only in the `auth_sessions.token_blob` encrypted field, `expires_at` invalidates expired sessions, and tokens must never appear in JSON responses.
