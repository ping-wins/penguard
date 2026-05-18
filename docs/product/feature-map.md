# Feature Map

Current product capability inventory. Status values are defined in
[README.md](README.md).

| Area | Feature | Owner | Status | Customer-visible? | Lab/demo dependency | Source of truth | Verification |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Auth | BFF login, register, logout, CSRF and session cookie flow | `apps/api` + `apps/web` | beta | yes | no | `apps/api/app/routers/auth.py`, `apps/api/app/auth/` | `cd apps/api && uv run pytest -q tests/test_audit_log.py tests/test_config.py` |
| SSO | Keycloak Kerberos/SPNEGO authorization-code flow | `apps/api` + Keycloak config | beta | yes | local AD/Kerberos lab for full validation | `apps/api/app/routers/auth.py`, `infra/keycloak/`, `configSSOKerberosKeycloak.md` | `docker compose config --quiet` |
| Integrations | FortiGate API-key connector with encrypted secrets and health checks | `apps/api` | beta | yes | no | `apps/api/app/integrations/fortigate/`, `apps/api/app/routers/integrations.py` | `cd apps/api && uv run pytest -q tests/test_fortigate_integrations.py` |
| Integrations | Safe FortiGate syslog/log-forwarding setup | `apps/api` + `apps/web` | beta | yes | no | `apps/api/app/integrations/fortigate/service.py`, `apps/web/src/stores/useIntegrationsStore.ts` | `cd apps/api && uv run pytest -q tests/test_fortigate_integrations.py` |
| Workspace | Administrative SOC policy manager widget | `apps/api` + `apps/web` | beta | yes | live provider lab required for validation | `apps/api/app/policies/`, `apps/api/app/routers/policies.py`, `apps/web/src/components/widgets/policies/WidgetSocPolicyManager.vue`, `docs/architecture/decisions/ADR-2026-05-17-admin-policy-manager.md` | `cd apps/api && uv run pytest -q tests/test_policies.py && cd ../web && pnpm exec vitest run tests/unit/widgetPolicyManager.test.ts tests/unit/policiesStore.test.ts` |
| Integrations | Governed FortiGate traffic-policy orchestration | `apps/api` | beta | yes | live FortiGate lab required for validation | `apps/api/app/integrations/fortigate/policy_orchestrator.py`, `apps/api/app/routers/integrations.py`, `docs/architecture/decisions/ADR-2026-05-15-fortigate-policy-orchestration.md` | `cd apps/api && uv run pytest -q tests/test_fortigate_policy_orchestrator.py tests/test_fortigate_policy_requests.py tests/test_fortigate_integrations.py` |
| Telemetry | FortiGate UDP syslog collector feeding SIEM-lite | `apps/api` + `apps/siem_kowalski` | beta | yes | no | `apps/api/app/integrations/fortigate/syslog.py`, `apps/api/app/main.py`, `docs/architecture/realtime-telemetry-flow.md` | `cd apps/api && uv run pytest -q tests/test_fortigate_syslog_ingestion.py tests/test_realtime_widget_push.py` |
| Realtime UX | SSE event stream for tickets and widget snapshots | `apps/api` + `apps/web` | beta | yes | no | `apps/api/app/realtime.py`, `apps/api/app/routers/realtime.py`, `apps/web/src/stores/useRealtimeStore.ts`, `apps/web/src/stores/useWidgetRealtimeStore.ts`, `docs/architecture/realtime-telemetry-flow.md` | `cd apps/web && pnpm test -- tests/unit/draggableWidget.test.ts tests/unit/ticketsRealtimeStore.test.ts` |
| SIEM-lite | Event ingestion, detections, incidents, timelines and tickets | `apps/siem_kowalski` + `apps/api` gateway | beta | yes | no | `apps/siem_kowalski/app/main.py`, `apps/api/app/routers/soc.py` | `cd apps/siem_kowalski && uv run pytest -q` |
| SIEM-lite | FortiGate brute-force and denied-traffic incident generation | `apps/siem_kowalski` | beta | yes | live FortiGate traffic required for real validation | `apps/siem_kowalski/app/main.py`, `docs/operations/fortigate-scan-detection.md` | `cd apps/siem_kowalski && uv run pytest -q tests/test_events_incidents.py` |
| SIEM-lite | FortiGate allow+log port-scan incident generation | `apps/siem_kowalski` | beta | yes | live FortiGate traffic required for real validation | `apps/siem_kowalski/app/main.py`, `docs/operations/fortigate-scan-detection.md` | `cd apps/siem_kowalski && uv run pytest -q tests/test_events_incidents.py` |
| Audit | BFF audit log with optional SIEM forwarding | `apps/api` | beta | yes | no | `apps/api/app/auth/audit.py`, `apps/api/app/routers/audit.py` | `cd apps/api && uv run pytest -q tests/test_audit_log.py` |
| SOAR-lite | Playbooks, dry-runs, approvals and run history | `apps/soar_skipper` + `apps/api` gateway | beta | yes | no | `apps/soar_skipper/app/main.py`, `apps/soar_skipper/app/store.py`, `apps/api/app/routers/soc.py` | `cd apps/soar_skipper && uv run pytest -q` |
| XDR-lite | Endpoint enrollment, inventory, telemetry and incident correlation | `apps/xdr_rico` + `apps/agent_private` | beta | yes | optional lab agent for telemetry | `apps/xdr_rico/app/main.py`, `apps/agent_private/README.md` | `cd apps/xdr_rico && uv run pytest -q && cd ../agent_private && uv run pytest -q` |
| Workspace | Power BI-like dashboard canvas, widgets, manifests and sharing | `apps/web` + `apps/api` | beta | yes | no | `apps/web/src/components/canvas/`, `apps/api/app/routers/workspaces.py`, `packages/contracts/fixtures/workspace.json` | `cd apps/web && pnpm test -- tests/unit/draggableWidget.test.ts` |
| Widget Catalog | Provider widget metadata and data fields | `packages/widget-catalog` + `apps/api` | beta | yes | no | `packages/widget-catalog/`, `packages/contracts/fixtures/widget_catalog_fortigate.json`, `apps/api/app/routers/widget_catalog.py` | `cd apps/api && uv run pytest -q tests/test_mock_contracts.py tests/test_fortigate_widgets.py` |
| AI Assistant | Cockpit chat, dashboard explanations and containment drafts | `apps/api` + `apps/web` | beta | yes | real provider must be configured outside lab mode | `apps/api/app/ai/`, `apps/api/app/routers/ai.py`, `apps/api/app/routers/soc.py` | `cd apps/api && uv run pytest -q tests/test_ai_tools.py tests/test_ai_provider_config.py` |
| Lab Tools | Synthetic SOC replay and simulator helpers | `apps/api` + lab docs | demo-only | no | yes | `apps/api/app/routers/lab_demo.py`, `docs/mvp/` | `cd apps/api && FORTIDASHBOARD_ENABLE_LAB_DEMO_TOOLS=true uv run pytest -q tests/test_mvp_demo_chain.py` |
| Marketplace | Add-on listing and refresh endpoint | `apps/api` | planned | future | no | `apps/api/app/routers/marketplace.py`, `docs/marketplace-plan.md` | `cd apps/api && uv run pytest -q` |
| Integrations | FortiWeb WAF marketplace add-on and native push telemetry | `apps/api` + `apps/web` + external add-on registry | beta | yes | FortiWeb 8.0.5 trial and external landing lab | `docs/operations/fortiweb-landing-waf-lab.md`, `docs/operations/fortiweb-dos-lab.md`, `ping-wins/fortidashboard-addons/fortiweb-waf` | `cd apps/api && uv run pytest -q tests/test_soc_ingest.py tests/test_fortiweb_integrations.py` |
| Widgets | FortiWeb WAF DoS visualization (rate, top IPs, feed) | `apps/api` + `apps/web` | beta | yes | FortiWeb lab + `/api/soc/ingest/fortiweb/{integrationId}` push | `apps/api/app/routers/widgets.py`, `apps/web/src/components/widgets/waf/` | `cd apps/api && uv run pytest -q tests/test_waf_dos_widgets.py && cd ../web && pnpm test -- tests/unit/widgetWafDos.test.ts` |
| Operations | Production readiness: structured logs, metrics, backups and retention | cross-cutting | planned | yes | no | [roadmap.md](roadmap.md), `docs/operations/` | Not yet covered by a single verification command. |

## Update Checklist

When a feature changes:

1. Update its status here.
2. Link the code path or runbook that proves the current behavior.
3. Add or update the verification command.
4. If the change is user-visible, add it to [release-notes.md](release-notes.md).
5. If the change alters priority, update [roadmap.md](roadmap.md).
