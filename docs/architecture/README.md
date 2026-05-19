# Architecture Documentation

Architecture docs describe service boundaries, data flow, security decisions and
runtime contracts. Keep operational checklists in `docs/operations/` and product
status in `docs/product/`.

## Current Contracts

| Document | Covers |
| --- | --- |
| [realtime-telemetry-flow.md](realtime-telemetry-flow.md) | FortiGate syslog to SIEM ingestion and SSE updates for tickets, incident toasts and workspace widgets. |
| [penguin-tools-data-flow.md](penguin-tools-data-flow.md) | SIEM-lite, SOAR-lite and XDR-lite service data flow through the BFF. |
| [penguin-tools-realization-plan.md](penguin-tools-realization-plan.md) | Implementation direction for replacing fake Fortinet surfaces with honest SOC-lite providers. |
| [threat-model.md](threat-model.md) | Current trust boundaries, security controls and high-risk areas. |

## Accepted Decisions

| Decision | Covers |
| --- | --- |
| [ADR-2026-05-15-fortigate-policy-orchestration.md](decisions/ADR-2026-05-15-fortigate-policy-orchestration.md) | FortiGate traffic-policy writes as governed Penguard orchestration instead of draft/mock-only guidance. |
| [ADR-2026-05-17-admin-policy-manager.md](decisions/ADR-2026-05-17-admin-policy-manager.md) | Admin-controlled policy management across connected SOC providers, including external/customer-owned policies, with review and audit gates. |

## Update Rules

- Add a document here when a change alters service boundaries, data flow,
  security posture or runtime contracts.
- Link the same change from `docs/product/feature-map.md` when it represents a
  product capability.
- Use an ADR under `docs/architecture/decisions/` for decisions that need a
  durable accepted/rejected rationale.
