# Real Telemetry Cutover Implementation Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** Remove customer-visible demo/mock/synthetic behavior from FortiDashboard runtime and make SOC detections depend on live FortiGate, live endpoint agent, real persisted services, and explicitly configured AI providers.

**Architecture:** Keep test fixtures and unit-test fakes, but remove or gate every runtime/demo surface from production builds. Replace synthetic replay/simulator paths with operator flows that validate live integrations, ingestion health, endpoint enrollment, and real telemetry arrival. Fail closed when a real provider is not configured instead of silently falling back to scripted/demo output.

**Tech Stack:** FastAPI, Pydantic, SQLAlchemy, Vue 3, Pinia, vue-i18n, Pytest, Vitest, Docker Compose.

---

## Non-negotiable scope boundary

Do not remove test-only mocks/fakes used inside `tests/` unless they leak into production runtime. The cutover targets runtime APIs, cockpit UI, docs, startup defaults, and scripts exposed to operators.

## Current runtime/demo surfaces found

1. Synthetic SIEM replay in `apps/api/app/routers/soc.py`:
   - `POST /api/soc/demo/replay`
   - `DEMO_SOURCE_TAG = "demo.replay"`
   - `_demo_attack_event()` and `_demo_replay_events()`
   - audit action `soc.demo.replay`

2. Cockpit replay UI in `apps/web/src/components/workspace/WorkspacePanel.vue`:
   - yellow `MVP demo` block
   - `Replay` attack picker
   - `lastDemoRun`, `demoPickerOpen`, `demoBusyType`, `handleReplayDemo()`

3. Demo replay client/types in `apps/web/src/services/workspaceClient.ts`:
   - `DemoAttackType`
   - `DEMO_ATTACK_TYPES`
   - `replayDemoIncident()`

4. Demo/i18n copy in `apps/web/src/i18n/messages/pt-BR.ts` and `apps/web/src/i18n/messages/en-US.ts`:
   - `workspaces.mvpDemo.*`
   - audit label for `soc.demo.replay`

5. Demo/source badges in `apps/web/src/utils/sourceBadges.ts`:
   - `Seeded demo`
   - `Simulator`
   - `Scripted AI`
   These may remain only if historical data can contain those markers, but the cockpit should not create new demo/simulator data in production.

6. XDR simulator runtime endpoint in `apps/xdr_rico/app/main.py`:
   - `POST /simulator/events`
   - deterministic endpoint `demo-endpoint-01`

7. Demo seed script in `apps/api/scripts/seed_soc_demo.py`:
   - inserts demo SIEM events
   - calls XDR simulator

8. AI fallback/runtime default in `apps/api/app/core/config.py` and `apps/api/app/ai/provider.py`:
   - `ai_provider: str = "scripted"`
   - missing/invalid Anthropic/OpenAI config silently returns `ScriptedAIProvider()`
   - malformed model JSON falls back to scripted output

9. Frontend empty-state copy in widgets:
   - `apps/web/src/components/widgets/WidgetThreats.vue`: "Trigger a scan or seed demo events"
   - `apps/web/src/components/widgets/WidgetGenericData.vue`: "Seed SOC demo data..." and "XDR simulator..."

10. Docs/AGENTS still describe synthetic replay as the recommended demo path.

---

## Phase 1: Remove customer-visible synthetic controls

### Task 1.1: Remove replay client API from workspace client

**Objective:** Ensure the web app cannot call `/api/soc/demo/replay`.

**Files:**
- Modify: `apps/web/src/services/workspaceClient.ts`
- Test: `apps/web/tests` affected by imports if any

**Steps:**
1. Delete `DemoAttackType` and `DEMO_ATTACK_TYPES` exports.
2. Delete `replayDemoIncident()`.
3. Run `cd apps/web && pnpm test`.
4. Fix any imports that still reference those symbols.

### Task 1.2: Remove MVP demo panel from WorkspacePanel

**Objective:** Remove all synthetic replay UI from the cockpit.

**Files:**
- Modify: `apps/web/src/components/workspace/WorkspacePanel.vue`
- Modify: `apps/web/src/i18n/messages/pt-BR.ts`
- Modify: `apps/web/src/i18n/messages/en-US.ts`

**Steps:**
1. Remove import of `Zap`, `DemoAttackType`, `DEMO_ATTACK_TYPES`, and `replayDemoIncident` if no longer used.
2. Delete the `// ----- MVP Demo -----` state/functions.
3. Delete the `<!-- MVP demo replay -->` template block.
4. Remove `workspaces.mvpDemo` i18n keys.
5. Run `cd apps/web && pnpm test`.
6. Run `cd apps/web && pnpm build`.

### Task 1.3: Replace empty-state copy that suggests demo/simulator data

**Objective:** Empty states must point operators to real ingestion/enrollment paths only.

**Files:**
- Modify: `apps/web/src/components/widgets/WidgetThreats.vue`
- Modify: `apps/web/src/components/widgets/WidgetGenericData.vue`

**Copy changes:**
- Replace "Trigger a scan or seed demo events." with "Verify FortiGate logging and run ingestion from the integration card."
- Replace "Seed SOC demo data or ingest FortiGate events..." with "Connect a SIEM/FortiGate provider and ingest real events to populate this chart."
- Replace "XDR simulator or run agent_private." with "Enroll an endpoint and run agent_private to send live telemetry."

**Verification:**
- `cd apps/web && pnpm test`
- `cd apps/web && pnpm build`

---

## Phase 2: Disable synthetic runtime APIs by default, then remove them

### Task 2.1: Add explicit lab/demo feature flag, default false

**Objective:** Make synthetic routes fail closed in all normal environments while tests can still enable them temporarily.

**Files:**
- Modify: `apps/api/app/core/config.py`
- Modify: `apps/api/app/routers/soc.py`
- Modify: `apps/xdr_rico/app/main.py`
- Test: API/XDR tests that exercise demo/simulator endpoints

**Implementation:**
- Add `enable_lab_demo_tools: bool = False` to `Settings`.
- In `replay_demo_incident()`, before role checks, reject unless enabled:
  `if not get_settings().enable_lab_demo_tools: raise HTTPException(status_code=404, detail="Not found")`
- Add equivalent flag in `xdr_rico` settings or environment guard for `/simulator/events`.

**Verification:**
- New test: default call to `/api/soc/demo/replay` returns 404.
- Existing replay tests set the env/override flag explicitly.

### Task 2.2: Move demo replay route into lab-only router/module

**Objective:** Separate production SOC routes from lab/demo code.

**Files:**
- Create: `apps/api/app/routers/lab_demo.py`
- Modify: `apps/api/app/main.py` or router registration location
- Modify: `apps/api/app/routers/soc.py`

**Steps:**
1. Move `DEMO_SOURCE_TAG`, `DEMO_ATTACK_TYPES`, `_demo_attack_event()`, `_demo_replay_events()`, and `replay_demo_incident()` to `lab_demo.py`.
2. Register this router only when `enable_lab_demo_tools=true`.
3. Keep tests under an explicit lab-demo test file.

### Task 2.3: Delete or quarantine `seed_soc_demo.py`

**Objective:** Prevent operators from using demo data as a normal setup path.

**Options:**
- Preferred: move to `tools/lab/seed_soc_demo.py` and make it print a warning plus require `--i-understand-this-is-demo-data`.
- Strict: delete script and update docs/tests to use test fixtures only.

**Verification:**
- `search_files("seed_soc_demo|demo/replay|simulator/events", path=".")` returns only tests/lab docs after migration.

---

## Phase 3: Make scan detection rely on real telemetry

### Task 3.1: FortiGate ingestion checklist in UI

**Objective:** Replace replay button with a real readiness panel for FortiGate scan detection.

**Files:**
- Modify: integrations drawer component in `apps/web/src/components/layout/Sidebar.vue` or extracted integration card component
- Modify: i18n catalogs

**Panel should show:**
- FortiGate integration connected/not connected
- Last ingestion success/error
- Raw event count
- Created SIEM event count
- Whether scheduler is enabled
- Operator checklist:
  - traffic must cross FortiGate interfaces
  - relevant policy must have `set logtraffic all`
  - run ingestion after scan or enable scheduler

### Task 3.2: Add real FortiGate scan detection smoke test using recorded non-secret fixture

**Objective:** Prove aggregator converts multiple real FortiGate deny records into one SIEM event that triggers `denied_traffic_burst`.

**Files:**
- Create/modify API tests around `_aggregate_fortigate_events()`
- Use sanitized fixture with no lab IP/hostnames/secrets.

**Acceptance:**
- 20+ deny events from same source aggregate to one `network.deny` event with `attributes.count >= 20`.
- SIEM creates an incident with rule `denied_traffic_burst`.

### Task 3.3: Dashboard scan detection path

**Objective:** Ensure the user sees real scan detections without any demo labels.

**Verification flow:**
1. Connect FortiGate.
2. Generate routed scan traffic in lab.
3. Run FortiGate ingestion from integration card.
4. Confirm ticket appears in SOC Tickets T1/T2 lane.
5. Confirm `SOC recent incidents`, severity widgets, and audit trail show live source.

---

## Phase 4: Remove simulator runtime and require live endpoint agent

### Task 4.1: Gate or remove XDR `/simulator/events`

**Objective:** No operator-accessible endpoint should create fake endpoints.

**Files:**
- Modify: `apps/xdr_rico/app/main.py`
- Modify: `apps/api/scripts/seed_soc_demo.py` if still present
- Modify tests to use store-level fixtures instead of HTTP simulator route where possible

### Task 4.2: Promote cockpit endpoint onboarding as the only normal path

**Objective:** Endpoint data comes from enrollment + `agent_private`, not simulator.

**Verification:**
- Create enrollment in cockpit.
- Run `agent_private run-headless` with issued token.
- Endpoint appears online.
- Suspicious process/connection telemetry forwards to SIEM as real `agent_private` source.

---

## Phase 5: Make AI real-provider only in production

### Task 5.1: Remove scripted provider as silent fallback

**Objective:** If AI is enabled but no real provider/key exists, return a clear configuration error instead of scripted output.

**Files:**
- Modify: `apps/api/app/core/config.py`
- Modify: `apps/api/app/ai/provider.py`
- Modify API tests that expect fallback behavior

**Implementation direction:**
- Keep `ScriptedAIProvider` only under `enable_lab_demo_tools=true` or test overrides.
- Change missing-key behavior for Anthropic/OpenAI to raise a configuration error.
- Change invalid JSON behavior to return 502/partial failure, not scripted substitute.

### Task 5.2: Update cockpit AI UI for configuration errors

**Objective:** Analyst sees "AI provider not configured" rather than fake/scripted analysis.

**Files:**
- Modify: `apps/web/src/components/tickets/TicketsPanel.vue`
- Modify: i18n catalogs

**Verification:**
- With no AI provider configured, Analyze/Suggest containment displays actionable config error.
- With real provider configured, responses are model-backed and audited with provider/model.

---

## Phase 6: Docs and AGENTS cleanup

### Task 6.1: Rewrite scan testing instructions

**Objective:** Docs should describe real FortiGate scan detection first, not synthetic replay.

**Files:**
- Modify: `AGENTS.md`
- Modify: `docs/mvp/walkthrough.md` or replace with production readiness docs
- Add: `docs/operations/fortigate-scan-detection.md`

### Task 6.2: Remove demo-roadmap language from customer-facing docs

**Objective:** Product docs should not present the platform as a demo tool.

**Verification:**
- `search_files("MVP demo|synthetic|seed demo|simulator|scripted AI|demo replay", path="docs")` returns only archived/internal lab docs.

---

## Global verification commands

Run after each phase:

```bash
git diff --check
cd apps/api && uv run ruff check . && uv run pytest -q
cd apps/siem_kowalski && uv run ruff check . && uv run pytest -q
cd apps/soar_skipper && uv run ruff check . && uv run pytest -q
cd apps/xdr_rico && uv run pytest -q
cd apps/agent_private && uv run pytest -q
cd apps/web && pnpm test && pnpm build
```

## Done criteria

- No production UI contains "MVP demo", "Replay", "seed demo", "simulator", or "scripted AI" as an operator flow.
- Synthetic replay and XDR simulator endpoints are absent or 404 unless an explicit lab-only flag is enabled.
- AI endpoints do not silently fabricate scripted responses when a real provider fails or is missing.
- Scan detection can be validated from real FortiGate logs through the integration card.
- Endpoint detections can be validated from real `agent_private` telemetry.
- Docs explain live setup and troubleshooting, not demo seeding as the default path.
