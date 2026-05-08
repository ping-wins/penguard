# SOC Catalog

Shared SOC-lite metadata for FortiDashboard and the Penguin tools.

- `event-types.json` defines normalized event classes used by `siem_kowalski`.
- `severities.json` defines shared incident/event severity levels.
- `entity-fields.json` defines common SOC entities used for correlation and widgets.
- `playbook-node-types.json` defines allowed workflow nodes used by `soar_skipper`.
- `widgets.json` defines SOC widgets that can be surfaced in the FortiDashboard cockpit.

This package contains static metadata only. Runtime state belongs in the owning app tables.
