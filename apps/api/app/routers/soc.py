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
) -> None:
    audit_store.record(
        action=action,
        outcome="success",
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
