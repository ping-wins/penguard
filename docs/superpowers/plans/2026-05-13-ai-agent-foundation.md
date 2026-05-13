# AI Agent Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the first shared internal AI tool contracts so cockpit chat,
LangGraph triage and future MCP tools can reuse one audited backend boundary.

**Architecture:** Add a focused `app.ai.tools` package with Pydantic schemas,
registry metadata and widget-draft logic. Expose read-only tool discovery and a
CSRF-protected draft-widget route from `apps/api/app/routers/ai.py`.

**Tech Stack:** FastAPI, Pydantic v2, Pytest, existing fixture catalogs and
existing auth/audit dependencies.

---

### Task 1: Tool Registry API

**Files:**
- Create: `apps/api/app/ai/tools/schemas.py`
- Create: `apps/api/app/ai/tools/registry.py`
- Create: `apps/api/app/ai/tools/__init__.py`
- Modify: `apps/api/app/routers/ai.py`
- Test: `apps/api/tests/test_ai_tools.py`

- [x] Write tests proving `/api/ai/tools` lists only safe, non-destructive tools
  with schema metadata and confirmation flags.
- [x] Implement `ToolSpec` and `list_tool_specs()`.
- [x] Wire `GET /api/ai/tools` behind authenticated BFF sessions.

### Task 2: Draft Widget Tool

**Files:**
- Create: `apps/api/app/ai/tools/widget_tools.py`
- Modify: `apps/api/app/routers/ai.py`
- Test: `apps/api/tests/test_ai_tools.py`

- [x] Write tests proving `POST /api/ai/tools/draft-widget` creates a draft
  from real provider fields and does not persist it.
- [x] Write tests proving unknown fields return `422` and audit a failure.
- [x] Implement field flattening from provider fixtures.
- [x] Implement `draft_widget()` with `fieldBindings[]`, suggested layout,
  preview data and validation warnings.
- [x] Audit success and failure as `ai.widget_draft.created`.

### Task 3: Documentation Alignment

**Files:**
- Modify: `AGENTS.md`

- [x] Replace stale AI/MCP backlog checkboxes with the Pydantic AI + LangGraph +
  MCP layering.
- [x] Mark internal tool contracts and widget draft foundation as delivered.
- [x] Keep future Pydantic AI runtime, LangGraph triage and MCP server as
  separate pending cuts.

### Task 4: Verification

**Commands:**

```bash
cd apps/api && uv run pytest tests/test_ai_tools.py -q
cd apps/api && uv run pytest tests/test_ai_tools.py tests/test_soc_gateway.py -q
cd apps/api && uv run ruff check app tests
git diff --check
```

Expected result: all commands pass with no lint or whitespace errors.
