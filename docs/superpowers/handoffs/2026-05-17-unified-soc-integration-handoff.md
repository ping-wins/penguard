# Unified SOC Integration — Execution Handoff

**Date:** 2026-05-17
**For:** Felipe (continuing execution)
**Plan:** [`../plans/2026-05-17-unified-soc-integration.md`](../plans/2026-05-17-unified-soc-integration.md)
**Spec:** [`../specs/2026-05-17-unified-soc-integration-design.md`](../specs/2026-05-17-unified-soc-integration-design.md)
**Execution method:** Subagent-Driven Development (superpowers) — fresh subagent per task + two-stage review (spec compliance, then code quality).

---

## Where execution stopped

Stopped **before starting Task 1.4** (user request). Tasks 1.1, 1.2, 1.3 are **complete, reviewed (spec ✅ + quality ✅), and committed**. Task 1.4 is **not started**.

### Two git repos in play

| Repo | Path | Remote |
|---|---|---|
| **DASH** (dashboard) | `C:\Users\lucas\Desktop\PingWins-FortiDashboard\FortiDashboard` | `github.com/ping-wins/fortidashboard` |
| **PKGS** (add-on packages) | `C:\Users\lucas\Desktop\PingWins-FortiDashboard\fortidashboard-addons` | `github.com/ping-wins/fortidashboard-addons` |

### Done

| Task | Repo | Result | Commit |
|---|---|---|---|
| Plan + spec status | DASH | plan doc written, spec → "Planned" | `3ea4882` |
| 1.1 Manifest `capabilities` field | DASH | `AddonCapabilities` added + 2 tests, 7 passed | `e886a9a`, `05b1e11` (alias polish) |
| 1.2 External repo scaffold | PKGS | `catalog.json` (5 addons) + `README.md` rewritten, test packages deleted | `ab33307` |
| 1.3 `fortigate-core` package | PKGS | `fortigate-core/0.2.0/` addon.json + connector + ported client; smoke ✅ | `0926938` + local tag `fortigate-core-v0.2.0` |

### Not done — remaining work (Tasks 1.4 → 3.5, 14 tasks)

- **1.4** `fortiweb-core` package (PKGS) — NEXT
- **1.5** `penguin-siem` / `penguin-xdr` / `penguin-soar` packages (PKGS)
- **1.6** Vendor connector parity tests (DASH)
- **2.1** Wizard catalog builder (DASH)
- **2.2** Connect-persistence adapter (DASH)
- **2.3** `integrations_v2` router (DASH)
- **2.4** Connect store (web)
- **2.5** `ConnectWizard.vue` (web)
- **2.6** Mount wizard in Sidebar (web)
- **3.1** `integration_wiring` + `soar_targets` tables (DASH)
- **3.2** Wiring orchestration module (DASH)
- **3.3** Connect wiring + `soar-actions` (DASH)
- **3.4** Wizard wiring results (web)
- **3.5** Smoke-flow extension (DASH)

Full step-by-step code for every task is in the plan doc. Each task is bite-sized and independently testable.

---

## How to resume

1. Re-enter Subagent-Driven Development on the plan. Next task = **Task 1.4** (full text in the plan).
2. Branch: work was done on **`feat/unified-soc-integration`**, now merged to **`main`** (see "Git state" below). Continue from `main` or cut a fresh branch off it — your call.
3. PKGS is on its `main` branch; keep authoring packages there.

### Critical environment notes (these bit us — don't relearn them)

- **API container has NO pytest.** Do NOT use `docker compose exec api pytest`. Run API tests on the host venv:
  `& "C:\Users\lucas\Desktop\PingWins-FortiDashboard\FortiDashboard\apps\api\.venv\Scripts\python.exe" -m pytest apps/api/tests/<file> -q`
  Run from the DASH repo root (running from the monorepo root collects other apps' tests and errors — always scope to `apps/api/tests`).
- **Backend no source bind mount.** For tasks that change running API behavior, `docker compose up -d --build api` after the edit (per project memory). Pure schema/unit tests run fine on the host venv without rebuild.
- **PKGS ⇄ DASH cross-repo copy:** subagents can't `cp` reliably across the two repo roots in one shell. Use Read (source) → Write (dest) with identical content. Confirmed the ported clients have **zero `app.*` imports** (fortigate `client.py` ✅; fortiweb `client.py` ✅ — only `json`/`typing`/`httpx`), so ports are byte-for-byte, no edits.
- **Pre-verified class names for the ports:**
  - fortigate: `FortiGateApiClient`, `FortiGateApiError` (kw-only ctor `host=/api_key=/verify_tls=`).
  - fortiweb: `FortiWebApiClient`, `FortiWebApiError` (same kw-only ctor shape). Plan's `connector/__init__.py` for 1.4 already targets these names — no adjustment needed.
  - penguin (1.5): port `apps/api/app/soc/client.py` → `SocServiceClient`; verify its `__init__` kwargs before finalizing the connector.

### Deviations from the plan already adopted (keep consistent)

1. **Wizard catalog** is built from each *installed package's* `addon.json` (`record.path/addon.json`), NOT `list_installed() ∩ list_addons()`. Already baked into Task 2.1. (Reason: external-only packages never appear in local `list_addons()`.)
2. **SOAR wiring** uses a dashboard-owned `soar_targets` table + `GET /api/integrations/{id}/soar-actions` (Tasks 3.1–3.3). No Skipper-internal coupling.
3. **No `git push` inside tasks.** Plan Tasks 1.3–1.5 say "push tag". We deferred all pushing; the controller pushes at handoff/finish. fortigate-core's tag was created locally. **Felipe: see "Remaining push work" below.**
4. **Connector stub methods** (`get_widget_data` / `ingest_events` returning empty) are intentional Phase-1 scaffold (widget/event data flows via SIEM widgets per spec). Code reviewer flagged it as a non-blocking note; we keep all 5 connectors byte-identical to the plan for consistency rather than adding per-package TODOs. Do the same for 1.4/1.5.

### Test baseline (for regression judgment)

Before any code, DASH `apps/api` baseline was **327 passed, 8 failed**. The 8 failures are pre-existing and unrelated to this work (ai provider key/config, keycloak realm seeding, auth session cookie, `soc_ingest` token-disabled). Treat only *new* failures as regressions; these 8 are known-bad in this environment.

---

## Git state (what was pushed)

### DASH
- `feat/unified-soc-integration` merged into `main` and **pushed to `origin/main`**.
- Includes: plan doc, spec status update, this handoff doc, Task 1.1 (`e886a9a`, `05b1e11`).
- The `feat/unified-soc-integration` branch is left in place locally (not deleted) in case you want its history; `main` has everything.

### PKGS
- `main` with Task 1.2 (`ab33307`) + Task 1.3 (`0926938`) **pushed to `origin/main`**.
- Tag **`fortigate-core-v0.2.0` pushed** (needed for the marketplace install flow to fetch the package).

### Remaining push work (Felipe)
- As you complete 1.4 / 1.5, create + push the tags: `fortiweb-core-v8.0.5`, `penguin-siem-v1.0.0`, `penguin-xdr-v1.0.0`, `penguin-soar-v1.0.0` (commands are in the plan's Step "Tag + commit" for each task).
- The legacy `fortiweb-waf-v0.1.0` tag still exists on PKGS origin — harmless (its package dir was deleted from `main`); can be deleted later or left.

---

## Task tracker

A live task list (17 items, 1.1–3.5) was created during execution; 1.1–1.3 marked completed, 1.4 reset to pending. If resuming in a new session the tracker won't persist — drive directly off the plan's task list and this doc.
