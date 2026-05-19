# Real LLM Agent Runtime — Design

**Status:** Approved (sections 1-6) — pending user review of written spec
**Date:** 2026-05-17
**Owner:** luskotav-cloud
**Related:** [`2026-05-13-ai-agent-architecture-design.md`](2026-05-13-ai-agent-architecture-design.md) (original architecture vision; this spec implements its Phase 2+ for the streaming agent runtime), [`2026-05-13-pydantic-ai-cockpit-agent.md`](../plans/2026-05-13-pydantic-ai-cockpit-agent.md), [`2026-05-13-ai-agent-foundation.md`](../plans/2026-05-13-ai-agent-foundation.md)

## Vision

Make the AI agent in Penguard actually useful: plug real LLM providers (Anthropic + OpenAI) into the streaming agent runner, route the right model per task automatically, stream tokens in real time, and let some agent roles do more than read — all with token budgets, per-tier tool capabilities, and a working approval gate for write actions.

Today `app/ai/agent/` only ships a `ScriptedBackend`; the real LLM code lives in a separate `app/ai/provider.py` used by `/api/ai/chat`'s incident analysis flow, not by the streaming agent runner. The cockpit chat experience is therefore mock-only end-to-end. This spec fixes that.

## Decisions locked with user

| Question | Decision |
|---|---|
| Which providers first | **Anthropic + Gemini + OpenAI** (CLI-passthrough deferred). |
| Model selection | **Auto-routing by task** (a role declares a tier; tier → model table picks). |
| How the router knows the task | **Explicit role per session.** Frontend picks at chat open. |
| Streaming | **Real token-a-token** streaming, not single block. |
| Write capability | **Tier-policy:** fast=read only, balanced=read+draft, deep=read+draft+write (write requires approval). |
| Guardrails | **Token budget per role (per session) + step limit.** Exceed → session aborts with `budget_exceeded`. |

## Current state (for context)

- `app/ai/agent/`: synchronous protocol `AgentBackend.decide(history, tools, locale) -> BackendDecision`. One `ScriptedBackend`. Runner emits a single `TextDeltaEvent` at the end. Sessions in-memory, TTL 1h, max 10/user. `AwaitingApprovalEvent` shape reserved but not wired.
- `app/ai/provider.py`: real Anthropic / OpenAI-compatible / Gemini code, but only for the non-agent `analyze` / `containment` JSON-prompt flow. No tool-use.
- `app/ai/cockpit_agent.py`: pydantic-ai `Agent` with `FunctionModel` — drafts widgets. Lives outside the streaming runner. Stays as-is in this work.
- `app/ai/tools/` (widget draft tools, used by cockpit) and `app/ai/agent/tools/` (audit/incidents/integrations/playbook_runs/widgets/workspace/xdr_endpoints, used by streaming runner) are two parallel tool registries. Unification is out of scope for this spec.
- `UserAiPreference` stores per-user provider + single `api_key` (encrypted). `settings.ai_provider` + per-provider env keys are the fallback.

## Architecture

```
POST /api/ai-agent/sessions { role, locale, ... }
        │
        ▼
    SessionStore.create(session, role=...)
        │
        ▼
POST /api/ai-agent/sessions/{id}/messages   (SSE)
        │
        ▼
    AgentRunner.run_turn(...)
        │  loads RoleConfig from roles.py
        │  picks Backend (Anthropic | OpenAI | Scripted) via tier + credentials
        │  filters tool registry by RoleConfig.allowed_tool_categories
        │  enforces token_budget + max_steps
        ▼
    Backend.stream_decide(history, tools, system_prompt, locale, max_output_tokens)
        │  translates → native API (Messages API / Chat Completions)
        │  streams native events
        ▼
    yields BackendStreamEvent: text_delta | tool_call | final | error
        ▼
    Runner emits AgentEvent over SSE:
        text_delta | tool_call | tool_result | awaiting_approval | done | error
```

### New / refactored layers

- `app/ai/agent/roles.py` (**new**) — immutable registry of 5 roles. Each role: `tier`, `system_prompt`, `allowed_tool_categories`, `token_budget`, `max_steps`, `locale_default`.
- `app/ai/agent/router.py` (**new**) — `pick_backend(role, user_id) -> AgentBackend`. Resolves provider (per-user > env > scripted), maps role's tier → model, instantiates concrete backend.
- `app/ai/agent/backends/base.py` (**redesigned**) — async streaming protocol; emits `BackendStreamEvent` (`TextDelta`, `ToolCall`, `Final`, `BackendError`).
- `app/ai/agent/backends/anthropic.py` (**new**) — wraps `anthropic` SDK Messages stream + tool-use.
- `app/ai/agent/backends/openai.py` (**new**) — wraps `openai` SDK chat-completions stream + tool_calls.
- `app/ai/agent/backends/scripted.py` (**reworked**) — same deterministic rules, now async iterator interface.
- `app/ai/agent/registry.py` — `AgentTool.category` becomes `Literal["read", "draft", "write"]`. `register_tool` validates `category == "write" implies requires_approval == True`.
- `app/ai/agent/session.py` — `AgentSession.role_id`, `AgentSession.tokens_in_total`, `AgentSession.tokens_out_total`, `AgentSession.pending_approvals` (call_id → `asyncio.Future`). `AgentMessage` carries `tool_calls: list[(call_id, tool_name, args)] | None` on assistant turns.
- `app/ai/agent/runner.py` — consumes the new async iterator, sums tokens from `Final` events, aborts on `budget_exceeded` / `max_steps_exceeded`, gates `write` tools on approval futures.
- `app/routers/ai_agent.py` — `POST /sessions` requires `role`; new `GET /roles`; new `POST /sessions/{id}/approvals/{call_id}` (RBAC slug `ai.agent.approve`, CSRF).
- `apps/web/src/stores/useAgentStore.ts` (**new**) — `roles`, `activeRole`, `sessionId`, `messages`, `pendingApproval`, `tokens`. Methods: `fetchRoles`, `createSession`, `sendMessage` (EventSource), `approve`.
- `apps/web/src/components/cockpit/AgentChat.vue` — role selector at open, model badge, approval banner, budget-exceeded banner.

### Roles (initial set)

| Role | Tier | Tools | Budget | Steps | Use case |
|---|---|---|---|---|---|
| `chat` | fast | read | 20k | 8 | Quick questions about state. |
| `widget-builder` | balanced | read + draft | 100k | 12 | Drafts custom widgets. |
| `incident-triage` | balanced | read + draft | 150k | 20 | Analyze incident, summarize, suggest playbook. |
| `playbook-draft` | balanced | read + draft | 150k | 20 | Build a SOAR playbook draft from intent. |
| `soc-investigation` | deep | read + draft + write | 300k | 30 | End-to-end investigation that may contain (write w/ approval). |

By convention only `deep`-tier roles include `write` in `allowed_tool_categories`. The enforcement is the role definition itself in `roles.py`, not a tier→category lookup at runtime — runtime only checks `tool.category in role.allowed_tool_categories`.

### Tier → model

| Tier | Anthropic | OpenAI |
|---|---|---|
| fast | `claude-haiku-4-5-20251001` | `gpt-4o-mini` |
| balanced | `claude-sonnet-4-6` | `gpt-4o` |
| deep | `claude-opus-4-7` | `gpt-4o` (alias; OpenAI has no Opus equivalent) |

ENV escape hatch per role: `PENGUARD_ROLE_<ROLE_ID>_TIER` overrides the tier without code change (e.g. `PENGUARD_ROLE_CHAT_TIER=deep`).

### System prompts

Hardcoded in `roles.py`. Each declares: identity ("SOC assistant for Penguard"), locale-driven language, hard restrictions (drafts until user confirms; never emit secrets; never request API keys), tool catalogue (rendered from the filtered set), and stopping criteria.

## Backend protocol

```python
@dataclass(frozen=True)
class TextDelta:
    kind: Literal["text_delta"] = "text_delta"
    text: str = ""

@dataclass(frozen=True)
class ToolCall:
    kind: Literal["tool_call"] = "tool_call"
    call_id: str = ""
    tool_name: str = ""
    args: dict[str, Any] = field(default_factory=dict)

@dataclass(frozen=True)
class Final:
    kind: Literal["final"] = "final"
    stop_reason: str = ""           # "end_turn" | "tool_use" | "max_tokens" | "stop_sequence"
    tokens_in: int = 0
    tokens_out: int = 0

@dataclass(frozen=True)
class BackendError:
    kind: Literal["error"] = "error"
    message: str = ""
    code: str = ""                  # "rate_limit" | "auth" | "transport" | "context_overflow" | "other"
    retryable: bool = False

BackendStreamEvent = TextDelta | ToolCall | Final | BackendError


class AgentBackend(Protocol):
    name: str
    model: str

    async def stream_decide(
        self,
        *,
        history: list[dict[str, Any]],
        tools: list[AgentTool],
        system_prompt: str,
        locale: str,
        max_output_tokens: int,
    ) -> AsyncIterator[BackendStreamEvent]: ...
```

### Contract

- One `stream_decide` call = one model turn. Yields zero-or-more `TextDelta`, zero-or-more `ToolCall`, exactly one terminal `Final` or `BackendError`.
- Backends never execute tools. They yield `ToolCall`; the runner executes and re-calls `stream_decide` with updated history.
- `Final.stop_reason="tool_use"` ⇒ runner runs the yielded tool calls then loops. `"end_turn"` ⇒ runner emits `DoneEvent`.
- Token accounting is authoritative from `Final.tokens_in/out`.
- Errors are never raised; always yielded as `BackendError`. Runner decides retry/abort by `retryable`.

### Canonical history (runner-side)

```python
[
  {"role": "system",    "content": "<role.system_prompt>"},
  {"role": "user",      "content": "..."},
  {"role": "assistant", "content": "...", "tool_calls": [{"id":"...","name":"...","args":{...}}]},
  {"role": "tool",      "tool_call_id": "...", "tool_name": "...", "result": {...}},
  ...
]
```

Each backend translates this canonical form to its native messages format. Tool schemas come from `AgentTool.input_schema` (already JSON Schema). Anthropic: `tools=[{name, description, input_schema}]`. OpenAI: `tools=[{type:"function", function:{name, description, parameters: input_schema}}]`.

### Cancellation

Runner uses `asyncio.Task`. SSE client disconnect cancels the task; the native SDK stream's `async for` raises `CancelledError`; backend stops yielding; runner exits without persisting partial assistant reply.

## Runner changes

- Loads `RoleConfig` from `session.role_id`.
- Calls `backend_picker(role, user_id)` (injected at app startup).
- `allowed_tools = [t for t in list_tools() if t.category in role.allowed_tool_categories]`.
- Before each `stream_decide`, checks `tokens_in_total + tokens_out_total >= role.token_budget` → `ErrorEvent("budget_exceeded")`, abort.
- `max_output_tokens` passed to backend = `min(4096, remaining_budget // 2)` where `4096` is `PROVIDER_DEFAULT_MAX_OUTPUT_TOKENS` (constant in `runner.py`).
- Consumes `BackendStreamEvent` async iterator: forwards `TextDelta` as `TextDeltaEvent`, accumulates `ToolCall`s into `pending_tool_calls`, applies `Final.tokens_in/out` to running totals, breaks the inner loop on `Final` (`end_turn` → `DoneEvent`; `tool_use` → execute pending).
- For each pending tool call:
  - If tool not in `allowed_tools`: emits `ToolResultEvent(status="error", error="tool not allowed for this role")`; appends a tool result to history so the next turn can self-correct.
  - If `tool.category == "write"` (which implies `requires_approval`): creates `asyncio.Future` keyed by `call_id` in `session.pending_approvals`, emits `AwaitingApprovalEvent`, awaits with timeout 5 min. Granted → invokes tool. Denied / timeout → tool result = `{"error":"approval_denied"|"approval_timeout"}`.
  - Otherwise emits `ToolCallEvent`, invokes tool with `tool.timeout_seconds`, emits `ToolResultEvent`.
- Audit recorder always called per tool call with `argsKeys` (never `args` values), backend name + model, latency, status.
- Per-session lock: only one in-flight turn per `session.id`. Concurrent message → 409.

## Credentials

```python
def pick_backend(role: RoleConfig, user_id: str | None) -> AgentBackend:
    provider, api_key = _resolve_credentials(user_id)   # per-user > env > none
    model = _resolve_model(provider, role.tier)         # tier table + ENV override
    if provider == "anthropic": return AnthropicBackend(api_key=api_key, model=model)
    if provider == "openai":    return OpenAIBackend(api_key=api_key, model=model)
    return ScriptedBackend()
```

`UserAiPreference` gains optional `api_keys: dict[str, str]` (provider → encrypted key). Legacy single `api_key` is read and mapped to the user's selected `provider`. Alembic migration adds the column (nullable JSON).

Tools never see `api_key` — `ToolContext` does not carry it; backend instances hold it as a private field.

## Sessions

- `POST /api/ai-agent/sessions` body: `{ role: str (required after Phase B done), locale?: str, ... }`. Phase B transitional default is `"chat"`; default removed at Phase B done.
- `GET /api/ai-agent/roles` — authenticated; returns `[{id, label, tier, localeDefault}]` from `roles.py`.
- `POST /api/ai-agent/sessions/{id}/approvals/{call_id}` — `require_permission("ai.agent.approve")` + CSRF; body `{granted: bool, reason?: str}`; resolves the runner's pending future.
- Persistence stays in-memory (`SessionStore`, TTL 1h, max 10/user). DB persistence is out of scope.

## Frontend

- Role selector at chat open (5 options with label + 1-line description). Default `chat`.
- Model badge below the input: e.g. *"Claude Sonnet 4.6 · 12.4k / 150k tokens"* — populated from `DoneEvent`.
- Token-stream rendering: `TextDeltaEvent` concatenated into a reactive buffer; `DoneEvent.reply` reconciles in case any delta was dropped.
- `awaiting_approval` event renders a yellow banner with tool name + args + Approve / Deny buttons → POST `/approvals/{call_id}`.
- `budget_exceeded` / `max_steps_exceeded` renders a red banner with "New session" CTA.

## Error handling

| Case | Behavior |
|---|---|
| `BackendError(retryable=True, code="rate_limit")` | One retry with 2 s backoff; second failure → `ErrorEvent`; session not terminated. |
| `code="context_overflow"` | Runner truncates: keep system + last 4 user messages + last tool results; one retry; still failing → `ErrorEvent`. |
| `code="auth"` | `ErrorEvent` immediately; session terminated; UI suggests `/ai/preferences`. |
| `Final.stop_reason="max_tokens"` with no `tool_call` | `DoneEvent(reply, truncated=true)`; not an error. |
| Provider down + fallback enabled + alternate provider configured for same tier | Try alternate provider once (per turn). Flag `ai_agent_fallback_enabled` (default true). |
| Approval timeout (5 min) | Tool result `{"error":"approval_timeout"}`, status `"denied"`, agent continues. |
| Unknown / unallowed tool requested by model | `ToolResultEvent(status="error", error="tool not allowed")` + history entry so the next turn can recover. |

## Security / guardrails

- Tools never receive credentials. Backend keeps key as a private field.
- System prompts explicitly forbid emitting secrets and requesting API keys.
- Audit recorder logs `argsKeys` (key list), never `args` values.
- `register_tool` raises `ValueError` if `category=="write"` and `requires_approval` is False.
- Per-session lock prevents concurrent turns from the same client.

## Testing

| Layer | Test |
|---|---|
| `roles.py` | All 5 roles present; non-empty system prompts; tier in `{fast,balanced,deep}`; budget > 0; `soc-investigation` is the only role with `"write"` in `allowed_tool_categories`. |
| `router.py` | Per-user pref beats env; missing key falls back to `ScriptedBackend`; tier→model resolves; ENV override applied. |
| `AnthropicBackend` | Fake httpx transport returning a recorded stream (text deltas + tool_use); translation of history/tools verified; `rate_limit` response yields retryable `BackendError`; `auth` yields non-retryable. |
| `OpenAIBackend` | Same with `delta.tool_calls` chunks; non-streaming usage record parsed into `Final.tokens_*`. |
| `ScriptedBackend` (new async) | Pre-existing keyword-routing behavior preserved (all old tests updated to async iterator consumption). |
| `runner.py` | Budget exceeded aborts; role-filtered tool blocked by both backend (never offered) and runner (defense in depth); awaiting_approval pauses, resolves on POST, denial returns error; cancellation finishes cleanly; per-session lock returns 409 on concurrent turn. |
| Integration SSE | TestClient SSE: create session with role, send message, assert sequence `text_delta+ ... tool_call ... tool_result ... done` with token counts. |

## Migration / rollout

Phased delivery — each phase is independently shippable, ordered A→B→C→D→E (C and D are interchangeable; E may be deferred if no `write` tool ships):

1. **Phase A — Protocol redesign + ScriptedBackend rewrite.** `base.py` async, `runner.py` consumes iterator, `scripted.py` adapted, session/message schema fields added. No real LLM yet.
2. **Phase B — `roles.py` + `router.py` + `/roles` endpoint + role-aware sessions + tool category filter + budget enforcement.** Recategorizes existing tools (`draft_widget` and `draft_containment_playbook` move from the cockpit registry into the agent registry as `draft`; everything else stays `read`).
3. **Phase C — `AnthropicBackend` + Claude default + tier table applied.**
4. **Phase D — `OpenAIBackend` + provider fallback.**
5. **Phase E — Approval gate end-to-end + UI banner + RBAC slug `ai.agent.approve`.** No `write` tools yet; infrastructure ready.

`/api/ai/chat` and `app/ai/cockpit_agent.py` are untouched. Existing in-memory sessions are dropped on restart (already the behavior). Tool files get a one-line `category=` addition each.

## Out of scope (deferred)

- DB-persisted sessions.
- Streaming tool results (tools that return chunked output).
- Parallel tool execution within a turn.
- Gemini and CLI-passthrough backends.
- Daily per-user usage quotas.
- MCP server (original spec phase 4).
- LangGraph triage workflow (original spec phase 3).
- Cost / pricing dashboard.
- Unifying the cockpit (`app/ai/tools/`) and agent (`app/ai/agent/tools/`) registries.

## Acceptance criteria

1. Creating a session with `role="incident-triage"` runs Sonnet (Anthropic when configured), uses the triage system prompt, exposes only `read`+`draft` tools, and enforces a 150k token budget.
2. The SSE stream emits real token-by-token `text_delta` plus `tool_call`/`tool_result` events plus a final `done` carrying real `tokens_in/out`.
3. A `write`-category tool emits `awaiting_approval`; absence of approval within 5 min becomes `denied` and the agent continues.
4. `tokens_in_total + tokens_out_total > role.token_budget` aborts the session with `budget_exceeded`.
5. A user without credentials falls back to `ScriptedBackend` without raising.
6. Switching `UserAiPreference.provider` between `anthropic` and `openai` is picked up by the next session.
7. `PENGUARD_ROLE_CHAT_TIER=deep` forces the `chat` role to use the deep tier without code change.
8. RBAC slug `ai.agent.approve` is required by the approvals endpoint, CSRF enforced.
