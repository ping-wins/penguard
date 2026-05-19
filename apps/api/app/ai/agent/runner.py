"""Runner — drives one user turn end-to-end.

For each user message:
  1. Append to session history.
  2. Ask the selected backend to stream one model turn.
  3. Forward text deltas, collect tool calls, and account final token usage.
  4. If tool_use → execute approved/allowed tools, record results, loop.
  5. If end_turn → persist the assistant reply and emit Done.

Step events are streamed to the caller as an async iterator so the
router can forward them over SSE.

Write-category tools always pause on an approval future before invocation.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from typing import Any

from app.ai.agent.backends.base import AgentBackend, BackendError, Final, TextDelta, ToolCall
from app.ai.agent.events import (
    AgentEvent,
    AwaitingApprovalEvent,
    DoneEvent,
    ErrorEvent,
    TextDeltaEvent,
    ToolCallEvent,
    ToolResultEvent,
)
from app.ai.agent.registry import (
    AgentTool,
    ToolContext,
    get_tool,
    list_tools,
    missing_required_permissions,
    tool_allowed_by_permissions,
)
from app.ai.agent.roles import RoleConfig, get_role, render_system_prompt
from app.ai.agent.router import AgentNotConfiguredError
from app.ai.agent.session import AgentMessage, AgentSession, SessionStore

logger = logging.getLogger(__name__)

MAX_STEPS_DEFAULT = 20
PROVIDER_DEFAULT_MAX_OUTPUT_TOKENS = 2048
PROVIDER_OUTPUT_TOKEN_CAPS = {"gemini": 1024}
PROVIDER_SESSION_TOKEN_BUDGET_CAPS = {"gemini": 20_000}
APPROVAL_TIMEOUT_SECONDS = 300
MAX_MODEL_HISTORY_MESSAGES = 12
MAX_MODEL_TEXT_CHARS = 2000
MAX_MODEL_TOOL_RESULT_CHARS = 3000
MAX_MODEL_TOOL_FIELD_CHARS = 500
MAX_MODEL_TOOL_RESULT_ITEMS = 5
MAX_MODEL_TOOL_RESULT_DEPTH = 4

BackendPicker = Callable[[RoleConfig, str | None], AgentBackend]


@dataclass
class AgentRunner:
    session_store: SessionStore
    backend: AgentBackend | None = None
    backend_picker: BackendPicker | None = None
    max_steps: int | None = None
    approval_timeout_seconds: float = APPROVAL_TIMEOUT_SECONDS
    audit_recorder: Any | None = None  # callable: (action, outcome, details) -> None

    async def run_turn(
        self,
        *,
        session: AgentSession,
        user_message: str,
        tool_context: ToolContext,
    ) -> AsyncIterator[AgentEvent]:
        if not user_message.strip():
            yield ErrorEvent(step=0, message="empty user message", code="empty_message")
            return

        if session.turn_lock.locked():
            yield ErrorEvent(
                step=0,
                message="session already has an active turn",
                code="concurrent_turn",
            )
            return

        async with session.turn_lock:
            self.session_store.append_message(
                session,
                AgentMessage(role="user", content=user_message),
            )
            async for event in self._run_locked_turn(session=session, tool_context=tool_context):
                yield event

    async def _run_locked_turn(
        self,
        *,
        session: AgentSession,
        tool_context: ToolContext,
    ) -> AsyncIterator[AgentEvent]:
        role = _role_for_session(session.role_id)
        if role is None:
            yield ErrorEvent(step=0, message="agent role registry unavailable", code="role_error")
            return

        try:
            backend = self._resolve_backend(role, session.user_id)
        except AgentNotConfiguredError as exc:
            yield ErrorEvent(step=0, message=str(exc), code="agent_not_configured")
            return
        session.backend = backend.name
        session.model = backend.model

        allowed_tools = [
            tool
            for tool in list_tools()
            if tool.category in role.allowed_tool_categories
            and tool_allowed_by_permissions(tool, tool_context.effective_permissions)
        ]
        allowed_names = {tool.name for tool in allowed_tools}
        used_tools: list[str] = []
        max_steps = self.max_steps if self.max_steps is not None else role.max_steps
        last_final_text = ""
        token_budget = min(
            role.token_budget,
            PROVIDER_SESSION_TOKEN_BUDGET_CAPS.get(backend.name, role.token_budget),
        )

        for step in range(1, max_steps + 1):
            if session.tokens_in_total + session.tokens_out_total >= token_budget:
                yield ErrorEvent(
                    step=step,
                    message="agent token budget exceeded",
                    code="budget_exceeded",
                )
                return

            remaining_budget = token_budget - (
                session.tokens_in_total + session.tokens_out_total
            )
            max_output_tokens = max(
                1,
                min(
                    PROVIDER_OUTPUT_TOKEN_CAPS.get(
                        backend.name,
                        PROVIDER_DEFAULT_MAX_OUTPUT_TOKENS,
                    ),
                    remaining_budget // 2,
                ),
            )
            system_prompt = render_system_prompt(role, allowed_tools, locale=session.locale)
            history = _history_snapshot(session)
            pending_tool_calls: list[ToolCall] = []
            text_chunks: list[str] = []
            final_event: Final | None = None

            try:
                async for backend_event in backend.stream_decide(
                    history=history,
                    tools=allowed_tools,
                    system_prompt=system_prompt,
                    locale=session.locale,
                    max_output_tokens=max_output_tokens,
                ):
                    if isinstance(backend_event, TextDelta):
                        text_chunks.append(backend_event.text)
                        yield TextDeltaEvent(step=step, text=backend_event.text)
                    elif isinstance(backend_event, ToolCall):
                        pending_tool_calls.append(backend_event)
                    elif isinstance(backend_event, Final):
                        final_event = backend_event
                        session.tokens_in_total += max(0, backend_event.tokens_in)
                        session.tokens_out_total += max(0, backend_event.tokens_out)
                        break
                    elif isinstance(backend_event, BackendError):
                        yield ErrorEvent(
                            step=step,
                            message=backend_event.message,
                            code=backend_event.code or "backend_error",
                        )
                        return
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001
                logger.exception("agent backend stream failed")
                yield ErrorEvent(
                    step=step,
                    message=f"backend error: {exc}"[:300],
                    code="backend_error",
                )
                return

            if final_event is None:
                yield ErrorEvent(
                    step=step,
                    message="backend ended without a terminal event",
                    code="backend_error",
                )
                return

            reply_text = "".join(text_chunks)
            if final_event.stop_reason in {"end_turn", "max_tokens", "stop_sequence"}:
                last_final_text = reply_text
                self.session_store.append_message(
                    session,
                    AgentMessage(role="assistant", content=reply_text),
                )
                yield DoneEvent(
                    step=step,
                    reply=reply_text,
                    used_tools=list(used_tools),
                    tokens_in=session.tokens_in_total,
                    tokens_out=session.tokens_out_total,
                )
                return

            if final_event.stop_reason != "tool_use":
                yield ErrorEvent(
                    step=step,
                    message=f"unsupported stop reason: {final_event.stop_reason}",
                    code="unsupported_stop_reason",
                )
                return

            self.session_store.append_message(
                session,
                AgentMessage(
                    role="assistant",
                    content=reply_text,
                    tool_calls=[
                        {
                            "id": call.call_id,
                            "name": call.tool_name,
                            "args": dict(call.args),
                            "providerMetadata": dict(call.provider_metadata),
                        }
                        for call in pending_tool_calls
                    ],
                ),
            )

            if not pending_tool_calls:
                yield ErrorEvent(
                    step=step,
                    message="backend requested tool use without tool calls",
                    code="missing_tool_call",
                )
                return

            for call in pending_tool_calls:
                tool = get_tool(call.tool_name)
                if tool is None or tool.name not in allowed_names:
                    missing_permissions = (
                        missing_required_permissions(
                            tool,
                            tool_context.effective_permissions,
                        )
                        if tool is not None
                        and tool.category in role.allowed_tool_categories
                        else []
                    )
                    error_msg = (
                        "missing required permission: "
                        + ", ".join(missing_permissions)
                        if missing_permissions
                        else "tool not allowed for this role"
                    )
                    yield ToolResultEvent(
                        step=step,
                        call_id=call.call_id,
                        tool_name=call.tool_name,
                        status="error",
                        result={"error": error_msg},
                        error=error_msg,
                        latency_ms=0,
                    )
                    self.session_store.append_message(
                        session,
                        AgentMessage(
                            role="tool",
                            tool_call_id=call.call_id,
                            tool_name=call.tool_name,
                            tool_args=dict(call.args),
                            tool_result=_model_tool_result({"error": error_msg}),
                        ),
                    )
                    continue

                call_event = ToolCallEvent(
                    step=step,
                    call_id=call.call_id,
                    tool_name=tool.name,
                    args=dict(call.args),
                )

                if tool.requires_approval:
                    approval_future = self._create_approval_future(session, call.call_id)
                    yield AwaitingApprovalEvent(
                        step=step,
                        call_id=call.call_id,
                        tool_name=tool.name,
                        args=dict(call.args),
                        reason=f"{tool.category} tool requires approval",
                    )
                    approved = await self._await_approval(session, call.call_id, approval_future)
                    if not approved:
                        result_payload = {"error": "approval_denied"}
                        status_label = "denied"
                        error_msg = "approval_denied"
                        latency_ms = 0
                        yield ToolResultEvent(
                            step=step,
                            call_id=call.call_id,
                            tool_name=tool.name,
                            status=status_label,
                            result=result_payload,
                            error=error_msg,
                            latency_ms=latency_ms,
                        )
                        self.session_store.append_message(
                            session,
                            AgentMessage(
                                role="tool",
                                tool_call_id=call.call_id,
                                tool_name=tool.name,
                                tool_args=dict(call.args),
                                tool_result=_model_tool_result(result_payload),
                            ),
                        )
                        self._record_tool_audit(
                            session=session,
                            backend=backend,
                            tool=tool,
                            args=call.args,
                            status=status_label,
                            latency_ms=latency_ms,
                            error=error_msg,
                        )
                        continue
                else:
                    yield call_event

                result_payload, status_label, error_msg, latency_ms = await _invoke_tool(
                    tool, tool_context, call.args
                )
                used_tools.append(tool.name)
                session.used_tools.append(tool.name)
                self._record_tool_audit(
                    session=session,
                    backend=backend,
                    tool=tool,
                    args=call.args,
                    status=status_label,
                    latency_ms=latency_ms,
                    error=error_msg,
                )

                yield ToolResultEvent(
                    step=step,
                    call_id=call.call_id,
                    tool_name=tool.name,
                    status=status_label,
                    result=result_payload,
                    error=error_msg,
                    latency_ms=latency_ms,
                )

                self.session_store.append_message(
                    session,
                    AgentMessage(
                        role="tool",
                        tool_call_id=call.call_id,
                        tool_name=tool.name,
                        tool_args=dict(call.args),
                        tool_result=_model_tool_result(result_payload),
                    ),
                )
            continue

        # Loop exit means we hit max_steps without a final.
        fallback = last_final_text or (
            "agent stopped: reached max steps without producing a final reply"
        )
        yield ErrorEvent(step=step, message=fallback, code="max_steps_exceeded")

    def _resolve_backend(self, role: RoleConfig, user_id: str | None) -> AgentBackend:
        if self.backend is not None:
            return self.backend
        if self.backend_picker is None:
            raise RuntimeError("AgentRunner requires backend or backend_picker")
        return self.backend_picker(role, user_id)

    def _create_approval_future(self, session: AgentSession, call_id: str) -> asyncio.Future:
        loop = asyncio.get_running_loop()
        future: asyncio.Future = loop.create_future()
        session.pending_approvals[call_id] = future
        return future

    async def _await_approval(
        self,
        session: AgentSession,
        call_id: str,
        future: asyncio.Future,
    ) -> bool:
        try:
            decision = await asyncio.wait_for(
                future,
                timeout=self.approval_timeout_seconds,
            )
        except TimeoutError:
            return False
        finally:
            session.pending_approvals.pop(call_id, None)
        if isinstance(decision, dict):
            return bool(decision.get("granted"))
        return bool(decision)

    def _record_tool_audit(
        self,
        *,
        session: AgentSession,
        backend: AgentBackend,
        tool: AgentTool,
        args: dict[str, Any],
        status: str,
        latency_ms: int,
        error: str | None,
    ) -> None:
        if self.audit_recorder is None:
            return
        try:
            self.audit_recorder(
                action="ai.agent.tool_call",
                outcome=status,
                details={
                    "sessionId": session.id,
                    "toolName": tool.name,
                    "backend": backend.name,
                    "model": backend.model,
                    "argsKeys": sorted(args.keys()),
                    "latencyMs": latency_ms,
                    "error": error,
                },
            )
        except Exception:  # noqa: BLE001
            logger.exception("agent tool audit_recorder failed")


async def _invoke_tool(
    tool: AgentTool,
    ctx: ToolContext,
    args: dict[str, Any],
) -> tuple[Any, str, str | None, int]:
    started = time.perf_counter()
    try:
        coro = tool.impl(ctx, args)
        result = await asyncio.wait_for(coro, timeout=tool.timeout_seconds)
    except TimeoutError:
        latency_ms = int((time.perf_counter() - started) * 1000)
        return None, "error", f"tool timed out after {tool.timeout_seconds}s", latency_ms
    except Exception as exc:  # noqa: BLE001
        latency_ms = int((time.perf_counter() - started) * 1000)
        return None, "error", str(exc)[:300], latency_ms
    latency_ms = int((time.perf_counter() - started) * 1000)
    if isinstance(result, dict) and "error" in result and "data" not in result:
        return result, "error", str(result["error"])[:300], latency_ms
    return result, "ok", None, latency_ms


def _history_snapshot(session: AgentSession) -> list[dict[str, Any]]:
    snapshot: list[dict[str, Any]] = []
    recent: list[dict[str, Any]] = []
    omitted = max(0, len(session.history) - MAX_MODEL_HISTORY_MESSAGES)
    if omitted:
        snapshot.append(
            {
                "role": "user",
                "content": (
                    f"[Earlier conversation omitted from model context: "
                    f"{omitted} messages. Use visible recent messages and tools only.]"
                ),
            }
        )
    for message in session.history[-MAX_MODEL_HISTORY_MESSAGES:]:
        entry: dict[str, Any] = {"role": message.role}
        if message.role == "tool":
            entry["tool_call_id"] = message.tool_call_id
            entry["tool_name"] = message.tool_name
            entry["args"] = _compact_for_model(
                message.tool_args or {},
                max_chars=MAX_MODEL_TEXT_CHARS,
            )
            entry["result"] = _model_tool_result(message.tool_result)
        else:
            entry["content"] = _trim_text(message.content, MAX_MODEL_TEXT_CHARS)
            if message.tool_calls:
                entry["tool_calls"] = _compact_tool_calls(message.tool_calls)
        recent.append(entry)
    return [*snapshot, *_preserve_leading_tool_call_pairs(recent)]


def _preserve_leading_tool_call_pairs(snapshot: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not snapshot or snapshot[0].get("role") != "tool":
        return snapshot
    tool_call_id = str(snapshot[0].get("tool_call_id") or "")
    if not tool_call_id:
        return snapshot[1:]
    return [
        {
            "role": "assistant",
            "content": "[Earlier assistant tool call omitted from compacted context.]",
            "tool_calls": [
                {
                    "id": tool_call_id,
                    "name": str(snapshot[0].get("tool_name") or ""),
                    "args": snapshot[0].get("args") or {},
                }
            ],
        },
        *snapshot,
    ]


def _compact_tool_calls(calls: list[dict[str, Any]]) -> list[dict[str, Any]]:
    compacted: list[dict[str, Any]] = []
    for call in calls:
        if not isinstance(call, dict):
            continue
        compacted_call = {
            "id": call.get("id"),
            "name": call.get("name"),
            "args": _compact_for_model(call.get("args") or {}, max_chars=MAX_MODEL_TEXT_CHARS),
        }
        provider_metadata = call.get("providerMetadata") or call.get("provider_metadata")
        if provider_metadata:
            compacted_call["providerMetadata"] = provider_metadata
        compacted.append(compacted_call)
    return compacted


def _model_tool_result(result: Any) -> Any:
    compacted = _compact_for_model(
        result,
        max_chars=MAX_MODEL_TOOL_FIELD_CHARS,
        max_items=MAX_MODEL_TOOL_RESULT_ITEMS,
        max_depth=MAX_MODEL_TOOL_RESULT_DEPTH,
    )
    encoded = _json_size(compacted)
    if encoded <= MAX_MODEL_TOOL_RESULT_CHARS:
        return compacted
    return {
        "_compactNotice": (
            "Tool result exceeded model context budget and was compacted. "
            "Use exact ids from the preview or call a narrower get_* tool."
        ),
        "preview": _trim_text(
            json.dumps(compacted, ensure_ascii=False, default=str),
            MAX_MODEL_TOOL_RESULT_CHARS,
        ),
    }


def _compact_for_model(
    value: Any,
    *,
    max_chars: int,
    max_items: int = MAX_MODEL_TOOL_RESULT_ITEMS,
    max_depth: int = MAX_MODEL_TOOL_RESULT_DEPTH,
) -> Any:
    if max_depth <= 0:
        return _summary_for_value(value)
    if isinstance(value, str):
        return _trim_text(value, max_chars)
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, list):
        items = [
            _compact_for_model(
                item,
                max_chars=max_chars,
                max_items=max_items,
                max_depth=max_depth - 1,
            )
            for item in value[:max_items]
        ]
        if len(value) > max_items:
            items.append({"_truncated": len(value) - max_items})
        return items
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key, raw in _ordered_model_items(value)[:32]:
            out[str(key)] = _compact_for_model(
                raw,
                max_chars=max_chars,
                max_items=max_items,
                max_depth=max_depth - 1,
            )
        if len(value) > 32:
            out["_truncatedKeys"] = len(value) - 32
        return out
    return _trim_text(str(value), max_chars)


def _ordered_model_items(value: dict[Any, Any]) -> list[tuple[Any, Any]]:
    priority = {
        "id",
        "incidentId",
        "ticketId",
        "title",
        "severity",
        "status",
        "ticketStatus",
        "triageLevel",
        "source",
        "createdAt",
        "updatedAt",
        "summary",
        "count",
        "items",
        "error",
    }
    return sorted(
        value.items(),
        key=lambda item: (0 if str(item[0]) in priority else 1, str(item[0])),
    )


def _summary_for_value(value: Any) -> Any:
    if isinstance(value, list):
        return {"_type": "list", "count": len(value)}
    if isinstance(value, dict):
        return {"_type": "object", "keys": [str(key) for key in list(value)[:12]]}
    return _trim_text(str(value), 200)


def _trim_text(value: str, max_chars: int) -> str:
    if len(value) <= max_chars:
        return value
    omitted = len(value) - max_chars
    return value[:max_chars].rstrip() + f"… [truncated {omitted} chars]"


def _json_size(value: Any) -> int:
    try:
        return len(json.dumps(value, ensure_ascii=False, default=str))
    except TypeError:
        return len(str(value))


def _role_for_session(role_id: str) -> RoleConfig | None:
    if role_id == "soc-assistant":
        return get_role("soc-investigation")
    return get_role(role_id)
