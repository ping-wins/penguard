# Generic Triage Engine With MITRE ATT&CK Design

Date: 2026-05-15

## Context

Penguard is moving from a port-scan-only SOC demo into a generic SOC lab
and orchestration cockpit. The current SIEM and ticket flow already detects
multiple alert types, including network scans, denied traffic bursts, repeated
failed logins, suspicious endpoint connections and FortiGate resource pressure.

The current ticket response flow is too coupled to the port-scan path. It can
draft containment, run SOAR dry-runs and approve FortiGate policy reviews, but
the product lacks a generic contract that explains any incident, maps it to
MITRE ATT&CK, recommends response actions and chooses eligible SOAR templates.

This design introduces a deterministic Triage Engine. AI remains an explanation
and drafting layer, not the source of truth for classification or allowed
actions.

## Goals

- Produce a normalized `TriageContext` for every SOC incident.
- Map supported alert families to MITRE ATT&CK tactics and techniques with
  confidence and rationale.
- Extract structured evidence from incidents, entities, attributes, timelines
  and related events.
- Generate response candidates from a registry instead of hardcoding port-scan
  behavior in the ticket UI.
- Match SOAR playbook templates by alert family, technique and available
  provider capabilities.
- Support both port-scan and brute-force triage in the first implementation
  slice while keeping the engine extensible.
- Make missing data explicit so the UI can explain why an action is unavailable.
- Audit triage generation, AI explanation, playbook instantiation, approval,
  rejection and policy application.

## Non-Goals

- Do not make AI an autonomous incident commander.
- Do not auto-approve SOAR steps, FortiGate policies, endpoint actions or
  identity actions.
- Do not require a full FortiSOAR, FortiSIEM or FortiEDR deployment for the MVP.
- Do not build every ATT&CK technique. Only map techniques supported by actual
  detections and evidence.
- Do not treat ATT&CK mappings as absolute truth; every mapping carries
  confidence and a reason.

## Core Flow

```txt
SIEM incident
  -> Triage Engine
    -> Alert Family Classifier
    -> Evidence Extractors
    -> MITRE Mapping Registry
    -> Response Candidate Registry
    -> Playbook Template Matcher
  -> Ticket drawer
  -> Optional AI explanation
  -> SOAR template instantiation
  -> Human approval
  -> Governed response action
  -> Audit and ticket timeline
```

## Triage Context Contract

The gateway should expose a typed triage payload through the ticket detail API
or a dedicated triage endpoint. The recommended shape is:

```txt
triageContext:
  incidentId: string
  ruleId: string
  alertFamily: string
  attackType: string
  severity: string
  confidence: low | medium | high
  recommendedTriageLevel: T1 | T2 | T3
  recommendedTicketStatus: new | investigating | contained | closed
  summary: string
  evidence: EvidenceItem[]
  entities: TriageEntity[]
  impactedAssets: ImpactedAsset[]
  mitreMappings: MitreMapping[]
  responseCandidates: ResponseCandidate[]
  playbookTemplates: PlaybookTemplateRecommendation[]
  missingData: MissingDataItem[]
  generatedAt: ISO8601 string
```

### EvidenceItem

```txt
id: stable string
type: threshold | entity | event | timeline | correlation | provider_state
label: string
value: string | number | string[] | object
threshold: optional number/string/object
severity: informational | low | medium | high | critical
source: siem_kowalski | fortigate | xdr_rico | soar_skipper | manual
```

Evidence is intentionally display-ready and testable. It should not contain
secrets, credentials or raw unbounded logs.

### MitreMapping

```txt
tacticId: string
tacticName: string
techniqueId: string
techniqueName: string
subtechniqueId: optional string
subtechniqueName: optional string
confidence: low | medium | high
reason: string
evidenceIds: string[]
```

### ResponseCandidate

```txt
id: string
type: string
label: string
description: string
riskLevel: low | medium | high
requiresApproval: boolean
availableNow: boolean
providerRequired: optional string
reason: string
parameters: object
mappedMitreTechniqueIds: string[]
playbookTemplateIds: string[]
```

Unavailable candidates are first-class. They explain what the SOC could do if a
future provider existed, such as an identity provider for account lockout.

### PlaybookTemplateRecommendation

```txt
templateId: string
label: string
reason: string
confidence: low | medium | high
requiredCandidateIds: string[]
parameters: object
requiresApproval: boolean
```

## Alert Families

The first engine version should support these families:

```txt
network.scan
network.denied_burst
auth.bruteforce
endpoint.suspicious_connection
identity.privileged_logon
fortigate.resource_pressure
manual.investigation
```

Each family has its own evidence extractor and response-candidate mapping. The
engine should choose family by `ruleId`, then refine `attackType` from incident
attributes.

## Initial MITRE ATT&CK Mappings

### network.scan

```txt
Tactic: TA0007 Discovery
Technique: T1046 Network Service Discovery
Confidence: high when unique destination ports exceed threshold in a short window.
```

Used for allowed or denied port scan incidents when evidence includes source IP,
destination IP and unique destination port count.

### network.denied_burst

```txt
Tactic: TA0007 Discovery or TA0043 Reconnaissance
Technique: T1046 Network Service Discovery or T1595 Active Scanning
Confidence: medium unless unique destination ports or scan target pattern is present.
```

Denied bursts may be noisy firewall background traffic. The engine should state
why confidence is medium and avoid overclaiming confirmed attack behavior.

### auth.bruteforce

```txt
Tactic: TA0006 Credential Access
Technique: T1110 Brute Force
Confidence: high when repeated failed login count crosses threshold for a source,
user or target surface inside the detection window.
```

Used for FortiGate failed admin/VPN login attempts and endpoint failed login
events when enough source/user evidence is available.

### endpoint.suspicious_connection

```txt
Tactic: TA0011 Command and Control
Technique: T1071 Application Layer Protocol
Confidence: low to medium unless destination, process or protocol evidence
supports C2-like behavior.
```

This mapping is conditional. If the incident only says "suspicious connection"
without protocol/process evidence, the mapping should be lower confidence.

### identity.privileged_logon

```txt
Tactic: TA0005 Defense Evasion or TA0006 Credential Access, depending on context
Technique: T1078 Valid Accounts
Confidence: medium when privileged authentication succeeds from unusual context.
```

This family should be conservative. A valid admin login is not automatically a
compromise.

### fortigate.resource_pressure

Resource pressure does not get a default ATT&CK mapping. CPU, memory and session
pressure can be operational. If future evidence shows flood behavior, a separate
DoS-related family should be created.

## Response Candidate Registry

Candidates are deterministic functions of triage context and provider
capabilities.

### Shared candidates

- `case.add_note`: always available, low risk, no approval.
- `ticket.escalate_tier`: available for T1/T2/T3 changes, low risk.
- `entity.add_watchlist`: available when source IP, username, host or endpoint
  exists.
- `soar.run_template`: available when a matching template exists.

### FortiGate candidates

- `fortigate.temporary_source_block`
  - Available when FortiGate integration and source IP exist.
  - Requires approval.
  - High risk when scope is broad.
- `fortigate.temporary_source_destination_block`
  - Available when source IP and destination IP exist.
  - Requires approval.
  - Preferred for network scan containment when destination evidence is reliable.
- `fortigate.policy_review_only`
  - Available when a policy write cannot be safely applied.
  - Produces operator-facing review guidance.

### Identity candidates

- `identity.review_account`
  - Available when username exists.
  - No live provider required; produces investigation guidance.
- `identity.lock_user`
  - Unavailable until an identity provider connector exists.
  - Requires approval and stronger RBAC when implemented.
- `identity.force_password_reset`
  - Unavailable until an identity provider connector exists.
  - Requires approval and strong audit when implemented.

### Endpoint candidates

- `endpoint.collect_context`
  - Available when endpoint ID, hostname or IP correlates with XDR.
- `endpoint.isolate_host`
  - Future action only. Requires XDR/EDR provider support, approval and a new
    architecture decision before live execution.

## Playbook Templates

Templates are SOAR-lite playbooks with deterministic IDs and parameter slots.
The engine recommends templates; it does not need to create a new graph from
scratch for every incident.

Initial templates:

```txt
pb_network_scan_triage
pb_auth_bruteforce_triage
pb_fortigate_temp_block
pb_endpoint_connection_triage
pb_resource_pressure_review
```

### pb_network_scan_triage

Steps:

```txt
trigger.incident_created
case.note
enrich.ip
approval.required
fortigate.temporary_block
case.note
```

Parameters:

- source IP
- destination IP
- destination ports
- integration ID
- block scope
- duration

### pb_auth_bruteforce_triage

Steps:

```txt
trigger.incident_created
case.note
enrich.ip
case.note for username/target surface
approval.required
fortigate.temporary_block when source IP exists
case.note for identity review when username exists
```

Parameters:

- source IP
- username
- target service
- failed login count
- integration ID
- recommended account action

Identity actions remain recommendations until an identity connector exists.

## AI Role

AI should consume `TriageContext`, not raw service internals. It may:

- Explain the incident in the analyst's locale.
- Summarize evidence.
- Suggest which recommended template to use.
- Draft analyst notes.
- Explain unavailable actions and missing data.

AI must not:

- Invent actions outside the response-candidate registry.
- Approve SOAR runs.
- Apply FortiGate policies.
- Lock users or isolate endpoints.
- Hide confidence or missing evidence.

The AI output should reference candidate IDs and template IDs from the
deterministic engine.

## API Surface

Recommended gateway endpoints:

```txt
GET  /api/soc/incidents/{incidentId}/triage-context
POST /api/soc/incidents/{incidentId}/triage-context/recompute
POST /api/soc/incidents/{incidentId}/playbook-recommendations/{templateId}/instantiate
POST /api/soc/tickets/{ticketId}/response-candidates/{candidateId}/reject
```

Ticket detail may inline `triageContext` for UX speed. A dedicated endpoint is
still useful for recompute, testing and future LangGraph nodes.

## Ticket UI

The ticket drawer should use five fixed sections:

```txt
1. Detection
   rule ID, alert family, attack type, severity, confidence and MITRE mapping.

2. Evidence
   threshold matches, entities, counts, windows, related events and rationale.

3. Entity Context
   source, target, user, endpoint, provider and integration correlation.

4. Recommended Response
   available and unavailable response candidates with risk and approval labels.

5. Execution
   SOAR runs, approval gates, policy reviews, timeline and audit links.
```

The UI should never show a single generic "apply playbook" button without first
showing why that playbook is eligible.

## Storage And Audit

The first version can compute triage context on read and persist only the audit
events and SIEM timeline notes. Once the context becomes stable, persist:

- latest triage context hash.
- generated context payload.
- recommendation decisions.
- rejected candidate notes.
- selected playbook template.
- approval and execution correlation IDs.

Every state-changing action must audit:

- triage recompute.
- response candidate rejection.
- playbook instantiation.
- run approval.
- FortiGate policy review creation.
- FortiGate policy apply.

## Implementation Slices

### Slice 1: Contracts And Engine

- Add shared Pydantic contracts for triage context in `packages/contracts` and
  backend models.
- Implement deterministic engine under `apps/api/app/soc/triage/`.
- Support `network_scan`, `denied_traffic_burst` and `repeated_failed_login`.
- Add gateway endpoint and tests.

### Slice 2: Ticket UI

- Render triage context in the ticket drawer.
- Show MITRE mappings with confidence and reason.
- Show available/unavailable response candidates.
- Link candidates to SOAR template recommendations.

### Slice 3: SOAR Templates

- Add deterministic templates for network scan and brute force.
- Instantiate templates with incident parameters.
- Keep approval and FortiGate policy apply governed by existing policy review.

### Slice 4: AI Explanation

- Change AI analysis and containment suggestion prompts to consume
  `TriageContext`.
- Require AI output to reference candidate IDs and template IDs.
- Localize explanations while preserving strict JSON schemas.

## Verification Strategy

Backend tests:

- `network_scan` maps to ATT&CK `T1046` with high confidence when port-count
  evidence exists.
- `repeated_failed_login` maps to `T1110` with high confidence when failed
  login threshold evidence exists.
- `denied_traffic_burst` maps with medium confidence unless scan-specific
  evidence exists.
- resource pressure produces no ATT&CK mapping by default.
- response candidates explain unavailable identity actions when no identity
  provider is connected.
- FortiGate temporary block candidates require source IP and approval.

Frontend tests:

- ticket drawer shows Detection, Evidence, Entity Context, Recommended Response
  and Execution.
- MITRE technique, confidence and reason render for port scan and brute force.
- unavailable candidates are visible and cannot be executed.
- playbook template selection displays required approvals before run creation.

End-to-end lab tests:

- nmap from attacker to victim creates `network.scan`, maps to `T1046`, suggests
  FortiGate temporary block and requires approval.
- FortiGate failed login burst creates `auth.bruteforce`, maps to `T1110`,
  suggests source block plus account review and marks identity actions
  unavailable when no identity connector exists.

## Design Decisions

- MITRE ATT&CK is a triage contract field, not only a UI badge.
- The deterministic engine owns classification, confidence, candidates and
  template eligibility.
- AI explains and drafts from the engine output; it does not invent allowed
  actions.
- Unavailable actions stay visible because they explain SOC capability gaps and
  future connector value.
- The first complete demo should cover both network scan and brute force using
  the same engine.
