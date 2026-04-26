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

Before `POST /api/auth/register`, `POST /api/auth/login`, or `POST /api/auth/logout`, frontend code must call `GET /api/auth/csrf` and echo `csrfToken` in `X-CSRF-Token`. Failed CSRF checks return `403`; login/register rate limits return `429`; auth security events are recorded in `auth_audit_events` in live mode.

## FortiGate Integration Contract

`POST /api/integrations/fortigate` accepts `name`, `host`, `apiKey`, and `verifyTls`. In mock mode, it returns the shared fixture. In live mode (`FORTIDASHBOARD_MOCK_MODE=false`), the backend persists the integration in Postgres and stores the API key only as encrypted `fortigate_integrations.api_key_blob`.

Integration responses must never include `apiKey`.

The live FortiGate client is read-only and currently targets:

- `GET /api/v2/monitor/system/status`
- `GET /api/v2/cmdb/system/interface`
- `GET /api/v2/cmdb/firewall/policy`
- `GET /api/v2/log/memory/utm/ips`

Normalized responses cover system status, interfaces, policies, and threat logs. If a lab token returns `401`, verify the FortiGate `api-user` token, `accprofile`, `vdom`, and `trusthost` before changing backend code.
