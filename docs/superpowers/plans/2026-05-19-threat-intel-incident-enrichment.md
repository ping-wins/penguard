# Threat Intel Incident Enrichment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Threat Intel enrichment for existing SOC incidents and Sysmon endpoint IoCs using a configurable VirusTotal provider.

**Architecture:** The BFF owns Threat Intel orchestration, cache, audit, and SIEM notes. `agent_private` and `xdr_rico` only provide minimized IoCs; model/runtime code never receives secrets. VirusTotal is configured through environment variables and wrapped behind a small provider interface.

**Tech Stack:** FastAPI, Pydantic, httpx, Pytest, Vue 3, Pinia-adjacent services, vue-i18n.

---

### Task 1: Backend Threat Intel Core

**Files:**
- Create: `apps/api/app/threat_intel/models.py`
- Create: `apps/api/app/threat_intel/extractors.py`
- Create: `apps/api/app/threat_intel/providers.py`
- Create: `apps/api/app/threat_intel/service.py`
- Create: `apps/api/app/threat_intel/__init__.py`
- Modify: `apps/api/app/core/config.py`
- Test: `apps/api/tests/test_threat_intel.py`

- [x] Write failing tests for IoC extraction, URL sanitization, VirusTotal stats normalization, and cache hits.
- [x] Implement models, extractors, provider, and service.
- [x] Run focused tests and Ruff.

### Task 2: BFF Incident And Sysmon Integration

**Files:**
- Modify: `apps/api/app/routers/soc.py`
- Modify: `apps/api/tests/test_soc_gateway.py`

- [x] Write failing tests for `POST /api/soc/incidents/{id}/threat-intel/enrich`.
- [x] Write failing tests for Sysmon auto-enrichment using minimized `attributes.ioc`.
- [x] Implement dependency, audit, SIEM note persistence, and safe forwarding.
- [x] Run focused API tests and Ruff.

### Task 3: Cockpit UI

**Files:**
- Modify: `apps/web/src/services/ticketsClient.ts`
- Modify: `apps/web/src/components/tickets/TicketsPanel.vue`
- Modify: `apps/web/src/i18n/messages/en-US.ts`
- Modify: `apps/web/src/i18n/messages/pt-BR.ts`
- Test: existing web tests if feasible.

- [x] Add typed Threat Intel client call.
- [x] Add drawer state, action button, result panel, and localized strings.
- [x] Run focused web tests/build if dependency state allows.

### Task 4: Docs, Verification, Commit

**Files:**
- Modify: `WINDOWS_SERVER_EDR_SYSMON.md`
- Modify: `apps/agent_private/README.md`

- [x] Document VirusTotal env vars and workflow.
- [x] Run backend tests, Ruff, `git diff --check`, and web checks.
- [x] Stage only task-scope files and commit.
