from functools import lru_cache
from typing import Annotated

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, ConfigDict, Field, HttpUrl

from app.auth.dependencies import get_current_api_user
from app.auth.token_cipher import TokenCipher
from app.core.config import get_settings
from app.integrations.fortigate.service import (
    FortiGateIntegrationService,
    MockFortiGateIntegrationService,
)
from app.integrations.fortigate.store import SqlAlchemyFortiGateIntegrationStore

router = APIRouter(tags=["integrations"])
FortiGateService = FortiGateIntegrationService | MockFortiGateIntegrationService


class FortiGateIntegrationCreate(BaseModel):
    name: str
    host: HttpUrl
    api_key: str = Field(alias="apiKey")
    verify_tls: bool = Field(alias="verifyTls", default=True)

    model_config = ConfigDict(populate_by_name=True)


class FortiGateConnectionTest(BaseModel):
    host: HttpUrl
    api_key: str = Field(alias="apiKey")
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
    payload: FortiGateIntegrationCreate,
    service: Annotated[FortiGateService, Depends(get_fortigate_integration_service)],
    current_user: Annotated[dict, Depends(get_current_api_user)],
) -> dict:
    return service.create(
        owner_user_id=str(current_user["id"]),
        name=payload.name,
        host=str(payload.host),
        api_key=payload.api_key,
        verify_tls=payload.verify_tls,
    )


@router.post("/integrations/fortigate/test")
def test_fortigate_connection(
    payload: FortiGateConnectionTest,
    service: Annotated[FortiGateService, Depends(get_fortigate_integration_service)],
    _current_user: Annotated[dict, Depends(get_current_api_user)],
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
