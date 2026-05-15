# Roadmap

This roadmap is intentionally short. It tracks priorities, acceptance criteria
and links to implementation plans. Detailed task lists stay in
`docs/superpowers/plans/`.

## Now: Real Telemetry Stabilization

Goal: FortiDashboard should feel live with real FortiGate and endpoint telemetry
without synthetic replay or dashboard polling.

Acceptance criteria:

- [x] FortiGate syslog/log-forwarding is the primary FortiGate telemetry path.
- [x] SOC tickets and recent incident surfaces update through the BFF realtime
  stream.
- [x] FortiGate system-status widgets receive event-triggered snapshots through
  SSE and share the latest snapshot across duplicate widgets.
- [x] FortiGate syslog resolver prefers FortiGate device identifiers over host
  fallback when multiple connectors point at the same host.
- [ ] Realtime event payloads expose enough metadata for an operator-facing
  "last telemetry source" indicator.
- [ ] Incident dedupe prevents repeated alerts for the same rule/entity/window.
- [x] FortiGate onboarding includes governed policy orchestration for
  log-enabled lab/customer traffic paths, including preflight, diff/summary,
  approval and audit.
- [ ] FortiWeb 8.0.5 trial protects the external landing page and forwards WAF
  telemetry into SIEM incidents through FortiDashboard.

Links:

- Plan: [2026-05-14-real-telemetry-cutover.md](../superpowers/plans/2026-05-14-real-telemetry-cutover.md)
- Architecture: [realtime-telemetry-flow.md](../architecture/realtime-telemetry-flow.md)
- Runbook: [fortigate-scan-detection.md](../operations/fortigate-scan-detection.md)
- Feature inventory: [feature-map.md](feature-map.md)

## Next: Customer Readiness

Goal: a single-tenant customer stack can be deployed, observed, backed up and
operated without hidden demo assumptions.

Acceptance criteria:

- [ ] First-run onboarding covers first admin, FortiGate connector,
  log-forwarding verification and endpoint enrollment.
- [ ] Structured JSON logging includes request, integration, incident and
  playbook correlation IDs.
- [ ] `/health/live`, `/health/ready` and Prometheus `/metrics` are available.
- [ ] Retention policies exist for raw events, incidents, audit logs and AI
  analyses.
- [ ] Backup/restore runbook covers Postgres, Redis and Keycloak.
- [ ] CI quality gates run API tests, web tests, build, Ruff,
  `git diff --check`, secrets scan and smoke tests.
- [ ] Product docs no longer require reading historical MVP notes to understand
  the current setup path.

Links:

- Maturity analysis: [maturity-analysis.md](../maturity-analysis.md)
- Threat model: [threat-model.md](../architecture/threat-model.md)
- Internal service auth note: [internal-service-auth.md](../api/internal-service-auth.md)

## Later: Automation Expansion

Goal: expand analysis and response automation after the live telemetry and
operational foundation is trustworthy.

Acceptance criteria:

- [ ] LangGraph ticket triage workflow runs on top of the formal AI tool
  registry with human approval gates.
- [ ] MCP server is added only after stable audited APIs exist for incidents,
  playbooks and workspace tools.
- [ ] Additional live connectors follow the same integration, RBAC, audit and
  source-labeling contract as FortiGate and Penguin tools.
- [ ] Sensitive response actions use the accepted FortiGate policy orchestration
  boundary: RBAC, explicit approval, preflight, diff/summary, audit and rollback
  guidance.

Links:

- AI architecture spec: [2026-05-13-ai-agent-architecture-design.md](../superpowers/specs/2026-05-13-ai-agent-architecture-design.md)
- LangGraph readiness: [2026-05-14-langgraph-triage-readiness.md](../superpowers/specs/2026-05-14-langgraph-triage-readiness.md)
- Penguin realization plan: [penguin-tools-realization-plan.md](../architecture/penguin-tools-realization-plan.md)
