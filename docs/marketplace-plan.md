# Marketplace Plan

## Goal

Let an operator browse and install provider integrations without
touching the dashboard codebase. Each integration is an *add-on*: a
self-contained manifest that maps the dashboard's generic concepts
(routes, auth fields, widget ids, SIEM event types) to a specific
vendor product. The cockpit reads the manifest, renders the connect
form, registers the routes it can call, and lights up the widgets the
add-on declares.

## Repository topology

```
github.com/pingwins
├── fortidashboard          # this repo — runtime, UI, gateway, SIEM
└── fortidashboard-addons   # planned — only manifests, signed releases
```

For the MVP every manifest lives in this repo under `addons/<id>/`.
Once the manifest schema stops changing, the directory will move to
the `pingwins/fortidashboard-addons` repo. The dashboard registry will
then fetch a signed release tarball (or a list of raw manifest URLs)
from that external repo, with signature verification before loading.

Keeping the add-ons in a dedicated repo gives us:

- Community contributions can land without touching the gateway code.
- Add-on releases version independently of the dashboard binary.
- Signing keys can be scoped to that repo's release process.

## Add-on shape

A minimum manifest covers four blocks. The pydantic schema lives in
`apps/api/app/addons/manifest.py`; this section is the conceptual
view.

1. **Identity** — `id`, `version`, `name`, `vendor`, `category`,
   `description`, `icon`. Used by the marketplace UI and audit log.
2. **Provider auth** — `provider.type` (gateway-side connector key)
   and `provider.auth.fields` (field id, label, type, required,
   default, placeholder). The cockpit renders these fields when the
   user clicks Install, so a new add-on cannot ship without describing
   exactly how to authenticate.
3. **Route map** — `routes[]`. Every REST path the connector calls.
   Each entry has an `id`, method, path, optional summary, and
   optional `params[]` describing how to format query/body
   parameters. Today this is documentation + audit; tomorrow it can
   power capability checks, permission scoping and contract tests.
4. **Bindings** — `widgets[]` (catalog ids the add-on enables) and
   `siemEventTypes[]` (event type strings the connector emits). These
   declare what the dashboard should expose once the add-on is
   installed.

The first concrete manifest, `addons/fortigate/addon.json`, documents
the existing FortiGate connector with seven REST routes (system
status, performance, interface counters, policies, IPS memory log,
admin login events with the repeated-filter quirk), nine widget
catalog ids, and the three SIEM event types the gateway currently
emits.

## Install flow (target state)

1. User opens Settings → Marketplace tab.
2. Cockpit calls `GET /api/marketplace/addons`. Registry returns all
   manifests it loaded at boot (cached, refreshable via
   `POST /api/marketplace/addons/refresh`).
3. User clicks Install on an add-on.
4. Gateway calls a planned `POST /api/marketplace/addons/{id}/install`
   that:
   - Verifies the manifest signature.
   - Calls the matching `apps/api/app/integrations/<provider>/service`
     to register the connector (today, this is just the FortiGate
     integration create flow).
   - Persists the active add-on id alongside the user's integration
     row so the cockpit can show "installed via marketplace" in the
     audit trail.
5. Cockpit pulls the freshly created integration and renders the
   connect form from `provider.auth.fields`.
6. Once the integration probe succeeds, the dashboard widgets named
   in `widgets[]` become available in the widget catalog.

The current build stops at step 3 — the Install button closes the
Settings modal and routes the user to the existing Integrations form.
This keeps the UI honest about what is real.

## Why Settings, not a sidebar tab

Marketplace browsing is a low-frequency, configuration-style action,
not part of the analyst's daily flow. Putting it inside the Settings
modal alongside Profile/Appearance/Language keeps the sidebar lean
for the operational tabs (Integrations, Tickets, Workspaces,
Endpoints, Audit).

## Today (2026-05-14)

- `addons/fortigate/addon.json` — first manifest.
- `apps/api/app/addons/{manifest,registry}.py` + new
  `/api/marketplace/addons` endpoints (list, detail, admin refresh).
- `apps/web/src/components/marketplace/MarketplacePanel.vue` +
  `useMarketplaceStore` + `marketplaceClient.ts` — list, search,
  detail dialog, install action.
- Surface: SettingsModal exposes a new **Marketplace** tab that
  embeds the panel. The standalone sidebar tab was removed in favor
  of this one entry point.

## Next

- Real `POST /api/marketplace/addons/{id}/install` endpoint backed by
  the integrations service.
- Dynamic connect form from `provider.auth.fields` inside the
  marketplace dialog (no detour through the Integrations tab).
- Detached manifest registry under `pingwins/fortidashboard-addons`
  with signed releases, and a registry loader that pulls + verifies
  signatures before activating.
- Second connector (Palo Alto / Cisco / Sophos) to validate the
  manifest schema against more than one product.
