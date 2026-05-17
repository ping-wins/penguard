# Unified SOC Integration — Completion Handoff

**Date:** 2026-05-17
**Continues:** [`2026-05-17-unified-soc-integration-handoff.md`](./2026-05-17-unified-soc-integration-handoff.md)
**Plan:** [`../plans/2026-05-17-unified-soc-integration.md`](../plans/2026-05-17-unified-soc-integration.md)

## Completed After Lucas Handoff

Tasks **1.4 through 3.5** are complete.

### PKGS (`ping-wins/fortidashboard-addons`)

- `300db5d` `feat(fortiweb-core): self-contained connector package 8.0.5`
- `c7302de` `feat(penguin): self-contained SIEM/XDR/SOAR connector packages 1.0.0`

Pushed tags:

- `fortiweb-core-v8.0.5`
- `penguin-siem-v1.0.0`
- `penguin-xdr-v1.0.0`
- `penguin-soar-v1.0.0`

### DASH (`ping-wins/fortidashboard`)

- `0d4793a` `test(addons): parity smoke for vendor connector packages`
- `303a86b` `feat(integrations): wizard catalog from installed package manifests`
- `6a7b011` `feat(integrations): connect-persistence adapter over legacy stores`
- `2c4a472` `feat(api): generic integrations connect catalog endpoints`
- `5060ee8` `feat(web): integration connect store`
- `a1645c4` `feat(web): unified SOC connect wizard component`
- `344bcb5` `feat(web): replace integration forms with connect wizard`
- `00c6969` `feat(integrations): add wiring and SOAR target persistence`
- `85ca8a6` `feat(api): connect drives per-destination wiring`
- `dc4a71a` `feat(web): surface per-destination wiring results in wizard`
- `25696b0` `test(smoke): unified connect and wiring end-to-end`

## Verification

Passed:

- `docker compose config --quiet`
- `cd apps/api && PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests/test_addon_vendor_connectors.py tests/test_integration_catalog.py tests/test_connect_persistence.py tests/test_integrations_connect.py tests/test_integration_wiring.py tests/test_integration_wiring_store.py tests/test_smoke_flows.py -q` (`24 passed`)
- `cd apps/api && PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m ruff check app/routers/integrations_v2.py app/integrations/catalog.py app/integrations/connect_persistence.py app/integrations/wiring.py tests/test_addon_vendor_connectors.py tests/test_integration_catalog.py tests/test_connect_persistence.py tests/test_integrations_connect.py tests/test_integration_wiring.py tests/test_integration_wiring_store.py tests/test_smoke_flows.py`
- `cd apps/web && pnpm test -- ConnectWizard` (`30 files / 181 tests passed`)
- `cd apps/web && pnpm build`
- `git diff --check`

Known baseline issue:

- Full `cd apps/api && PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m ruff check app ...` still fails in pre-existing, unrelated files under `app/ai`, `app/routers/roles.py` and `app/workspaces/store.py`.

## Remaining Follow-Up

- Deprecate legacy per-vendor connect forms/endpoints only after product parity review.
- Decide whether to delete the old `fortiweb-waf-v0.1.0` tag from the add-ons repo. It is harmless because the package directory is no longer on `main`.
