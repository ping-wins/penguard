# Penguard Documentation

This directory is organized by purpose, not by sprint history. Use this index to
decide where new information belongs.

## Read First

- [Product docs](product/README.md): feature inventory, roadmap, timeline and
  release notes.
- [Architecture docs](architecture/README.md): data flow, threat model and
  runtime contracts such as the realtime telemetry flow.
- [Operations docs](operations/): operator runbooks for real FortiGate and lab
  validation.
- [API docs](api/): gateway and internal-service API notes.

## Documentation Ownership

| Area | Purpose | Update when |
| --- | --- | --- |
| `docs/product/feature-map.md` | Current product capability inventory. | A feature is added, retired, renamed or changes status. |
| `docs/product/roadmap.md` | Now / Next / Later priorities. | Priorities or acceptance criteria change. |
| `docs/product/timeline.md` | Durable shipped outcomes and decisions. | A meaningful product decision or release lands. |
| `docs/product/release-notes.md` | Customer-facing changelog. | A user-visible change ships. |
| `docs/architecture/` | System boundaries, data flow and threat model. | A design decision changes service boundaries, data flow or risk. |
| `docs/operations/` | Real setup, validation and troubleshooting. | Operators need a repeatable checklist. |
| `docs/mvp/` | Historical MVP scripts and lab-only walkthroughs. | Preserving demo/lab history only; do not use as product truth. |
| `docs/superpowers/` | AI-agent specs and implementation plans. | Planning or executing a bounded implementation phase. |

## Rules

- Product setup must lead with live FortiGate syslog/log-forwarding and
  `agent_private` telemetry, not synthetic replay.
- Demo replay, simulator paths and recording scripts stay in `docs/mvp/` or
  future `docs/lab/` files and must be labeled lab-only.
- `AGENTS.md` holds durable contributor rules. Do not paste sprint history into
  it.
- Plans under `docs/superpowers/` are implementation artifacts. Summarize their
  durable outcomes in `docs/product/timeline.md` instead of linking every task
  in normal product docs.

## Status Vocabulary

- `planned`: accepted direction, not started.
- `in-progress`: active branch or working tree work.
- `demo-only`: works only for lab, synthetic or demo paths.
- `beta`: implemented and usable, still needs hardening.
- `production-ready`: documented, tested, observable and secure by default.
- `deferred`: intentionally not being built now.
