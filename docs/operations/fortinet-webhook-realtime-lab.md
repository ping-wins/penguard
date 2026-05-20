# Fortinet Webhook Realtime Lab

Use this runbook when the dashboard SSE path must show real lab telemetry
without relying on UDP syslog delivery.

This is a push path, not simulator data:

```txt
FortiGate Automation Stitch webhook -> Penguard API -> siem_kowalski -> SSE
FortiWeb telemetry webhook          -> Penguard API -> siem_kowalski -> SSE
```

## Backend

Set a long random token for FortiGate shared-token webhook ingest:

```env
PENGUARD_SOC_INGEST_TOKEN=<long-random-token>
```

Rebuild the API container after changing backend code or env:

```bash
docker compose up -d --build api
docker compose logs -f api siem_kowalski
```

Check whether the shared FortiGate webhook endpoint is enabled:

```bash
curl http://localhost:8000/api/soc/ingest/health
```

## FortiGate Automation Stitch

Use FortiGate management reachability to the host running Penguard.

Endpoint:

```txt
POST http://<HOST_MGMT_IP>:8000/api/soc/ingest/fortigate
Authorization: Bearer <PENGUARD_SOC_INGEST_TOKEN>
X-Penguard-Integration-Id: <FORTIGATE_INTEGRATION_ID>
Content-Type: application/json
```

Preferred demo trigger:

```txt
Trigger: Log event for IPS/anomaly/scan detection
Action: Webhook POST to Penguard
```

Webhook JSON body:

```json
{
  "logid": "%%log.logid%%",
  "type": "%%log.type%%",
  "subtype": "%%log.subtype%%",
  "action": "%%log.action%%",
  "status": "%%log.status%%",
  "level": "%%log.level%%",
  "srcip": "%%log.srcip%%",
  "dstip": "%%log.dstip%%",
  "user": "%%log.user%%",
  "msg": "%%log.msg%%",
  "eventtime": "%%log.eventtime%%"
}
```

Manual host-side test, without FortiGate:

```bash
curl -X POST http://localhost:8000/api/soc/ingest/fortigate \
  -H "Authorization: Bearer <PENGUARD_SOC_INGEST_TOKEN>" \
  -H "X-Penguard-Integration-Id: <FORTIGATE_INTEGRATION_ID>" \
  -H "Content-Type: application/json" \
  -d '{"type":"utm","subtype":"anomaly","action":"detected","srcip":"10.10.10.10","dstip":"10.10.20.30","level":"warning","msg":"TCP port scan detected"}'
```

Expected:

```txt
{"received":1,"emitted":1,"throttled":0,...}
```

Brute-force/admin-login-failed events are aggregated before emission so the
dashboard receives one incident for a burst instead of one per attempt.
Scan/anomaly events emit immediately.

## FortiWeb Native Telemetry

Use the integration-scoped FortiWeb endpoint and token shown by the cockpit.
Do not use `PENGUARD_SOC_INGEST_TOKEN` for this path.

Endpoint:

```txt
POST http://<HOST_MGMT_IP>:8000/api/soc/ingest/fortiweb/<INTEGRATION_ID>
Authorization: Bearer <FORTIWEB_TELEMETRY_TOKEN>
Content-Type: application/json
```

Manual host-side test:

```bash
curl -X POST http://localhost:8000/api/soc/ingest/fortiweb/<INTEGRATION_ID> \
  -H "Authorization: Bearer <FORTIWEB_TELEMETRY_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{"type":"attack","subtype":"dos","src":"10.10.10.10","dst":"10.10.20.30","msg":"HTTP flood detected","action":"block"}'
```

Expected:

```txt
{"received":1,"emitted":1,"integrationId":"<INTEGRATION_ID>"}
```

## Dashboard Validation

1. Open the dashboard with the same user that owns the integration.
2. Keep the browser connected to `/api/events/stream`.
3. Trigger FortiGate scan/anomaly or FortiWeb WAF/DoS traffic.
4. Confirm these update without browser refresh:
   - incident toast
   - recent incidents widget
   - tickets panel
   - WAF DoS widgets for FortiWeb events
5. Confirm backend logs show the webhook endpoint and `siem_event_ingested`.

If the API receives events but the browser does not update, check that the
posted integration id belongs to the logged-in user. Realtime events are scoped
by `ownerUserId`.
