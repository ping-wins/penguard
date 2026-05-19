# Executive SIEM Template Metrics Design

**Date:** 2026-05-19
**Scope:** Improve curated workspace templates, especially the executive
overview, and move executive SOC widget calculations into `siem_kowalski`.

---

## Context

The curated workspace presets live in `apps/api/app/workspaces/presets/`.
The executive preset already references SOC widgets for severity and MTTD/MTTR,
but `soc-mttd-mttr` and `soc-sla-breach` are catalog entries without first-class
BFF routing. Their catalog endpoints also point at the recent-incidents endpoint,
which forces the Vue components to derive executive metrics client-side from a
short incident feed.

This makes executive templates fragile: the SIEM owns incidents and event
provenance, but the browser estimates MTTD, MTTR and SLA breach counts. The SIEM
should calculate these aggregates and expose widget-ready sections.

---

## Design

Add `GET /metrics/executive` to `apps/siem_kowalski`. The response is a single
aggregate payload with:

- `severity`: incident counts by severity.
- `recentIncidents`: latest incidents for feed widgets.
- `topEntities`: top incident entities.
- `sla`: open incidents breaching amber/red SLA thresholds.
- `responseTimes`: MTTD/MTTR average, median and per-incident rows.

The BFF keeps the public widget API unchanged. For SIEM widgets it calls the new
SIEM metrics endpoint and returns the relevant section:

- `soc-incidents-by-severity` -> `severity`
- `soc-recent-incidents` -> `recentIncidents`
- `soc-top-entities` -> `topEntities`
- `soc-sla-breach` -> `sla`
- `soc-mttd-mttr` -> `responseTimes`

`soc-sla-breach` and `soc-mttd-mttr` are added to the SIEM widget routing and to
the Penguin-tool integration type mapping.

---

## Template Updates

Curated preset JSON files remain the source of truth for fresh installs. A new
Alembic migration upserts curated template rows so existing deployments receive
the improved presets without losing install counts.

The executive preset becomes a broader board with severity, response time, SLA
breach, risk posture, recent incidents and top entities. Analyst and incident
response presets get the missing high-signal SIEM widgets. Network and WAF
presets receive smaller layout and description improvements without changing
their provider boundaries.

---

## Metrics Rules

MTTD is calculated as incident creation time minus the earliest related event
time from `eventIds`. If event provenance is unavailable, the incident is
excluded from the MTTD sample.

MTTR is calculated from incident creation time to the first timeline status
change to `contained`, `resolved` or `false_positive`. Open incidents are
excluded from the MTTR sample.

SLA excludes closed, contained, resolved and false-positive incidents. Amber is
15 minutes old, red is 60 minutes old. The response includes counts plus breach
rows sorted by age descending.

---

## Testing

Backend tests cover:

- SIEM executive metrics aggregate severity, entities, recent incidents and
  response-time values from stored events/incidents.
- SLA calculations identify red and amber breach buckets.
- BFF SIEM widgets call `/metrics/executive` and return the correct section.
- `soc-sla-breach` and `soc-mttd-mttr` require a SIEM Penguin integration.
- Curated preset JSON remains valid and routes executive widgets through SIEM.

Frontend tests cover component fallback/consumption for calculated SLA and
MTTD/MTTR fields without requiring browser-side recomputation.

---

## Non-Goals

- No new autonomous action, playbook approval or FortiGate write path.
- No new polling loop.
- No new provider integration or marketplace add-on schema.
