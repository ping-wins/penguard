# SOC Pipeline Progress — 2026-05-14

End-to-end work to make the FortiGate → SIEM → cockpit pipeline fire real
incidents from a live brute-force lab. Captures what was changed, why,
and what still needs follow-up.

## Outcome

A Hydra SSH brute-force against the lab FortiGate now produces a
`repeated_failed_login` incident visible in the cockpit's recent
incidents widget. The widget exposes the per-source attempt list with
usernames and timestamps. Closed/contained tickets stay reachable
through an `archived` toggle. Inline reset clears the SIEM backlog
during lab iteration.

## Changes shipped

- `apps/api/app/integrations/fortigate/client.py` — switched the IPS
  log path from `/api/v2/log/memory/utm/ips` (404 on FortiOS 7.6.6) to
  `/api/v2/log/memory/ips`. Added `get_admin_login_failures`, which
  hits `/api/v2/log/memory/event/system` with repeated `filter`
  parameters (`action==login`, `status==failed`) because FortiOS does
  not honour a single combined filter string. Friendlier 401/403/404
  error messages instead of `HTTP <code>`.
- `apps/api/app/integrations/fortigate/normalizers.py` — added
  `normalize_admin_login_failures`. Output carries an explicit
  `eventType: "auth.failed_login"` so the gateway aggregator does not
  collapse admin events into `network.event`.
- `apps/api/app/integrations/fortigate/widgets.py` — recent-events
  widget merges IPS threats with admin login failures.
- `apps/api/app/routers/integrations.py`
  - `_aggregate_fortigate_events` now respects an explicit `eventType`
    on the raw record, captures `users` (set) and a 20-entry `attempts`
    sample with `(at, user, message)` per source IP.
  - `_filter_events_after_cursor` skips events whose ISO timestamp is
    `<= lastSuccessAt`, using `get_ingestion_status(...)` to read the
    cursor before each run.
  - `POST /soc/incidents/reset` (lab-only) calls the SIEM admin reset
    and zeroes every FortiGate ingestion cursor, with audit log.
- `apps/api/app/integrations/fortigate/store.py` — `reset_ingestion_cursors`
  on both SqlAlchemy and in-memory ingestion stores.
- `apps/siem_kowalski/app/main.py` — `_incident_attributes` carries
  forward `count`, `users`, `attempts`, `message`, `action`, `subtype`
  alongside the existing `source`/`demoRunId`/`attackType`. Added
  `POST /admin/reset` that truncates the events + incidents tables.
- `apps/siem_kowalski/app/store.py` — `reset()` method backing the
  admin endpoint.
- `apps/web/src/components/widgets/soc/WidgetSocRecentIncidents.vue`
  - Removed the `slice(0, 12)` cap and dropped `no-scrollbar` so the
    list scrolls naturally when there are many alerts.
  - Split closed/contained tickets into an archived bucket with a
    toggle in the header (`{shown} · {archived}` counter).
  - Drill panel renders the new `attempts` list and `users` summary
    plus a note that FortiGate does not log attempted passwords.
- `apps/web/src/components/tickets/TicketsPanel.vue` + i18n + service —
  Reset button next to Refresh; confirm dialog, status banner, PT/EN
  strings.
- `apps/web/src/components/layout/Sidebar.vue` — renders Markdown for
  AI assistant replies through the existing `renderMarkdown` helper.
- `apps/web/src/main.ts` — registers `MotionPlugin` so the
  `v-motion` directive on draggable widgets resolves (was emitting a
  Vue warn on every render).
- `apps/web/src/stores/useIntegrationsStore.ts` — clearer error
  messages on 401 / 403 during FortiGate integration calls; refresh
  the session store on 401 so guards run again.

## Lab plumbing

- FortiGate admin lockout settings raised for the demo:
  `admin-lockout-threshold=10` (was `3`),
  `admin-lockout-duration=1` (was `60s`). Hydra runs can now produce
  enough fails to cross `count >= 5` without locking `admin-rest`.
- Trusted Hosts on `admin-rest`:
  - `192.168.56.0/24` (Debian on the host-only segment)
  - `192.168.0.138/32` (Windows host masquerade onto the bridged port)
- Dashboard host points at `https://192.168.0.100` (FortiGate bridged
  port). Calls from Docker traverse `WSL2 → Windows → Wi-Fi → FG bridge`.
  The host-only IP `192.168.56.100` is unreachable from the Docker
  containers because the host-only adapter is not exposed inside WSL2.
- Scheduler runs every 5 s (`FORTIDASHBOARD_FORTIGATE_INGESTION_*`
  environment variables in `.env`):
  ```
  FORTIDASHBOARD_FORTIGATE_INGESTION_SCHEDULER_ENABLED=true
  FORTIDASHBOARD_FORTIGATE_INGESTION_SCHEDULER_TICK_SECONDS=5
  FORTIDASHBOARD_FORTIGATE_INGESTION_MIN_INTERVAL_SECONDS=5
  FORTIDASHBOARD_FORTIGATE_INGESTION_DEFAULT_INTERVAL_SECONDS=5
  ```

## Known follow-ups

- **Cursor on reset replays the FortiGate backlog.** After
  `POST /soc/incidents/reset`, the cursor is set to `NULL`. The next
  scheduled run pulls the full FortiGate event/system backlog,
  aggregates per source, and creates `repeated_failed_login` incidents
  even though the analyst's intent was a clean slate. Fix is to set
  the cursor to "now" on reset (or to the newest event timestamp at
  reset time) so only events that arrive *after* the reset are
  ingested.
- **Same source-IP backlog re-fires the SIEM rule every run.** Even
  with the cursor in place, if more than five matching events land in
  one tick the SIEM rule emits a new incident rather than reopening or
  updating the existing one. Long-term fix is incident deduping in the
  SIEM rule engine (open incident per `(rule, sourceIp)` window).
- **Port scan ingestion is not wired.** Hydra works because admin
  login failures land in `event/system`. nmap-style scans only show
  up when the LAN→WAN policy has an IPS profile that fires a scan
  signature; the backend already consumes `/api/v2/log/memory/ips`,
  but no policy currently has IPS enabled in the lab. Forward Traffic
  deny logs are not consumed yet — extending the client to also pull
  `/api/v2/log/memory/traffic/forward` with `action==deny` is the
  smallest change needed for a port-scan-only flow.
- **Backend containers run from baked images.** Any change under
  `apps/api/**`, `apps/siem_kowalski/**` (etc.) requires
  `docker compose up -d --build <service>` before the change actually
  ships. The frontend (`apps/web`) hot-reloads via Vite.

## Verification commands

```bash
# Reset
docker exec fortidashboard-db-1 psql -U fortidashboard -d fortidashboard \
  -c "TRUNCATE siem_kowalski_incidents, siem_kowalski_events RESTART IDENTITY;"

# Manual ingest from the API container (uses stored credentials)
docker exec fortidashboard-api-1 uv run python -c "
import os
os.chdir('/app/apps/api')
from app.routers.integrations import (
    _run_fortigate_event_ingestion,
    get_fortigate_widget_service,
    get_fortigate_ingestion_store,
)
from app.routers.soc import get_siem_client
import psycopg
from app.core.config import get_settings
s = get_settings()
with psycopg.connect(s.database_url.replace('postgresql+psycopg','postgresql')) as c:
    with c.cursor() as cur:
        cur.execute('SELECT id, owner_user_id FROM fortigate_integrations LIMIT 1')
        iid, owner = cur.fetchone()
r = _run_fortigate_event_ingestion(
    integration_id=iid, owner_user_id=owner, trigger='manual',
    widget_service=get_fortigate_widget_service(),
    siem_client=get_siem_client(),
    ingestion_store=get_fortigate_ingestion_store(),
)
print(r)
"

# Check incidents
docker exec fortidashboard-db-1 psql -U fortidashboard -d fortidashboard \
  -c "SELECT id, rule_id, severity, payload->'attributes'->'count' as cnt FROM siem_kowalski_incidents ORDER BY created_at DESC LIMIT 5;"
```
