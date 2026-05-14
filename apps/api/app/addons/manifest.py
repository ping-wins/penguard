from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class AddonAuthField(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    label: str
    type: Literal["text", "url", "secret", "boolean", "number"]
    required: bool = False
    default: Any = None
    placeholder: str | None = None


class AddonAuth(BaseModel):
    kind: Literal["apiKey", "oauth2", "none"]
    fields: list[AddonAuthField] = Field(default_factory=list)


class AddonProvider(BaseModel):
    type: str
    auth: AddonAuth


class AddonRouteParam(BaseModel):
    name: str
    repeated: bool = False
    required: bool = False


class AddonRoute(BaseModel):
    id: str
    method: Literal["GET", "POST", "PUT", "PATCH", "DELETE"]
    path: str
    summary: str | None = None
    params: list[AddonRouteParam] = Field(default_factory=list)


class AddonManifest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    version: str
    name: str
    vendor: str
    category: str
    description: str
    icon: str | None = None
    min_dashboard_version: str | None = Field(default=None, alias="minDashboardVersion")
    provider: AddonProvider
    routes: list[AddonRoute] = Field(default_factory=list)
    widgets: list[str] = Field(default_factory=list)
    siem_event_types: list[str] = Field(default_factory=list, alias="siemEventTypes")
