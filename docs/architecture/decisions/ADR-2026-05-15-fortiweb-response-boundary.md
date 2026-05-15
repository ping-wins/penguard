# ADR 2026-05-15: FortiWeb And FortiGate Response Boundary

## Status

Proposed

## Context

FortiDashboard will ingest FortiWeb WAF telemetry from a FortiWeb 8.0.5 trial
protecting the external landing page. SIEM incidents may require response
suggestions such as blocking an abusive source IP, increasing WAF enforcement,
or asking FortiGate to block traffic upstream.

## Decision

All response actions must be initiated from FortiDashboard, require an
authenticated admin session, require explicit approval, and write audit events
before and after the action.

For the first FortiWeb WAF MVP, live response actions are not auto-applied.
`soar_skipper` may create recommendation-only or dry-run actions:

- Recommend FortiWeb block rule.
- Recommend FortiGate upstream block.
- Draft CLI/API payload for operator review.

Live FortiWeb/FortiGate writes require a follow-up ADR that names exact API
paths, preflight reads, rollback behavior, audit fields, and permission checks.

## Consequences

- The demo can show FortiWeb blocking attacks and FortiDashboard generating
  incidents in realtime.
- FortiDashboard remains the only place where response actions are requested.
- The project does not silently modify customer WAF/firewall policy.
