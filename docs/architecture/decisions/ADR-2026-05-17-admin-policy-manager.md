# ADR 2026-05-17: Administrative SOC Policy Manager

## Status

Accepted.

## Context

FortiDashboard currently treats live policy writes as narrow governed
orchestration. FortiGate policy orchestration is limited to
FortiDashboard-owned objects, and the FortiWeb response boundary still describes
live WAF writes as a follow-up decision.

The product direction now requires an administrative workspace widget that can
view and manage every policy exposed by connected SOC providers. This includes
FortiGate firewall policies, FortiWeb WAF/server-policy response controls and
future provider policy objects.

## Decision

FortiDashboard may let permitted administrators create, edit, enable, disable
and remove policies returned by connected SOC providers, including policies not
created by FortiDashboard. Reordering policy priority remains out of scope for
the MVP.

Every write must go through the BFF with permission `policies.manage`, CSRF
protection, preflight, provider-specific diff, explicit confirmation, audit
events and rollback guidance.

Audit details must identify:

- provider type;
- integration id;
- native policy id;
- policy ownership;
- whether the policy was FortiDashboard-owned or external/customer-owned;
- before/after summary;
- rollback guidance;
- provider response status with secrets redacted.

AI, SIEM detections, background jobs and browser state may not apply or approve
policy changes by themselves.

## Consequences

The FortiGate policy orchestration ADR remains valid for governed writes, but
its FortiDashboard-owned-only restriction is superseded for human-confirmed
administrator actions through the SOC Policy Manager.

The proposed FortiWeb response boundary remains valid for non-admin automation,
but live FortiWeb policy/block writes are allowed through this admin policy
manager boundary after provider-specific preflight and review.

Provider adapters must disable unsupported actions and must reject stale reviews
if provider state changes between review and apply.
