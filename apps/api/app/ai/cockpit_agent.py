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
    draft_containment_playbook,
    draft_widget,
    get_incident,
    list_data_fields,
    list_incidents,
    list_tool_specs,
    update_incident_status,
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
        direct_reply, used_tools, widget_drafts = _direct_tool_reply(
            messages, locale=locale, user_id=user_id
        )
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


_INCIDENT_ID_RE = re.compile(r"\binc_[a-f0-9]{8,}\b", re.I)
_TICKET_ID_RE = re.compile(r"\b(?:tk|ticket|tkt)[-_][a-z0-9]+\b", re.I)


def _direct_tool_reply(
    messages: list[ChatMessage],
    *,
    locale: str,
    user_id: str | None = None,
) -> tuple[str | None, list[str], list[WidgetDraftResponse]]:
    prompt = _latest_user_prompt(messages)
    normalized = prompt.lower()
    if "tool" in normalized or "ferramenta" in normalized:
        return _available_tools_reply(locale), [], []

    # Incident management intents — checked BEFORE widget so phrases like
    # "incidentes recentes" never get mistaken for a widget request.
    incident_reply = _try_incident_intent(prompt, normalized, locale, user_id)
    if incident_reply is not None:
        return incident_reply

    draft_request = _draft_widget_request_from_prompt(prompt)
    if draft_request is None:
        return None, [], []

    try:
        response = draft_widget(draft_request)
    except WidgetDraftValidationError as exc:
        return _widget_error_reply(exc.errors, locale=locale), ["draft_widget"], []
    return _widget_draft_reply(response, locale=locale), ["draft_widget"], [response]


def _try_incident_intent(
    prompt: str,
    normalized: str,
    locale: str,
    user_id: str | None,
) -> tuple[str | None, list[str], list[WidgetDraftResponse]] | None:
    # 1) Containment playbook draft for a ticket.
    if (
        ("playbook" in normalized or "contencao" in normalized or "containment" in normalized)
        and ("rascun" in normalized or "draft" in normalized or "esbo" in normalized
             or "criar" in normalized or "gerar" in normalized or "build" in normalized)
    ):
        ticket = _extract_ticket_id(prompt)
        if ticket:
            result = draft_containment_playbook(user_id=user_id, ticket_id=ticket)
            if result.get("error"):
                return _tool_error_reply(result["error"], locale), ["draft_containment_playbook"], []
            return (
                _containment_reply(result, ticket, locale),
                ["draft_containment_playbook"],
                [],
            )

    # 2) Incident lookup / list.
    incident_id = _extract_incident_id(prompt)
    if incident_id and any(k in normalized for k in ("detalh", "abre", "abrir", "show", "open", "detail", "ver ", "view")):
        result = get_incident(incident_id, user_id=user_id)
        if result.get("error"):
            return _tool_error_reply(result["error"], locale), ["get_incident"], []
        return _incident_detail_reply(result, locale), ["get_incident"], []

    severity = None
    for sev in ("critical", "critico", "high", "alta", "alto", "medium", "media", "medio", "low", "baixo"):
        if sev in normalized:
            severity = _normalize_severity(sev)
            break
    mentions_incident = (
        "incidente" in normalized
        or "incident" in normalized
        or "alerta" in normalized
        or "alert" in normalized
    )
    # "mostre/mostra/exiba/show/adicione" are widget-add verbs handled by
    # the frontend catalog shortcut. Only intercept textual list intents.
    wants_incident_list = mentions_incident and (
        severity is not None
        or "lista" in normalized
        or "listar" in normalized
        or "list " in normalized
        or "list:" in normalized
        or normalized.endswith("list")
        or "ultim" in normalized
        or "abertos" in normalized
        or "quantos" in normalized
        or "how many" in normalized
        or "quais" in normalized
    ) and not any(verb in normalized for verb in (
        "mostre", "mostra", "exiba", "exibir", "show", "abre", "abrir",
        "adicione", "adicionar", "add ", "abrir painel", "open panel",
    ))
    if wants_incident_list and incident_id is None:
        result = list_incidents(user_id=user_id, limit=10, severity=severity)
        if result.get("error"):
            return _tool_error_reply(result["error"], locale), ["list_incidents"], []
        return _incident_list_reply(result, locale, severity), ["list_incidents"], []

    # 3) Status change (returns DRAFT — user must confirm via UI).
    if incident_id and any(k in normalized for k in (
        "fechar", "fechado", "resolver", "resolvido", "marcar", "close", "resolve", "acknowledge", "ack"
    )):
        status = "closed"
        if "resolv" in normalized or "resolve" in normalized:
            status = "resolved"
        elif "ack" in normalized or "acknowledge" in normalized or "reconhec" in normalized:
            status = "acknowledged"
        return (
            _confirm_status_change_reply(incident_id, status, locale),
            ["update_incident_status"],
            [],
        )

    return None


def _extract_incident_id(prompt: str) -> str | None:
    match = _INCIDENT_ID_RE.search(prompt)
    return match.group(0).lower() if match else None


def _extract_ticket_id(prompt: str) -> str | None:
    match = _TICKET_ID_RE.search(prompt)
    return match.group(0).lower() if match else None


def _normalize_severity(value: str) -> str:
    mapping = {
        "critical": "critical", "critico": "critical",
        "high": "high", "alta": "high", "alto": "high",
        "medium": "medium", "media": "medium", "medio": "medium",
        "low": "low", "baixo": "low",
    }
    return mapping.get(value, value)


def _incident_list_reply(result: dict[str, Any], locale: str, severity: str | None) -> str:
    items = result.get("items") or []
    if not items:
        if locale.lower().startswith("en"):
            return "No incidents matched. Try without a severity filter or run the brute-force smoke test."
        return "Nenhum incidente encontrado. Tira o filtro de severidade ou roda o teste de brute-force."
    lines = []
    for item in items[:10]:
        iid = item.get("id", "?")
        title = item.get("title") or item.get("ruleId") or item.get("rule_id") or "—"
        sev = item.get("severity", "?")
        status = item.get("status", "?")
        lines.append(f"• `{iid}` — {title} ({sev}, {status})")
    body = "\n".join(lines)
    header = (
        f"Found {len(items)} incident(s){' filtered by ' + severity if severity else ''}:"
        if locale.lower().startswith("en")
        else f"Encontrei {len(items)} incidente(s){' filtrados por ' + severity if severity else ''}:"
    )
    hint = (
        "\n\nAsk for one with `inc_...` id to see full detail."
        if locale.lower().startswith("en")
        else "\n\nPede um pelo id `inc_...` pra ver detalhes completos."
    )
    return f"{header}\n{body}{hint}"


def _incident_detail_reply(item: dict[str, Any], locale: str) -> str:
    iid = item.get("id", "?")
    title = item.get("title") or item.get("ruleId") or "—"
    sev = item.get("severity", "?")
    status = item.get("status", "?")
    rule = item.get("ruleId") or item.get("rule_id") or "—"
    created = item.get("createdAt") or item.get("created_at") or "?"
    entities = item.get("entities") or {}
    src = entities.get("sourceIp") or entities.get("source_ip") or "—"
    if locale.lower().startswith("en"):
        return (
            f"**{iid}** — {title}\n"
            f"Severity: {sev} | Status: {status} | Rule: `{rule}`\n"
            f"Source IP: `{src}` | Created: {created}\n\n"
            f"Reply with `containment for tk_<ticketId>` to draft a SOAR playbook, "
            f"or `close {iid}` / `resolve {iid}` to draft a status change."
        )
    return (
        f"**{iid}** — {title}\n"
        f"Severidade: {sev} | Status: {status} | Regra: `{rule}`\n"
        f"IP origem: `{src}` | Criado: {created}\n\n"
        f"Responda `containment tk_<ticketId>` pra esboçar playbook SOAR, "
        f"ou `fechar {iid}` / `resolver {iid}` pra preparar mudança de status."
    )


def _containment_reply(playbook: dict[str, Any], ticket_id: str, locale: str) -> str:
    name = playbook.get("name") or playbook.get("title") or "containment playbook"
    steps = playbook.get("nodes") or playbook.get("steps") or []
    if locale.lower().startswith("en"):
        return (
            f"Drafted **{name}** for ticket `{ticket_id}` — {len(steps)} step(s). "
            "Open the SOAR drawer to review and apply."
        )
    return (
        f"Rascunhei **{name}** para ticket `{ticket_id}` — {len(steps)} passo(s). "
        "Abra o painel SOAR pra revisar e aplicar."
    )


def _confirm_status_change_reply(incident_id: str, status: str, locale: str) -> str:
    if locale.lower().startswith("en"):
        return (
            f"Draft: change `{incident_id}` status to **{status}**. "
            "Confirm by opening the incident in the SOC pane (status changes still need a human click)."
        )
    return (
        f"Rascunho: mudar status de `{incident_id}` para **{status}**. "
        "Confirme abrindo o incidente no painel SOC (mudança de status precisa de clique humano)."
    )


def _tool_error_reply(message: str, locale: str) -> str:
    if locale.lower().startswith("en"):
        return f"Tool call failed: {message}"
    return f"Falha na tool: {message}"


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
