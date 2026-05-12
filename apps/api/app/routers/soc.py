from datetime import UTC, datetime, timedelta
from functools import lru_cache
from secrets import token_urlsafe
from typing import Annotated, Any, Protocol

from fastapi import APIRouter, Body, Depends, Header, HTTPException, Query, Request, status

from app.ai import (
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
from app.core.config import get_settings
from app.soc.client import SocServiceClient

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


DEMO_SOURCE_TAG = "demo.replay"

DEMO_ATTACK_TYPES = ("port_scan", "brute_force", "c2_beacon")


def _demo_attack_event(
    attack_type: str, *, now: datetime, demo_run_id: str
) -> dict[str, Any]:
    base = now.astimezone(UTC)

    def stamp(offset_seconds: int) -> str:
        return (
            (base - timedelta(seconds=offset_seconds))
            .isoformat(timespec="milliseconds")
            .replace("+00:00", "Z")
        )

    if attack_type == "port_scan":
        return {
            "source": DEMO_SOURCE_TAG,
            "eventType": "network.deny",
            "severity": "high",
            "occurredAt": stamp(180),
            "entities": {
                "sourceIp": "203.0.113.77",
                "destinationIp": "192.168.0.50",
                "integrationId": "demo-fortigate",
            },
            "attributes": {
                "action": "deny",
                "subtype": "port_scan",
                "message": "Inbound port scan from 203.0.113.77",
                "count": 42,
                "uniqueDestinationCount": 1,
                "demoRunId": demo_run_id,
                "attackType": attack_type,
            },
        }
    if attack_type == "brute_force":
        return {
            "source": DEMO_SOURCE_TAG,
            "eventType": "auth.failed_login",
            "severity": "medium",
            "occurredAt": stamp(120),
            "entities": {
                "sourceIp": "203.0.113.77",
                "username": "svc-backup",
                "integrationId": "demo-fortigate",
            },
            "attributes": {
                "count": 9,
                "message": "Repeated SSH login failures for svc-backup",
                "demoRunId": demo_run_id,
                "attackType": attack_type,
            },
        }
    if attack_type == "c2_beacon":
        return {
            "source": DEMO_SOURCE_TAG,
            "eventType": "endpoint.suspicious_connection",
            "severity": "high",
            "occurredAt": stamp(60),
            "entities": {
                "endpointId": "demo-endpoint-01",
                "hostname": "demo-endpoint-01",
                "sourceIp": "192.168.0.50",
                "destinationIp": "203.0.113.77",
            },
            "attributes": {
                "message": "Endpoint demo-endpoint-01 dialed back to attacker IP",
                "demoRunId": demo_run_id,
                "attackType": attack_type,
            },
        }
    raise HTTPException(
        status_code=400, detail=f"Unknown demo attack type: {attack_type}"
    )


def _demo_replay_events(
    *, now: datetime, demo_run_id: str, attack_types: list[str] | None = None
) -> list[dict[str, Any]]:
    """Synthetic burst designed to trip `denied_traffic_burst` and seed an
    obvious incident timeline for the MVP video. Counts are inflated past
    every detection threshold so the demo always produces an incident.

    When `attack_types` is empty or None, every attack in `DEMO_ATTACK_TYPES`
    is injected (legacy "replay all" behavior). Otherwise only the requested
    subset is injected, in the canonical chain order so the timeline still
    reads correctly.
    """
    requested = list(attack_types) if attack_types else list(DEMO_ATTACK_TYPES)
    unknown = [t for t in requested if t not in DEMO_ATTACK_TYPES]
    if unknown:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown demo attack type(s): {', '.join(sorted(set(unknown)))}",
        )
    ordered = [t for t in DEMO_ATTACK_TYPES if t in set(requested)]
    return [_demo_attack_event(t, now=now, demo_run_id=demo_run_id) for t in ordered]


@router.post("/soc/demo/replay")
def replay_demo_incident(
    request: Request,
    client: Annotated[SocClient, Depends(get_siem_client)],
    current_user: Annotated[dict, Depends(get_current_api_user)],
    audit_store: Annotated[AuditStore, Depends(get_auth_audit_store)],
    _csrf: Annotated[None, Depends(require_csrf)],
    payload: Annotated[dict[str, Any] | None, Body(default=None)] = None,
) -> dict:
    """Re-inject canned MVP demo events so the analyst can re-record the video
    without depending on real-world FortiGate denies. Each event is tagged
    with `source="demo.replay"`, an `attackType` attribute and a fresh
    `demoRunId` so they are easy to filter out of production dashboards.

    Optional JSON body: `{"attackTypes": ["port_scan", "brute_force", "c2_beacon"]}`.
    Omit or pass an empty list to inject the full canonical chain.
    """
    raw_types = (payload or {}).get("attackTypes") if isinstance(payload, dict) else None
    if raw_types is not None and not isinstance(raw_types, list):
        raise HTTPException(status_code=400, detail="attackTypes must be a list of strings")
    attack_types = [str(t) for t in raw_types] if raw_types else None

    now = datetime.now(UTC)
    demo_run_id = f"demo_{now.strftime('%Y%m%d_%H%M%S')}"
    events = _demo_replay_events(
        now=now, demo_run_id=demo_run_id, attack_types=attack_types
    )
    created: list[dict[str, Any]] = []
    for event in events:
        try:
            created.append(client.request("POST", "/events", json=event))
        except HTTPException:
            raise
        except Exception as exc:  # noqa: BLE001
            _audit(
                audit_store,
                request=request,
                current_user=current_user,
                action="soc.demo.replay",
                details={
                    "demoRunId": demo_run_id,
                    "error": str(exc),
                    "stage": event["eventType"],
                    "attackTypes": [e["attributes"]["attackType"] for e in events],
                },
                outcome="failure",
            )
            raise HTTPException(
                status_code=502,
                detail=f"Demo replay failed at {event['eventType']}: {exc}",
            ) from exc

    injected_types = [e["attributes"]["attackType"] for e in events]
    _audit(
        audit_store,
        request=request,
        current_user=current_user,
        action="soc.demo.replay",
        details={
            "demoRunId": demo_run_id,
            "eventCount": len(created),
            "service": "siem_kowalski",
            "attackTypes": injected_types,
        },
    )
    return {
        "demoRunId": demo_run_id,
        "eventCount": len(created),
        "attackTypes": injected_types,
        "eventIds": [event.get("id") for event in created if isinstance(event, dict) and event.get("id")],
    }


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


def _analysis_to_dict(analysis: IncidentAnalysis, *, analysis_id: str) -> dict[str, Any]:
    return {
        "id": analysis_id,
        "incidentId": analysis.incident_id,
        "headline": analysis.headline,
        "summary": analysis.summary,
        "riskScore": analysis.risk_score,
        "suggestedTriage": analysis.suggested_triage,
        "suggestedTicketStatus": analysis.suggested_ticket_status,
        "indicatorsOfCompromise": analysis.indicators_of_compromise,
        "nextSteps": analysis.next_steps,
        "references": analysis.references,
    }


_SOAR_NODE_MAPPING = {
    "firewall.block_ip": ("fortigate.recommend_block", True),
    "fortigate.block_ip": ("fortigate.recommend_block", True),
    "fortigate.recommend_block": ("fortigate.recommend_block", True),
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


def _containment_to_dict(suggestion: ContainmentSuggestion) -> dict[str, Any]:
    return {
        "incidentId": suggestion.incident_id,
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
    provider = get_ai_provider()
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
    response = _analysis_to_dict(analysis, analysis_id=analysis_id)
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
    provider = get_ai_provider()
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
            nodes.append({"id": approval_id, "type": "approval.required", "config": {"role": "admin"}})
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
        raise HTTPException(status_code=502, detail=f"Failed to create draft playbook: {exc}") from exc

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
        "suggestion": _containment_to_dict(suggestion),
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

    audit_action = "soc.ticket.contained" if new_ticket_status == "contained" else "soc.ticket.containment_paused"
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
    provider = get_ai_provider()
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
    return _containment_to_dict(suggestion)


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
            detail="Body must include at least one of triageLevel, ticketStatus, assigneeUserId, aiAnalysisId, note",
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
    return response


@router.get("/soc/playbook-runs/{run_id}")
def get_playbook_run(
    run_id: str,
    client: Annotated[SocClient, Depends(get_soar_client)],
    _current_user: Annotated[dict, Depends(get_current_api_user)],
) -> dict:
    return client.request("GET", f"/playbook-runs/{run_id}")


@router.post("/soc/playbook-runs/{run_id}/approve")
def approve_playbook_run(
    run_id: str,
    request: Request,
    client: Annotated[SocClient, Depends(get_soar_client)],
    current_user: Annotated[dict, Depends(require_admin_user)],
    audit_store: Annotated[AuditStore, Depends(get_auth_audit_store)],
    _csrf: Annotated[None, Depends(require_csrf)],
) -> dict:
    response = client.request("POST", f"/playbook-runs/{run_id}/approve", json={})
    _audit(
        audit_store,
        request=request,
        current_user=current_user,
        action="soc.playbook_run.approved",
        details={
            "runId": run_id,
            "playbookId": response.get("playbookId"),
            "incidentId": response.get("incidentId"),
            "service": "soar_skipper",
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
    audit_store: Annotated[AuditStore, Depends(get_auth_audit_store)],
    authorization: Annotated[str | None, Header(alias="Authorization")] = None,
) -> dict:
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Endpoint enrollment token required",
        )
    response = client.request(
        "POST",
        "/endpoint-events",
        json=payload,
        headers={"Authorization": authorization},
        pass_through_statuses={401, 403},
    )
    audit_store.record(
        action="xdr.endpoint_event.created",
        outcome="success",
        client_ip=_client_ip(request),
        user_agent=request.headers.get("user-agent"),
        details={
            "endpointId": payload.get("endpointId"),
            "eventType": payload.get("eventType"),
            "service": "xdr_rico",
            "actorType": "agent_private",
        },
    )
    return response


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


@router.post("/weapons/simulator/events")
def create_simulator_events(
    request: Request,
    client: Annotated[SocClient, Depends(get_xdr_client)],
    current_user: Annotated[dict, Depends(get_current_api_user)],
    audit_store: Annotated[AuditStore, Depends(get_auth_audit_store)],
    _csrf: Annotated[None, Depends(require_csrf)],
    payload: Annotated[dict[str, Any] | None, Body()] = None,
) -> dict:
    response = client.request("POST", "/simulator/events", json=payload or {})
    _audit(
        audit_store,
        request=request,
        current_user=current_user,
        action="xdr.simulator_events.created",
        details={"service": "xdr_rico", "count": response.get("createdEvents")},
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
