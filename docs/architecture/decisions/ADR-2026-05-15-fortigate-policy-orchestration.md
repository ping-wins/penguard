# ADR 2026-05-15: FortiGate Policy Orchestration

## Status

Accepted.

## Context

FortiDashboard is intended to orchestrate SOC tools, not only observe them. The
previous contract treated FortiGate as effectively read-only except for syslog
forwarding and allowed traffic-policy helpers to stop at draft CLI guidance.
That does not match the product premise or the lab need to create a log-enabled
traffic path for scan detection from inside FortiDashboard.

The FortiGate API credentials used by the connector may have the permissions
needed to create or update firewall policy objects. That power must be governed
inside FortiDashboard rather than hidden, mocked, or pushed out to manual
FortiGate UI work.

## Decision

FortiDashboard may perform real FortiGate firewall traffic-policy orchestration.
Policy orchestration is a first-class product capability, not a draft/mock-only
helper.

Every live FortiGate policy write must go through the BFF and satisfy all of
these controls:

- admin RBAC on the server side;
- CSRF protection for browser-triggered requests;
- preflight reads of interfaces, address objects, services and relevant current
  policies;
- a human-readable diff or summary before apply;
- explicit human confirmation;
- FortiDashboard-owned objects/policies only, unless a later ADR expands scope;
- no silent overwrite of customer configuration;
- audit events with secrets redacted, including target entities, before/after
  summary, FortiGate response and rollback guidance;
- incident timeline updates when the policy change is tied to a SIEM/SOAR flow.

The first implementation target is a lab/customer validation policy flow that
can create or verify log-enabled deny/log and allow/log policies for traffic
between selected FortiGate interfaces. Later response flows may reuse the same
orchestration boundary for temporary source-IP containment after approval.

## Non-Goals

- AI may not directly apply or approve FortiGate policy changes.
- SIEM detections may not trigger FortiGate policy writes without a human
  approval gate.
- Background jobs may not silently mutate FortiGate policies.
- This ADR does not approve route, interface, admin, global setting, VPN,
  authentication or feature-disable changes.
- This ADR does not approve destructive or stealthy actions.

## Consequences

- Existing draft-only FortiGate traffic-policy helpers are deprecated as the
  product path and should be replaced by real policy orchestration endpoints.
- SOAR FortiGate action nodes may become live only by calling the governed BFF
  orchestration API after approval.
- Tests must cover both refusal paths and successful FortiGate write paths using
  fakes; lab validation must use a real FortiGate before marking the feature
  beta or production-ready.
- Operations docs can keep CLI examples for manual recovery or troubleshooting,
  but normal lab/customer validation should be possible from FortiDashboard.
