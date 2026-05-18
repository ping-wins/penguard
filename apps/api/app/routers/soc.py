from functools import lru_cache
from secrets import token_urlsafe
from typing import Annotated, Any, Literal, Protocol

from fastapi import APIRouter, Body, Depends, Header, HTTPException, Query, Request, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.ai import (
    AIConfigurationError,
    ContainmentSuggestion,
    IncidentAnalysis,
    IncidentContext,
    get_ai_provider,
)
from app.auth.csrf_dependency import require_csrf
from app.auth.dependencies import (
    get_auth_audit_store,
    get_current_api_user,
    require_admin_user,
)
from app.auth.token_cipher import TokenCipher
from app.core.config import get_settings
from app.db.session import SessionLocal
from app.integrations.fortigate.policy_models import (
    FortiGatePolicyApplyRequest,
    FortiGatePolicyIntent,
    FortiGatePolicyReviewRequest,
)
from app.integrations.fortigate.policy_workflow import (
    apply_policy_review_for_user,
    create_policy_review_for_user,
)
from app.integrations.fortigate.service import (
    FortiGateIntegrationService,
    MockFortiGateIntegrationService,
)
from app.integrations.fortigate.store import SqlAlchemyFortiGateIntegrationStore
from app.playbooks.effects import execute_playbook_effects
from app.playbooks.webhook_destinations import (
    InMemoryPlaybookWebhookDestinationStore,
    PlaybookWebhookDestinationService,
    SqlAlchemyPlaybookWebhookDestinationStore,
    WebhookSender,
)
from app.soc.client import SocServiceClient
from app.soc.triage import build_triage_context

router = APIRouter(tags=["soc"])


class SocClient(Protocol):
    def request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        pass_through_statuses: set[int] | None = None,
    ) -> dict[str, Any]:
        pass


class AuditStore(Protocol):
    def record(
        self,
        *,
        action: str,
        outcome: str,
        email: str | None = None,
        user_id: str | None = None,
        client_ip: str | None = None,
        user_agent: str | None = None,
        details: dict | None = None,
    ) -> None:
        pass


class PlaybookRunPolicyReviewRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    integration_id: str = Field(alias="integrationId")
    scope: Literal["source_only", "source_destination", "source_destination_service"]
    source_ip: str = Field(alias="sourceIp")
    destination_ip: str | None = Field(default=None, alias="destinationIp")
    service: str | None = None
    source_interface: str = Field(alias="sourceInterface")
    destination_interface: str = Field(alias="destinationInterface")
    duration_minutes: int = Field(default=30, alias="durationMinutes", ge=5, le=1440)


class PlaybookRunPolicyApplyRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    integration_id: str = Field(alias="integrationId")
    request_id: str = Field(alias="requestId")
    review_hash: str = Field(alias="reviewHash")


class PlaybookWebhookDestinationCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    kind: Literal["discord", "generic"] = "discord"
    url: str = Field(min_length=1, max_length=2048)


class PlaybookWebhookDestinationTestRequest(BaseModel):
    content: str = Field(default="FortiDashboard test", max_length=1800)


@lru_cache
def get_siem_client() -> SocServiceClient:
    settings = get_settings()
    return SocServiceClient(
        base_url=settings.siem_kowalski_url,
        service_name="siem_kowalski",
        timeout_seconds=settings.internal_service_timeout_seconds,
    )


@lru_cache
def get_soar_client() -> SocServiceClient:
    settings = get_settings()
    return SocServiceClient(
        base_url=settings.soar_skipper_url,
        service_name="soar_skipper",
        timeout_seconds=settings.internal_service_timeout_seconds,
    )


@lru_cache
def get_xdr_client() -> SocServiceClient:
    settings = get_settings()
    return SocServiceClient(
        base_url=settings.xdr_rico_url,
        service_name="xdr_rico",
        timeout_seconds=settings.internal_service_timeout_seconds,
    )


@lru_cache
def get_fortigate_policy_service() -> FortiGateIntegrationService | MockFortiGateIntegrationService:
    settings = get_settings()
    if settings.mock_mode:
        return MockFortiGateIntegrationService()
    return FortiGateIntegrationService(
        store=SqlAlchemyFortiGateIntegrationStore(
            database_url=settings.database_url,
            secret_cipher=TokenCipher.from_secret(
                settings.token_encryption_key or settings.secret_key
            ),
        )
    )


def create_playbook_webhook_destination_service(
    *,
    sender: WebhookSender | None = None,
) -> PlaybookWebhookDestinationService:
    settings = get_settings()
    if settings.mock_mode:
        store = InMemoryPlaybookWebhookDestinationStore()
    else:
        store = SqlAlchemyPlaybookWebhookDestinationStore(
            database_url=settings.database_url,
            token_cipher=TokenCipher.from_secret(
                settings.token_encryption_key or settings.secret_key
            ),
        )
    return PlaybookWebhookDestinationService(store=store, sender=sender)


@lru_cache
def get_playbook_webhook_destination_service() -> PlaybookWebhookDestinationService:
    return create_playbook_webhook_destination_service()


def get_policy_db():
    with SessionLocal() as db:
        yield db


def _build_incident_context(incident: dict[str, Any]) -> IncidentContext:
    return IncidentContext(
        incident_id=str(incident.get("id") or ""),
        title=str(incident.get("title") or "Untitled incident"),
        severity=str(incident.get("severity") or "informational"),
        triage_level=str(incident.get("triageLevel") or "T3"),
        ticket_status=str(incident.get("ticketStatus") or "new"),
        summary=str(incident.get("summary") or ""),
        entities=incident.get("entities") or {},
        timeline=[item for item in (incident.get("timeline") or []) if isinstance(item, dict)],
        rule_id=incident.get("ruleId"),
        event_ids=list(incident.get("eventIds") or []),
    )


def _analysis_to_dict(
    analysis: IncidentAnalysis, *, analysis_id: str, provider_name: str
) -> dict[str, Any]:
    return {
        "id": analysis_id,
        "incidentId": analysis.incident_id,
        "provider": provider_name,
        "headline": analysis.headline,
        "summary": analysis.summary,
        "riskScore": analysis.risk_score,
        "suggestedTriage": analysis.suggested_triage,
        "suggestedTicketStatus": analysis.suggested_ticket_status,
        "indicatorsOfCompromise": analysis.indicators_of_compromise,
        "nextSteps": analysis.next_steps,
        "references": analysis.references,
        "cvss": {
            "score": analysis.cvss_score,
            "severity": analysis.cvss_severity,
            "vector": analysis.cvss_vector,
            "justification": analysis.cvss_justification,
        },
        "mitreTechniques": [
            {"id": t.id, "name": t.name, "url": t.url} for t in analysis.mitre_techniques
        ],
    }


_SOAR_NODE_MAPPING = {
    "firewall.block_ip": ("fortigate.temporary_block", True),
    "fortigate.block_ip": ("fortigate.temporary_block", True),
    "fortigate.recommend_block": ("fortigate.temporary_block", True),
    "fortigate.temporary_block": ("fortigate.temporary_block", True),
    "notify.slack": ("notify.webhook", False),
    "notify.email": ("notify.webhook", False),
    "notify.teams": ("notify.webhook", False),
    "notify.webhook": ("notify.webhook", False),
    "endpoint.collect_telemetry": ("enrich.ip", False),
    "endpoint.isolate": ("approval.required", True),
    "enrich.ip": ("enrich.ip", False),
    "enrich.hostname": ("enrich.ip", False),
    "case.note": ("case.note", False),
    "case.escalate": ("case.note", False),
    "approval.required": ("approval.required", False),
}


def _map_ai_step_to_soar_node(playbook_node_type: str) -> tuple[str, bool]:
    """Map an AI-emitted node type to a soar_skipper-compatible node and
    sensitive flag. Unknown types fall back to `case.note` so the draft is
    always inert.
    """
    return _SOAR_NODE_MAPPING.get(playbook_node_type, ("case.note", False))


def _containment_to_dict(
    suggestion: ContainmentSuggestion, *, provider_name: str
) -> dict[str, Any]:
    return {
        "incidentId": suggestion.incident_id,
        "provider": provider_name,
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
        "playbookDraftId": suggestion.playbook_draft_id,
    }


def _incident_value(incident: dict[str, Any], key: str) -> str:
    attributes = incident.get("attributes") if isinstance(incident.get("attributes"), dict) else {}
    entities = incident.get("entities") if isinstance(incident.get("entities"), dict) else {}
    for payload in (attributes, entities):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, int | float) and not isinstance(value, bool):
            return str(value)
    return ""


def _append_node(
    nodes: list[dict[str, Any]],
    edges: list[dict[str, str]],
    previous_id: str,
    node: dict[str, Any],
) -> str:
    nodes.append(node)
    edges.append({"from": previous_id, "to": str(node["id"])})
    return str(node["id"])


def _mitre_technique_summary(triage_context) -> str:
    techniques = ", ".join(
        mapping.technique_id for mapping in triage_context.mitre_mappings
    )
    return techniques or "no MITRE mapping"


def _recommended_template_playbook(
    incident: dict[str, Any],
    template_id: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    triage_context = build_triage_context(incident)
    template = next(
        (
            item
            for item in triage_context.playbook_templates
            if item.template_id == template_id
        ),
        None,
    )
    if template is None:
        raise HTTPException(status_code=404, detail="Playbook recommendation is not eligible")

    source_ip = _incident_value(incident, "sourceIp")
    destination_ip = _incident_value(incident, "destinationIp")
    integration_id = _incident_value(incident, "integrationId")
    title = str(incident.get("title") or triage_context.attack_type or "incident")[:80]
    playbook_id = f"pb_tpl_{token_urlsafe(6)}"
    nodes: list[dict[str, Any]] = [{"id": "trigger", "type": "trigger.incident_created"}]
    edges: list[dict[str, str]] = []
    steps: list[dict[str, Any]] = []
    previous_id = "trigger"

    previous_id = _append_node(
        nodes,
        edges,
        previous_id,
        {
            "id": "triage_note",
            "type": "case.note",
            "config": {
                "template": (
                    f"{triage_context.alert_family} mapped to "
                    f"{_mitre_technique_summary(triage_context)}."
                )
            },
        },
    )
    steps.append(
        {
            "title": "Record triage context",
            "description": template.reason,
            "playbookNodeType": "case.note",
            "severity": "low",
            "requiresApproval": False,
        }
    )

    if source_ip:
        previous_id = _append_node(
            nodes,
            edges,
            previous_id,
            {
                "id": "enrich_source_ip",
                "type": "enrich.ip",
                "config": {"field": "entities.sourceIp", "value": source_ip},
            },
        )
        steps.append(
            {
                "title": "Enrich source IP",
                "description": f"Collect context for source IP {source_ip}.",
                "playbookNodeType": "enrich.ip",
                "severity": "low",
                "requiresApproval": False,
            }
        )

    needs_fortigate_block = template_id in {
        "pb_network_scan_triage",
        "pb_fortigate_temp_block",
        "pb_auth_bruteforce_triage",
    } and bool(source_ip and integration_id)
    if needs_fortigate_block:
        previous_id = _append_node(
            nodes,
            edges,
            previous_id,
            {"id": "approval", "type": "approval.required", "config": {"role": "admin"}},
        )
        scope = "source_destination" if destination_ip else "source_only"
        block_config: dict[str, Any] = {
            "scope": scope,
            "durationMinutes": 30,
            "sourceField": "entities.sourceIp",
            "integrationId": integration_id,
            "sourceIp": source_ip,
        }
        if destination_ip:
            block_config["destinationField"] = "entities.destinationIp"
            block_config["destinationIp"] = destination_ip
        previous_id = _append_node(
            nodes,
            edges,
            previous_id,
            {
                "id": "temporary_block",
                "type": "fortigate.temporary_block",
                "config": block_config,
            },
        )
        steps.append(
            {
                "title": "Prepare FortiGate temporary block",
                "description": "Create a governed FortiDashboard policy review after approval.",
                "playbookNodeType": "fortigate.temporary_block",
                "severity": "high",
                "requiresApproval": True,
            }
        )

    if template_id == "pb_auth_bruteforce_triage":
        username = _incident_value(incident, "username")
        previous_id = _append_node(
            nodes,
            edges,
            previous_id,
            {
                "id": "identity_review_note",
                "type": "case.note",
                "config": {"template": f"Review account activity for {username or 'the user'}."},
            },
        )
        steps.append(
            {
                "title": "Review account activity",
                "description": (
                    "Identity lockout remains unavailable until an identity "
                    "connector exists."
                ),
                "playbookNodeType": "case.note",
                "severity": "medium",
                "requiresApproval": False,
            }
        )

    _append_node(
        nodes,
        edges,
        previous_id,
        {
            "id": "final_note",
            "type": "case.note",
            "config": {"template": "Append outcome and approval status to the ticket timeline."},
        },
    )
    steps.append(
        {
            "title": "Record response outcome",
            "description": "Append the execution outcome to the ticket.",
            "playbookNodeType": "case.note",
            "severity": "low",
            "requiresApproval": False,
        }
    )

    playbook = {
        "id": playbook_id,
        "name": f"{template.label} — {title}",
        "enabled": False,
        "nodes": nodes,
        "edges": edges,
    }
    suggestion = {
        "incidentId": triage_context.incident_id,
        "provider": "deterministic",
        "summary": template.reason,
        "steps": steps,
        "playbookDraftId": playbook_id,
    }
    return playbook, suggestion


def _request_locale(request: Request) -> str:
    """Resolve the locale to use for AI prompts. Trusts the
    `X-FortiDashboard-Locale` header if present, otherwise falls back to a
    light `Accept-Language` parse, and finally defaults to `pt-BR`.
    """
    explicit = request.headers.get("x-fortidashboard-locale")
    if explicit and explicit.lower().startswith(("pt", "en")):
        return "en-US" if explicit.lower().startswith("en") else "pt-BR"
    accept = request.headers.get("accept-language", "")
    if accept.lower().startswith("en"):
        return "en-US"
    return "pt-BR"


def _configured_ai_provider_or_502():
    try:
        return get_ai_provider()
    except AIConfigurationError as exc:
        raise HTTPException(status_code=502, detail=f"AI provider not configured: {exc}") from exc


@router.post("/soc/incidents/{incident_id}/analyze")
def analyze_incident(
    incident_id: str,
    request: Request,
    client: Annotated[SocClient, Depends(get_siem_client)],
    current_user: Annotated[dict, Depends(get_current_api_user)],
    audit_store: Annotated[AuditStore, Depends(get_auth_audit_store)],
    _csrf: Annotated[None, Depends(require_csrf)],
) -> dict:
    incident = client.request("GET", f"/incidents/{incident_id}")
    context = _build_incident_context(incident)
    provider = _configured_ai_provider_or_502()
    locale = _request_locale(request)
    try:
        analysis = provider.analyze_incident(context, locale=locale)
    except Exception as exc:  # noqa: BLE001
        _audit(
            audit_store,
            request=request,
            current_user=current_user,
            action="soc.incident.analyzed",
            outcome="failure",
            details={
                "incidentId": incident_id,
                "provider": provider.name,
                "error": str(exc)[:200],
            },
        )
        raise HTTPException(status_code=502, detail=f"AI provider failed: {exc}") from exc

    analysis_id = f"aian_{token_urlsafe(9)}"
    response = _analysis_to_dict(
        analysis,
        analysis_id=analysis_id,
        provider_name=provider.name,
    )
    # Persist the analysis_id back on the ticket so the cockpit can deep link.
    try:
        client.request(
            "PATCH",
            f"/incidents/{incident_id}/triage",
            json={"aiAnalysisId": analysis_id, "note": f"AI analysis attached ({analysis_id})."},
        )
    except Exception as exc:  # noqa: BLE001
        # Persistence is best-effort; the analyst still sees the analysis.
        _audit(
            audit_store,
            request=request,
            current_user=current_user,
            action="soc.incident.analyzed",
            outcome="partial",
            details={
                "incidentId": incident_id,
                "analysisId": analysis_id,
                "provider": provider.name,
                "warning": f"Failed to persist analysisId: {exc}"[:200],
            },
        )
        return response
    _audit(
        audit_store,
        request=request,
        current_user=current_user,
        action="soc.incident.analyzed",
        details={
            "incidentId": incident_id,
            "analysisId": analysis_id,
            "provider": provider.name,
            "riskScore": analysis.risk_score,
            "suggestedTriage": analysis.suggested_triage,
        },
    )
    return response


@router.post("/soc/tickets/{ticket_id}/draft-playbook", status_code=status.HTTP_201_CREATED)
def draft_containment_playbook(
    ticket_id: str,
    request: Request,
    siem_client: Annotated[SocClient, Depends(get_siem_client)],
    soar_client: Annotated[SocClient, Depends(get_soar_client)],
    current_user: Annotated[dict, Depends(get_current_api_user)],
    audit_store: Annotated[AuditStore, Depends(get_auth_audit_store)],
    _csrf: Annotated[None, Depends(require_csrf)],
) -> dict:
    """Build a soar_skipper-compatible draft playbook from the AI containment
    suggestion. The playbook is always disabled and always dry-run; the
    cockpit must call apply-containment to actually execute it.
    """
    incident = siem_client.request("GET", f"/incidents/{ticket_id}")
    context = _build_incident_context(incident)
    provider = _configured_ai_provider_or_502()
    locale = _request_locale(request)
    try:
        suggestion = provider.suggest_containment(context, locale=locale)
    except Exception as exc:  # noqa: BLE001
        _audit(
            audit_store,
            request=request,
            current_user=current_user,
            action="soc.ticket.playbook_drafted",
            outcome="failure",
            details={
                "ticketId": ticket_id,
                "provider": provider.name,
                "error": str(exc)[:200],
            },
        )
        raise HTTPException(status_code=502, detail=f"AI provider failed: {exc}") from exc

    nodes: list[dict[str, Any]] = [{"id": "trigger", "type": "trigger.incident_created"}]
    edges: list[dict[str, str]] = []
    previous_id = "trigger"
    sensitive_present = False
    for index, step in enumerate(suggestion.steps):
        node_type, default_sensitive = _map_ai_step_to_soar_node(step.playbook_node_type)
        node_id = f"step_{index + 1}"
        node_config: dict[str, Any] = {"title": step.title, "description": step.description}
        if step.requires_approval or default_sensitive:
            sensitive_present = True
            approval_id = f"approval_{index + 1}"
            nodes.append(
                {"id": approval_id, "type": "approval.required", "config": {"role": "admin"}}
            )
            edges.append({"from": previous_id, "to": approval_id})
            previous_id = approval_id
        nodes.append({"id": node_id, "type": node_type, "config": node_config})
        edges.append({"from": previous_id, "to": node_id})
        previous_id = node_id

    playbook_id = f"pb_ai_{token_urlsafe(6)}"
    playbook_payload = {
        "id": playbook_id,
        "name": f"AI containment draft — {context.title[:80]}",
        "enabled": False,
        "nodes": nodes,
        "edges": edges,
    }

    try:
        created_playbook = soar_client.request("POST", "/playbooks", json=playbook_payload)
    except Exception as exc:  # noqa: BLE001
        _audit(
            audit_store,
            request=request,
            current_user=current_user,
            action="soc.ticket.playbook_drafted",
            outcome="failure",
            details={
                "ticketId": ticket_id,
                "stage": "create_playbook",
                "error": str(exc)[:200],
            },
        )
        raise HTTPException(
            status_code=502,
            detail=f"Failed to create draft playbook: {exc}",
        ) from exc

    try:
        simulation = soar_client.request("POST", f"/playbooks/{playbook_id}/simulate")
    except Exception as exc:  # noqa: BLE001
        simulation = {"dryRun": True, "valid": False, "steps": [], "error": str(exc)[:200]}

    _audit(
        audit_store,
        request=request,
        current_user=current_user,
        action="soc.ticket.playbook_drafted",
        details={
            "ticketId": ticket_id,
            "playbookId": playbook_id,
            "provider": provider.name,
            "stepCount": len(suggestion.steps),
            "sensitive": sensitive_present,
        },
    )
    return {
        "ticketId": ticket_id,
        "playbook": created_playbook,
        "simulation": simulation,
        "suggestion": _containment_to_dict(suggestion, provider_name=provider.name),
    }


@router.post(
    "/soc/incidents/{incident_id}/playbook-recommendations/{template_id}/instantiate",
    status_code=status.HTTP_201_CREATED,
)
def instantiate_recommended_playbook(
    incident_id: str,
    template_id: str,
    request: Request,
    siem_client: Annotated[SocClient, Depends(get_siem_client)],
    soar_client: Annotated[SocClient, Depends(get_soar_client)],
    current_user: Annotated[dict, Depends(get_current_api_user)],
    audit_store: Annotated[AuditStore, Depends(get_auth_audit_store)],
    _csrf: Annotated[None, Depends(require_csrf)],
) -> dict:
    incident = siem_client.request("GET", f"/incidents/{incident_id}")
    playbook_payload, suggestion = _recommended_template_playbook(incident, template_id)

    try:
        created_playbook = soar_client.request("POST", "/playbooks", json=playbook_payload)
    except Exception as exc:  # noqa: BLE001
        _audit(
            audit_store,
            request=request,
            current_user=current_user,
            action="soc.ticket.playbook_drafted",
            outcome="failure",
            details={
                "ticketId": incident_id,
                "templateId": template_id,
                "stage": "create_playbook",
                "provider": "deterministic",
                "error": str(exc)[:200],
            },
        )
        raise HTTPException(
            status_code=502,
            detail=f"Failed to create recommended playbook: {exc}",
        ) from exc

    try:
        simulation = soar_client.request(
            "POST",
            f"/playbooks/{playbook_payload['id']}/simulate",
        )
    except Exception as exc:  # noqa: BLE001
        simulation = {"dryRun": True, "valid": False, "steps": [], "error": str(exc)[:200]}

    _audit(
        audit_store,
        request=request,
        current_user=current_user,
        action="soc.ticket.playbook_drafted",
        details={
            "ticketId": incident_id,
            "playbookId": playbook_payload["id"],
            "templateId": template_id,
            "provider": "deterministic",
            "stepCount": len(suggestion["steps"]),
            "sensitive": any(step["requiresApproval"] for step in suggestion["steps"]),
        },
    )
    return {
        "ticketId": incident_id,
        "playbook": created_playbook,
        "simulation": simulation,
        "suggestion": suggestion,
    }


@router.post("/soc/tickets/{ticket_id}/apply-containment")
def apply_containment_playbook(
    ticket_id: str,
    payload: Annotated[dict[str, Any], Body()],
    request: Request,
    siem_client: Annotated[SocClient, Depends(get_siem_client)],
    soar_client: Annotated[SocClient, Depends(get_soar_client)],
    current_user: Annotated[dict, Depends(get_current_api_user)],
    audit_store: Annotated[AuditStore, Depends(get_auth_audit_store)],
    _csrf: Annotated[None, Depends(require_csrf)],
) -> dict:
    """Trigger a dry-run of the AI-drafted playbook against the ticket's
    incident. On success transition the ticket to `contained` and append a
    success timeline note. Destructive operations remain blocked at the
    soar_skipper layer (the lite service always runs dry-run for the MVP).
    """
    playbook_id = payload.get("playbookId")
    if not isinstance(playbook_id, str) or not playbook_id:
        raise HTTPException(status_code=422, detail="playbookId is required")

    try:
        run = soar_client.request(
            "POST",
            f"/incidents/{ticket_id}/playbooks/{playbook_id}/run",
        )
    except Exception as exc:  # noqa: BLE001
        _audit(
            audit_store,
            request=request,
            current_user=current_user,
            action="soc.ticket.contained",
            outcome="failure",
            details={
                "ticketId": ticket_id,
                "playbookId": playbook_id,
                "stage": "soar_run",
                "error": str(exc)[:200],
            },
        )
        raise HTTPException(status_code=502, detail=f"Failed to run draft playbook: {exc}") from exc

    run_status = str(run.get("status") or "unknown")
    waiting_approval = run_status == "waiting_approval"
    new_ticket_status = "investigating" if waiting_approval else "contained"
    note = (
        f"Dry-run for playbook {playbook_id} completed with status `{run_status}`."
        if not waiting_approval
        else f"Playbook {playbook_id} dry-run paused at approval gate."
    )

    try:
        updated_ticket = siem_client.request(
            "PATCH",
            f"/incidents/{ticket_id}/triage",
            json={"ticketStatus": new_ticket_status, "note": note},
        )
    except Exception as exc:  # noqa: BLE001
        updated_ticket = None
        _audit(
            audit_store,
            request=request,
            current_user=current_user,
            action="soc.ticket.contained",
            outcome="partial",
            details={
                "ticketId": ticket_id,
                "playbookId": playbook_id,
                "runId": run.get("id"),
                "warning": f"Ticket patch failed: {exc}"[:200],
            },
        )

    audit_action = (
        "soc.ticket.contained"
        if new_ticket_status == "contained"
        else "soc.ticket.containment_paused"
    )
    _audit(
        audit_store,
        request=request,
        current_user=current_user,
        action=audit_action,
        details={
            "ticketId": ticket_id,
            "playbookId": playbook_id,
            "runId": run.get("id"),
            "runStatus": run_status,
            "newTicketStatus": new_ticket_status,
        },
    )
    return {
        "ticketId": ticket_id,
        "playbookId": playbook_id,
        "run": run,
        "ticket": updated_ticket,
        "ticketStatus": new_ticket_status,
    }


@router.post("/soc/incidents/{incident_id}/containment-suggestions")
def suggest_incident_containment(
    incident_id: str,
    request: Request,
    client: Annotated[SocClient, Depends(get_siem_client)],
    current_user: Annotated[dict, Depends(get_current_api_user)],
    audit_store: Annotated[AuditStore, Depends(get_auth_audit_store)],
    _csrf: Annotated[None, Depends(require_csrf)],
) -> dict:
    incident = client.request("GET", f"/incidents/{incident_id}")
    context = _build_incident_context(incident)
    provider = _configured_ai_provider_or_502()
    locale = _request_locale(request)
    try:
        suggestion = provider.suggest_containment(context, locale=locale)
    except Exception as exc:  # noqa: BLE001
        _audit(
            audit_store,
            request=request,
            current_user=current_user,
            action="soc.incident.containment_suggested",
            outcome="failure",
            details={
                "incidentId": incident_id,
                "provider": provider.name,
                "error": str(exc)[:200],
            },
        )
        raise HTTPException(status_code=502, detail=f"AI provider failed: {exc}") from exc

    _audit(
        audit_store,
        request=request,
        current_user=current_user,
        action="soc.incident.containment_suggested",
        details={
            "incidentId": incident_id,
            "provider": provider.name,
            "stepCount": len(suggestion.steps),
        },
    )
    return _containment_to_dict(suggestion, provider_name=provider.name)


@router.get("/soc/tickets")
def list_tickets(
    client: Annotated[SocClient, Depends(get_siem_client)],
    _current_user: Annotated[dict, Depends(get_current_api_user)],
    triage: Annotated[str | None, Query()] = None,
    status: Annotated[str | None, Query()] = None,
    severity: Annotated[str | None, Query()] = None,
) -> dict:
    """Tickets are the analyst view of SIEM incidents enriched with triage
    metadata. The siem_kowalski service stores triage fields inside the
    incident payload, so the gateway lists incidents and filters/forwards
    server-side.
    """
    params: dict[str, Any] = {}
    if triage is not None:
        params["triageLevel"] = triage
    if status is not None:
        params["ticketStatus"] = status
    if severity is not None:
        params["severity"] = severity
    response = client.request("GET", "/incidents", params=params)
    items = response if isinstance(response, list) else response.get("items", [])
    return {"items": items}


@router.get("/soc/tickets/{ticket_id}")
def get_ticket(
    ticket_id: str,
    client: Annotated[SocClient, Depends(get_siem_client)],
    _current_user: Annotated[dict, Depends(get_current_api_user)],
) -> dict:
    return client.request("GET", f"/incidents/{ticket_id}")


@router.patch("/soc/tickets/{ticket_id}")
def update_ticket(
    ticket_id: str,
    payload: Annotated[dict[str, Any], Body()],
    request: Request,
    client: Annotated[SocClient, Depends(get_siem_client)],
    current_user: Annotated[dict, Depends(get_current_api_user)],
    audit_store: Annotated[AuditStore, Depends(get_auth_audit_store)],
    _csrf: Annotated[None, Depends(require_csrf)],
) -> dict:
    allowed_keys = {
        "triageLevel",
        "ticketStatus",
        "assigneeUserId",
        "aiAnalysisId",
        "note",
    }
    body = {k: v for k, v in payload.items() if k in allowed_keys}
    if not body:
        raise HTTPException(
            status_code=422,
            detail=(
                "Body must include at least one of triageLevel, ticketStatus, "
                "assigneeUserId, aiAnalysisId, note"
            ),
        )
    response = client.request("PATCH", f"/incidents/{ticket_id}/triage", json=body)
    action = "soc.ticket.updated"
    if "ticketStatus" in body:
        action = "soc.ticket.status_changed"
    if "assigneeUserId" in body:
        action = "soc.ticket.assigned"
    _audit(
        audit_store,
        request=request,
        current_user=current_user,
        action=action,
        details={
            "ticketId": ticket_id,
            "changes": list(body.keys()),
            "service": "siem_kowalski",
        },
    )
    return response


@router.post("/soc/events")
def create_security_event(
    request: Request,
    payload: Annotated[dict[str, Any], Body()],
    client: Annotated[SocClient, Depends(get_siem_client)],
    current_user: Annotated[dict, Depends(get_current_api_user)],
    audit_store: Annotated[AuditStore, Depends(get_auth_audit_store)],
    _csrf: Annotated[None, Depends(require_csrf)],
) -> dict:
    response = client.request("POST", "/events", json=payload)
    _audit(
        audit_store,
        request=request,
        current_user=current_user,
        action="soc.event.created",
        details={
            "source": payload.get("source"),
            "eventType": payload.get("eventType"),
            "service": "siem_kowalski",
        },
    )
    return response


@router.get("/soc/events")
def list_security_events(
    client: Annotated[SocClient, Depends(get_siem_client)],
    _current_user: Annotated[dict, Depends(get_current_api_user)],
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    event_type: Annotated[str | None, Query(alias="eventType")] = None,
) -> dict:
    return client.request(
        "GET",
        "/events",
        params={"limit": limit, "eventType": event_type},
    )


@router.get("/soc/incidents")
def list_incidents(
    client: Annotated[SocClient, Depends(get_siem_client)],
    _current_user: Annotated[dict, Depends(get_current_api_user)],
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    status: str | None = None,
    severity: str | None = None,
) -> dict:
    return client.request(
        "GET",
        "/incidents",
        params={"limit": limit, "status": status, "severity": severity},
    )


@router.get("/soc/rules")
def list_detection_rules(
    client: Annotated[SocClient, Depends(get_siem_client)],
    _current_user: Annotated[dict, Depends(get_current_api_user)],
) -> dict:
    return client.request("GET", "/rules")


@router.get("/soc/incidents/{incident_id}")
def get_incident(
    incident_id: str,
    client: Annotated[SocClient, Depends(get_siem_client)],
    _current_user: Annotated[dict, Depends(get_current_api_user)],
) -> dict:
    return client.request("GET", f"/incidents/{incident_id}")


@router.get("/soc/incidents/{incident_id}/triage-context")
def get_incident_triage_context(
    incident_id: str,
    client: Annotated[SocClient, Depends(get_siem_client)],
    _current_user: Annotated[dict, Depends(get_current_api_user)],
) -> dict:
    incident = client.request("GET", f"/incidents/{incident_id}")
    return build_triage_context(incident).model_dump(by_alias=True, mode="json")


@router.get("/soc/incidents/{incident_id}/endpoint-context")
def get_incident_endpoint_context(
    incident_id: str,
    siem_client: Annotated[SocClient, Depends(get_siem_client)],
    xdr_client: Annotated[SocClient, Depends(get_xdr_client)],
    _current_user: Annotated[dict, Depends(get_current_api_user)],
    limit: Annotated[int, Query(ge=1, le=50)] = 5,
) -> dict:
    incident = siem_client.request("GET", f"/incidents/{incident_id}")
    entities = incident.get("entities")
    if not isinstance(entities, dict):
        entities = {}
    endpoint_context = xdr_client.request(
        "POST",
        "/correlations/endpoint-context",
        json={"entities": entities, "limit": limit},
    )
    return {
        "incidentId": incident_id,
        "incident": incident,
        "items": endpoint_context.get("items", []),
        "total": endpoint_context.get("total", 0),
    }


@router.patch("/soc/incidents/{incident_id}")
def update_incident(
    incident_id: str,
    request: Request,
    payload: Annotated[dict[str, Any], Body()],
    client: Annotated[SocClient, Depends(get_siem_client)],
    current_user: Annotated[dict, Depends(get_current_api_user)],
    audit_store: Annotated[AuditStore, Depends(get_auth_audit_store)],
    _csrf: Annotated[None, Depends(require_csrf)],
) -> dict:
    response = client.request("PATCH", f"/incidents/{incident_id}", json=payload)
    _audit(
        audit_store,
        request=request,
        current_user=current_user,
        action="soc.incident.updated",
        details={
            "incidentId": incident_id,
            "status": payload.get("status"),
            "service": "siem_kowalski",
        },
    )
    return response


@router.get("/soc/playbooks")
def list_playbooks(
    client: Annotated[SocClient, Depends(get_soar_client)],
    _current_user: Annotated[dict, Depends(get_current_api_user)],
) -> dict:
    return client.request("GET", "/playbooks")


@router.get("/soc/playbook-node-types")
def list_playbook_node_types(
    client: Annotated[SocClient, Depends(get_soar_client)],
    _current_user: Annotated[dict, Depends(get_current_api_user)],
) -> dict:
    return client.request("GET", "/node-types")


@router.get("/soc/playbook-webhook-destinations")
def list_playbook_webhook_destinations(
    service: Annotated[
        PlaybookWebhookDestinationService,
        Depends(get_playbook_webhook_destination_service),
    ],
    current_user: Annotated[dict, Depends(get_current_api_user)],
) -> dict:
    return {"items": service.list(owner_user_id=str(current_user["id"]))}


@router.post("/soc/playbook-webhook-destinations", status_code=status.HTTP_201_CREATED)
def create_playbook_webhook_destination(
    payload: PlaybookWebhookDestinationCreateRequest,
    request: Request,
    service: Annotated[
        PlaybookWebhookDestinationService,
        Depends(get_playbook_webhook_destination_service),
    ],
    current_user: Annotated[dict, Depends(get_current_api_user)],
    audit_store: Annotated[AuditStore, Depends(get_auth_audit_store)],
    _csrf: Annotated[None, Depends(require_csrf)],
) -> dict:
    try:
        result = service.create(
            owner_user_id=str(current_user["id"]),
            name=payload.name,
            kind=payload.kind,
            url=payload.url,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    _audit(
        audit_store,
        request=request,
        current_user=current_user,
        action="soc.playbook.webhook_destination.created",
        details={
            "destinationId": result["id"],
            "kind": result["kind"],
            "name": result["name"],
            "redactedUrl": result["redactedUrl"],
        },
    )
    return result


@router.post("/soc/playbook-webhook-destinations/{destination_id}/test")
def test_playbook_webhook_destination(
    destination_id: str,
    payload: PlaybookWebhookDestinationTestRequest,
    request: Request,
    service: Annotated[
        PlaybookWebhookDestinationService,
        Depends(get_playbook_webhook_destination_service),
    ],
    current_user: Annotated[dict, Depends(get_current_api_user)],
    audit_store: Annotated[AuditStore, Depends(get_auth_audit_store)],
    _csrf: Annotated[None, Depends(require_csrf)],
) -> dict:
    try:
        result = service.send(
            owner_user_id=str(current_user["id"]),
            destination_id=destination_id,
            payload={"content": payload.content},
        )
        public_destination = service.public_item(
            owner_user_id=str(current_user["id"]),
            destination_id=destination_id,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Webhook destination not found") from exc
    except Exception as exc:
        _audit(
            audit_store,
            request=request,
            current_user=current_user,
            action="soc.playbook.webhook_destination.tested",
            outcome="failure",
            details={"destinationId": destination_id, "error": str(exc)[:200]},
        )
        raise HTTPException(status_code=502, detail=f"Webhook test failed: {exc}") from exc
    _audit(
        audit_store,
        request=request,
        current_user=current_user,
        action="soc.playbook.webhook_destination.tested",
        outcome="success" if result["ok"] else "failure",
        details={
            "destinationId": destination_id,
            "redactedUrl": public_destination.get("redactedUrl"),
            "statusCode": result["statusCode"],
        },
    )
    return result


@router.post("/soc/playbooks")
def create_playbook(
    request: Request,
    payload: Annotated[dict[str, Any], Body()],
    client: Annotated[SocClient, Depends(get_soar_client)],
    current_user: Annotated[dict, Depends(get_current_api_user)],
    audit_store: Annotated[AuditStore, Depends(get_auth_audit_store)],
    _csrf: Annotated[None, Depends(require_csrf)],
) -> dict:
    response = client.request("POST", "/playbooks", json=payload)
    _audit(
        audit_store,
        request=request,
        current_user=current_user,
        action="soc.playbook.created",
        details={"playbookId": response.get("id"), "service": "soar_skipper"},
    )
    return response


@router.get("/soc/playbooks/{playbook_id}")
def get_playbook(
    playbook_id: str,
    client: Annotated[SocClient, Depends(get_soar_client)],
    _current_user: Annotated[dict, Depends(get_current_api_user)],
) -> dict:
    return client.request("GET", f"/playbooks/{playbook_id}")


@router.put("/soc/playbooks/{playbook_id}")
def update_playbook(
    playbook_id: str,
    request: Request,
    payload: Annotated[dict[str, Any], Body()],
    client: Annotated[SocClient, Depends(get_soar_client)],
    current_user: Annotated[dict, Depends(get_current_api_user)],
    audit_store: Annotated[AuditStore, Depends(get_auth_audit_store)],
    _csrf: Annotated[None, Depends(require_csrf)],
) -> dict:
    response = client.request("PUT", f"/playbooks/{playbook_id}", json=payload)
    _audit(
        audit_store,
        request=request,
        current_user=current_user,
        action="soc.playbook.updated",
        details={"playbookId": playbook_id, "service": "soar_skipper"},
    )
    return response


@router.delete("/soc/playbooks/{playbook_id}")
def delete_playbook(
    playbook_id: str,
    request: Request,
    client: Annotated[SocClient, Depends(get_soar_client)],
    current_user: Annotated[dict, Depends(get_current_api_user)],
    audit_store: Annotated[AuditStore, Depends(get_auth_audit_store)],
    _csrf: Annotated[None, Depends(require_csrf)],
) -> dict:
    response = client.request("DELETE", f"/playbooks/{playbook_id}")
    _audit(
        audit_store,
        request=request,
        current_user=current_user,
        action="soc.playbook.deleted",
        details={"playbookId": playbook_id, "service": "soar_skipper"},
    )
    return response


@router.post("/soc/playbooks/{playbook_id}/simulate")
def simulate_playbook(
    playbook_id: str,
    request: Request,
    client: Annotated[SocClient, Depends(get_soar_client)],
    current_user: Annotated[dict, Depends(get_current_api_user)],
    audit_store: Annotated[AuditStore, Depends(get_auth_audit_store)],
    _csrf: Annotated[None, Depends(require_csrf)],
    payload: Annotated[dict[str, Any] | None, Body()] = None,
) -> dict:
    response = client.request("POST", f"/playbooks/{playbook_id}/simulate", json=payload or {})
    _audit(
        audit_store,
        request=request,
        current_user=current_user,
        action="soc.playbook.simulated",
        details={"playbookId": playbook_id, "service": "soar_skipper"},
    )
    return response


@router.post("/soc/incidents/{incident_id}/playbooks/{playbook_id}/run")
def run_playbook(
    incident_id: str,
    playbook_id: str,
    request: Request,
    client: Annotated[SocClient, Depends(get_soar_client)],
    siem_client: Annotated[SocClient, Depends(get_siem_client)],
    webhook_destinations: Annotated[
        PlaybookWebhookDestinationService,
        Depends(get_playbook_webhook_destination_service),
    ],
    current_user: Annotated[dict, Depends(get_current_api_user)],
    audit_store: Annotated[AuditStore, Depends(get_auth_audit_store)],
    _csrf: Annotated[None, Depends(require_csrf)],
    payload: Annotated[dict[str, Any] | None, Body()] = None,
) -> dict:
    response = client.request(
        "POST",
        f"/incidents/{incident_id}/playbooks/{playbook_id}/run",
        json=payload or {},
    )
    _audit(
        audit_store,
        request=request,
        current_user=current_user,
        action="soc.playbook.run_created",
        details={
            "incidentId": incident_id,
            "playbookId": playbook_id,
            "runId": response.get("id"),
            "service": "soar_skipper",
        },
    )
    try:
        playbook = client.request("GET", f"/playbooks/{playbook_id}")
        if _playbook_has_effect_nodes(playbook):
            incident = siem_client.request("GET", f"/incidents/{incident_id}")
            effects = execute_playbook_effects(
                playbook=playbook,
                run=response,
                incident=incident,
                siem_client=siem_client,
                audit_store=audit_store,
                webhook_destinations=webhook_destinations,
                actor=current_user,
                client_ip=_client_ip(request),
                user_agent=request.headers.get("user-agent"),
            )
            if effects:
                response["effects"] = effects
                response["effectCount"] = len(effects)
    except Exception as exc:  # noqa: BLE001
        response["effectsError"] = str(exc)[:200]
        _audit(
            audit_store,
            request=request,
            current_user=current_user,
            action="soc.playbook.effects_failed",
            outcome="failure",
            details={
                "incidentId": incident_id,
                "playbookId": playbook_id,
                "runId": response.get("id"),
                "error": str(exc)[:200],
            },
        )
    return response


@router.get("/soc/playbook-runs")
def list_playbook_runs(
    client: Annotated[SocClient, Depends(get_soar_client)],
    _current_user: Annotated[dict, Depends(get_current_api_user)],
) -> dict:
    return client.request("GET", "/playbook-runs")


@router.get("/soc/playbook-runs/{run_id}")
def get_playbook_run(
    run_id: str,
    client: Annotated[SocClient, Depends(get_soar_client)],
    _current_user: Annotated[dict, Depends(get_current_api_user)],
) -> dict:
    return client.request("GET", f"/playbook-runs/{run_id}")


@router.post("/soc/playbook-runs/{run_id}/policy-review")
def create_playbook_run_policy_review(
    run_id: str,
    payload: PlaybookRunPolicyReviewRequest,
    request: Request,
    db: Annotated[Session, Depends(get_policy_db)],
    soar_client: Annotated[SocClient, Depends(get_soar_client)],
    fortigate_service: Annotated[Any, Depends(get_fortigate_policy_service)],
    current_user: Annotated[dict, Depends(get_current_api_user)],
    audit_store: Annotated[AuditStore, Depends(get_auth_audit_store)],
    _csrf: Annotated[None, Depends(require_csrf)],
) -> dict:
    run = soar_client.request("GET", f"/playbook-runs/{run_id}")
    _ensure_fortigate_policy_run(run)
    incident_id = str(run.get("incidentId") or "")
    owner_user_id = str(current_user["id"])
    review_request = FortiGatePolicyReviewRequest(
        intent=FortiGatePolicyIntent.TEMPORARY_BLOCK,
        scope=payload.scope,
        source_interface=payload.source_interface,
        destination_interface=payload.destination_interface,
        source_ip=payload.source_ip,
        destination_ip=payload.destination_ip,
        service=payload.service,
        duration_minutes=payload.duration_minutes,
        incident_id=incident_id or None,
        playbook_run_id=run_id,
    )
    review = create_policy_review_for_user(
        db=db,
        integration_id=payload.integration_id,
        owner_user_id=owner_user_id,
        service=fortigate_service,
        payload=review_request,
    )
    _audit(
        audit_store,
        request=request,
        current_user=current_user,
        action="soc.playbook.policy_review_created",
        details={
            "runId": run_id,
            "incidentId": incident_id,
            "integrationId": payload.integration_id,
            "requestId": review.request_id,
        },
    )
    return {
        **review.model_dump(mode="json"),
        "runId": run_id,
        "incidentId": incident_id,
    }


@router.post("/soc/playbook-runs/{run_id}/policy-apply")
def apply_playbook_run_policy(
    run_id: str,
    payload: PlaybookRunPolicyApplyRequest,
    request: Request,
    db: Annotated[Session, Depends(get_policy_db)],
    soar_client: Annotated[SocClient, Depends(get_soar_client)],
    siem_client: Annotated[SocClient, Depends(get_siem_client)],
    fortigate_service: Annotated[Any, Depends(get_fortigate_policy_service)],
    current_user: Annotated[dict, Depends(get_current_api_user)],
    audit_store: Annotated[AuditStore, Depends(get_auth_audit_store)],
    _csrf: Annotated[None, Depends(require_csrf)],
) -> dict:
    run = soar_client.request("GET", f"/playbook-runs/{run_id}")
    _ensure_fortigate_policy_run(run)
    incident_id = str(run.get("incidentId") or "")
    owner_user_id = str(current_user["id"])
    policy = apply_policy_review_for_user(
        db=db,
        integration_id=payload.integration_id,
        owner_user_id=owner_user_id,
        service=fortigate_service,
        payload=FortiGatePolicyApplyRequest(
            request_id=payload.request_id,
            review_hash=payload.review_hash,
        ),
    )
    ticket_update: dict[str, Any] | None = None
    if incident_id:
        ticket = siem_client.request(
            "PATCH",
            f"/incidents/{incident_id}/triage",
            json={
                "ticketStatus": "contained",
                "note": (
                    f"FortiGate policy request {payload.request_id} applied "
                    f"from playbook run {run_id}."
                ),
            },
        )
        ticket_update = {
            "status": "contained",
            "incidentId": incident_id,
            "ticket": ticket,
        }
    _audit(
        audit_store,
        request=request,
        current_user=current_user,
        action="soc.playbook.policy_applied",
        details={
            "runId": run_id,
            "incidentId": incident_id,
            "integrationId": payload.integration_id,
            "requestId": policy.request_id,
            "ticketUpdate": ticket_update,
        },
    )
    return {
        "runId": run_id,
        "incidentId": incident_id,
        "policy": policy.model_dump(mode="json"),
        "ticketUpdate": ticket_update,
    }


def _ensure_fortigate_policy_run(run: dict[str, Any]) -> None:
    if not _run_has_fortigate_policy_step(run):
        raise HTTPException(
            status_code=409,
            detail="Playbook run does not contain a FortiGate temporary block step",
        )


def _run_has_fortigate_policy_step(run: dict[str, Any]) -> bool:
    steps = run.get("steps")
    if not isinstance(steps, list):
        return False
    return any(
        isinstance(step, dict) and step.get("nodeType") == "fortigate.temporary_block"
        for step in steps
    )


def _playbook_has_effect_nodes(playbook: dict[str, Any]) -> bool:
    nodes = playbook.get("nodes")
    if not isinstance(nodes, list):
        return False
    effect_types = {
        "condition.severity",
        "enrich.ip",
        "case.note",
        "audit.note",
        "notify.webhook",
        "webhook.dry_run",
        "approval.required",
        "fortigate.recommend_block",
        "fortigate.temporary_block",
        "fortiweb.recommend_block",
    }
    return any(
        isinstance(node, dict) and node.get("type") in effect_types
        for node in nodes
    )


@router.post("/soc/playbook-runs/{run_id}/approve")
def approve_playbook_run(
    run_id: str,
    request: Request,
    client: Annotated[SocClient, Depends(get_soar_client)],
    siem_client: Annotated[SocClient, Depends(get_siem_client)],
    current_user: Annotated[dict, Depends(require_admin_user)],
    audit_store: Annotated[AuditStore, Depends(get_auth_audit_store)],
    _csrf: Annotated[None, Depends(require_csrf)],
) -> dict:
    response = client.request("POST", f"/playbook-runs/{run_id}/approve", json={})
    ticket_update: dict[str, Any] | None = None
    outcome = "success"
    policy_review_required = _run_has_fortigate_policy_step(response)
    if policy_review_required:
        response["policyReviewRequired"] = True
    if (
        response.get("status") == "completed"
        and response.get("incidentId")
        and not policy_review_required
    ):
        incident_id = str(response["incidentId"])
        try:
            ticket = siem_client.request(
                "PATCH",
                f"/incidents/{incident_id}/triage",
                json={
                    "ticketStatus": "contained",
                    "note": f"Playbook run {run_id} approved and completed containment.",
                },
            )
            ticket_update = {
                "status": "contained",
                "incidentId": incident_id,
                "ticket": ticket,
            }
        except Exception as exc:  # noqa: BLE001
            outcome = "partial"
            ticket_update = {
                "status": "failed",
                "incidentId": incident_id,
                "error": str(exc)[:200],
            }
        response["ticketUpdate"] = ticket_update
    _audit(
        audit_store,
        request=request,
        current_user=current_user,
        action="soc.playbook_run.approved",
        outcome=outcome,
        details={
            "runId": run_id,
            "playbookId": response.get("playbookId"),
            "incidentId": response.get("incidentId"),
            "service": "soar_skipper",
            "ticketUpdate": ticket_update,
        },
    )
    return response


@router.get("/weapons/endpoints")
def list_endpoints(
    client: Annotated[SocClient, Depends(get_xdr_client)],
    _current_user: Annotated[dict, Depends(get_current_api_user)],
) -> dict:
    return client.request("GET", "/endpoints")


@router.get("/weapons/endpoints/{endpoint_id}")
def get_endpoint(
    endpoint_id: str,
    client: Annotated[SocClient, Depends(get_xdr_client)],
    _current_user: Annotated[dict, Depends(get_current_api_user)],
) -> dict:
    return client.request("GET", f"/endpoints/{endpoint_id}")


@router.delete("/weapons/endpoints/{endpoint_id}")
def delete_endpoint(
    endpoint_id: str,
    request: Request,
    client: Annotated[SocClient, Depends(get_xdr_client)],
    current_user: Annotated[dict, Depends(get_current_api_user)],
    audit_store: Annotated[AuditStore, Depends(get_auth_audit_store)],
    _csrf: Annotated[None, Depends(require_csrf)],
) -> dict:
    client.request("DELETE", f"/endpoints/{endpoint_id}", pass_through_statuses={404})
    _audit(
        audit_store,
        request=request,
        current_user=current_user,
        action="xdr.endpoint.deleted",
        details={"endpointId": endpoint_id, "service": "xdr_rico"},
    )
    return {"deleted": True, "endpointId": endpoint_id}


@router.get("/weapons/endpoints/{endpoint_id}/related-incidents")
def get_endpoint_related_incidents(
    endpoint_id: str,
    xdr_client: Annotated[SocClient, Depends(get_xdr_client)],
    siem_client: Annotated[SocClient, Depends(get_siem_client)],
    _current_user: Annotated[dict, Depends(get_current_api_user)],
) -> dict:
    endpoint = xdr_client.request("GET", f"/endpoints/{endpoint_id}")
    incidents_response = siem_client.request("GET", "/incidents", params={"limit": 200})
    items = incidents_response.get("items")
    incidents = items if isinstance(items, list) else []

    matched_incidents: list[dict[str, Any]] = []
    matched_fields: dict[str, list[str]] = {}
    for incident in incidents:
        if not isinstance(incident, dict):
            continue
        fields = _incident_endpoint_matched_fields(incident, endpoint)
        if not fields:
            continue
        matched_incidents.append(incident)
        incident_id = incident.get("id")
        if isinstance(incident_id, str) and incident_id:
            matched_fields[incident_id] = fields

    response: dict[str, Any] = {
        "endpointId": endpoint_id,
        "items": matched_incidents,
        "total": len(matched_incidents),
    }
    if matched_fields:
        response["matchedFields"] = matched_fields
    return response


@router.get("/weapons/endpoints/{endpoint_id}/timeline")
def get_endpoint_timeline(
    endpoint_id: str,
    client: Annotated[SocClient, Depends(get_xdr_client)],
    _current_user: Annotated[dict, Depends(get_current_api_user)],
) -> dict:
    return client.request("GET", f"/endpoints/{endpoint_id}/timeline")


@router.post("/weapons/endpoint-events")
def create_endpoint_event(
    request: Request,
    payload: Annotated[dict[str, Any], Body()],
    client: Annotated[SocClient, Depends(get_xdr_client)],
    siem_client: Annotated[SocClient, Depends(get_siem_client)],
    audit_store: Annotated[AuditStore, Depends(get_auth_audit_store)],
    authorization: Annotated[str | None, Header(alias="Authorization")] = None,
) -> dict:
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Endpoint enrollment token required",
        )
    payload = _endpoint_payload_with_observed_source_ip(payload, request)
    response = client.request(
        "POST",
        "/endpoint-events",
        json=payload,
        headers={"Authorization": authorization},
        pass_through_statuses={401, 403},
    )
    siem_forwarding = _forward_endpoint_event_to_siem(
        payload,
        response=response,
        siem_client=siem_client,
    )
    audit_store.record(
        action="xdr.endpoint_event.created",
        outcome="partial" if siem_forwarding.get("status") == "failed" else "success",
        client_ip=_client_ip(request),
        user_agent=request.headers.get("user-agent"),
        details={
            "endpointId": payload.get("endpointId"),
            "eventType": payload.get("eventType"),
            "service": "xdr_rico",
            "actorType": "agent_private",
            "siemForwarding": siem_forwarding,
        },
    )
    if siem_forwarding["status"] != "skipped":
        response["siemForwarding"] = siem_forwarding
    return response


def _endpoint_payload_with_observed_source_ip(
    payload: dict[str, Any],
    request: Request,
) -> dict[str, Any]:
    attributes = payload.get("attributes") if isinstance(payload.get("attributes"), dict) else {}
    return {
        **payload,
        "attributes": {
            **attributes,
            "observedSourceIp": _client_ip(request),
        },
    }


def _incident_endpoint_matched_fields(
    incident: dict[str, Any],
    endpoint: dict[str, Any],
) -> list[str]:
    entities = incident.get("entities")
    if not isinstance(entities, dict):
        return []

    endpoint_id = endpoint.get("id")
    hostname = endpoint.get("hostname")
    current_user = endpoint.get("currentUser")
    ip_addresses = {
        value
        for value in endpoint.get("ipAddresses", [])
        if isinstance(value, str) and value
    }
    attributes = endpoint.get("attributes")
    if isinstance(attributes, dict):
        observed_source_ip = attributes.get("observedSourceIp")
        if isinstance(observed_source_ip, str) and observed_source_ip:
            ip_addresses.add(observed_source_ip)

    matched: list[str] = []
    for field, value in _entity_string_values(entities):
        normalized_field = field.lower()
        if (
            normalized_field in {"endpointid", "endpoint_id", "endpoint.id"}
            and isinstance(endpoint_id, str)
            and value == endpoint_id
        ):
            matched.append(field)
            continue

        if "ip" in normalized_field and value in ip_addresses:
            matched.append(field)
            continue

        if normalized_field in {"hostname", "host", "endpointhostname"} and _same_text(
            value,
            hostname,
        ):
            matched.append(field)
            continue

        if normalized_field in {
            "username",
            "user",
            "principal",
            "currentuser",
            "current_user",
            "userprincipalname",
        } and _same_user(value, current_user):
            matched.append(field)

    return matched


def _entity_string_values(entities: dict[str, Any]) -> list[tuple[str, str]]:
    values: list[tuple[str, str]] = []
    for field, raw_value in entities.items():
        if isinstance(raw_value, str) and raw_value:
            values.append((field, raw_value))
        elif isinstance(raw_value, list):
            values.extend(
                (field, value)
                for value in raw_value
                if isinstance(value, str) and value
            )
    return values


def _same_text(left: str, right: Any) -> bool:
    return isinstance(right, str) and left.casefold() == right.casefold()


def _same_user(left: str, right: Any) -> bool:
    if not isinstance(right, str) or not right:
        return False
    left_folded = left.casefold()
    right_folded = right.casefold()
    if left_folded == right_folded:
        return True
    return _principal_name(left_folded) == _principal_name(right_folded)


def _principal_name(value: str) -> str:
    if "\\" in value:
        value = value.rsplit("\\", 1)[-1]
    if "/" in value:
        value = value.rsplit("/", 1)[-1]
    if "@" in value:
        value = value.split("@", 1)[0]
    return value


def _forward_endpoint_event_to_siem(
    payload: dict[str, Any],
    *,
    response: dict[str, Any],
    siem_client: SocClient,
) -> dict[str, Any]:
    events = _endpoint_event_to_siem_events(payload, response=response)
    if not events:
        return {"status": "skipped", "eventCount": 0, "eventIds": []}
    created: list[dict[str, Any]] = []
    try:
        for event in events:
            created.append(siem_client.request("POST", "/events", json=event))
    except Exception as exc:  # noqa: BLE001
        return {
            "status": "failed",
            "eventCount": len(events),
            "eventIds": [event.get("id") for event in created if isinstance(event, dict)],
            "error": str(exc)[:200],
        }
    return {
        "status": "created",
        "eventCount": len(created),
        "eventIds": [event.get("id") for event in created if isinstance(event, dict)],
    }


def _endpoint_event_to_siem_events(
    payload: dict[str, Any],
    *,
    response: dict[str, Any],
) -> list[dict[str, Any]]:
    event_type = payload.get("eventType")
    if event_type in {"suspicious.process", "connection.snapshot"}:
        suspicious_event = _suspicious_endpoint_event_to_siem_event(payload, response=response)
        return [suspicious_event] if suspicious_event else []
    if event_type not in {"auth.failed_login", "auth.privileged_logon", "file.change"}:
        return []
    attributes = payload.get("attributes") if isinstance(payload.get("attributes"), dict) else {}
    hostname = payload.get("hostname")
    current_user = payload.get("currentUser") or attributes.get("username")
    source_ip = attributes.get("sourceIp") or attributes.get("IpAddress")
    timeline_item = response.get("timelineItem") if isinstance(response, dict) else {}
    severity = _endpoint_siem_severity(str(event_type), attributes)
    entities: dict[str, Any] = {
        "endpointId": payload.get("endpointId"),
        "hostname": hostname,
    }
    if current_user:
        entities["username"] = current_user
    if source_ip:
        entities["sourceIp"] = source_ip
    if event_type == "file.change" and attributes.get("objectName"):
        entities["filePath"] = attributes["objectName"]
    siem_attributes = dict(attributes)
    if isinstance(timeline_item, dict) and timeline_item.get("id"):
        siem_attributes["xdrTimelineItemId"] = timeline_item["id"]
    return [
        {
            "source": "xdr_rico.agent_private",
            "eventType": event_type,
            "severity": severity,
            "occurredAt": payload.get("occurredAt"),
            "entities": {key: value for key, value in entities.items() if value},
            "attributes": siem_attributes,
        }
    ]


def _suspicious_endpoint_event_to_siem_event(
    payload: dict[str, Any],
    *,
    response: dict[str, Any],
) -> dict[str, Any] | None:
    event_type = payload.get("eventType")
    attributes = payload.get("attributes") if isinstance(payload.get("attributes"), dict) else {}
    suspicious_connection = _suspicious_connection(attributes)
    if event_type == "connection.snapshot" and suspicious_connection is None:
        return None
    destination_ip = (
        _first_string(
            attributes.get("destinationIp"),
            attributes.get("remoteIp"),
            attributes.get("dstIp"),
        )
        or _first_string(
            suspicious_connection.get("remoteIp") if suspicious_connection else None,
            suspicious_connection.get("destinationIp") if suspicious_connection else None,
            suspicious_connection.get("dstIp") if suspicious_connection else None,
        )
        or _first_string(
            attributes.get("processRemoteIp"),
            attributes.get("processDestinationIp"),
        )
    )
    observed_source_ip = _first_string(attributes.get("observedSourceIp"))
    source_ip = observed_source_ip or _first_payload_ip(payload)
    current_user = payload.get("currentUser") or attributes.get("username")
    timeline_item = response.get("timelineItem") if isinstance(response, dict) else {}
    origin_source = _first_string(attributes.get("source"), payload.get("source"))

    siem_attributes = dict(attributes)
    siem_attributes["originKind"] = "xdr.endpoint_event"
    if origin_source:
        siem_attributes["originSource"] = origin_source
    if observed_source_ip:
        siem_attributes["observedSourceIp"] = observed_source_ip
    if isinstance(timeline_item, dict) and timeline_item.get("id"):
        siem_attributes["xdrTimelineItemId"] = timeline_item["id"]

    entities: dict[str, Any] = {
        "endpointId": payload.get("endpointId"),
        "hostname": payload.get("hostname"),
    }
    if current_user:
        entities["username"] = current_user
    if source_ip:
        entities["sourceIp"] = source_ip
    if destination_ip:
        entities["destinationIp"] = destination_ip

    return {
        "source": "xdr_rico.agent_private",
        "eventType": "endpoint.suspicious_connection",
        "severity": "high",
        "occurredAt": payload.get("occurredAt"),
        "entities": {key: value for key, value in entities.items() if value},
        "attributes": siem_attributes,
    }


def _suspicious_connection(attributes: dict[str, Any]) -> dict[str, Any] | None:
    if attributes.get("suspicious") is True:
        return attributes
    connections = attributes.get("connections")
    if not isinstance(connections, list):
        return None
    for connection in connections:
        if isinstance(connection, dict) and connection.get("suspicious") is True:
            return connection
    return None


def _first_string(*values: Any) -> str | None:
    for value in values:
        if isinstance(value, str) and value:
            return value
    return None


def _first_payload_ip(payload: dict[str, Any]) -> str | None:
    ip_addresses = payload.get("ipAddresses")
    if isinstance(ip_addresses, list):
        return _first_string(*ip_addresses)
    return _first_string(ip_addresses)


def _endpoint_siem_severity(event_type: str, attributes: dict[str, Any]) -> str:
    if event_type == "auth.failed_login":
        count = attributes.get("count")
        return "high" if isinstance(count, int | float) and count >= 10 else "medium"
    if event_type == "auth.privileged_logon":
        return "high" if attributes.get("unusualHost") is True else "medium"
    if event_type == "file.change":
        return "high" if attributes.get("criticalPath") is True else "low"
    return "informational"


@router.post("/weapons/enrollments")
def create_enrollment(
    request: Request,
    payload: Annotated[dict[str, Any], Body()],
    client: Annotated[SocClient, Depends(get_xdr_client)],
    current_user: Annotated[dict, Depends(get_current_api_user)],
    audit_store: Annotated[AuditStore, Depends(get_auth_audit_store)],
    _csrf: Annotated[None, Depends(require_csrf)],
) -> dict:
    response = client.request("POST", "/enrollments", json=payload)
    _audit(
        audit_store,
        request=request,
        current_user=current_user,
        action="xdr.enrollment.created",
        details={"enrollmentId": response.get("id"), "service": "xdr_rico"},
    )
    return response



def _audit(
    audit_store: AuditStore,
    *,
    request: Request,
    current_user: dict,
    action: str,
    details: dict,
    outcome: str = "success",
) -> None:
    audit_store.record(
        action=action,
        outcome=outcome,
        email=current_user.get("email"),
        user_id=str(current_user["id"]),
        client_ip=_client_ip(request),
        user_agent=request.headers.get("user-agent"),
        details=details,
    )


def _client_ip(request: Request) -> str:
    if request.client is None:
        return "unknown"
    return request.client.host
