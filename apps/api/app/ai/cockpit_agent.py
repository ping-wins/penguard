from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from pydantic_ai import Agent, ModelMessage, ModelResponse, TextPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from app.ai import ChatMessage, resolve_ai_provider
from app.ai.tools import (
    DraftWidgetRequest,
    WidgetDraftValidationError,
    draft_widget,
    list_data_fields,
    list_tool_specs,
)
from app.ai.tools.schemas import WidgetDraftResponse
from app.core.config import get_settings


@dataclass(frozen=True)
class CockpitAgentResult:
    reply: str
    provider: str
    model: str
    runtime: str = "pydantic_ai"
    used_tools: list[str] = field(default_factory=list)
    tool_count: int = 0
    widget_drafts: list[WidgetDraftResponse] = field(default_factory=list)


class CockpitAgentRuntime:
    runtime = "pydantic_ai"

    def chat(
        self,
        messages: list[ChatMessage],
        *,
        locale: str = "pt-BR",
        user_id: str | None = None,
    ) -> CockpitAgentResult:
        settings = get_settings()
        direct_reply, used_tools, widget_drafts = _direct_tool_reply(messages, locale=locale)
        provider = resolve_ai_provider(user_id)

        def model_function(
            model_messages: list[ModelMessage],
            info: AgentInfo,
        ) -> ModelResponse:
            if direct_reply is not None:
                content = direct_reply
            else:
                content = provider.chat(messages, locale=locale)
            return ModelResponse(
                parts=[TextPart(content=content)],
                model_name=getattr(provider, "model", "") or settings.ai_model or f"{provider.name}-cockpit",
                provider_name=f"pydantic_ai.{provider.name}",
                metadata={"toolCount": len(info.function_tools)},
            )

        agent = _build_agent(
            model_function=model_function,
            model_name=getattr(provider, "model", "") or settings.ai_model or f"{provider.name}-cockpit",
            locale=locale,
        )
        result = agent.run_sync(_latest_user_prompt(messages))
        return CockpitAgentResult(
            reply=str(result.output),
            provider=f"pydantic_ai.{provider.name}",
            model=getattr(provider, "model", "") or settings.ai_model or f"{provider.name}-cockpit",
            used_tools=used_tools,
            tool_count=len(list_tool_specs()),
            widget_drafts=widget_drafts,
        )


def _build_agent(
    *,
    model_function: Any,
    model_name: str,
    locale: str,
) -> Agent[None, str]:
    agent = Agent(
        FunctionModel(model_function, model_name=model_name),
        instructions=_system_prompt(locale),
    )

    @agent.tool_plain(
        name="list_data_fields",
        description="List bindable provider fields available to FortiDashboard widgets.",
        timeout=2,
    )
    def list_data_fields_tool(provider: str) -> dict[str, Any]:
        return list_data_fields(provider)

    @agent.tool_plain(
        name="draft_widget",
        description="Create a draft custom widget from provider fields. Does not persist.",
        requires_approval=True,
        timeout=3,
    )
    def draft_widget_tool(
        provider: str,
        visual_type: str,
        field_ids: list[str],
        integration_id: str | None = None,
        title: str | None = None,
    ) -> dict[str, Any]:
        response = draft_widget(
            DraftWidgetRequest(
                provider=provider,
                visual_type=visual_type,
                field_ids=field_ids,
                integration_id=integration_id,
                title=title,
            )
        )
        return response.model_dump(by_alias=True)

    return agent


def _system_prompt(locale: str) -> str:
    if locale.lower().startswith("en"):
        return (
            "You are the FortiDashboard cockpit agent. Use safe internal tools "
            "for dashboard data, widget drafts and SOC context. Never persist "
            "a widget or playbook without explicit user confirmation."
        )
    return (
        "Voce e o agente de cockpit do FortiDashboard. Use tools internas "
        "seguras para dados do dashboard, rascunhos de widgets e contexto SOC. "
        "Nunca persista um widget ou playbook sem confirmacao explicita do usuario."
    )


def _direct_tool_reply(
    messages: list[ChatMessage],
    *,
    locale: str,
) -> tuple[str | None, list[str], list[WidgetDraftResponse]]:
    prompt = _latest_user_prompt(messages)
    normalized = prompt.lower()
    if "tool" in normalized or "ferramenta" in normalized:
        return _available_tools_reply(locale), [], []

    draft_request = _draft_widget_request_from_prompt(prompt)
    if draft_request is None:
        return None, [], []

    try:
        response = draft_widget(draft_request)
    except WidgetDraftValidationError as exc:
        return _widget_error_reply(exc.errors, locale=locale), ["draft_widget"], []
    return _widget_draft_reply(response, locale=locale), ["draft_widget"], [response]


def _available_tools_reply(locale: str) -> str:
    tool_names = ", ".join(spec.name for spec in list_tool_specs())
    if locale.lower().startswith("en"):
        return (
            f"I can use these safe FortiDashboard tools: {tool_names}. "
            "Anything that changes a workspace or playbook stays as a draft until you confirm it."
        )
    return (
        f"Posso usar estas tools seguras do FortiDashboard: {tool_names}. "
        "Qualquer mudanca em workspace ou playbook fica como rascunho ate voce confirmar."
    )


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
        "fortigate"
        if "fortigate" in lowered or field_ids[0].startswith("system.")
        else "soc"
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
            f"draft_widget created a {response.draft.visual_type} draft for {labels}. "
            "Review the preview and confirm before adding it to the workspace."
        )
    return (
        f"draft_widget criou um rascunho {response.draft.visual_type} para {labels}. "
        "Revise o preview e confirme antes de adicionar na workspace."
    )


def _widget_error_reply(errors: list[str], *, locale: str) -> str:
    joined = "; ".join(errors)
    if locale.lower().startswith("en"):
        return f"I could not draft the widget: {joined}."
    return f"Nao consegui criar o rascunho do widget: {joined}."


def _latest_user_prompt(messages: list[ChatMessage]) -> str:
    for message in reversed(messages):
        if message.get("role") == "user":
            return message.get("content", "")
    return messages[-1].get("content", "") if messages else ""


def get_cockpit_agent_runtime() -> CockpitAgentRuntime:
    return CockpitAgentRuntime()
