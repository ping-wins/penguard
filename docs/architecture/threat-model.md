# Penguin Tools Threat Model

Scope: FortiDashboard plus `siem_kowalski`, `soar_skipper`, `xdr_rico` and `agent_private`.

Current foundation is local-development oriented. The main security boundary today is `apps/api`; internal Penguin service authentication is not implemented yet.

## Assets

- Browser sessions and CSRF tokens.
- Keycloak server-side tokens stored by `apps/api`.
- FortiGate API keys stored by `apps/api`.
- Endpoint enrollment tokens and endpoint identity.
- SOC events, incidents, timelines and playbooks.
- Audit records for auth, integrations, workspace, incident, playbook and endpoint actions.
- AI-generated widget and playbook drafts.

## Trust Boundaries

```txt
Browser <-> apps/api
apps/api <-> Keycloak
apps/api <-> FortiGate
apps/api <-> Penguin services
agent_private <-> apps/api or xdr_rico
apps/api and Penguin services <-> Postgres/Redis
```

Only `apps/api` is browser-facing. Penguin services should be treated as internal services with explicit service identity before non-health endpoints are added.

## Threats and Controls

### Phishing and Session Abuse

Risk:

- A user is tricked into entering credentials or performing sensitive SOC actions.
- A stolen browser session is used to view incidents, change playbooks or create endpoint enrollment tokens.

Controls:

- Keep Keycloak tokens server-side and never expose them to Vue.
- Use HTTP-only session cookies and CSRF protection for mutating requests.
- Require RBAC for admin and sensitive SOC actions.
- Audit login, logout, failed auth, admin reads, playbook changes and endpoint enrollment.
- Add step-up approval for sensitive playbook actions when those actions exist.

Review checks:

- Mutating APIs require CSRF.
- Missing or malformed roles fall back to `analyst`, not `admin`.
- Audit entries do not include session cookies or token values.

### Supply Chain

Risk:

- A dependency, container image, package script or generated client introduces malicious code.
- A compromised agent package sends unexpected telemetry or secrets.

Controls:

- Keep dependencies minimal and pinned through each app lockfile.
- Prefer small service-owned dependencies over large SIEM/SOAR platforms for the MVP.
- Run Ruff and tests for each Python service.
- Review Dockerfiles for remote install behavior and build context.
- Do not mount host `node_modules` into production containers.
- For `agent_private`, document visible lab/demo behavior and avoid hidden persistence.

Review checks:

- New dependencies are justified in the PR.
- Lockfiles are updated with dependency changes.
- Agent telemetry is documented and bounded.

### Insider Misuse

Risk:

- An authenticated user abuses legitimate access to inspect audit data, change playbooks or enroll rogue endpoints.
- An admin bypasses process by activating unsafe automation.

Controls:

- Enforce role checks in `apps/api`, not the frontend.
- Audit successful admin reads and all SOC state changes.
- Keep playbooks disabled or draft until authorized validation.
- Require explicit approval for sensitive steps.
- Limit FortiGate writes to governed policy orchestration: admin RBAC, preflight,
  diff/summary, explicit approval, FortiDashboard-owned objects/policies and
  audit. Destructive FortiGate changes remain out of scope.

Review checks:

- Admin-only APIs check `admin` server-side.
- Playbook create/update/simulate/run/approve actions write audit events.
- Audit filters cannot be used to hide the caller's own actions.

### Malicious Playbook

Risk:

- A playbook is crafted to execute arbitrary code, loop forever, exfiltrate data or perform destructive changes.
- AI-generated playbooks are treated as trusted automation.

Controls:

- Store playbooks as validated JSON graphs only.
- Disallow arbitrary Python, shell, SQL and browser code execution.
- Keep workflow loops out until guardrails exist.
- Default actions to `dry_run`.
- Treat AI-generated playbooks as drafts and require human validation.
- Require approval and RBAC before any sensitive live FortiGate/FortiWeb step.

Review checks:

- Node types come from the allowed SOC catalog.
- Unknown node types fail validation.
- FortiGate policy/block nodes cannot execute from AI or a background job alone;
  they must go through the BFF policy orchestration path with approval and audit.
- Draft playbooks cannot run as active automation.

### Endpoint Spoofing

Risk:

- A fake endpoint registers as a trusted host.
- A stolen enrollment token is replayed.
- Telemetry is forged to mislead incident correlation.

Controls:

- Use one-time or short-lived enrollment tokens.
- Store endpoint tokens hashed or encrypted and never return them after creation.
- Bind enrollment to expected tenant/user context and optional host metadata.
- Require signed or token-authenticated telemetry after enrollment.
- Rate-limit enrollment and telemetry endpoints.
- Mark simulator data clearly so it cannot be confused with real endpoint telemetry.

Review checks:

- Enrollment token values are not logged or returned after creation.
- Endpoint event ingestion rejects unknown or disabled endpoint IDs.
- Correlation logic does not trust hostname alone when endpoint ID or token proof is missing.

### Secret Leakage

Risk:

- FortiGate API keys, Keycloak tokens, service tokens or endpoint enrollment tokens appear in responses, logs, fixtures or audit records.
- Internal errors reveal private service URLs or stack traces.

Controls:

- Encrypt provider keys and Keycloak token blobs at rest in `apps/api`.
- Never return API keys, refresh tokens, service tokens or enrollment tokens in JSON responses.
- Redact `Authorization`, cookies and token-like fields from logs and audit metadata.
- Use placeholder values in fixtures and docs.
- Map internal service failures to stable external errors without secret details.

Review checks:

- Fixtures and docs contain no real hostnames, lab IPs, personal identifiers or secrets.
- Audit metadata redacts token-like fields.
- Error responses do not include internal stack traces or token validation details.

## Review Checklist

- [ ] Each listed threat has at least one prevention or detection control.
- [ ] No control claims internal service auth is already implemented.
- [ ] FortiGate writes are scoped to governed policy orchestration and audited.
- [ ] AI-generated widgets and playbooks remain draft-only until confirmed.
- [ ] Endpoint enrollment tokens are protected from replay and disclosure.
- [ ] Audit requirements cover auth, integrations, incidents, playbooks, endpoint enrollment and admin views.
- [ ] This threat model is updated when real SOC routes, AI tools or endpoint enrollment ship.
