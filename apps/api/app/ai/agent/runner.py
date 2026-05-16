"""Runner — drives one user turn end-to-end.

For each user message:
  1. Append to session history.
  2. Ask backend for next decision.
  3. If tool_call → execute it (audit + record result), emit
     ToolCall+ToolResult events, loop back to (2).
  4. If final → emit Done, persist assistant message.

Step events are streamed to the caller as an async iterator so the
router can forward them over SSE.

Write-tool approval is NOT wired in PR1 — every registered tool is
read-only. The `AwaitingApprovalEvent` shape is reserved for PR4.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

from app.ai.agent.backends.base import AgentBackend, BackendDecision
from app.ai.agent.events import (
    AgentEvent,
    DoneEvent,
    ErrorEvent,
    TextDeltaEvent,
    ToolCallEvent,
    ToolResultEvent,
)
from app.ai.agent.registry import AgentTool, ToolContext, get_tool, list_tools
from app.ai.agent.session import AgentMessage, AgentSession, SessionStore

logger = logging.getLogger(__name__)

MAX_STEPS_DEFAULT = 20


@dataclass
class AgentRunner:
    backend: AgentBackend
    session_store: SessionStore
    max_steps: int = MAX_STEPS_DEFAULT
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

        self.session_store.append_message(
            session,
            AgentMessage(role="user", content=user_message),
        )

        used_tools: list[str] = []
        step = 0
        last_final_text = ""

        for step in range(1, self.max_steps + 1):
            history = _history_snapshot(session)
            try:
                decision: BackendDecision = self.backend.decide(
                    history=history,
                    tools=list_tools(),
                    locale=session.locale,
                )
            except Exception as exc:  # noqa: BLE001
                logger.exception("agent backend decide failed")
                yield ErrorEvent(
                    step=step,
                    message=f"backend error: {exc}"[:300],
                    code="backend_error",
                )
                return

            if decision.kind == "final":
                last_final_text = decision.text
                # Emit one text_delta so the UI has streaming-style copy.
                yield TextDeltaEvent(step=step, text=decision.text)
                self.session_store.append_message(
                    session,
                    AgentMessage(role="assistant", content=decision.text),
                )
                yield DoneEvent(
                    step=step,
                    reply=decision.text,
                    used_tools=list(used_tools),
                    tokens_in=decision.tokens_in,
                    tokens_out=decision.tokens_out,
                )
                return

            if decision.kind == "tool_call":
                tool = get_tool(decision.tool_name)
                if tool is None:
                    yield ErrorEvent(
                        step=step,
                        message=f"unknown tool: {decision.tool_name}",
                        code="unknown_tool",
                    )
                    return

                call_event = ToolCallEvent(
                    step=step,
                    tool_name=tool.name,
                    args=dict(decision.args),
                )
                yield call_event

                result_payload, status_label, error_msg, latency_ms = await _invoke_tool(
                    tool, tool_context, decision.args
                )
                used_tools.append(tool.name)
                session.used_tools.append(tool.name)

                if self.audit_recorder is not None:
                    try:
                        self.audit_recorder(
                            action="ai.agent.tool_call",
                            outcome=status_label,
                            details={
                                "sessionId": session.id,
                                "toolName": tool.name,
                                "backend": self.backend.name,
                                "model": self.backend.model,
                                "argsKeys": sorted(decision.args.keys()),
                                "latencyMs": latency_ms,
                                "error": error_msg,
                            },
                        )
                    except Exception:  # noqa: BLE001
                        logger.exception("agent tool audit_recorder failed")

                yield ToolResultEvent(
                    step=step,
                    call_id=call_event.call_id,
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
                        tool_call_id=call_event.call_id,
                        tool_name=tool.name,
                        tool_args=dict(decision.args),
                        tool_result=result_payload,
                    ),
                )
                continue

            yield ErrorEvent(
                step=step,
                message=f"unsupported decision kind: {decision.kind}",
                code="unsupported_decision",
            )
            return

        # Loop exit means we hit max_steps without a final.
        fallback = last_final_text or (
            "agent stopped: reached max steps without producing a final reply"
        )
        yield ErrorEvent(step=step, message=fallback, code="max_steps_exceeded")


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
    for message in session.history:
        entry: dict[str, Any] = {"role": message.role}
        if message.role == "tool":
            entry["tool_call_id"] = message.tool_call_id
            entry["tool_name"] = message.tool_name
            entry["args"] = message.tool_args or {}
            entry["result"] = message.tool_result
        else:
            entry["content"] = message.content
        snapshot.append(entry)
    return snapshot
