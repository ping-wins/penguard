# Pydantic AI Cockpit Agent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Route the existing dashboard chat through a Pydantic AI cockpit
runtime that can see the shared internal tool registry and execute safe draft
tools without persisting changes.

**Architecture:** Keep `/api/ai/chat` as the frontend contract, but move the
runtime behind `app.ai.cockpit_agent`. The first implementation uses Pydantic
AI's `Agent` and `FunctionModel` so local/scripted labs stay deterministic
while the runtime exposes registered tools for future provider-backed agents.

**Tech Stack:** FastAPI, Pydantic AI, Pydantic v2, Pytest, existing AI provider
fallbacks and existing audit dependencies.

---

### Task 1: Cockpit Agent Runtime

**Files:**
- Create: `apps/api/app/ai/cockpit_agent.py`
- Modify: `apps/api/pyproject.toml`
- Modify: `apps/api/uv.lock`
- Test: `apps/api/tests/test_ai_tools.py`

- [x] Add failing tests proving `/api/ai/status` reports `runtime:
  pydantic_ai`.
- [x] Add failing tests proving `/api/ai/chat` returns provider
  `pydantic_ai.scripted` in the offline lab path.
- [x] Add `pydantic-ai>=1.0.0` to the API package.
- [x] Implement `CockpitAgentRuntime` using Pydantic AI `Agent` and
  `FunctionModel`.
- [x] Register `list_data_fields` and `draft_widget` as Pydantic AI tools.

### Task 2: Safe Tool-Aware Chat

**Files:**
- Modify: `apps/api/app/routers/ai.py`
- Modify: `apps/web/src/services/aiClient.ts`
- Test: `apps/api/tests/test_ai_tools.py`

- [x] Route `/api/ai/chat` through `CockpitAgentRuntime`.
- [x] Preserve the existing frontend response contract and add `runtime`.
- [x] Audit provider, runtime, prompt length, reply length, tool count and
  used tools.
- [x] Add deterministic natural-language widget drafting for prompts that
  mention known data field IDs such as `system.cpu`.

### Task 3: Documentation Alignment

**Files:**
- Modify: `AGENTS.md`

- [x] Mark the Pydantic AI cockpit agent wrapper as delivered.
- [x] Keep LangGraph ticket triage and MCP server as separate pending cuts.

### Task 4: Verification

**Commands:**

```bash
cd apps/api && uv run pytest tests/test_ai_tools.py -q
cd apps/api && uv run pytest -q
cd apps/api && uv run ruff check app tests
git diff --check
```

Expected result: all commands pass with no lint or whitespace errors.
