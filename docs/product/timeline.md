# Product Timeline

Short chronology of durable product decisions and shipped outcomes. This is not
a sprint log; link to implementation plans for detail.

| Date | Outcome | Why It Matters | Links |
| --- | --- | --- | --- |
| 2026-04-29 | Defined admin/audit/RBAC direction for sensitive cockpit actions. | Established that sensitive actions must be role-gated and audited. | [audit-admin-rbac plan](../superpowers/plans/2026-04-29-audit-admin-rbac.md), [audit-admin-rbac spec](../superpowers/specs/2026-04-29-audit-admin-rbac-design.md) |
| 2026-05-08 | Accepted the Penguin tools model: SIEM-lite, SOAR-lite and XDR-lite are optional connected providers, not fake global tabs. | Keeps Fortinet-unavailable capabilities honest while preserving a modular SOC cockpit. | [Penguin foundation plan](../superpowers/plans/2026-05-08-penguin-tools-foundation.md), [Penguin data flow](../architecture/penguin-tools-data-flow.md) |
| 2026-05-11 | Persisted SIEM and XDR data and added endpoint-to-incident correlation. | Moved SOC state beyond in-memory demos and made endpoint context useful to analysts. | [SIEM persistence](../superpowers/plans/2026-05-11-siem-persistence.md), [XDR persistence](../superpowers/plans/2026-05-11-xdr-persistence.md), [endpoint correlation](../superpowers/plans/2026-05-11-penguin-endpoint-correlation.md) |
| 2026-05-12 | Added provenance labels and demo-readiness polish while keeping demo data visibly labeled. | Analysts can distinguish live, simulator, seeded demo and scripted AI output. | [MVP demo readiness](../superpowers/plans/2026-05-12-mvp-demo-readiness.md) |
| 2026-05-13 | Defined the AI assistant as a cockpit assistant, not an autonomous operator. | Prevents AI from bypassing human approval, secrets boundaries or destructive-action safeguards. | [AI architecture spec](../superpowers/specs/2026-05-13-ai-agent-architecture-design.md), [Pydantic AI plan](../superpowers/plans/2026-05-13-pydantic-ai-cockpit-agent.md) |
| 2026-05-13 | Added endpoint onboarding direction for `agent_private`. | Moves endpoint telemetry toward operator-owned onboarding instead of hidden behavior. | [XDR onboarding spec](../superpowers/specs/2026-05-13-xdr-agent-onboarding-design.md), [XDR onboarding plan](../superpowers/plans/2026-05-13-xdr-agent-onboarding.md) |
| 2026-05-14 | Chose real telemetry cutover over synthetic replay as the normal product path. | Product setup now leads with live FortiGate/syslog and endpoint telemetry. | [real telemetry cutover](../superpowers/plans/2026-05-14-real-telemetry-cutover.md), [FortiGate runbook](../operations/fortigate-scan-detection.md) |
| 2026-05-14 | Validated live FortiGate brute-force telemetry through the SOC pipeline. | Proved FortiGate events can create analyst-visible SIEM incidents without `/demo/replay`. | [SOC pipeline progress](../mvp/soc-pipeline-progress-2026-05-14.md), [FortiGate brute-force lab](../mvp/fortigate-brute-force-lab.md) |
| 2026-05-15 | Added BFF realtime event stream for FortiGate/SIEM tickets and widget snapshots. | Dashboard widgets and tickets can update from provider-triggered events instead of browser polling. | [realtime telemetry flow](../architecture/realtime-telemetry-flow.md), [roadmap](roadmap.md), [feature map](feature-map.md) |
| 2026-05-15 | Reorganized product documentation into feature map, roadmap, timeline and release notes. | Future plans and shipped state now have one canonical location instead of being scattered across MVP notes. | [product README](README.md), [release notes](release-notes.md) |
| 2026-05-15 | Planned FortiWeb 8.0.5 WAF marketplace integration for the landing-page demo. | Gives Fortinet evaluators a concrete WAF story while preserving honest integration boundaries. | [FortiWeb WAF plan](../superpowers/plans/2026-05-15-fortiweb-waf-marketplace-landing-lab.md), [FortiWeb lab runbook](../operations/fortiweb-landing-waf-lab.md) |

## Timeline Rules

- Add only durable decisions, shipped milestones and externally relevant
  changes.
- Do not list every commit or every plan task.
- Prefer absolute dates.
- Link to the plan, runbook or source-of-truth document that has the detailed
  context.
