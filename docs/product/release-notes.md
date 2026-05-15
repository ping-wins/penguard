# Release Notes

Customer-facing changelog. Internal implementation plans stay in
`docs/superpowers/`; this file summarizes user-visible behavior.

## Unreleased

### Added

- Added FortiGate syslog/log-forwarding telemetry as the normal live ingestion
  path.
- Added realtime BFF event stream support for SIEM tickets and FortiGate widget
  snapshots.
- Added shared frontend realtime widget state so duplicate widgets render the
  same latest provider snapshot.
- Added audit-to-SIEM forwarding for security-relevant BFF actions.
- Added governed FortiGate policy orchestration: lab allow+log wizard,
  ticket-linked temporary block review/apply, review hashes and audit events.
- Added SIEM detection for allowed FortiGate port-scan traffic when an allow+log
  policy records many destination ports from one source in the detection window.
- Added product documentation set: feature map, roadmap, timeline and release
  notes.
- Planned FortiWeb WAF marketplace add-on for the external landing-page demo,
  with WAF telemetry normalized into SIEM incidents.

### Changed

- Product setup now leads with live FortiGate and endpoint telemetry instead of
  synthetic replay.
- Scheduled/manual FortiGate event ingestion is documented as fallback or
  diagnostic behavior, not the normal dashboard refresh path.
- Synthetic replay and simulator endpoints are lab-only and require explicit
  lab/demo enablement.
- The cockpit keeps SOC and FortiGate widget data source labels visible so
  analysts can distinguish live, simulator, seeded demo and scripted AI output.
- FortiGate policy changes now use governed orchestration work rather than
  draft/mock-only CLI guidance.

### Fixed

- Fixed stale duplicate FortiGate widgets by sharing the latest realtime widget
  snapshot across widget instances.
- Fixed FortiGate syslog source resolution when multiple connectors point at
  the same host by preferring device identifiers before host fallback.
- Fixed SOC incident updates so realtime FortiGate brute-force findings can
  surface in tickets without a browser refresh.

### Security

- FortiGate policy orchestration must be admin-gated, explicit, audited and
  based on preflight plus diff/summary. AI, SIEM detections and background jobs
  cannot apply policy changes by themselves.
- API keys remain encrypted at rest and are not returned to the browser.
- Lab/demo tools are separated from normal runtime paths and must remain
  clearly labeled.

### Known Gaps

- Production readiness work is still pending for structured JSON logging,
  `/health/live`, `/health/ready`, Prometheus `/metrics`, retention policies,
  backup/restore and CI quality gates.
- Incident dedupe for repeated same-rule/same-entity bursts is still planned.
