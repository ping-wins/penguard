# Incident Drawer Triage UX Design

**Status:** Approved in brainstorming, pending written spec review

**Date:** 2026-05-20

**Owner:** Codex

**Related:** [`2026-05-15-generic-triage-engine-mitre-design.md`](2026-05-15-generic-triage-engine-mitre-design.md), [`2026-05-15-fortigate-policy-orchestration-design.md`](2026-05-15-fortigate-policy-orchestration-design.md), [`2026-05-17-soar-playbook-canvas-engine-design.md`](2026-05-17-soar-playbook-canvas-engine-design.md), [`2026-05-18-unified-soc-assistant-ux-design.md`](2026-05-18-unified-soc-assistant-ux-design.md)

## Goal

Clean up the right-side incident drawer so an analyst can open a SOC ticket,
understand the incident, analyze it, and run the approved containment flow
without being hit by every available field at once.

The immediate pain point is a high-severity port-scan incident where the drawer
currently exposes detection details, deterministic triage, manual status
controls, threat intel, FortiWeb response, AI analysis, playbook execution,
FortiGate policy review, raw entities, and timeline in one narrow scrolling
surface. The new UX keeps the same capabilities but presents them as a guided
workflow.

## Scope

In scope:

- The incident detail drawer opened from `TicketsPanel.vue`.
- The flow from ticket receipt to analysis to playbook/policy containment.
- Frontend organization, copy, state derivation, and tests.
- Existing SOC, SOAR, FortiGate, FortiWeb, AI, and threat intel API contracts.

Out of scope:

- Replacing the dashboard canvas, sidebar, or ticket lane model.
- Backend schema or detection-engine changes.
- Changing FortiGate orchestration behavior.
- Removing analyst access to raw entities, timelines, evidence, or provider
  details.

## UX Decisions

| Question | Decision |
|---|---|
| Default drawer model | Use a guided three-step drawer: Summary, Analysis, Containment. |
| First screen | Show only the incident facts and the next recommended action. |
| Raw fields | Keep raw entities, full evidence, timeline, MITRE details, and provider IDs behind explicit details/disclosure controls. |
| Containment | Present one primary containment path at a time, based on current state. |
| FortiGate policy form | Hide advanced policy inputs until a policy review is actually required or the analyst chooses to edit them. |
| FortiWeb actions | Keep available, but move behind secondary provider actions unless the incident is FortiWeb/WAF scoped. |
| APIs | Reuse existing endpoints. Do not add a backend dependency for the UX cleanup. |
| Localization | All new visible strings go through `pt-BR` and `en-US` catalogs. |

## Information Architecture

### Drawer Header

The header remains fixed at the top of the drawer and should answer:

- What incident is open.
- Current severity, triage level, and ticket status.
- When it was opened.
- The primary entities involved when known.

For a port-scan case, the header should summarize:

- "Port scan detected".
- Source to destination relationship.
- Observed port count and detection window.
- `T3`, high severity, and current ticket status.

The incident id remains visible but secondary. It should not compete with the
incident title or next action.

### Workflow Stepper

The drawer shows three top-level steps:

1. **Summary** - read the incident and confirm it deserves attention.
2. **Analysis** - review deterministic evidence, optional AI analysis, and
   optional threat intel.
3. **Containment** - instantiate/run the playbook, approve the run, review the
   FortiGate policy, and apply it when permitted.

The stepper is local UI state. It does not change ticket state by itself.

Default step:

- New or investigating tickets open on Summary.
- Contained tickets may open on Containment if a playbook/policy result exists,
  otherwise Summary.

Automatic nudges:

- Running analysis moves the active step to Analysis.
- Requesting containment or using a recommended playbook template moves the
  active step to Containment.
- Applying a policy keeps the active step on Containment and shows the final
  result.

## Step Details

### Summary Step

Purpose: make the incident understandable in under 10 seconds.

Show:

- One short summary sentence.
- Key facts as compact rows or chips:
  - detection rule or attack type,
  - source entity,
  - target entity,
  - observed scope such as unique port count and window,
  - FortiGate integration/provider presence when relevant.
- Manual triage/status controls in a compact secondary area.
- Primary CTA: **Analyze incident**.
- Secondary CTA: **Prepare containment** when deterministic triage already
  identifies an available response.

Hide by default:

- Full detection object.
- All related event ids.
- Destination port list.
- Full entities table.
- Timeline.
- FortiWeb form.
- FortiGate policy form.

### Analysis Step

Purpose: explain why this is a real incident and what evidence supports the
response.

Show:

- Deterministic triage summary first.
- Confidence, recommended triage level, and recommended status.
- Top evidence items, capped for scanability.
- MITRE mapping chips with technique id and name.
- Threat intel and AI analysis as explicit analyst actions, not always-visible
  blocks.
- Results from threat intel or AI only after the analyst triggers them.

Use disclosures for:

- Full evidence list.
- Full MITRE reasoning.
- Raw indicator verdicts.
- AI CVSS/reference details.
- Missing data details.

Errors stay inside the Analysis step. If triage context fails to load, the
drawer still shows the Summary step and lets the analyst retry or continue with
manual controls.

### Containment Step

Purpose: make the live response path clear and governed.

Show a single primary path with current state:

1. Recommended playbook template or draft.
2. Dry-run/simulation status.
3. Approval gate.
4. FortiGate policy review.
5. FortiGate apply result.
6. Ticket contained status.

The visible primary CTA should depend on state:

- No playbook draft: **Prepare playbook** or **Use recommended template**.
- Draft exists and no run: **Run dry-run**.
- Run waits for approval: **Approve run**.
- Policy review required and no review exists: **Create FortiGate review**.
- Policy review exists and not applied: **Apply FortiGate policy**.
- Policy applied: show contained confirmation and rollback/audit guidance when
  available from the existing response payload.

Advanced FortiGate inputs remain available but collapsed:

- integration,
- source interface,
- destination interface,
- source IP,
- destination IP,
- scope,
- service,
- duration.

The default presentation should prefer the system-derived values from the
incident and triage context. Analysts should edit advanced fields only when the
defaults are wrong.

FortiWeb source block controls move under a secondary **Other provider actions**
disclosure unless the ticket source or attack family is WAF/FortiWeb related.

## Component Boundaries

The current `TicketsPanel.vue` is doing too much. The implementation should
extract the drawer into focused ticket components while preserving existing
store and service contracts.

Suggested structure:

```txt
apps/web/src/components/tickets/
  TicketsPanel.vue
  incident-drawer/
    IncidentDrawer.vue
    IncidentSummaryStep.vue
    IncidentAnalysisStep.vue
    IncidentContainmentStep.vue
    IncidentDetailsDisclosure.vue
    incidentDrawerState.ts
```

Responsibilities:

- `TicketsPanel.vue`: ticket list, filters, lane selection, selected ticket.
- `IncidentDrawer.vue`: shell, header, stepper, active step state, close action.
- `IncidentSummaryStep.vue`: key facts, compact triage/status controls, next
  action buttons.
- `IncidentAnalysisStep.vue`: deterministic triage, AI, threat intel, evidence
  disclosures.
- `IncidentContainmentStep.vue`: playbook, approval, policy review/apply, and
  secondary provider actions.
- `IncidentDetailsDisclosure.vue`: reusable disclosure for raw entities,
  timeline, full evidence, and provider payloads.
- `incidentDrawerState.ts`: pure helpers for deriving incident facts, available
  response labels, primary containment action, and step status.

The first implementation may keep business functions in the parent while
extracting display components. Helper functions that do not need Vue state
should move to `incidentDrawerState.ts` and receive typed inputs.

## Data Flow

No new backend endpoint is required.

Existing calls remain:

- `GET /api/soc/tickets`
- `GET /api/soc/tickets/{ticketId}`
- `GET /api/soc/incidents/{incidentId}/triage-context`
- `POST /api/soc/incidents/{incidentId}/analyze`
- `POST /api/soc/incidents/{incidentId}/containment-suggestions`
- `POST /api/soc/tickets/{ticketId}/draft-playbook`
- `POST /api/soc/tickets/{ticketId}/apply-containment`
- `POST /api/soc/playbook-runs/{runId}/approve`
- FortiGate policy review/apply endpoints already used by the ticket drawer.
- FortiWeb review/apply/remove endpoints already used by the ticket drawer.

Derived UI state:

- `incidentFacts`: normalized title, attack type, source, target, observed
  count/window, provider, severity, triage level, ticket status.
- `analysisStatus`: idle/loading/ready/error for deterministic triage, AI, and
  threat intel.
- `containmentState`: draft/run/approval/policy-review/policy-applied status.
- `primaryContainmentAction`: label, disabled state, loading state, and handler
  for the next response action.
- `hasAdvancedPolicyFields`: true only when review/apply is available or the
  analyst explicitly opens advanced fields.

## Error Handling

- Network/API errors render in the active step, near the action that failed.
- The drawer never collapses the entire incident because one optional enrichment
  failed.
- Disabled actions include a concise reason when required data is missing.
- Policy review errors keep entered values intact.
- Applying a FortiGate policy can mark containment partial if the ticket update
  fails, using the existing error text.

## Visual Rules

- Keep density appropriate for a SOC cockpit, but reduce simultaneous blocks.
- Use small icon+text buttons for actions.
- Avoid nested cards. Use drawer bands, disclosures, and compact rows.
- Keep text within fixed-width controls at mobile and desktop widths.
- Preserve dark cockpit theme tokens and severity token helpers.
- Do not add marketing-style hero sections or decorative visuals.

## Testing

Add focused frontend tests around the drawer behavior:

- Opening a high-severity port-scan ticket shows the Summary step by default.
- Summary shows the concise facts and does not render raw entities, full
  timeline, FortiWeb controls, or FortiGate policy form by default.
- Analysis step shows deterministic triage evidence and MITRE mapping after the
  triage context loads.
- AI and threat intel results appear only after their actions are triggered.
- Containment step exposes the correct primary CTA for each state:
  draft missing, draft ready, run waiting approval, policy review required,
  review ready, policy applied.
- Advanced FortiGate fields are hidden until policy review is required or the
  analyst opens advanced settings.
- Existing `data-test` selectors used by current tests are preserved or mapped
  to stable replacements.
- New strings exist in both `pt-BR` and `en-US` catalogs.

Run before handoff:

```bash
cd apps/web && pnpm test
cd apps/web && pnpm build
git diff --check
```

## Acceptance Criteria

- Opening an incident drawer first shows a concise Summary step, not the full
  incident payload.
- The analyst can still reach every existing capability: manual status updates,
  deterministic triage context, AI analysis, threat intel, playbook draft/run,
  approval, FortiGate review/apply, FortiWeb source block, entities, and
  timeline.
- The primary path for a FortiGate port-scan containment is clear without
  scrolling through unrelated provider forms.
- Raw operational details are present but intentional to open.
- The implementation touches only the frontend ticket drawer and localization
  unless tests reveal a contract bug.
