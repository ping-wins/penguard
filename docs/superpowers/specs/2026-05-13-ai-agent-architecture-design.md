# AI Agent Architecture Design

## Goal

Build Penguard's AI layer as a safe SOC copilot that can inspect dashboard
state, draft widgets, assist ticket triage and prepare containment playbooks
without becoming an autonomous operator.

## Architecture Decision

Use three layers with different responsibilities:

- **Pydantic AI cockpit agent:** interactive dashboard assistant for typed,
  short-running tasks such as summarizing tickets, explaining widgets, drafting
  custom visuals and validating field bindings.
- **LangGraph triage workflow:** durable incident/ticket workflow for multi-step
  triage, endpoint correlation, containment planning, human approval pauses and
  retryable AI/provider failures.
- **MCP server, later:** public tool surface for customers who want to connect
  their own agents to Penguard. MCP must only expose stable, audited,
  permission-aware tools.

The first implementation cut is not a full agent runtime. It establishes the
shared internal tool contracts that Pydantic AI, LangGraph and future MCP routes
will call.

## Shared Tool Boundary

All AI tools live behind backend-owned Python functions. The frontend and model
never call service internals directly.

Initial tools:

- `list_data_fields`: return bindable provider fields from the same catalog used
  by the Build Panel.
- `draft_widget`: create a draft custom widget from provider fields and a visual
  type.
- `validate_widget`: reject unknown fields, unsupported visuals and malformed
  bindings before anything reaches a workspace manifest.
- `simulate_widget_data`: return clearly labeled sample values for preview only.
- `draft_containment_playbook`: reuse the existing SOAR draft flow.

Every tool contract must define input schema, output schema, permission model,
timeout and whether human confirmation is required.

## Safety Rules

- AI output is always a draft until a user confirms it.
- AI cannot approve playbook gates, execute real containment, change FortiGate,
  reveal secrets or persist workspace changes directly.
- All mutating or draft-producing tool calls are audited.
- Tool outputs must avoid embedding API keys, Keycloak tokens, endpoint
  enrollment tokens or FortiGate secrets.
- MCP will be added only after the internal tools have stable schemas and tests.

## Implementation Phases

1. Internal AI tool registry and widget draft tool.
2. Pydantic AI cockpit agent wrapper that calls the registry.
3. LangGraph triage workflow for ticket analysis and containment planning.
4. MCP server exposing a safe subset of the same registry.

## Acceptance Criteria

- `/api/ai/tools` lists safe tools with schemas and confirmation requirements.
- `/api/ai/tools/draft-widget` returns a validated draft widget without
  persisting it.
- Failed draft attempts produce useful validation errors and audit events.
- `AGENTS.md` documents the architecture and backlog order.
