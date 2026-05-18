import asyncio
import logging
import re
import shlex
from collections.abc import Callable
from contextlib import suppress
from datetime import UTC, datetime
from typing import Any, Protocol

logger = logging.getLogger(__name__)


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


SyslogIntegrationRef = str | dict[str, str | None] | None
IntegrationResolver = Callable[[tuple[str, int] | None, dict[str, str]], SyslogIntegrationRef]


class StatusRecorder(Protocol):
    def __call__(
        self,
        *,
        owner_user_id: str,
        integration_id: str,
        event_id: str | None,
        event: dict[str, Any] | None = None,
        ticket: dict[str, Any] | None = None,
    ) -> None:
        pass

NowFactory = Callable[[], datetime]

_PRI_PREFIX_RE = re.compile(r"^<\d+>")
_INT_FIELDS = {
    "srcport": "sourcePort",
    "dstport": "destinationPort",
}
_STRING_FIELDS = {
    "action": "action",
    "type": "type",
    "subtype": "subtype",
    "level": "level",
    "service": "service",
    "proto": "protocol",
    "msg": "message",
    "logid": "logId",
    "policyid": "policyId",
    "vd": "vdom",
    "status": "status",
    "user": "user",
}


def parse_fortigate_syslog(
    line: str,
    *,
    integration_id: str | None,
    collector_source_ip: str | None = None,
    transport: str | None = None,
    now: NowFactory | None = None,
) -> dict[str, Any]:
    fields = parse_fortinet_key_values(line)
    occurred_at = _occurred_at(fields, now=now or _utcnow)
    action = fields.get("action", "").lower()
    log_type = fields.get("type", "")
    subtype = fields.get("subtype", "")
    level = fields.get("level", "")

    event_type = _event_type(fields=fields, log_type=log_type, subtype=subtype, action=action)
    severity = _severity(level=level, action=action)

    entities: dict[str, Any] = {}
    if fields.get("srcip"):
        entities["sourceIp"] = fields["srcip"]
    if fields.get("dstip"):
        entities["destinationIp"] = fields["dstip"]
    if integration_id:
        entities["integrationId"] = integration_id
    if fields.get("devname"):
        entities["deviceName"] = fields["devname"]

    attributes: dict[str, Any] = {"originKind": "fortigate.syslog"}
    for raw_key, normalized_key in _STRING_FIELDS.items():
        value = fields.get(raw_key)
        if value not in (None, ""):
            attributes[normalized_key] = value
    for raw_key, normalized_key in _INT_FIELDS.items():
        value = _maybe_int(fields.get(raw_key))
        if value is not None:
            attributes[normalized_key] = value
    if transport:
        attributes["transport"] = transport
    if collector_source_ip:
        attributes["collectorSourceIp"] = collector_source_ip
    if event_type == "auth.failed_login":
        attributes["count"] = _failed_login_count(fields)
        if _is_lockout_event(fields):
            attributes["lockout"] = True
            attributes["attackType"] = "brute_force"
    elif fields.get("probe", "").lower() == "true":
        attributes["count"] = 1
        attributes["probe"] = True
    else:
        attributes["count"] = 1
    attributes["raw"] = line

    return {
        "source": "fortigate.syslog",
        "eventType": event_type,
        "severity": severity,
        "occurredAt": occurred_at,
        "entities": entities,
        "attributes": attributes,
    }


def parse_fortinet_key_values(line: str) -> dict[str, str]:
    stripped = _PRI_PREFIX_RE.sub("", line.strip())
    lexer = shlex.shlex(stripped, posix=True)
    lexer.whitespace_split = True
    lexer.commenters = ""
    fields: dict[str, str] = {}
    for token in lexer:
        if "=" not in token:
            continue
        key, value = token.split("=", 1)
        fields[key.strip().lower()] = value.strip()
    return fields


class FortiGateSyslogForwarder:
    def __init__(
        self,
        *,
        siem_client: SocClient,
        integration_resolver: IntegrationResolver,
        status_recorder: StatusRecorder | None = None,
        now: NowFactory | None = None,
    ) -> None:
        self.siem_client = siem_client
        self.integration_resolver = integration_resolver
        self.status_recorder = status_recorder
        self.now = now or _utcnow

    def handle_datagram(
        self,
        data: bytes,
        *,
        addr: tuple[str, int] | None = None,
    ) -> dict[str, Any]:
        line = data.decode("utf-8", errors="replace").strip()
        if not line:
            return {"status": "skipped", "reason": "empty"}
        fields = parse_fortinet_key_values(line)
        integration_ref = self.integration_resolver(addr, fields)
        integration_id, owner_user_id = _split_integration_ref(integration_ref)
        event = parse_fortigate_syslog(
            line,
            integration_id=integration_id,
            collector_source_ip=addr[0] if addr else None,
            transport="udp",
            now=self.now,
        )
        created = self.siem_client.request("POST", "/events/ingest", json=event)
        created_event = created.get("event") if isinstance(created.get("event"), dict) else created
        ticket = created.get("incident") if isinstance(created.get("incident"), dict) else None
        event_id = created_event.get("id") if isinstance(created_event, dict) else None
        if integration_id and owner_user_id and self.status_recorder is not None:
            self.status_recorder(
                owner_user_id=owner_user_id,
                integration_id=integration_id,
                event_id=event_id,
                event=created_event if isinstance(created_event, dict) else None,
                ticket=ticket,
            )
        return {
            "status": "forwarded",
            "integrationId": integration_id,
            "eventId": event_id,
            "event": created_event if isinstance(created_event, dict) else None,
            "ticket": ticket,
            "eventType": event["eventType"],
        }


class FortiGateSyslogProtocol(asyncio.DatagramProtocol):
    def __init__(
        self,
        forwarder: FortiGateSyslogForwarder,
        *,
        queue_max_size: int = 1000,
    ) -> None:
        self.forwarder = forwarder
        self.queue: asyncio.Queue[tuple[bytes, tuple[str, int]]] = asyncio.Queue(
            maxsize=max(1, queue_max_size),
        )
        self.worker_task: asyncio.Task[None] | None = None
        self.dropped_datagrams = 0
        self.closed = False

    def connection_made(self, transport: asyncio.BaseTransport) -> None:
        self._ensure_worker()

    def connection_lost(self, exc: Exception | None) -> None:
        self.closed = True
        if self.worker_task is not None:
            self.worker_task.cancel()

    def _ensure_worker(self) -> None:
        if self.worker_task is not None and not self.worker_task.done():
            return
        self.worker_task = asyncio.create_task(self._forward_loop())
        self.worker_task.add_done_callback(self._log_worker_failure)

    def datagram_received(self, data: bytes, addr: tuple[str, int]) -> None:
        if self.closed:
            return
        self._ensure_worker()
        try:
            self.queue.put_nowait((bytes(data), addr))
        except asyncio.QueueFull:
            self.dropped_datagrams += 1
            if self.dropped_datagrams == 1 or self.dropped_datagrams % 100 == 0:
                logger.warning(
                    "fortigate_syslog_queue_full dropped_datagrams=%s queue_size=%s",
                    self.dropped_datagrams,
                    self.queue.qsize(),
                )

    async def _forward_loop(self) -> None:
        while True:
            data, addr = await self.queue.get()
            try:
                await asyncio.to_thread(self._forward_datagram, data, addr)
            finally:
                self.queue.task_done()

    def _forward_datagram(self, data: bytes, addr: tuple[str, int]) -> None:
        try:
            result = self.forwarder.handle_datagram(data, addr=addr)
            logger.info(
                "fortigate_syslog_forwarded status=%s integration_id=%s event_id=%s",
                result.get("status"),
                result.get("integrationId"),
                result.get("eventId"),
            )
        except Exception:
            logger.exception(
                "fortigate_syslog_forward_failed source=%s",
                addr[0] if addr else "unknown",
            )

    def _log_worker_failure(self, task: asyncio.Task[None]) -> None:
        exc: BaseException | None = None
        with suppress(asyncio.CancelledError):
            exc = task.exception()
        if exc is not None:
            logger.error(
                "fortigate_syslog_worker_failed",
                exc_info=(type(exc), exc, exc.__traceback__),
            )


async def start_fortigate_syslog_udp_collector(
    *,
    host: str,
    port: int,
    forwarder: FortiGateSyslogForwarder,
    queue_max_size: int = 1000,
) -> asyncio.DatagramTransport:
    loop = asyncio.get_running_loop()
    transport, _protocol = await loop.create_datagram_endpoint(
        lambda: FortiGateSyslogProtocol(forwarder, queue_max_size=queue_max_size),
        local_addr=(host, port),
    )
    logger.info("fortigate_syslog_collector_started host=%s port=%s transport=udp", host, port)
    return transport  # type: ignore[return-value]


async def send_fortigate_syslog_probe(
    *,
    host: str,
    port: int,
    integration_id: str,
    now: NowFactory | None = None,
) -> dict[str, Any]:
    sent_at = (now or _utcnow)().astimezone(UTC)
    message = _build_probe_syslog_line(integration_id=integration_id, sent_at=sent_at)
    loop = asyncio.get_running_loop()
    transport, _protocol = await loop.create_datagram_endpoint(
        asyncio.DatagramProtocol,
        remote_addr=(host, port),
    )
    try:
        transport.sendto(message.encode("utf-8"))
    finally:
        transport.close()
    return {
        "sent": True,
        "collectorHost": host,
        "collectorPort": port,
        "integrationId": integration_id,
        "sentAt": sent_at.isoformat(timespec="milliseconds").replace("+00:00", "Z"),
        "sample": message,
    }


def _build_probe_syslog_line(*, integration_id: str, sent_at: datetime) -> str:
    return (
        f'<189>date={sent_at:%Y-%m-%d} time={sent_at:%H:%M:%S} '
        'devname="FortiDashboardCollectorProbe" type="traffic" subtype="forward" '
        'level="information" srcip=127.0.0.1 dstip=127.0.0.1 '
        'srcport=55140 dstport=5514 proto=17 service="SYSLOG" action="accept" '
        f'integrationid="{integration_id}" probe=true '
        'msg="FortiDashboard synthetic syslog collector probe"'
    )


def source_ip_resolver(expected_source_ip: str | None = None) -> IntegrationResolver:
    def resolve(addr: tuple[str, int] | None, fields: dict[str, str]) -> str | None:
        if expected_source_ip and addr and addr[0] != expected_source_ip:
            return None
        return fields.get("integrationid") or fields.get("devid") or expected_source_ip

    return resolve


def _split_integration_ref(ref: SyslogIntegrationRef) -> tuple[str | None, str | None]:
    if isinstance(ref, str):
        return ref, None
    if isinstance(ref, dict):
        return ref.get("integrationId"), ref.get("ownerUserId")
    return None, None


def _event_type(*, fields: dict[str, str], log_type: str, subtype: str, action: str) -> str:
    if log_type == "traffic" and action in {"deny", "blocked", "block"}:
        return "network.deny"
    if log_type == "traffic":
        return "network.event"
    if log_type == "event" and _is_failed_login_event(fields):
        return "auth.failed_login"
    return f"fortigate.{log_type or 'event'}"


def _is_failed_login_event(fields: dict[str, str]) -> bool:
    action = fields.get("action", "").lower()
    status = fields.get("status", "").lower()
    subtype = fields.get("subtype", "").lower()
    message = " ".join(
        str(fields.get(key, "")).lower() for key in ("msg", "logdesc", "message")
    )
    return (
        (action == "login" and status == "failed")
        or "admin login failed" in message
        or "login disabled" in message
        or ("login" in subtype and "failed" in message)
    )


def _is_lockout_event(fields: dict[str, str]) -> bool:
    message = " ".join(
        str(fields.get(key, "")).lower() for key in ("msg", "logdesc", "message")
    )
    return "login disabled" in message or "bad attempts" in message or "lockout" in message


def _failed_login_count(fields: dict[str, str]) -> int:
    for key in ("count", "attempts"):
        value = _maybe_int(fields.get(key))
        if value is not None and value > 0:
            return value
    message = " ".join(str(fields.get(key, "")) for key in ("msg", "logdesc", "message"))
    match = re.search(r"because of\s+(\d+)\s+bad attempts", message, flags=re.IGNORECASE)
    if match:
        return int(match.group(1))
    return 1


def _severity(*, level: str, action: str) -> str:
    normalized = level.lower()
    if normalized in {"critical", "alert", "emergency"}:
        return "critical"
    if normalized in {"error", "warning"}:
        return "high"
    if action in {"deny", "blocked", "block"}:
        return "medium"
    if normalized in {"notice"}:
        return "medium"
    return "informational"


def _occurred_at(fields: dict[str, str], *, now: NowFactory) -> str:
    date_value = fields.get("date")
    time_value = fields.get("time")
    event_time = fields.get("eventtime")
    if date_value and time_value:
        try:
            parsed = datetime.strptime(f"{date_value} {time_value}", "%Y-%m-%d %H:%M:%S")
            return parsed.replace(tzinfo=UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
        except ValueError:
            pass
    if event_time and event_time.isdigit():
        try:
            parsed = datetime.fromtimestamp(int(event_time) / 1_000_000_000, tz=UTC)
            return parsed.isoformat(timespec="seconds").replace("+00:00", "Z")
        except (OverflowError, OSError, ValueError):
            pass
    return now().astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _maybe_int(value: str | None) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _utcnow() -> datetime:
    return datetime.now(UTC)
