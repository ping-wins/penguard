# Add-ons (Marketplace foundation)

Each subdirectory in `addons/` declares one provider integration through an
`addon.json` manifest. The API loads every manifest at boot and exposes them
under `/api/marketplace/addons`.

## Why bundle in-repo for now

The marketplace lives inside this monorepo while the manifest schema is
unstable. Once routes, auth, widget bindings and SIEM event types stop
changing, extract the directory into a public registry repo
(e.g. `hendrixes/penguard-addons`) and switch the registry loader
to fetch from a signed GitHub release asset. Until then, every add-on
ships with the dashboard build and benefits from the same code review
as the gateway code that consumes its routes.

## Manifest contract

See `apps/api/app/addons/manifest.py` for the authoritative pydantic
schema. Minimum required fields:

- `id`, `version` — stable identifiers; `version` follows semver.
- `name`, `vendor`, `category`, `description` — listing metadata.
- `provider.type` — gateway-side connector name (`fortigate`,
  `palo-alto`, ...).
- `provider.auth.kind` + `provider.auth.fields` — schema for the
  connect form rendered by the cockpit.
- `routes` — every REST path the connector calls. Used for docs, audit
  and future static-analysis of permission scopes.
- `widgets` — widget catalog ids the add-on contributes.
- `siemEventTypes` — event type strings the connector emits.

## Adding a new add-on

1. Create `addons/<id>/addon.json`.
2. Validate locally: `uv run python -c "from app.addons.registry import list_addons; print(list_addons())"`.
3. Rebuild the API container so the manifest ships inside the image
   (see the docker-rebuild note in MEMORY.md).
4. Confirm `GET /api/marketplace/addons` returns the new entry.

## Roadmap

- `POST /api/marketplace/addons/{id}/install` — wire to the existing
  integrations stores so installing an add-on creates a provisioned
  integration shell.
- Manifest signing + signature verification on load.
- Pull manifests from a remote registry (GitHub release asset, signed
  tarball) instead of the local filesystem.
- Frontend marketplace tab inside the cockpit that lists add-ons and
  drives `install` plus the connect-form (uses `provider.auth.fields`).
