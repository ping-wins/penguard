import logging
from functools import lru_cache
from typing import Annotated, Any, Protocol

from fastapi import APIRouter, Depends, HTTPException, Query

from app.auth.dependencies import get_current_api_user
from app.auth.token_cipher import TokenCipher
from app.core.config import get_settings
from app.integrations.fortigate.store import SqlAlchemyFortiGateIntegrationStore
from app.integrations.fortigate.widgets import (
    FortiGateWidgetDataService,
    MockFortiGateWidgetDataService,
)
from app.integrations.penguin_tools import (
    MockPenguinToolIntegrationService,
    PenguinToolIntegrationService,
    SqlAlchemyPenguinToolIntegrationStore,
    build_penguin_tool_clients,
    expected_tool_type_for_widget,
)
from app.routers.soc import get_siem_client, get_soar_client, get_xdr_client

router = APIRouter(tags=["widgets"])
logger = logging.getLogger("uvicorn.error")
FortiGateWidgetService = FortiGateWidgetDataService | MockFortiGateWidgetDataService
PenguinToolService = PenguinToolIntegrationService | MockPenguinToolIntegrationService
SOC_WIDGET_IDS = {
    "soc-incidents-by-severity",
    "soc-recent-incidents",
    "soc-top-entities",
    "xdr-endpoint-health",
    "soar-active-playbook-runs",
}


class SocWidgetClient(Protocol):
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


@lru_cache
def get_fortigate_widget_service() -> FortiGateWidgetService:
    settings = get_settings()
    if settings.mock_mode:
        return MockFortiGateWidgetDataService()
    return FortiGateWidgetDataService(
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


@router.get("/widgets/{widget_id}/data")
def get_widget_data(
    widget_id: str,
    service: Annotated[FortiGateWidgetService, Depends(get_fortigate_widget_service)],
    penguin_service: Annotated[
        PenguinToolService, Depends(get_penguin_tool_integration_service)
    ],
    siem_client: Annotated[SocWidgetClient, Depends(get_siem_client)],
    xdr_client: Annotated[SocWidgetClient, Depends(get_xdr_client)],
    soar_client: Annotated[SocWidgetClient, Depends(get_soar_client)],
    current_user: Annotated[dict, Depends(get_current_api_user)],
    integration_id: Annotated[str | None, Query(alias="integrationId")] = None,
) -> dict:
    if widget_id in SOC_WIDGET_IDS:
        if integration_id is None:
            raise HTTPException(status_code=422, detail="integrationId is required")
        expected_type = expected_tool_type_for_widget(widget_id)
        integration = penguin_service.get(
            integration_id=integration_id,
            owner_user_id=str(current_user["id"]),
        )
        if integration is None or integration.get("type") != expected_type:
            raise HTTPException(status_code=404, detail="Widget data not found")
        return _soc_widget_data(
            widget_id,
            integration_id=integration_id,
            siem_client=siem_client,
            xdr_client=xdr_client,
            soar_client=soar_client,
        )
    if integration_id is None:
        raise HTTPException(status_code=422, detail="integrationId is required")
    try:
        return service.get_widget_data(
            widget_id,
            integration_id,
            owner_user_id=str(current_user["id"]),
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Widget data not found") from exc


def _soc_widget_data(
    widget_id: str,
    *,
    integration_id: str,
    siem_client: SocWidgetClient,
    xdr_client: SocWidgetClient,
    soar_client: SocWidgetClient,
) -> dict[str, Any]:
    match widget_id:
        case "soc-incidents-by-severity":
            incidents = _items(siem_client.request("GET", "/incidents", params={"limit": 200}))
            data = _incidents_by_severity(incidents)
            source = "siem_kowalski"
        case "soc-recent-incidents":
            incidents = _items(siem_client.request("GET", "/incidents", params={"limit": 10}))
            data = {"incidents": incidents, "count": len(incidents)}
            source = "siem_kowalski"
        case "soc-top-entities":
            incidents = _items(siem_client.request("GET", "/incidents", params={"limit": 200}))
            data = {"entities": _top_entities(incidents)}
            source = "siem_kowalski"
        case "xdr-endpoint-health":
            endpoints = _items(xdr_client.request("GET", "/endpoints"))
            data = _endpoint_health(endpoints)
            source = "xdr_rico"
        case "soar-active-playbook-runs":
            runs = _items(soar_client.request("GET", "/playbook-runs"))
            active_runs = [run for run in runs if run.get("status") != "completed"]
            data = {"runs": active_runs, "count": len(active_runs)}
            source = "soar_skipper"
        case _:
            raise HTTPException(status_code=404, detail="Widget data not found")
    _log_soc_widget_data(
        widget_id=widget_id,
        integration_id=integration_id,
        source=source,
        data=data,
    )
    return {
        "widgetId": widget_id,
        "integrationId": integration_id,
        "status": "ready",
        "data": data,
        "meta": {
            "source": source,
            "cacheTtlSeconds": 5,
            "refreshIntervalSeconds": 5,
        },
    }


def _log_soc_widget_data(
    *,
    widget_id: str,
    integration_id: str,
    source: str,
    data: dict[str, Any],
) -> None:
    summary = _soc_widget_summary(widget_id, data)
    if _soc_widget_is_empty(widget_id, data):
        logger.info(
            "soc_widget_data_empty widget_id=%s integration_id=%s source=%s summary=%s "
            "hint=seed_demo_data_or_ingest_events",
            widget_id,
            integration_id,
            source,
            summary,
        )
        return
    logger.info(
        "soc_widget_data_ready widget_id=%s integration_id=%s source=%s summary=%s",
        widget_id,
        integration_id,
        source,
        summary,
    )


def _soc_widget_summary(widget_id: str, data: dict[str, Any]) -> str:
    match widget_id:
        case "soc-incidents-by-severity":
            return f"items={len(data.get('items', []))} total={data.get('total', 0)}"
        case "soc-recent-incidents":
            return f"incidents={len(data.get('incidents', []))} count={data.get('count', 0)}"
        case "soc-top-entities":
            return f"entities={len(data.get('entities', []))}"
        case "xdr-endpoint-health":
            return f"endpoints={len(data.get('endpoints', []))} total={data.get('total', 0)}"
        case "soar-active-playbook-runs":
            return f"runs={len(data.get('runs', []))} count={data.get('count', 0)}"
        case _:
            return "unknown"


def _soc_widget_is_empty(widget_id: str, data: dict[str, Any]) -> bool:
    match widget_id:
        case "soc-incidents-by-severity":
            return not data.get("items")
        case "soc-recent-incidents":
            return not data.get("incidents")
        case "soc-top-entities":
            return not data.get("entities")
        case "xdr-endpoint-health":
            return not data.get("endpoints")
        case "soar-active-playbook-runs":
            return not data.get("runs")
        case _:
            return False


def _items(payload: dict[str, Any]) -> list[dict[str, Any]]:
    items = payload.get("items", [])
    if not isinstance(items, list):
        return []
    return [item for item in items if isinstance(item, dict)]


def _incidents_by_severity(incidents: list[dict[str, Any]]) -> dict[str, Any]:
    order = ["critical", "high", "medium", "low", "informational"]
    counts = {severity: 0 for severity in order}
    for incident in incidents:
        severity = str(incident.get("severity") or "informational").lower()
        counts.setdefault(severity, 0)
        counts[severity] += 1
    return {
        "items": [
            {"severity": severity, "count": count}
            for severity, count in counts.items()
            if count > 0
        ],
        "total": len(incidents),
    }


def _top_entities(incidents: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counts: dict[tuple[str, str], int] = {}
    for incident in incidents:
        entities = incident.get("entities")
        if not isinstance(entities, dict):
            continue
        for key, value in entities.items():
            if value in (None, ""):
                continue
            entity_key = (str(key), str(value))
            counts[entity_key] = counts.get(entity_key, 0) + 1
    rows = [
        {"field": field, "value": value, "count": count}
        for (field, value), count in counts.items()
    ]
    return sorted(rows, key=lambda row: row["count"], reverse=True)[:10]


def _endpoint_health(endpoints: list[dict[str, Any]]) -> dict[str, Any]:
    summary: dict[str, int] = {}
    for endpoint in endpoints:
        health = str(endpoint.get("health") or "unknown")
        summary[health] = summary.get(health, 0) + 1
    return {
        "endpoints": endpoints,
        "summary": summary,
        "total": len(endpoints),
    }
