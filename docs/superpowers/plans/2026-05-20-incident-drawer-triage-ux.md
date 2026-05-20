# Incident Drawer Triage UX Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a guided right-side incident drawer that opens on a concise Summary step, then lets the analyst move through Analysis and Containment without showing every raw field at once.

**Architecture:** Keep ticket loading and mutation behavior in `TicketsPanel.vue`, but move incident drawer-specific derivation into pure helpers and reorganize the drawer template around local step state. Preserve existing services, stores, endpoints, and `data-test` selectors for action buttons where practical.

**Tech Stack:** Vue 3 `<script setup>`, Pinia, Vitest, Vue Test Utils, vue-i18n, Tailwind utility classes, Lucide Vue icons.

---

### Task 1: Add Drawer State Tests

**Files:**
- Create: `apps/web/tests/unit/ticketsPanel.test.ts`
- Modify: `apps/web/src/components/tickets/TicketsPanel.vue`
- Modify: `apps/web/src/components/tickets/incidentDrawerState.ts`

- [x] **Step 1: Write the failing component test**

Create a test that mounts `TicketsPanel.vue` with a high-severity port scan ticket. The test must assert that selecting the ticket renders a guided Summary step, shows source/target/port-window facts, and hides raw entities, timeline, FortiWeb controls, and FortiGate policy form by default.

- [x] **Step 2: Run the focused test and verify RED**

Run:

```bash
cd apps/web && pnpm test tests/unit/ticketsPanel.test.ts
```

Expected: FAIL because the guided stepper and summary selectors do not exist.

- [x] **Step 3: Add minimal state helpers**

Create `incidentDrawerState.ts` with pure helpers for:

- extracting source/destination/port-count/window facts from `Ticket` and optional triage context,
- deciding the default active step,
- deciding whether FortiWeb controls should be primary for WAF/FortiWeb incidents.

- [x] **Step 4: Re-run the focused test and verify GREEN**

Run:

```bash
cd apps/web && pnpm test tests/unit/ticketsPanel.test.ts
```

Expected: PASS.

### Task 2: Reorganize The Drawer Into Three Steps

**Files:**
- Modify: `apps/web/src/components/tickets/TicketsPanel.vue`
- Modify: `apps/web/src/i18n/messages/pt-BR.ts`
- Modify: `apps/web/src/i18n/messages/en-US.ts`
- Test: `apps/web/tests/unit/ticketsPanel.test.ts`

- [x] **Step 1: Add failing tests for Analysis and Containment navigation**

Extend the test file to click Analysis and Containment tabs. Assert that:

- Analysis shows deterministic triage evidence and MITRE data after context load.
- Containment shows the recommended playbook action path.
- Raw details remain behind explicit disclosure controls.

- [x] **Step 2: Run focused tests and verify RED**

Run:

```bash
cd apps/web && pnpm test tests/unit/ticketsPanel.test.ts
```

Expected: FAIL because the step navigation and disclosures are incomplete.

- [x] **Step 3: Implement the guided drawer**

Modify the drawer template to render:

- fixed header with compact status/severity facts,
- local stepper with Summary, Analysis, Containment,
- Summary step with compact facts and status/triage controls,
- Analysis step with deterministic triage, AI, and threat intel blocks,
- Containment step with playbook, approval, FortiGate policy review/apply, and secondary FortiWeb controls,
- raw entities and timeline only inside disclosure buttons.

- [x] **Step 4: Add localization keys**

Add all new visible strings under `tickets.drawer`, `tickets.workflow`, or existing ticket namespaces in both `pt-BR.ts` and `en-US.ts`.

- [x] **Step 5: Run focused tests and verify GREEN**

Run:

```bash
cd apps/web && pnpm test tests/unit/ticketsPanel.test.ts
```

Expected: PASS.

### Task 3: Verify Existing Frontend Contracts

**Files:**
- Modify only if tests expose a real regression.

- [x] **Step 1: Run relevant frontend tests**

Run:

```bash
cd apps/web && pnpm test tests/unit/ticketsPanel.test.ts tests/unit/playbooksPanel.test.ts tests/unit/sidebarIntegrations.test.ts
```

Expected: PASS.

- [x] **Step 2: Run full web test suite**

Run:

```bash
cd apps/web && pnpm test
```

Expected: PASS.

- [x] **Step 3: Run frontend build**

Run:

```bash
cd apps/web && pnpm build
```

Expected: PASS.

- [x] **Step 4: Run diff whitespace check**

Run:

```bash
git diff --check
```

Expected: PASS.
