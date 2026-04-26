from fastapi import APIRouter, status
from pydantic import BaseModel, ConfigDict, Field, HttpUrl

from app.core.fixtures import load_fixture

router = APIRouter(tags=["integrations"])


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


@router.post(
    "/integrations/fortigate",
    status_code=status.HTTP_201_CREATED,
)
def create_fortigate_integration(_: FortiGateIntegrationCreate) -> dict:
    return load_fixture("fortigate_integration_created")


@router.post("/integrations/fortigate/test")
def test_fortigate_connection(_: FortiGateConnectionTest) -> dict:
    return load_fixture("fortigate_connection_test")


@router.get("/integrations")
def list_integrations() -> dict:
    return load_fixture("integrations_list")
