# TanStack Query Realtime Server-State Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace hidden fetch/refresh behavior for SOC telemetry with TanStack Query server-state cache updates driven by backend SSE events.

**Architecture:** The backend emits typed SIEM domain events from the UDP syslog ingestion path. The frontend installs TanStack Query, loads initial server state with `useQuery`, and applies SSE payloads into query caches with immutable `setQueryData` reducers. Pinia remains responsible for local UI state.

**Tech Stack:** FastAPI, siem_kowalski, Vue 3, Pinia, TanStack Query for Vue, SSE/EventSource, Vitest, Pytest.

---

### Task 1: Backend Domain Realtime Events

**Files:**
- Modify: `apps/api/app/integrations/fortigate/syslog.py`
- Modify: `apps/api/app/main.py`
- Test: `apps/api/tests/test_fortigate_syslog_ingestion.py`
- Test: `apps/api/tests/test_realtime_widget_push.py`

- [x] **Step 1: Write backend tests for domain SSE payloads**

Add a test that constructs `FortiGateSyslogForwarder` with a fake SIEM response containing both `event` and `incident`, then asserts the status recorder receives both payloads.

- [x] **Step 2: Extend status recorder contract**

Change the status recorder to receive `event`, `event_id` and `ticket`, preserving the existing `event_id` behavior for ingestion status.

- [x] **Step 3: Publish typed realtime events**

In `apps/api/app/main.py`, publish `soc.event.created` for every forwarded SIEM event and `soc.incident.created` when the SIEM response includes an incident. Keep the legacy `fortigate.syslog.event` for compatibility without adding widget/ticket refresh hints.

- [x] **Step 4: Verify backend**

Run:

```bash
cd apps/api && uv run pytest tests/test_fortigate_syslog_ingestion.py tests/test_realtime_widget_push.py -q
cd apps/api && uv run ruff check app/main.py app/integrations/fortigate/syslog.py tests/test_fortigate_syslog_ingestion.py tests/test_realtime_widget_push.py
```

### Task 2: WAF DoS Widget Semantics

**Files:**
- Modify: `apps/api/app/routers/widgets.py`
- Test: `apps/api/tests/test_waf_dos_widgets.py`

- [x] **Step 1: Add failing tests for observed DoS**

Extend WAF DoS tests so `action=close` and `ingestionMode=fortigate_flow_inference` count as allowed/observed, not blocked, for rate/top IP/feed responses.

- [x] **Step 2: Centralize blocked action detection**

Add a helper in `apps/api/app/routers/widgets.py` that returns true only for `block`, `blocked`, `deny` and `dropped`.

- [x] **Step 3: Remove hardcoded SIEM-block behavior**

Use incident attributes for SIEM-backed WAF widgets instead of forcing `blocked=true` and `action="block"`.

- [x] **Step 4: Verify widget semantics**

Run:

```bash
cd apps/api && uv run pytest tests/test_waf_dos_widgets.py -q
cd apps/api && uv run ruff check app/routers/widgets.py tests/test_waf_dos_widgets.py
```

Additional implemented guard: `siem_kowalski` now suppresses duplicate open
HTTP-flood DoS incidents for the same integration/source/destination/port while
one matching incident remains open.

### Task 3: Install TanStack Query And Query Keys

**Files:**
- Modify: `apps/web/package.json`
- Modify: `pnpm-lock.yaml`
- Modify: `apps/web/src/main.ts`
- Create: `apps/web/src/services/queryClient.ts`
- Create: `apps/web/src/services/queryKeys.ts`
- Test: `apps/web/tests/unit/queryKeys.test.ts`

- [x] **Step 1: Add dependency**

Run:

```bash
cd apps/web && pnpm add @tanstack/vue-query
```

- [x] **Step 2: Install Vue Query plugin**

Create one shared `QueryClient` with telemetry-safe defaults: no refetch interval, no refetch on window focus, and nonzero `staleTime`.

- [x] **Step 3: Add stable query key helpers**

Create helpers for widget data, SOC tickets, SOC incidents and SIEM events.

- [x] **Step 4: Verify frontend unit helpers**

Run:

```bash
cd apps/web && pnpm test -- queryKeys
```

### Task 4: Realtime Query Bridge

**Files:**
- Create: `apps/web/src/services/realtimeQueryBridge.ts`
- Modify: `apps/web/src/stores/useRealtimeStore.ts`
- Test: `apps/web/tests/unit/realtimeQueryBridge.test.ts`

- [x] **Step 1: Add bridge reducers**

Implement pure functions that upsert tickets, incident widgets and WAF DoS widget data into cached query responses.

- [x] **Step 2: Wire SSE events to QueryClient**

Update the realtime store to pass typed events to the bridge after parsing SSE messages.

- [x] **Step 3: Add reconnect resync behavior**

On SSE error followed by a later event, invalidate active SOC/widget queries once.

- [x] **Step 4: Verify bridge without network polling**

Run:

```bash
cd apps/web && pnpm test -- realtimeQueryBridge
```

### Task 5: Convert Critical SOC/WAF Consumers

**Files:**
- Modify: `apps/web/src/components/canvas/DraggableWidget.vue`
- Modify: `apps/web/src/stores/useTicketsStore.ts`
- Test: `apps/web/tests/unit/draggableWidget.test.ts`
- Test: `apps/web/tests/unit/ticketsRealtimeStore.test.ts`
- Test: `apps/web/tests/unit/widgetWafDos.test.ts`

- [x] **Step 1: Use query cache for widget initial load**

Replace direct widget fetch state in `DraggableWidget.vue` with a query-backed adapter for widget data.

- [x] **Step 2: Keep explicit manual refresh**

The widget shell may still expose a user-triggered refresh, implemented as `refetch()`.

- [x] **Step 3: Use query cache for tickets**

Convert `useTicketsStore` to read/update the TanStack Query ticket cache while preserving the current store API for components.

- [x] **Step 4: Verify visible behavior**

Run:

```bash
cd apps/web && pnpm test -- draggableWidget ticketsRealtimeStore widgetWafDos
```

### Task 6: End-To-End Validation

**Files:**
- No source files expected beyond previous tasks.

- [x] **Step 1: Run targeted backend/frontend suites**

```bash
cd apps/api && uv run pytest tests/test_fortigate_syslog_ingestion.py tests/test_realtime_widget_push.py tests/test_waf_dos_widgets.py -q
cd apps/web && pnpm test -- realtimeQueryBridge draggableWidget widgetWafDos ticketsRealtimeStore
```

- [x] **Step 2: Build updated services**

```bash
docker compose up -d --build api web siem-kowalski
```

- [ ] **Step 3: Manual lab check**

With Ddosify running, keep the dashboard open and verify that no page refresh is needed for tickets, WAF DoS rate, WAF top IPs or WAF feed.

- [ ] **Step 4: Confirm no hidden polling**

In browser Network tab, verify there is one `/api/events/stream` request and no periodic `/api/widgets/*/data` requests during steady state.
