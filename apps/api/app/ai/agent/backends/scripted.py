"""Deterministic backend used in tests and offline demos.

Rules are intentionally crude — keyword detection routes the user
prompt to a single tool, then the next decide() returns "final" using
the tool result as the reply body. Good enough to exercise the SSE
pipeline end-to-end without an LLM key.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from typing import Any

from app.ai.agent.backends.base import AgentBackend, BackendDecision
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

    def decide(
        self,
        *,
        history: list[dict[str, Any]],
        tools: Iterable[AgentTool],
        locale: str,
    ) -> BackendDecision:
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
            return BackendDecision(kind="final", text=text)

        prompt = _latest_user_prompt(history).lower()
        if not prompt:
            return BackendDecision(
                kind="final",
                text=(
                    "Scripted agent: send a question about incidents, "
                    "integrations, widgets or playbooks."
                ),
            )

        tool_names = {tool.name for tool in tools}
        for keywords, name, args in _KEYWORDS:
            if name not in tool_names:
                continue
            if any(token in prompt for token in keywords):
                return BackendDecision(kind="tool_call", tool_name=name, args=dict(args))

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
        return BackendDecision(kind="final", text=text)


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
