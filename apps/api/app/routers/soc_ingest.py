"""Push-based ingestion endpoint for FortiGate (and compatible) log webhooks.

Complements the existing pull-based `_run_fortigate_event_ingestion` flow with
a low-latency path: the device fires an HTTP webhook on each interesting log
line (e.g. admin-login-failure) and the BFF translates that to a SIEM event,
which siem-kowalski matches against detection rules.

Auth is a single shared bearer token (`PENGUARD_SOC_INGEST_TOKEN`); the
endpoint is unauthenticated otherwise and skips CSRF because FortiGate
Automation Stitches cannot carry session cookies or CSRF headers.

A small in-memory aggregator collapses bursts (same eventType + sourceIp +
user within 60s) to a single emission so that hydra-style 100-attempts/sec
brute-force runs produce one incident, not one hundred.
"""

from __future__ import annotations

import hmac
import logging
import threading
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from functools import lru_cache
from typing import Annotated, Any, Protocol

from fastapi import APIRouter, Body, Depends, Header, HTTPException, Request, status

from app.auth.audit import InMemoryAuthAuditStore, SqlAlchemyAuthAuditStore
from app.auth.dependencies import get_auth_audit_store
from app.core.config import get_settings
from app.routers.integrations import get_fortiweb_integration_service
from app.routers.soc import get_siem_client

logger = logging.getLogger(__name__)

router = APIRouter(tags=["soc-ingest"])

AuditStore = InMemoryAuthAuditStore | SqlAlchemyAuthAuditStore


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
    ) -> dict[str, Any]: ...


class FortiWebTelemetryService(Protocol):
    def verify_telemetry_token(self, *, integration_id: str, token: str) -> bool: ...

    def record_telemetry_event(
        self,
        *,
        integration_id: str,
        event_id: str | None,
        event_type: str,
        occurred_at: str,
    ) -> dict[str, Any]: ...


_WINDOW_SECONDS = 60.0
_EMIT_THRESHOLD = 5
_EMIT_RATE_LIMIT_SECONDS = 30.0


@dataclass
class _BurstState:
    count: int = 0
    first_seen: float = 0.0
    last_emit: float = 0.0
    last_attempt: float = 0.0
    last_severity: str = "low"
    last_message: str = ""
    last_destination_ip: str | None = None
    users: set[str] = field(default_factory=set)


class BruteForceAggregator:
    """Per-key rolling counter used to throttle incident emission.

    The detection rule `repeated_failed_login` needs `attributes.count >= 5`;
    we count attempts in a 60-second window and only emit when the threshold
    is first crossed (then again every 30s while the burst is still active).
    """

    def __init__(
        self,
        *,
        window_seconds: float = _WINDOW_SECONDS,
        threshold: int = _EMIT_THRESHOLD,
        rate_limit_seconds: float = _EMIT_RATE_LIMIT_SECONDS,
    ) -> None:
        self.window_seconds = window_seconds
        self.threshold = threshold
        self.rate_limit_seconds = rate_limit_seconds
        self._states: dict[tuple[str, str, str], _BurstState] = defaultdict(_BurstState)
        self._lock = threading.Lock()

    def register(
        self,
        *,
        event_type: str,
        source_ip: str,
        integration_id: str,
        now: float,
        user: str | None = None,
        severity: str = "low",
        message: str = "",
        destination_ip: str | None = None,
    ) -> tuple[bool, _BurstState]:
        key = (event_type, source_ip, integration_id)
        with self._lock:
            state = self._states[key]
            if state.first_seen == 0.0 or now - state.first_seen > self.window_seconds:
                state.count = 0
                state.first_seen = now
                state.last_emit = 0.0
                state.users = set()
            state.count += 1
            state.last_attempt = now
            state.last_severity = severity
            state.last_message = message or state.last_message
            if destination_ip:
                state.last_destination_ip = destination_ip
            if user:
                state.users.add(user)
            should_emit = False
            if state.count >= self.threshold and (
                state.last_emit == 0.0
                or now - state.last_emit >= self.rate_limit_seconds
            ):
                state.last_emit = now
                should_emit = True
            return should_emit, state


_aggregator = BruteForceAggregator()


def get_aggregator() -> BruteForceAggregator:
    return _aggregator


def _verify_token(authorization: str | None) -> None:
    settings = get_settings()
    expected = (settings.soc_ingest_token or "").strip()
    if not expected:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="SOC ingest endpoint is disabled. Set PENGUARD_SOC_INGEST_TOKEN.",
        )
    presented = ""
    if authorization:
        parts = authorization.strip().split(None, 1)
        if len(parts) == 2 and parts[0].lower() == "bearer":
            presented = parts[1].strip()
    if not presented or not hmac.compare_digest(presented, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid ingestion token",
        )


def _client_ip(request: Request) -> str:
    if request.client is None:
        return "unknown"
    return request.client.host


def _bearer_token(authorization: str | None) -> str:
    if not authorization:
        return ""
    parts = authorization.strip().split(None, 1)
    if len(parts) == 2 and parts[0].lower() == "bearer":
        return parts[1].strip()
    return ""


def _now_dt() -> datetime:
    return datetime.now(UTC)


def _now_iso() -> str:
    return _now_dt().isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _coerce_str(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    return str(value).strip()


def _parse_fortigate_timestamp(raw: Any) -> str:
    """FortiGate `eventtime` may be epoch seconds, ms, us or ns. Normalize."""
    if isinstance(raw, str) and raw.strip().startswith(("19", "20")) and "T" in raw:
        return raw
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return _now_iso()
    if value > 10_000_000_000_000_000:
        value //= 1_000_000_000
    elif value > 10_000_000_000_000:
        value //= 1_000_000
    elif value > 10_000_000_000:
        value //= 1_000
    try:
        return (
            datetime.fromtimestamp(value, UTC)
            .isoformat(timespec="milliseconds")
            .replace("+00:00", "Z")
        )
    except (OverflowError, OSError, ValueError):
        return _now_iso()


_FORTI_LEVEL_TO_SEVERITY = {
    "emergency": "critical",
    "alert": "critical",
    "critical": "critical",
    "error": "high",
    "warning": "medium",
    "notice": "low",
    "information": "informational",
    "informational": "informational",
    "debug": "informational",
}


def _map_severity(raw: dict[str, Any]) -> str:
    explicit = _coerce_str(raw.get("severity")).lower()
    if explicit in {"critical", "high", "medium", "low", "informational"}:
        return explicit
    level = _coerce_str(raw.get("level")).lower()
    return _FORTI_LEVEL_TO_SEVERITY.get(level, "low")


def _classify_event_type(raw: dict[str, Any]) -> str:
    explicit = _coerce_str(raw.get("eventType"))
    if explicit:
        return explicit
    log_type = _coerce_str(raw.get("type")).lower()
    subtype = _coerce_str(raw.get("subtype")).lower()
    action = _coerce_str(raw.get("action")).lower()
    status_field = _coerce_str(raw.get("status")).lower()
    msg = _coerce_str(raw.get("msg") or raw.get("message") or raw.get("logdesc")).lower()
    logid = _coerce_str(raw.get("logid"))

    if logid in {"0100040704", "0100032003"}:
        return "auth.failed_login"
    if action in {"login-fail", "login_failed"} or (
        action == "login" and status_field in {"failed", "failure"}
    ):
        return "auth.failed_login"
    if subtype == "user" and "fail" in msg:
        return "auth.failed_login"
    if subtype == "system" and ("admin" in msg and "fail" in msg):
        return "auth.failed_login"
    if log_type == "traffic" and action in {"deny", "block", "blocked"}:
        return "network.deny"
    if subtype in {"ips", "anomaly"} or "scan" in msg:
        return "network.scan"
    if action in {"deny", "block", "blocked"}:
        return "network.deny"
    return "network.event"


def _build_siem_event(
    raw: dict[str, Any],
    *,
    integration_id: str,
    burst: _BurstState,
) -> dict[str, Any]:
    source_ip = _coerce_str(raw.get("srcip") or raw.get("sourceIp")) or "unknown"
    destination_ip = (
        _coerce_str(raw.get("dstip") or raw.get("destinationIp"))
        or burst.last_destination_ip
        or None
    )
    user = _coerce_str(raw.get("user") or raw.get("username"))
    message = _coerce_str(raw.get("msg") or raw.get("message") or raw.get("logdesc"))
    occurred_at = _parse_fortigate_timestamp(raw.get("eventtime") or raw.get("timestamp"))
    event_type = _classify_event_type(raw)
    severity = _map_severity(raw)

    entities: dict[str, Any] = {
        "sourceIp": source_ip,
        "integrationId": integration_id,
    }
    if destination_ip:
        entities["destinationIp"] = destination_ip
    if user:
        entities["username"] = user

    attributes: dict[str, Any] = {
        "source": "fortigate.webhook",
        "logid": _coerce_str(raw.get("logid")) or None,
        "type": _coerce_str(raw.get("type")) or None,
        "subtype": _coerce_str(raw.get("subtype")) or None,
        "action": _coerce_str(raw.get("action")) or None,
        "level": _coerce_str(raw.get("level")) or None,
        "message": message or None,
        "count": burst.count,
        "users": sorted(u for u in burst.users if u),
        "windowSeconds": int(_WINDOW_SECONDS),
        "ingestionMode": "push",
    }
    attributes = {k: v for k, v in attributes.items() if v not in (None, "")}

    return {
        "source": "fortigate",
        "eventType": event_type,
        "severity": severity,
        "occurredAt": occurred_at,
        "entities": entities,
        "attributes": attributes,
    }


def _normalize_payload(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, dict):
        events = payload.get("events")
        if isinstance(events, list):
            return [e for e in events if isinstance(e, dict)]
        return [payload]
    if isinstance(payload, list):
        return [e for e in payload if isinstance(e, dict)]
    raise HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail="Body must be a JSON object or an array of objects",
    )


def _integration_id_header(value: str | None) -> str:
    cleaned = _coerce_str(value)
    return cleaned or "fortigate-webhook"


@router.post("/soc/ingest/fortigate")
def ingest_fortigate_webhook(
    request: Request,
    payload: Annotated[Any, Body()],
    siem_client: Annotated[SocClient, Depends(get_siem_client)],
    audit_store: Annotated[AuditStore, Depends(get_auth_audit_store)],
    aggregator: Annotated[BruteForceAggregator, Depends(get_aggregator)],
    authorization: Annotated[str | None, Header(alias="Authorization")] = None,
    integration_header: Annotated[
        str | None,
        Header(alias="X-Penguard-Integration-Id"),
    ] = None,
) -> dict[str, Any]:
    _verify_token(authorization)
    integration_id = _integration_id_header(integration_header)
    raw_events = _normalize_payload(payload)
    now_ts = _now_dt().timestamp()
    emitted: list[dict[str, Any]] = []
    skipped = 0

    for raw in raw_events:
        event_type = _classify_event_type(raw)
        source_ip = _coerce_str(raw.get("srcip") or raw.get("sourceIp")) or "unknown"
        user = _coerce_str(raw.get("user") or raw.get("username")) or None
        severity = _map_severity(raw)
        message = _coerce_str(raw.get("msg") or raw.get("message") or raw.get("logdesc"))
        destination_ip = _coerce_str(raw.get("dstip") or raw.get("destinationIp")) or None
        should_emit, burst = aggregator.register(
            event_type=event_type,
            source_ip=source_ip,
            integration_id=integration_id,
            now=now_ts,
            user=user,
            severity=severity,
            message=message,
            destination_ip=destination_ip,
        )
        if not should_emit:
            skipped += 1
            continue
        siem_event = _build_siem_event(raw, integration_id=integration_id, burst=burst)
        try:
            created = siem_client.request("POST", "/events", json=siem_event)
        except HTTPException:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.exception(
                "soc_ingest_forward_failed event_type=%s source_ip=%s error=%s",
                event_type,
                source_ip,
                exc,
            )
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Failed to forward to siem-kowalski: {exc}",
            ) from exc
        emitted.append(created)

    audit_store.record(
        action="soc.ingest.fortigate",
        outcome="success",
        email=None,
        user_id=None,
        client_ip=_client_ip(request),
        user_agent=request.headers.get("user-agent"),
        details={
            "integrationId": integration_id,
            "received": len(raw_events),
            "emitted": len(emitted),
            "throttled": skipped,
            "service": "siem_kowalski",
        },
    )
    return {
        "received": len(raw_events),
        "emitted": len(emitted),
        "throttled": skipped,
        "eventIds": [
            event.get("id")
            for event in emitted
            if isinstance(event, dict) and event.get("id")
        ],
    }


def _fortiweb_field(raw: dict[str, Any], *names: str) -> str:
    for name in names:
        value = _coerce_str(raw.get(name))
        if value:
            return value
    return ""


def _classify_fortiweb_event(raw: dict[str, Any]) -> str:
    kind = _fortiweb_field(raw, "type", "log_type").lower()
    subtype = _fortiweb_field(raw, "subtype", "sub_type", "main_type").lower()
    message = _fortiweb_field(raw, "msg", "message", "attack", "signature").lower()
    action = _fortiweb_field(raw, "action").lower()

    if "dos" in subtype or "flood" in message or "rate" in message:
        return "waf.dos"
    if kind == "attack" or subtype or "attack" in message:
        return "waf.attack"
    if action in {"block", "blocked", "deny", "dropped"}:
        return "waf.blocked_request"
    return "http.attack"


def _normalize_fortiweb_event(
    raw: dict[str, Any],
    *,
    integration_id: str,
) -> dict[str, Any]:
    occurred_at = _parse_fortigate_timestamp(
        raw.get("eventtime") or raw.get("time") or raw.get("date")
    )
    source_ip = _fortiweb_field(raw, "src", "srcip", "source", "client_ip")
    destination_ip = _fortiweb_field(
        raw, "dst", "dstip", "destination", "server_ip"
    )
    host = _fortiweb_field(raw, "host", "http_host", "hostname")
    method = _fortiweb_field(raw, "method", "http_method").upper()
    url = _fortiweb_field(raw, "url", "uri", "path", "request")
    action = _fortiweb_field(raw, "action")
    policy = _fortiweb_field(raw, "policy", "policy_name", "server_policy")
    message = _fortiweb_field(raw, "msg", "message", "attack", "signature")
    severity = _map_severity(raw)

    count_raw = raw.get("count") or raw.get("matches") or raw.get("total")
    try:
        count = int(count_raw)
    except (TypeError, ValueError):
        count = 1

    return {
        "eventType": _classify_fortiweb_event(raw),
        "source": "fortiweb",
        "severity": severity,
        "message": message or "FortiWeb WAF event",
        "occurredAt": occurred_at,
        "entities": {
            "sourceIp": source_ip,
            "destinationIp": destination_ip,
            "httpHost": host,
            "integrationId": integration_id,
        },
        "attributes": {
            "action": action,
            "policy": policy,
            "method": method,
            "url": url,
            "count": count,
            "rawType": _fortiweb_field(raw, "type", "log_type"),
            "rawSubtype": _fortiweb_field(raw, "subtype", "sub_type"),
            "ingestionMode": "push",
        },
    }


@router.post("/soc/ingest/fortiweb")
def ingest_fortiweb_event(
    request: Request,
    payload: Annotated[Any, Body()],
    siem_client: Annotated[SocClient, Depends(get_siem_client)],
    audit_store: Annotated[AuditStore, Depends(get_auth_audit_store)],
    authorization: Annotated[str | None, Header(alias="Authorization")] = None,
    integration_header: Annotated[
        str | None,
        Header(alias="X-Penguard-Integration-Id"),
    ] = None,
) -> dict[str, Any]:
    _verify_token(authorization)
    raw_items = payload if isinstance(payload, list) else [payload]
    integration_id = _coerce_str(integration_header) or "fortiweb"
    emitted = 0

    for item in raw_items:
        if not isinstance(item, dict):
            continue
        event = _normalize_fortiweb_event(item, integration_id=integration_id)
        try:
            siem_client.request("POST", "/events", json=event)
        except HTTPException:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.exception(
                "soc_ingest_fortiweb_forward_failed event_type=%s error=%s",
                event["eventType"],
                exc,
            )
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Failed to forward to siem-kowalski: {exc}",
            ) from exc
        emitted += 1

    audit_store.record(
        action="soc.fortiweb_events.ingested",
        outcome="success",
        email=None,
        user_id=None,
        client_ip=_client_ip(request),
        user_agent=request.headers.get("user-agent"),
        details={
            "integrationId": integration_id,
            "received": len(raw_items),
            "emitted": emitted,
            "service": "siem_kowalski",
        },
    )
    return {"received": len(raw_items), "emitted": emitted}


@router.post("/soc/ingest/fortiweb/{integration_id}")
def ingest_native_fortiweb_event(
    integration_id: str,
    request: Request,
    payload: Annotated[Any, Body()],
    siem_client: Annotated[SocClient, Depends(get_siem_client)],
    fortiweb_service: Annotated[
        FortiWebTelemetryService,
        Depends(get_fortiweb_integration_service),
    ],
    audit_store: Annotated[AuditStore, Depends(get_auth_audit_store)],
    authorization: Annotated[str | None, Header(alias="Authorization")] = None,
) -> dict[str, Any]:
    token = _bearer_token(authorization)
    if not token or not fortiweb_service.verify_telemetry_token(
        integration_id=integration_id,
        token=token,
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid FortiWeb telemetry token",
        )

    raw_items = payload if isinstance(payload, list) else [payload]
    emitted = 0

    for item in raw_items:
        if not isinstance(item, dict):
            continue
        event = _normalize_fortiweb_event(item, integration_id=integration_id)
        try:
            response = siem_client.request("POST", "/events", json=event)
        except HTTPException:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.exception(
                "soc_ingest_fortiweb_forward_failed event_type=%s error=%s",
                event["eventType"],
                exc,
            )
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Failed to forward to siem-kowalski: {exc}",
            ) from exc
        emitted += 1
        fortiweb_service.record_telemetry_event(
            integration_id=integration_id,
            event_id=_coerce_str(response.get("id")) or None,
            event_type=str(event["eventType"]),
            occurred_at=str(event["occurredAt"]),
        )

    audit_store.record(
        action="soc.fortiweb_events.ingested",
        outcome="success",
        email=None,
        user_id=None,
        client_ip=_client_ip(request),
        user_agent=request.headers.get("user-agent"),
        details={
            "integrationId": integration_id,
            "received": len(raw_items),
            "emitted": emitted,
            "service": "siem_kowalski",
            "tokenScope": "integration",
        },
    )
    return {"received": len(raw_items), "emitted": emitted, "integrationId": integration_id}


@router.get("/soc/ingest/health")
def ingest_health() -> dict[str, Any]:
    settings = get_settings()
    return {
        "enabled": bool(settings.soc_ingest_token),
        "windowSeconds": int(_WINDOW_SECONDS),
        "threshold": _EMIT_THRESHOLD,
        "rateLimitSeconds": int(_EMIT_RATE_LIMIT_SECONDS),
    }


@lru_cache
def _aggregator_singleton_marker() -> str:
    return "soc-ingest-aggregator"
