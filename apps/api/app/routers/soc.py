from datetime import UTC, datetime, timedelta
from functools import lru_cache
from typing import Annotated, Any, Protocol

from fastapi import APIRouter, Body, Depends, Header, HTTPException, Query, Request, status

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


def _demo_replay_events(*, now: datetime, demo_run_id: str) -> list[dict[str, Any]]:
    """Synthetic burst designed to trip `denied_traffic_burst` and seed an
    obvious incident timeline for the MVP video. Counts are inflated past
    every detection threshold so the demo always produces an incident.
    """
    base = now.astimezone(UTC)

    def stamp(offset_seconds: int) -> str:
        return (
            (base - timedelta(seconds=offset_seconds))
            .isoformat(timespec="milliseconds")
            .replace("+00:00", "Z")
        )

    return [
        {
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
            },
        },
        {
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
            },
        },
        {
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
            },
        },
    ]


@router.post("/soc/demo/replay")
def replay_demo_incident(
    request: Request,
    client: Annotated[SocClient, Depends(get_siem_client)],
    current_user: Annotated[dict, Depends(get_current_api_user)],
    audit_store: Annotated[AuditStore, Depends(get_auth_audit_store)],
    _csrf: Annotated[None, Depends(require_csrf)],
) -> dict:
    """Re-inject the canned MVP demo incident so the analyst can re-record the
    video without depending on real-world FortiGate denies. Each event is
    tagged with `source="demo.replay"` and a fresh `demoRunId` so they are
    easy to filter out of production dashboards.
    """
    now = datetime.now(UTC)
    demo_run_id = f"demo_{now.strftime('%Y%m%d_%H%M%S')}"
    events = _demo_replay_events(now=now, demo_run_id=demo_run_id)
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
                },
                outcome="failure",
            )
            raise HTTPException(
                status_code=502,
                detail=f"Demo replay failed at {event['eventType']}: {exc}",
            ) from exc

    _audit(
        audit_store,
        request=request,
        current_user=current_user,
        action="soc.demo.replay",
        details={
            "demoRunId": demo_run_id,
            "eventCount": len(created),
            "service": "siem_kowalski",
        },
    )
    return {
        "demoRunId": demo_run_id,
        "eventCount": len(created),
        "eventIds": [event.get("id") for event in created if isinstance(event, dict) and event.get("id")],
    }


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
