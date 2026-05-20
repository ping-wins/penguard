from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from app.ai import ChatMessage, resolve_ai_provider
from app.ai.tools import DraftWidgetRequest, WidgetDraftValidationError, draft_widget, list_data_fields
from app.ai.tools.schemas import WidgetDraftResponse


@dataclass(frozen=True)
class CockpitAgentResult:
    reply: str
    provider: str
    model: str
    runtime: str = "direct"
    used_tools: list[str] = field(default_factory=list)
    tool_count: int = 0
    widget_drafts: list[WidgetDraftResponse] = field(default_factory=list)


class CockpitAgentRuntime:
    runtime = "direct"

    def chat(
        self,
        messages: list[ChatMessage],
        *,
        locale: str = "pt-BR",
        user_id: str | None = None,
    ) -> CockpitAgentResult:
        provider = resolve_ai_provider(user_id)
        model = getattr(provider, "model", "") or provider.name
        prompt = _latest_user_prompt(messages)

        # 1) Direct widget draft — regex match on field IDs, no LLM needed
        draft_req = _draft_widget_request_from_prompt(prompt)
        if draft_req is not None:
            try:
                response = draft_widget(draft_req)
                return CockpitAgentResult(
                    reply=_widget_draft_reply(response, locale=locale),
                    provider=provider.name,
                    model=model,
                    used_tools=["draft_widget"],
                    tool_count=1,
                    widget_drafts=[response],
                )
            except WidgetDraftValidationError as exc:
                return CockpitAgentResult(
                    reply=_widget_error_reply(exc.errors, locale=locale),
                    provider=provider.name,
                    model=model,
                    used_tools=["draft_widget"],
                    tool_count=1,
                )

        # 2) Data fields query — return field list without calling LLM
        fields_provider = _extract_fields_provider(prompt)
        if fields_provider:
            fields_result = list_data_fields(fields_provider)
            return CockpitAgentResult(
                reply=_fields_reply(fields_result, fields_provider, locale=locale),
                provider=provider.name,
                model=model,
                used_tools=["list_data_fields"],
                tool_count=1,
            )

        # 3) LLM fallback — short, widget-only context, only last exchange
        llm_messages: list[ChatMessage] = [
            {"role": "system", "content": _system_prompt(locale)},
            *messages[-2:],
        ]
        reply = provider.chat(llm_messages, locale=locale)
        return CockpitAgentResult(
            reply=reply or _no_reply(locale),
            provider=provider.name,
            model=model,
        )


def _system_prompt(locale: str) -> str:
    if locale.lower().startswith("en"):
        return (
            "You are a widget creation assistant for the Penguard dashboard. "
            "Help users create and configure dashboard widgets only. "
            "Keep replies short and direct. Do not discuss incidents, playbooks, or other topics."
        )
    return (
        "Voce e um assistente de criacao de widgets para o dashboard Penguard. "
        "Ajude o usuario a criar e configurar widgets. Respostas curtas e diretas. "
        "Nao discuta incidentes, playbooks ou outros topicos."
    )


def _extract_fields_provider(prompt: str) -> str | None:
    lowered = prompt.lower()
    if "campo" not in lowered and "field" not in lowered:
        return None
    for provider in ("fortigate", "siem_kowalski", "xdr_rico", "soar_skipper"):
        if provider in lowered:
            return provider
    return None


def _fields_reply(fields: dict[str, Any], provider: str, *, locale: str) -> str:
    items = fields.get("fields") or []
    if not items:
        if locale.lower().startswith("en"):
            return f"No fields found for provider '{provider}'."
        return f"Nenhum campo encontrado para o provider '{provider}'."
    names = ", ".join(str(f.get("id") or f.get("label") or f) for f in items[:20])
    if locale.lower().startswith("en"):
        return f"Available fields for **{provider}**: {names}."
    return f"Campos disponíveis para **{provider}**: {names}."


def _no_reply(locale: str) -> str:
    if locale.lower().startswith("en"):
        return "I can help you create widgets. Try describing a widget or mentioning field IDs."
    return "Posso ajudar a criar widgets. Descreva um widget ou mencione IDs de campos."


def _draft_widget_request_from_prompt(prompt: str) -> DraftWidgetRequest | None:
    lowered = prompt.lower()
    field_ids = _extract_field_ids(prompt)
    if not field_ids:
        return None
    if not any(marker in lowered for marker in ("widget", "card", "grafico", "chart", "visual")):
        return None
    visual_type = "card"
    if "bar" in lowered or "barra" in lowered:
        visual_type = "bar"
    elif "table" in lowered or "tabela" in lowered:
        visual_type = "table"
    elif "gauge" in lowered or "medidor" in lowered:
        visual_type = "gauge"
    provider = (
        "fortigate" if "fortigate" in lowered or field_ids[0].startswith("system.") else "soc"
    )
    return DraftWidgetRequest(
        provider=provider,
        visual_type=visual_type,
        field_ids=field_ids,
        title=None,
    )


def _extract_field_ids(prompt: str) -> list[str]:
    matches = re.findall(r"\b[a-z][a-z0-9_-]*(?:\.[a-z][a-z0-9_-]*)+\b", prompt, flags=re.I)
    seen: set[str] = set()
    field_ids: list[str] = []
    for match in matches:
        normalized = match.strip().lower()
        if normalized not in seen:
            field_ids.append(normalized)
            seen.add(normalized)
    return field_ids


def _widget_draft_reply(response: WidgetDraftResponse, *, locale: str) -> str:
    labels = ", ".join(binding.label for binding in response.draft.field_bindings)
    if locale.lower().startswith("en"):
        return (
            f"Draft created: {response.draft.visual_type} widget with {labels}. "
            "Review the preview and confirm to add it to the workspace."
        )
    return (
        f"Rascunho criado: widget {response.draft.visual_type} com {labels}. "
        "Revise o preview e confirme para adicionar na workspace."
    )


def _widget_error_reply(errors: list[str], *, locale: str) -> str:
    joined = "; ".join(errors)
    if locale.lower().startswith("en"):
        return f"Could not create widget draft: {joined}."
    return f"Nao consegui criar o rascunho: {joined}."


def _latest_user_prompt(messages: list[ChatMessage]) -> str:
    for message in reversed(messages):
        if message.get("role") == "user":
            return message.get("content", "")
    return messages[-1].get("content", "") if messages else ""


def get_cockpit_agent_runtime() -> CockpitAgentRuntime:
    return CockpitAgentRuntime()
