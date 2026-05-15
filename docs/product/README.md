# Product Documentation

`docs/product/` is the source of truth for what FortiDashboard is, what is
shipping now, what comes next and what changed for users.

## Canonical Files

| File | Purpose | Audience |
| --- | --- | --- |
| [feature-map.md](feature-map.md) | Current feature inventory with status, owner and verification command. | Product, engineering, reviewers. |
| [roadmap.md](roadmap.md) | Now / Next / Later priorities with acceptance criteria. | Product and implementation planning. |
| [timeline.md](timeline.md) | Short chronology of durable decisions and shipped outcomes. | Onboarding and historical context. |
| [release-notes.md](release-notes.md) | Customer-facing changelog grouped by release/date. | Users, demos, stakeholders. |

## Maintenance Contract

- Update `feature-map.md` when a capability is added, removed, renamed or
  changes status.
- Update `roadmap.md` when priorities move between Now, Next and Later.
- Update `timeline.md` only for durable product outcomes. Do not paste sprint
  logs.
- Update `release-notes.md` for user-visible changes, operational changes and
  security-relevant behavior.
- Keep lab-only or synthetic flows out of product setup. Link them from
  `docs/mvp/` or future `docs/lab/` files instead.

## Status Vocabulary

- `planned`: accepted direction, not started.
- `in-progress`: active branch or working tree work.
- `demo-only`: works only for lab, synthetic or demo paths.
- `beta`: implemented and usable, still needs hardening.
- `production-ready`: documented, tested, observable and secure by default.
- `deferred`: intentionally not being built now.

## Source-Of-Truth Rule

Product docs should summarize the current product state and point to source
files, tests, operations runbooks or implementation plans. They should not
duplicate long implementation details from `docs/superpowers/`.
