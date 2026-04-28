from functools import lru_cache
from typing import Annotated

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

router = APIRouter(tags=["integrations"])
FortiGateService = FortiGateIntegrationService | MockFortiGateIntegrationService
AuditStore = InMemoryAuthAuditStore | SqlAlchemyAuthAuditStore


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


@router.get("/integrations")
def list_integrations(
    service: Annotated[FortiGateService, Depends(get_fortigate_integration_service)],
    current_user: Annotated[dict, Depends(get_current_api_user)],
) -> dict:
    return service.list(owner_user_id=str(current_user["id"]))


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


def _client_ip(request: Request) -> str:
    if request.client is None:
        return "unknown"
    return request.client.host
