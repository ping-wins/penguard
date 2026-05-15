# FortiWeb Landing WAF Lab

This runbook describes the lab topology used to demonstrate FortiDashboard with
FortiWeb protecting an external landing page.

Tested FortiWeb version: 8.0.5.

## Topology

```txt
Internet or lab attacker
  -> FortiWeb trial virtual server (8.0.5)
  -> external landing page origin

FortiWeb
  -> FortiDashboard API /api/soc/ingest/fortiweb
  -> siem_kowalski
  -> FortiDashboard cockpit through SSE
```

## Landing Page Requirements

- The landing source code lives outside this repository.
- The landing origin must be reachable from FortiWeb.
- Public traffic must reach the landing through FortiWeb, not directly.
- The origin should expose:
  - `GET /`
  - `GET /demo/search?q=...`
  - `POST /api/contact`
- The origin must not contain real customer data or real credentials.

## Demo Attack Inputs

Use only against lab-owned infrastructure:

```bash
curl -k "https://<FORTIWEB_PUBLIC_HOST>/demo/search?q=%27%20OR%201%3D1--"
curl -k "https://<FORTIWEB_PUBLIC_HOST>/.env"
hey -z 20s -q 5 -c 20 "https://<FORTIWEB_PUBLIC_HOST>/"
```

The `hey` command is intentionally rate-limited. Do not run open-ended DoS
traffic against public infrastructure.

## Expected Result

- FortiWeb records Attack or Traffic logs.
- FortiDashboard receives FortiWeb telemetry.
- `siem_kowalski` creates a WAF incident.
- The dashboard shows an incident toast, recent incident, and ticket without a
  browser refresh.
- SOAR proposes an approved response action from inside FortiDashboard.
