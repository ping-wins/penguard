import logging
from datetime import UTC, datetime, timedelta
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
    "soar-playbook-run-history",
}
WAF_WIDGET_IDS = {
    "waf-dos-rate",
    "waf-dos-top-ips",
    "waf-dos-feed",
}
SELF_MANAGED_WIDGET_IDS = {
    "soc-policy-manager",
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
    penguin_service: Annotated[PenguinToolService, Depends(get_penguin_tool_integration_service)],
    siem_client: Annotated[SocWidgetClient, Depends(get_siem_client)],
    xdr_client: Annotated[SocWidgetClient, Depends(get_xdr_client)],
    soar_client: Annotated[SocWidgetClient, Depends(get_soar_client)],
    current_user: Annotated[dict, Depends(get_current_api_user)],
    integration_id: Annotated[str | None, Query(alias="integrationId")] = None,
    source: Annotated[str, Query()] = "siem",
    window: Annotated[str, Query()] = "1h",
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> dict:
    if widget_id in SELF_MANAGED_WIDGET_IDS:
        return {
            "widgetId": widget_id,
            "integrationId": integration_id or "policy-manager",
            "status": "ready",
            "data": {"selfManaged": True},
            "refreshedAt": datetime.now(UTC).isoformat(timespec="milliseconds").replace(
                "+00:00",
                "Z",
            ),
            "meta": {
                "source": "soc",
                "cacheTtlSeconds": 0,
                "refreshIntervalSeconds": 0,
            },
        }
    if widget_id in WAF_WIDGET_IDS:
        return _waf_widget_data(
            widget_id,
            source=source,
            window=window,
            limit=limit,
            siem_client=siem_client,
        )
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
        case "soar-playbook-run-history":
            runs = _items(soar_client.request("GET", "/playbook-runs"))
            data = {"runs": runs, "count": len(runs), "summary": _playbook_run_summary(runs)}
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
        case "soar-playbook-run-history":
            summary = data.get("summary") if isinstance(data.get("summary"), dict) else {}
            return (
                f"runs={len(data.get('runs', []))} count={data.get('count', 0)} "
                f"active={summary.get('active', 0)} completed={summary.get('completed', 0)}"
            )
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
        case "soar-playbook-run-history":
            return not data.get("runs")
        case _:
            return False


def _items(payload: dict[str, Any]) -> list[dict[str, Any]]:
    items = payload.get("items", [])
    if not isinstance(items, list):
        return []
    return [item for item in items if isinstance(item, dict)]


def _playbook_run_summary(runs: list[dict[str, Any]]) -> dict[str, int]:
    summary = {
        "active": 0,
        "completed": 0,
        "failed": 0,
        "running": 0,
        "waitingApproval": 0,
    }
    for run in runs:
        status = str(run.get("status") or "").lower()
        if status in {"completed", "succeeded"}:
            summary["completed"] += 1
        elif status in {"failed", "error"}:
            summary["failed"] += 1
        else:
            summary["active"] += 1
        if status == "running":
            summary["running"] += 1
        if status in {"waiting_approval", "pending_approval"}:
            summary["waitingApproval"] += 1
    return summary


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
        {"field": field, "value": value, "count": count} for (field, value), count in counts.items()
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


def _window_seconds(window: str) -> int:
    return {"15m": 900, "1h": 3600, "6h": 21600, "24h": 86400}.get(window, 3600)


def _parse_dt(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=UTC)
    except (TypeError, ValueError):
        return datetime.min.replace(tzinfo=UTC)


def _waf_dos_incidents(siem_client: SocWidgetClient, *, since: "datetime") -> list[dict[str, Any]]:
    raw = _items(siem_client.request("GET", "/incidents", params={"limit": 500}))
    return [
        inc for inc in raw
        if inc.get("ruleId") == "fortiweb_dos_activity"
        and _parse_dt(inc.get("createdAt")) >= since
    ]


def _waf_dos_events(
    siem_client: SocWidgetClient,
    *,
    since: "datetime",
    limit: int,
) -> list[dict[str, Any]]:
    raw = _items(
        siem_client.request(
            "GET",
            "/events",
            params={"eventType": "waf.dos", "limit": limit},
        )
    )
    return [e for e in raw if _parse_dt(e.get("occurredAt")) >= since]


def _waf_dos_rate(
    source: str,
    *,
    window: str,
    siem_client: SocWidgetClient,
) -> dict[str, Any]:
    seconds = _window_seconds(window)
    since = datetime.now(UTC) - timedelta(seconds=seconds)

    use_raw = source == "raw"
    if use_raw:
        records = _waf_dos_events(siem_client, since=since, limit=500)
    else:
        records = _waf_dos_incidents(siem_client, since=since)

    buckets: dict[str, dict[str, int]] = {}
    for record in records:
        ts_key = "occurredAt" if use_raw else "createdAt"
        dt = _parse_dt(record.get(ts_key))
        bucket_key = dt.strftime("%Y-%m-%dT%H:%M:00Z")
        if bucket_key not in buckets:
            buckets[bucket_key] = {"blocked": 0, "allowed": 0}
        if use_raw:
            attrs = record.get("attributes") or {}
            blocked = str(attrs.get("action", "")).lower() in {
                "block",
                "blocked",
                "deny",
                "dropped",
            }
        else:
            blocked = True
        if blocked:
            buckets[bucket_key]["blocked"] += 1
        else:
            buckets[bucket_key]["allowed"] += 1

    sorted_buckets = [
        {"ts": k, "blocked": v["blocked"], "allowed": v["allowed"]}
        for k, v in sorted(buckets.items())
    ]
    return {"buckets": sorted_buckets, "window": window, "source": source}


def _waf_dos_top_ips(
    source: str,
    *,
    window: str,
    limit: int,
    siem_client: SocWidgetClient,
) -> dict[str, Any]:
    seconds = _window_seconds(window)
    since = datetime.now(UTC) - timedelta(seconds=seconds)

    use_raw = source == "raw"
    if use_raw:
        records = _waf_dos_events(siem_client, since=since, limit=500)
    else:
        records = _waf_dos_incidents(siem_client, since=since)

    ip_data: dict[str, dict[str, Any]] = {}
    for record in records:
        if use_raw:
            ip = str(record.get("entities", {}).get("sourceIp") or "")
            ts = str(record.get("occurredAt") or "")
            attrs = record.get("attributes") or {}
            is_blocked = str(attrs.get("action", "")).lower() in {
                "block",
                "blocked",
                "deny",
                "dropped",
            }
        else:
            ip = str(record.get("entities", {}).get("sourceIp") or "")
            ts = str(record.get("createdAt") or "")
            is_blocked = True
        if not ip:
            continue
        if ip not in ip_data:
            ip_data[ip] = {"count": 0, "lastSeen": "", "blocked": False}
        ip_data[ip]["count"] += 1
        if is_blocked:
            ip_data[ip]["blocked"] = True
        if ts > ip_data[ip]["lastSeen"]:
            ip_data[ip]["lastSeen"] = ts

    rows = [
        {"ip": ip, "count": v["count"], "lastSeen": v["lastSeen"], "blocked": v["blocked"]}
        for ip, v in ip_data.items()
    ]
    rows.sort(key=lambda r: r["count"], reverse=True)
    return {"rows": rows[:limit], "source": source}


def _waf_dos_feed(
    source: str,
    *,
    limit: int,
    siem_client: SocWidgetClient,
) -> dict[str, Any]:
    # Feed always shows last 24h regardless of the chart window selector.
    since = datetime.now(UTC) - timedelta(hours=24)

    if source == "raw":
        records = _waf_dos_events(siem_client, since=since, limit=500)
        items_out = [
            {
                "id": r.get("id") or "",
                "ts": r.get("occurredAt") or "",
                "sourceIp": r.get("entities", {}).get("sourceIp") or "",
                "action": r.get("attributes", {}).get("action") or "",
                "severity": r.get("severity") or "medium",
                "message": r.get("message") or "DoS event",
                "policy": r.get("attributes", {}).get("policy") or "",
            }
            for r in records[:limit]
        ]
    else:
        records = _waf_dos_incidents(siem_client, since=since)
        records.sort(key=lambda r: r.get("createdAt") or "", reverse=True)
        items_out = [
            {
                "id": r.get("id") or "",
                "ts": r.get("createdAt") or "",
                "sourceIp": r.get("entities", {}).get("sourceIp") or "",
                "action": "block",
                "severity": r.get("severity") or "critical",
                "message": r.get("summary") or r.get("title") or "DoS activity detected",
                "policy": r.get("attributes", {}).get("policy") or "",
            }
            for r in records[:limit]
        ]
    return {"items": items_out, "source": source}


def _waf_widget_data(
    widget_id: str,
    *,
    source: str,
    window: str,
    limit: int,
    siem_client: SocWidgetClient,
) -> dict[str, Any]:
    normalized_source = source if source in {"siem", "raw"} else "siem"
    match widget_id:
        case "waf-dos-rate":
            data = _waf_dos_rate(normalized_source, window=window, siem_client=siem_client)
        case "waf-dos-top-ips":
            data = _waf_dos_top_ips(
                normalized_source,
                window=window,
                limit=limit,
                siem_client=siem_client,
            )
        case "waf-dos-feed":
            data = _waf_dos_feed(normalized_source, limit=limit, siem_client=siem_client)
        case _:
            raise HTTPException(status_code=404, detail="Widget data not found")
    logger.info(
        "waf_widget_data_ready widget_id=%s source=%s",
        widget_id,
        normalized_source,
    )
    return {
        "widgetId": widget_id,
        "status": "ready",
        "data": data,
        "meta": {
            "source": normalized_source,
            "cacheTtlSeconds": 5,
            "refreshIntervalSeconds": 5,
        },
    }
