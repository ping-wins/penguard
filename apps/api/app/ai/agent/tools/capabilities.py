"""Capability tools — analyze, draft widget, draft playbook.

Mirrors what the single-turn chat already does so chat + agent are
feature-equivalent. Persistence is deliberately omitted: drafts are
returned to the agent for review; the user (or a follow-up write tool
in PR4) actually saves them.
"""

from __future__ import annotations

from typing import Any

from app.ai.agent.registry import AgentTool, ToolContext, register_tool
from app.ai.agent.settings import get_ai_agent_settings_store, normalize_provider
from app.ai.provider import (
    AnthropicAIProvider,
    GeminiAIProvider,
    IncidentContext,
    OpenAICompatibleAIProvider,
)
from app.ai.tools import (
    DraftWidgetRequest,
    WidgetDraftValidationError,
    draft_widget,
)


def _incident_context(payload: dict[str, Any], *, incident_id: str) -> IncidentContext:
    entities = payload.get("entities") if isinstance(payload.get("entities"), dict) else {}
    timeline_raw = payload.get("timeline") if isinstance(payload.get("timeline"), list) else []
    timeline = [item for item in timeline_raw if isinstance(item, dict)]
    return IncidentContext(
        incident_id=incident_id,
        title=str(payload.get("title") or ""),
        severity=str(payload.get("severity") or "medium"),
        triage_level=str(payload.get("triageLevel") or payload.get("triage_level") or ""),
        ticket_status=str(payload.get("ticketStatus") or payload.get("ticket_status") or ""),
        summary=str(payload.get("summary") or ""),
        entities=entities or {},
        timeline=timeline,
        rule_id=payload.get("ruleId") or payload.get("rule_id"),
        event_ids=list(payload.get("eventIds") or payload.get("event_ids") or []),
    )


def _enterprise_ai_provider() -> (
    AnthropicAIProvider | GeminiAIProvider | OpenAICompatibleAIProvider
):
    settings = get_ai_agent_settings_store().get()
    if settings is None or not settings.configured:
        raise RuntimeError("SOC Assistant provider is not configured")

    provider = normalize_provider(settings.provider)
    if provider == "anthropic":
        return AnthropicAIProvider(api_key=settings.api_key, model=settings.model)
    if provider == "gemini":
        return GeminiAIProvider(api_key=settings.api_key, model=settings.model)
    if provider == "openai":
        return OpenAICompatibleAIProvider(api_key=settings.api_key, model=settings.model)
    raise RuntimeError("SOC Assistant provider is not configured")


async def _analyze_incident(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    incident_id = str(args.get("incidentId") or args.get("incident_id") or "").strip()
    if not incident_id:
        return {"error": "incidentId is required"}
    client = ctx.siem_client
    if client is None:
        return {"error": "siem client not configured"}
    try:
        incident_payload = client.request("GET", f"/incidents/{incident_id}")
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)[:200], "incidentId": incident_id}
    if not isinstance(incident_payload, dict):
        return {"error": "siem returned non-dict incident", "incidentId": incident_id}

    try:
        provider = _enterprise_ai_provider()
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)[:200], "incidentId": incident_id}
    context = _incident_context(incident_payload, incident_id=incident_id)
    try:
        analysis = provider.analyze_incident(context, locale=ctx.locale)
    except Exception as exc:  # noqa: BLE001
        return {"error": f"provider failed: {exc}"[:200], "incidentId": incident_id}
    return {
        "incidentId": analysis.incident_id,
        "headline": analysis.headline,
        "summary": analysis.summary,
        "riskScore": analysis.risk_score,
        "suggestedTriage": analysis.suggested_triage,
        "suggestedTicketStatus": analysis.suggested_ticket_status,
        "iocs": analysis.indicators_of_compromise,
        "nextSteps": analysis.next_steps,
        "references": analysis.references,
        "cvssScore": analysis.cvss_score,
        "cvssSeverity": analysis.cvss_severity,
        "cvssVector": analysis.cvss_vector,
        "mitre": [
            {"id": t.id, "name": t.name, "url": t.url}
            for t in analysis.mitre_techniques
        ],
    }


async def _draft_widget(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    provider = str(args.get("provider") or "").strip()
    visual_type = str(args.get("visualType") or args.get("visual_type") or "").strip()
    field_ids = args.get("fieldIds") or args.get("field_ids") or []
    if not provider or not visual_type or not isinstance(field_ids, list) or not field_ids:
        return {"error": "provider, visualType and fieldIds are required"}
    try:
        response = draft_widget(
            DraftWidgetRequest(
                provider=provider,
                visual_type=visual_type,
                field_ids=[str(field_id) for field_id in field_ids],
                integration_id=args.get("integrationId") or args.get("integration_id"),
                title=args.get("title"),
            )
        )
    except WidgetDraftValidationError as exc:
        return {"error": "validation failed", "errors": exc.errors}
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)[:200]}
    return response.model_dump(by_alias=True)


async def _draft_playbook(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    ticket_id = str(args.get("ticketId") or args.get("ticket_id") or "").strip()
    if not ticket_id:
        return {"error": "ticketId is required"}
    siem = ctx.siem_client
    if siem is None:
        return {"error": "siem client not configured"}
    try:
        ticket = siem.request("GET", f"/tickets/{ticket_id}")
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)[:200], "ticketId": ticket_id}
    incident_id = ticket.get("incidentId") if isinstance(ticket, dict) else None
    if not incident_id:
        return {"error": "ticket has no incidentId", "ticketId": ticket_id}
    try:
        incident_payload = siem.request("GET", f"/incidents/{incident_id}")
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)[:200], "ticketId": ticket_id}
    try:
        provider = _enterprise_ai_provider()
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)[:200], "ticketId": ticket_id}
    context = _incident_context(incident_payload, incident_id=str(incident_id))
    try:
        suggestion = provider.suggest_containment(context, locale=ctx.locale)
    except Exception as exc:  # noqa: BLE001
        return {"error": f"provider failed: {exc}"[:200], "ticketId": ticket_id}
    return {
        "ticketId": ticket_id,
        "incidentId": str(incident_id),
        "summary": suggestion.summary,
        "steps": [
            {
                "title": step.title,
                "description": step.description,
                "playbookNodeType": step.playbook_node_type,
                "severity": step.severity,
                "requiresApproval": step.requires_approval,
            }
            for step in suggestion.steps
        ],
    }


register_tool(
    AgentTool(
        name="analyze_incident",
        description=(
            "Run the configured AI provider against an incident. Returns "
            "headline, CVSS, IoCs, next steps and MITRE techniques. Read-only."
        ),
        input_schema={
            "type": "object",
            "required": ["incidentId"],
            "properties": {"incidentId": {"type": "string"}},
            "additionalProperties": False,
        },
        impl=_analyze_incident,
        timeout_seconds=30,
    )
)


register_tool(
    AgentTool(
        name="draft_widget",
        description=(
            "Build a draft cockpit widget from provider fields. Returns a "
            "preview payload — does not persist."
        ),
        input_schema={
            "type": "object",
            "required": ["provider", "visualType", "fieldIds"],
            "properties": {
                "provider": {"type": "string"},
                "visualType": {"type": "string"},
                "fieldIds": {"type": "array", "items": {"type": "string"}},
                "integrationId": {"type": "string"},
                "title": {"type": "string"},
            },
            "additionalProperties": False,
        },
        impl=_draft_widget,
        category="draft",
    )
)


register_tool(
    AgentTool(
        name="draft_containment_playbook",
        description=(
            "Generate a SOAR-style containment plan for a ticket using the "
            "configured AI provider. Read-only — steps are drafts requiring "
            "operator approval to execute."
        ),
        input_schema={
            "type": "object",
            "required": ["ticketId"],
            "properties": {"ticketId": {"type": "string"}},
            "additionalProperties": False,
        },
        impl=_draft_playbook,
        category="draft",
        required_permissions=frozenset({"playbooks.manage"}),
        timeout_seconds=30,
    )
)
