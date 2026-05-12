from datetime import UTC, datetime
from functools import lru_cache
from typing import Annotated, Any, Literal, Protocol

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, ConfigDict, Field, HttpUrl

from app.auth.audit import InMemoryAuthAuditStore, SqlAlchemyAuthAuditStore
from app.auth.csrf_dependency import require_csrf
from app.auth.dependencies import get_auth_audit_store, get_current_api_user
from app.auth.token_cipher import TokenCipher
from app.core.config import get_settings
from app.integrations.fortigate.service import (
    FortiGateConnectionFailed,
    FortiGateIntegrationService,
    MockFortiGateIntegrationService,
)
from app.integrations.fortigate.store import SqlAlchemyFortiGateIntegrationStore
from app.integrations.penguin_tools import (
    MockPenguinToolIntegrationService,
    PenguinToolConnectionFailed,
    PenguinToolIntegrationService,
    SqlAlchemyPenguinToolIntegrationStore,
    build_penguin_tool_clients,
)
from app.routers.soc import get_siem_client
from app.routers.widgets import (
    FortiGateWidgetService,
    get_fortigate_widget_service,
)

router = APIRouter(tags=["integrations"])
FortiGateService = FortiGateIntegrationService | MockFortiGateIntegrationService
PenguinToolService = PenguinToolIntegrationService | MockPenguinToolIntegrationService
AuditStore = InMemoryAuthAuditStore | SqlAlchemyAuthAuditStore
PenguinToolType = Literal["siem_kowalski", "soar_skipper", "xdr_rico"]


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


class FortiGateIntegrationCreate(BaseModel):
    name: str
    host: HttpUrl
    api_key: str = Field(alias="apiKey", min_length=16)
    verify_tls: bool = Field(alias="verifyTls", default=True)

    model_config = ConfigDict(populate_by_name=True)


class FortiGateConnectionTest(BaseModel):
    host: HttpUrl
    api_key: str = Field(alias="apiKey", min_length=16)
    verify_tls: bool = Field(alias="verifyTls", default=True)

    model_config = ConfigDict(populate_by_name=True)


class PenguinToolIntegrationCreate(BaseModel):
    type: PenguinToolType
    name: str | None = None


class PenguinToolConnectionTest(BaseModel):
    type: PenguinToolType


@lru_cache
def get_fortigate_integration_service() -> FortiGateService:
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


@lru_cache
def get_penguin_tool_integration_service() -> PenguinToolService:
    settings = get_settings()
    if settings.mock_mode:
        return MockPenguinToolIntegrationService()
    return PenguinToolIntegrationService(
        store=SqlAlchemyPenguinToolIntegrationStore(database_url=settings.database_url),
        clients=build_penguin_tool_clients(
            siem_kowalski_url=settings.siem_kowalski_url,
            soar_skipper_url=settings.soar_skipper_url,
            xdr_rico_url=settings.xdr_rico_url,
            timeout_seconds=settings.internal_service_timeout_seconds,
        ),
    )


@router.post(
    "/integrations/fortigate",
    status_code=status.HTTP_201_CREATED,
)
def create_fortigate_integration(
    request: Request,
    payload: FortiGateIntegrationCreate,
    service: Annotated[FortiGateService, Depends(get_fortigate_integration_service)],
    current_user: Annotated[dict, Depends(get_current_api_user)],
    audit_store: Annotated[AuditStore, Depends(get_auth_audit_store)],
    _csrf: Annotated[None, Depends(require_csrf)],
) -> dict:
    try:
        created = service.create(
            owner_user_id=str(current_user["id"]),
            name=payload.name,
            host=str(payload.host),
            api_key=payload.api_key,
            verify_tls=payload.verify_tls,
        )
    except FortiGateConnectionFailed as exc:
        audit_store.record(
            action="integration.fortigate.created",
            outcome="failed",
            email=current_user.get("email"),
            user_id=str(current_user["id"]),
            client_ip=_client_ip(request),
            user_agent=request.headers.get("user-agent"),
            details={
                "host": str(payload.host),
                "verifyTls": payload.verify_tls,
                "error": str(exc),
            },
        )
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    audit_store.record(
        action="integration.fortigate.created",
        outcome="success",
        email=current_user.get("email"),
        user_id=str(current_user["id"]),
        client_ip=_client_ip(request),
        user_agent=request.headers.get("user-agent"),
        details={
            "integrationId": created["id"],
            "host": str(payload.host),
            "verifyTls": payload.verify_tls,
        },
    )
    return created


@router.post("/integrations/fortigate/test")
def test_fortigate_connection(
    payload: FortiGateConnectionTest,
    service: Annotated[FortiGateService, Depends(get_fortigate_integration_service)],
    _current_user: Annotated[dict, Depends(get_current_api_user)],
    _csrf: Annotated[None, Depends(require_csrf)],
) -> dict:
    return service.test_connection(
        host=str(payload.host),
        api_key=payload.api_key,
        verify_tls=payload.verify_tls,
    )


@router.post("/integrations/penguin-tools/test")
def test_penguin_tool_connection(
    payload: PenguinToolConnectionTest,
    service: Annotated[PenguinToolService, Depends(get_penguin_tool_integration_service)],
    _current_user: Annotated[dict, Depends(get_current_api_user)],
    _csrf: Annotated[None, Depends(require_csrf)],
) -> dict:
    return service.test_connection(tool_type=payload.type)


@router.post(
    "/integrations/penguin-tools",
    status_code=status.HTTP_201_CREATED,
)
def create_penguin_tool_integration(
    request: Request,
    payload: PenguinToolIntegrationCreate,
    service: Annotated[PenguinToolService, Depends(get_penguin_tool_integration_service)],
    current_user: Annotated[dict, Depends(get_current_api_user)],
    audit_store: Annotated[AuditStore, Depends(get_auth_audit_store)],
    _csrf: Annotated[None, Depends(require_csrf)],
) -> dict:
    try:
        created = service.create(
            owner_user_id=str(current_user["id"]),
            tool_type=payload.type,
            name=payload.name,
        )
    except PenguinToolConnectionFailed as exc:
        audit_store.record(
            action="integration.penguin_tool.created",
            outcome="failed",
            email=current_user.get("email"),
            user_id=str(current_user["id"]),
            client_ip=_client_ip(request),
            user_agent=request.headers.get("user-agent"),
            details={
                "type": payload.type,
                "service": payload.type,
                "error": str(exc),
            },
        )
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    audit_store.record(
        action="integration.penguin_tool.created",
        outcome="success",
        email=current_user.get("email"),
        user_id=str(current_user["id"]),
        client_ip=_client_ip(request),
        user_agent=request.headers.get("user-agent"),
        details={
            "integrationId": created["id"],
            "type": created["type"],
            "service": created["type"],
        },
    )
    return created


@router.get("/integrations")
def list_integrations(
    fortigate_service: Annotated[FortiGateService, Depends(get_fortigate_integration_service)],
    penguin_service: Annotated[PenguinToolService, Depends(get_penguin_tool_integration_service)],
    current_user: Annotated[dict, Depends(get_current_api_user)],
) -> dict:
    owner_user_id = str(current_user["id"])
    fortigate_items = fortigate_service.list(owner_user_id=owner_user_id).get("items", [])
    penguin_items = penguin_service.list(owner_user_id=owner_user_id).get("items", [])
    return {"items": [*fortigate_items, *penguin_items]}


@router.delete("/integrations/{integration_id}")
def delete_integration(
    integration_id: str,
    request: Request,
    fortigate_service: Annotated[FortiGateService, Depends(get_fortigate_integration_service)],
    penguin_service: Annotated[PenguinToolService, Depends(get_penguin_tool_integration_service)],
    current_user: Annotated[dict, Depends(get_current_api_user)],
    audit_store: Annotated[AuditStore, Depends(get_auth_audit_store)],
    _csrf: Annotated[None, Depends(require_csrf)],
) -> dict:
    owner_user_id = str(current_user["id"])
    if not integration_id.startswith("int_fgt_"):
        penguin_integration = penguin_service.get(
            integration_id=integration_id,
            owner_user_id=owner_user_id,
        )
        if penguin_integration is None:
            audit_store.record(
                action="integration.penguin_tool.deleted",
                outcome="failed",
                email=current_user.get("email"),
                user_id=owner_user_id,
                client_ip=_client_ip(request),
                user_agent=request.headers.get("user-agent"),
                details={
                    "integrationId": integration_id,
                    "error": "Integration not found",
                },
            )
            raise HTTPException(status_code=404, detail="Integration not found")
        deleted = penguin_service.delete(
            integration_id=integration_id,
            owner_user_id=owner_user_id,
        )
        if deleted:
            audit_store.record(
                action="integration.penguin_tool.deleted",
                outcome="success",
                email=current_user.get("email"),
                user_id=owner_user_id,
                client_ip=_client_ip(request),
                user_agent=request.headers.get("user-agent"),
                details={
                    "integrationId": integration_id,
                    "type": (penguin_integration or {}).get("type"),
                },
            )
            return {"deleted": True, "id": integration_id}
        raise HTTPException(status_code=404, detail="Integration not found")

    deleted = fortigate_service.delete(
        integration_id=integration_id,
        owner_user_id=owner_user_id,
    )
    if not deleted:
        audit_store.record(
            action="integration.fortigate.deleted",
            outcome="failed",
            email=current_user.get("email"),
            user_id=owner_user_id,
            client_ip=_client_ip(request),
            user_agent=request.headers.get("user-agent"),
            details={
                "integrationId": integration_id,
                "error": "Integration not found",
            },
        )
        raise HTTPException(status_code=404, detail="Integration not found")
    audit_store.record(
        action="integration.fortigate.deleted",
        outcome="success",
        email=current_user.get("email"),
        user_id=owner_user_id,
        client_ip=_client_ip(request),
        user_agent=request.headers.get("user-agent"),
        details={"integrationId": integration_id},
    )
    return {"deleted": True, "id": integration_id}


@router.post("/integrations/fortigate/{integration_id}/health-check")
def run_fortigate_health_check(
    integration_id: str,
    request: Request,
    service: Annotated[FortiGateService, Depends(get_fortigate_integration_service)],
    current_user: Annotated[dict, Depends(get_current_api_user)],
    audit_store: Annotated[AuditStore, Depends(get_auth_audit_store)],
    _csrf: Annotated[None, Depends(require_csrf)],
) -> dict:
    try:
        result = service.run_health_check(
            integration_id=integration_id,
            owner_user_id=str(current_user["id"]),
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Integration not found") from exc
    audit_store.record(
        action="integration.fortigate.health_checked",
        outcome="success" if result["ok"] else "failed",
        email=current_user.get("email"),
        user_id=str(current_user["id"]),
        client_ip=_client_ip(request),
        user_agent=request.headers.get("user-agent"),
        details={
            "integrationId": integration_id,
            "status": result["status"],
            "ok": result["ok"],
        },
    )
    return result


@router.get("/integrations/fortigate/{integration_id}/health-checks")
def list_fortigate_health_checks(
    integration_id: str,
    service: Annotated[FortiGateService, Depends(get_fortigate_integration_service)],
    current_user: Annotated[dict, Depends(get_current_api_user)],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> dict:
    try:
        return service.list_health_checks(
            integration_id=integration_id,
            owner_user_id=str(current_user["id"]),
            limit=limit,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Integration not found") from exc


@router.post("/soc/fortigate/{integration_id}/ingest-events")
def ingest_fortigate_events_into_siem(
    integration_id: str,
    request: Request,
    widget_service: Annotated[FortiGateWidgetService, Depends(get_fortigate_widget_service)],
    siem_client: Annotated[SocClient, Depends(get_siem_client)],
    current_user: Annotated[dict, Depends(get_current_api_user)],
    audit_store: Annotated[AuditStore, Depends(get_auth_audit_store)],
    _csrf: Annotated[None, Depends(require_csrf)],
) -> dict:
    try:
        widget_payload = widget_service.get_widget_data(
            "fortigate-recent-events",
            integration_id,
            owner_user_id=str(current_user["id"]),
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Integration not found") from exc

    events = widget_payload.get("data", {}).get("events", [])
    created_events = []
    for event in events:
        if not isinstance(event, dict):
            continue
        created_events.append(
            siem_client.request(
                "POST",
                "/events",
                json=_fortigate_event_to_siem_event(event, integration_id=integration_id),
            )
        )

    audit_store.record(
        action="soc.fortigate_events.ingested",
        outcome="success",
        email=current_user.get("email"),
        user_id=str(current_user["id"]),
        client_ip=_client_ip(request),
        user_agent=request.headers.get("user-agent"),
        details={
            "integrationId": integration_id,
            "count": len(created_events),
            "service": "siem_kowalski",
        },
    )
    return {
        "integrationId": integration_id,
        "createdCount": len(created_events),
        "eventIds": [event.get("id") for event in created_events if event.get("id")],
    }


def _fortigate_event_to_siem_event(
    event: dict[str, Any],
    *,
    integration_id: str,
) -> dict[str, Any]:
    action = str(event.get("action") or "").lower()
    event_type = "network.deny" if action in {"deny", "blocked", "block"} else "network.event"
    return {
        "source": "fortigate",
        "eventType": event_type,
        "severity": str(event.get("severity") or "informational").lower(),
        "occurredAt": event.get("timestamp") or _now_iso(),
        "entities": {
            "sourceIp": event.get("sourceIp"),
            "destinationIp": event.get("destinationIp"),
            "integrationId": integration_id,
        },
        "attributes": {
            "action": event.get("action"),
            "type": event.get("type"),
            "subtype": event.get("subtype"),
            "message": event.get("message"),
            "count": 1,
        },
    }


def _now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _client_ip(request: Request) -> str:
    if request.client is None:
        return "unknown"
    return request.client.host
