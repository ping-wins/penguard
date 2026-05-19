# Unified SOC Integration — Design

**Status:** Planned — see [`../plans/2026-05-17-unified-soc-integration.md`](../plans/2026-05-17-unified-soc-integration.md)
**Date:** 2026-05-17
**Owner:** luskotav-cloud
**Related:** [`2026-05-14-marketplace-addon-packages-design.md`](2026-05-14-marketplace-addon-packages-design.md), [`2026-05-17-roles-permissions-manager-design.md`](2026-05-17-roles-permissions-manager-design.md)

## Vision

Replace the three separate, hardcoded integration forms (FortiGate, FortiWeb, Penguin tools) with one unified wizard. The user picks a **machine type + version** from the marketplace add-ons they have installed (e.g. *FortiGate 7.6.6*, *FortiWeb 8.0.5*), supplies credentials, the system tests the connection, then wires that machine's connector into Penguard and the sister tools (SIEM log consumption, SOAR playbook execution) via per-destination toggles.

## Decisions locked with user

| Question | Decision |
|---|---|
| Add-on model | **Everything becomes a marketplace add-on.** FortiWeb and the three Penguin tools (SIEM Kowalski, XDR Rico, SOAR Skipper) get migrated into the add-on package system. The picker is 100% add-on-driven. |
| Version source | **Add-on manifest `compatibility.testedVersions`.** User selects a version from the list the installed add-on advertises; the label is `"{name} {version}"`. |
| Auto-wire on connect | **Auto-wire with per-destination toggles** (design author's call). The connect step shows toggles for the destinations the add-on declares it can feed; enabled ones are wired immediately. |
| UI shape | **Multi-step wizard.** |

## Scope is large — decomposed into 3 phases

This is too big for one implementation pass. One design spec (this doc), phased delivery. Each phase is independently shippable and testable.

- **Phase 1 — Add-on-ify the built-in vendors.** Author add-on manifests + connectors for `fortiweb-core` and `penguin-siem` / `penguin-xdr` / `penguin-soar`, reusing the existing vendor service code behind the `AddonConnector` protocol. Keep the legacy endpoints alive in parallel.
- **Phase 2 — Unified wizard UI + connect orchestration.** New wizard replaces the three Sidebar forms. Backed by a new generic `/api/integrations/connect` flow that resolves the add-on, validates auth fields from the manifest, tests, and persists.
- **Phase 3 — Auto-wire orchestration.** On connect, per-destination toggles drive log-forwarding registration (→ SIEM) and playbook capability registration (→ SOAR). Legacy per-vendor endpoints deprecated.

Each phase ships behind the existing UI until the phase is complete; the legacy forms are removed only at the end of Phase 2.

## Current state (for context)

- Add-on system exists: `AddonManifest` (`provider.type`, `auth.fields`, `compatibility.testedVersions`, `widgets`, `siemEventTypes`, `routes`), `ConnectorRegistry`, `InstallService`, `installed_addons` table. Only `fortigate-core` ships as a real add-on.
- FortiWeb + Penguin tools are hardcoded services in `apps/api/app/routers/integrations.py` with their own create/test/delete endpoints, DB stores, and Sidebar form sections.
- `AddonConnector` protocol: `health_check`, `get_widget_data`, `ingest_events`, `close`. No playbook method — playbook actions are exposed through manifest `routes` instead.

## Architecture

### Add-on manifest extensions

Add an optional `capabilities` block so the wizard knows what an add-on can wire into:

```jsonc
"capabilities": {
  "logSource": true,            // can forward/emit events to SIEM
  "playbookTarget": true,       // exposes response actions for SOAR
  "managed": true               // dashboard can push config (e.g. log-forwarding)
}
```

`compatibility.testedVersions` is reused verbatim for the version picker. No new version field.

### New connector protocol method (optional, duck-typed)

Extend `AddonConnector` with an **optional** method (duck-typed, add-ons that lack it are treated as non-playbook):

```python
def list_playbook_actions(self) -> list[dict]: ...   # [{id,label,paramsSchema}]
def run_playbook_action(self, action_id: str, params: dict) -> dict: ...
```

Existing connectors keep working — absence of these methods ⇒ `capabilities.playbookTarget` is ignored.

### Backend: generic connect flow

New router `apps/api/app/routers/integrations_v2.py` (kept separate from the 1500-line `integrations.py` so it stays focused):

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/integrations/catalog` | Installed add-ons the user can connect: `[{addonId, name, vendor, category, versions:[...], authFields:[...], capabilities:{...}}]`. Derived from `list_installed()` ∩ `list_addons()`. |
| `POST` | `/api/integrations/connect` | Body: `{addonId, version, name, auth:{...}, wire:{siem:bool, soar:bool}}`. Validates `auth` against manifest `auth.fields`, runs connector `health_check`, persists integration, applies wiring. Returns the created integration + wiring results. |
| `POST` | `/api/integrations/connect/test` | Same body minus persistence — `health_check` only, returns detected device info. |
| `GET` | `/api/integrations` | Unchanged contract (still aggregates all integrations) — now also returns add-on-backed ones. |
| `DELETE` | `/api/integrations/{id}` | Unchanged; routes by integration-id prefix, now also handles add-on-backed. |

Gated by `integrations.write` (RBAC from the roles spec). CSRF required on all mutations (closes the gap noted in the roles work).

### Persistence

Reuse the existing per-vendor stores in Phase 1–2 (the add-on connectors wrap them). A unified `integrations` table is **out of scope** — explicitly deferred. Integration identity stays prefix-based (`int_fweb_…`, etc.); add a generic `addon_integrations` row only if a vendor has no existing store (none currently).

Wiring state (which integration forwards to SIEM / is a SOAR target) is stored in a new lightweight table:

`integration_wiring` — `(integration_id PK, siem_enabled bool, soar_enabled bool, updated_at)`.

### Connect orchestration (Phase 3)

`apps/api/app/integrations/wiring.py` — pure orchestration module:

1. Persist integration via the add-on's backing store.
2. If `wire.siem` and `capabilities.logSource`: call existing FortiGate-style log-forwarding apply (generalized) so the device ships logs to the Kowalski collector; record `siem_enabled`.
3. If `wire.soar` and `capabilities.playbookTarget`: register the integration's `list_playbook_actions()` with the SOAR catalog so Skipper playbooks can target it; record `soar_enabled`.
4. Each wiring step is best-effort and reported per-destination in the response (`{siem:{ok,detail}, soar:{ok,detail}}`); a wiring failure does not roll back the integration (user can retry from the integration's row).

## Frontend: the wizard

New component `apps/web/src/components/integrations/ConnectWizard.vue`, replacing the FortiGate/FortiWeb/Penguin form sections in `Sidebar.vue`. The Integrations tab opens the wizard; connected integrations render as a list above the "+ Connect machine" button.

Steps:

1. **Machine type** — grid of installed add-ons (icon, name, vendor, category). Empty state links to Settings → Marketplace. Only shows add-ons the user can connect (installed + `integrations.write`).
2. **Version** — dropdown from `compatibility.testedVersions`. Header now reads e.g. *FortiGate 7.6.6*.
3. **Credentials** — form rendered dynamically from manifest `auth.fields` (`text|url|secret|boolean|number`, required, placeholder, default). No hardcoded vendor fields.
4. **Test & confirm** — runs `/connect/test`, shows detected device (hostname/model/version). Per-destination wiring toggles shown only for capabilities the add-on declares (`logSource → "Forward logs to SIEM"`, `playbookTarget → "Enable SOAR playbooks"`). Defaults: both ON when capable.
5. **Done** — `/connect` called, wiring results surfaced (green/amber per destination), wizard closes, list refreshes.

State in a new `useIntegrationConnectStore` (catalog fetch, wizard draft, submit). Existing `useIntegrationsStore` keeps owning the connected-list.

i18n: new `integrations.wizard.*` keys (pt-BR + en-US), reusing existing `integrations.*` where possible.

Any data shown before a real backend exists for a step is suffixed `(mock)` and removed when the real wire lands (per project convention).

## Error handling

| Case | Behavior |
|---|---|
| No add-ons installed | Step 1 empty state → "Install an add-on in Marketplace". |
| `auth` missing a required manifest field | 422 from `/connect`, field-level error in wizard. |
| `health_check` fails | `/connect/test` returns `{ok:false, message}`; wizard stays on step 4, shows message, no persistence. |
| Version not in `testedVersions` | 422 — wizard only offers valid options, so this is a defense-in-depth check. |
| Wiring (SIEM/SOAR) fails but connect ok | Integration persisted; response flags the failed destination amber; row shows a "retry wiring" affordance. |
| Add-on uninstalled while integrations exist | Integration rows show "add-on missing" badge; data calls degrade gracefully (existing connector-registry behavior). |

## Testing

**Phase 1 (backend, add-on-ify):**
- `test_addon_fortiweb_connector.py`, `test_addon_penguin_connectors.py` — health_check / ingest / widget parity vs the legacy services (same fixtures).
- Manifest schema validation for the 4 new `addon.json`.

**Phase 2 (connect flow):**
- `test_integrations_connect.py` — catalog lists installed add-ons; connect validates auth fields against manifest; test endpoint returns device info; RBAC (`integrations.write`) + CSRF enforced; mock_mode path.
- Frontend `connectWizard.test.ts` — step progression, dynamic auth-field rendering from a stub manifest, empty state.

**Phase 3 (wiring):**
- `test_integration_wiring.py` — toggles drive SIEM forward + SOAR registration; per-destination failure isolation; `integration_wiring` persistence.
- Smoke extension in `test_smoke_flows.py`: connect a mock add-on with both toggles, assert events reach SIEM and the integration appears as a SOAR target.

## Migration / rollout

1. **Phase 1** ships add-ons + connectors; legacy endpoints untouched; no UI change.
2. **Phase 2** ships the wizard behind the Integrations tab, replacing the three forms. Legacy create/test endpoints kept for one release as fallback, then removed.
3. **Phase 3** ships auto-wire; legacy per-vendor log-forwarding/playbook endpoints deprecated, then removed once parity confirmed.
4. Existing integrations created via old forms keep working throughout (same stores, same ids).

## Out of scope / deferred

- Unified `integrations` table (keep per-vendor stores).
- OAuth2 auth kind in the wizard (manifest supports it; wizard handles `apiKey`/`none` first).
- Add-on hot-reload UX (covered by existing marketplace).
- Multi-tenant scoping (consistent with prior specs).
- Editing an existing integration's credentials via the wizard (Phase-later; delete + re-connect for now).

## Open questions (resolved inline, none blocking)

- *Playbook target wiring shape* — chosen: manifest `capabilities.playbookTarget` + optional duck-typed `list_playbook_actions`/`run_playbook_action`; SOAR registration via existing Skipper catalog. No protocol break for existing add-ons.
