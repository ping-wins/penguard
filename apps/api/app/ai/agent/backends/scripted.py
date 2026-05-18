"""Deterministic backend used in tests and offline demos.

Rules are intentionally crude — keyword detection routes the user
prompt to a single tool, then the next decide() returns "final" using
the tool result as the reply body. Good enough to exercise the SSE
pipeline end-to-end without an LLM key.
"""

from __future__ import annotations

import json
from typing import Any
from uuid import uuid4

from app.ai.agent.backends.base import Final, TextDelta, ToolCall
from app.ai.agent.registry import AgentTool

_KEYWORDS: list[tuple[tuple[str, ...], str, dict[str, Any]]] = [
    (("analisa", "analise", "analyze"), "analyze_incident", {"incidentId": "demo"}),
    (("rascunho widget", "draft widget", "criar widget"), "draft_widget",
     {"provider": "fortigate", "visualType": "card", "fieldIds": ["system.cpu"]}),
    (("conten", "playbook do", "containment"), "draft_containment_playbook",
     {"ticketId": "tk-demo"}),
    (("incidente", "incident"), "list_incidents", {"limit": 10}),
    (("integraç", "integration", "integracao"), "list_integrations", {}),
    (("widget",), "get_widget_data", {"widgetId": "fortigate-system-status"}),
    (("playbook", "soar"), "list_playbook_runs", {"limit": 10}),
    (("audit",), "search_audit", {"limit": 25}),
    (("endpoint", "host"), "get_endpoint", {"endpointId": "demo-endpoint-01"}),
    (("workspace", "layout"), "get_workspace", {}),
    (("event", "evento", "siem"), "search_events", {"limit": 25}),
]


class ScriptedBackend:
    name = "scripted"
    model = "scripted-cockpit-agent"

    async def stream_decide(
        self,
        *,
        history: list[dict[str, Any]],
        tools: list[AgentTool],
        system_prompt: str,
        locale: str,
        max_output_tokens: int,
    ):
        del system_prompt, max_output_tokens

        # If the most recent entry is a tool result, the agent has the
        # data it needs — wrap it into a final reply.
        if history and history[-1].get("role") == "tool":
            tool_name = history[-1].get("tool_name", "")
            result = history[-1].get("result")
            preview = _summarize(result)
            if (locale or "").lower().startswith("en"):
                text = f"Scripted agent ran `{tool_name}`. Result preview: {preview}"
            else:
                text = (
                    f"Agente scripted executou `{tool_name}`. Prévia do resultado: {preview}"
                )
            yield TextDelta(text=text)
            yield Final(
                stop_reason="end_turn",
                tokens_in=_estimate_tokens(history),
                tokens_out=_estimate_tokens(text),
            )
            return

        prompt = _latest_user_prompt(history).lower()
        if not prompt:
            text = (
                "Scripted agent: send a question about incidents, "
                "integrations, widgets or playbooks."
            )
            yield TextDelta(text=text)
            yield Final(
                stop_reason="end_turn",
                tokens_in=_estimate_tokens(history),
                tokens_out=_estimate_tokens(text),
            )
            return

        tool_names = {tool.name for tool in tools}
        for keywords, name, args in _KEYWORDS:
            if name not in tool_names:
                continue
            if any(token in prompt for token in keywords):
                yield ToolCall(call_id=uuid4().hex, tool_name=name, args=dict(args))
                yield Final(
                    stop_reason="tool_use",
                    tokens_in=_estimate_tokens(history),
                    tokens_out=_estimate_tokens(args) + 1,
                )
                return

        # No keyword match — answer directly.
        if (locale or "").lower().startswith("en"):
            text = (
                "Scripted agent: I matched no tool for that prompt. Try "
                'asking about "incidentes", "integrations", "widgets" or '
                '"playbook runs".'
            )
        else:
            text = (
                "Agente scripted: nenhuma tool casou com o prompt. Tente "
                'perguntar sobre "incidentes", "integrações", "widgets" '
                'ou "playbook runs".'
            )
        yield TextDelta(text=text)
        yield Final(
            stop_reason="end_turn",
            tokens_in=_estimate_tokens(history),
            tokens_out=_estimate_tokens(text),
        )


def _latest_user_prompt(history: list[dict[str, Any]]) -> str:
    for entry in reversed(history):
        if entry.get("role") == "user":
            return str(entry.get("content") or "")
    return ""


def _summarize(value: Any, *, limit: int = 240) -> str:
    try:
        text = json.dumps(value, ensure_ascii=False)
    except (TypeError, ValueError):
        text = str(value)
    if len(text) > limit:
        return text[: limit - 1] + "…"
    return text


def _estimate_tokens(value: Any) -> int:
    try:
        text = json.dumps(value, ensure_ascii=False) if not isinstance(value, str) else value
    except (TypeError, ValueError):
        text = str(value)
    return max(1, len(text) // 4)
