# XDR Agent Onboarding UX Design

## Problem

The current XDR path proves the backend contract, but it still feels like a
developer workflow. An operator must create an enrollment token, copy shell
environment variables, run one-off `agent_private` CLI commands and inspect
logs or the Endpoints drawer to confirm success. That is acceptable for early
smoke tests, but it does not match the product expectation of connecting an
XDR/EDR agent to a Windows host.

The product experience should make endpoint onboarding feel like a guided SOC
operation: generate enrollment, install agent, wait for heartbeat, confirm live
telemetry.

## Goals

- Let an analyst onboard a Windows endpoint from the FortiDashboard cockpit.
- Keep endpoint enrollment tokens secret, one-time visible and auditable.
- Make the first heartbeat visible in the UI without grepping container logs.
- Make `agent_private` behave like a lightweight foreground agent before adding
  background installation.
- Keep all install/background behavior explicit and reversible. No hidden
  persistence or stealthy host modifications.

## Non-Goals

- No real containment or destructive endpoint action.
- No stealth persistence, credential collection or privilege escalation.
- No full MSI/EXE packaging in the first cut.
- No Windows Service in the first cut; Scheduled Task comes after the foreground
  loop is stable.

## Proposed User Flow

1. The analyst opens **Endpoints** or **Integrations -> XDR/Rico**.
2. The analyst clicks **Add Windows Agent**.
3. The cockpit asks for a display name and optional hostname hint.
4. The BFF calls `POST /api/weapons/enrollments`.
5. The cockpit shows:
   - enrollment id,
   - token shown once,
   - expiration/pending state when supported,
   - copyable PowerShell command,
   - optional bootstrap script download.
6. The Windows operator runs the command on the host.
7. The cockpit enters **Waiting for first heartbeat** and polls endpoint state.
8. Once `agent_private` posts heartbeat, the UI shows endpoint online with
   hostname, IP addresses, current user, health, last seen time and collectors.

## Agent Runtime Direction

`agent_private` should gain:

- `agent-private run`: foreground loop, safe to kill with Ctrl+C.
- Configurable intervals:
  - heartbeat: default 30 seconds,
  - connection snapshot: default 60 seconds,
  - process snapshot: default 300 seconds,
  - Windows Security polling: default 60 seconds, opt-in.
- A local config file loaded from the existing config path.
- Clear logs with masked token and last post status.
- Backoff/retry when the BFF is offline.

After this foreground loop is validated, add:

- `agent-private install-scheduled-task`
- `agent-private uninstall-scheduled-task`

These commands should create/remove a visible Windows Scheduled Task that runs
the same `agent-private run` command. A true Windows Service can be a later
production hardening step.

## Backend Requirements

- Keep `POST /api/weapons/enrollments` as the source of enrollment tokens.
- Add enough metadata to support cockpit pending state:
  - display name,
  - hostname hint,
  - created at,
  - optional expires at,
  - used/first-seen state.
- Keep token values out of logs, audit metadata and follow-up responses.
- Audit enrollment creation and future revoke/rotate actions.
- Reuse existing `POST /api/weapons/endpoint-events` for all telemetry.

## Frontend Requirements

- Add an XDR onboarding wizard from the Endpoints area or XDR connector card.
- Show a pending enrollment card until first heartbeat.
- Show status transitions:
  - token created,
  - waiting for heartbeat,
  - online,
  - stale,
  - failed/expired when supported.
- Provide copyable Windows PowerShell snippets.
- Provide useful errors:
  - API unreachable,
  - invalid token,
  - Windows Security log access denied,
  - audit policy missing events.

## Testing Strategy

- Unit-test BFF enrollment metadata and token redaction.
- Unit-test `agent_private run` scheduling/backoff with a fake poster.
- Unit-test Windows command generation in the Vue wizard.
- Add an integration smoke:
  - create enrollment,
  - post heartbeat,
  - endpoint appears online,
  - timeline shows heartbeat.
- Manual Windows smoke:
  - run generated PowerShell command,
  - observe pending -> online transition,
  - post `windows-security --post`,
  - confirm incident/ticket for failed-login burst.

## Implementation Slices

1. **Onboarding UX only**
   Add cockpit wizard and pending status around the existing enrollment and
   endpoint APIs.

2. **Foreground agent loop**
   Add `agent-private run` with interval scheduling, config loading and masked
   logs.

3. **Windows Scheduled Task**
   Add explicit install/uninstall commands that wrap the foreground loop.

4. **Hardening**
   Token expiry/revocation, stale endpoint thresholds, richer collector health
   and packaging.
