from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any, Protocol

from app.core.fixtures import load_fixture
from app.integrations.fortigate.client import FortiGateApiClient, FortiGateApiError
from app.integrations.fortigate.normalizers import normalize_system_status


class FortiGateIntegrationStore(Protocol):
    def create(
        self,
        *,
        owner_user_id: str,
        name: str,
        host: str,
        api_key: str,
        verify_tls: bool,
        device: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        pass

    def list_public(self, *, owner_user_id: str) -> dict[str, list[dict[str, Any]]]:
        pass

    def get_connection(self, integration_id: str, *, owner_user_id: str) -> dict[str, Any] | None:
        pass

    def find_public_by_host(self, source_host: str) -> dict[str, Any] | None:
        pass

    def find_syslog_source(
        self,
        source_host: str,
        fields: dict[str, str] | None = None,
    ) -> dict[str, Any] | None:
        pass

    def delete(self, *, owner_user_id: str, integration_id: str) -> bool:
        pass

    def record_health_check(
        self,
        *,
        owner_user_id: str,
        integration_id: str,
        ok: bool,
        status: str,
        device: dict[str, Any],
        message: str | None,
        latency_ms: int | None,
        checked_at: datetime,
    ) -> dict[str, Any]:
        pass

    def list_health_checks(
        self,
        *,
        owner_user_id: str,
        integration_id: str,
        limit: int = 20,
    ) -> dict[str, list[dict[str, Any]]]:
        pass

    def get_ingestion_status(
        self,
        *,
        owner_user_id: str,
        integration_id: str,
    ) -> dict[str, Any]:
        pass

    def record_syslog_event(
        self,
        *,
        owner_user_id: str,
        integration_id: str,
        event_id: str | None,
        received_at: datetime,
    ) -> dict[str, Any]:
        pass

    def mark_syslog_forwarding_configured(
        self,
        *,
        owner_user_id: str,
        integration_id: str,
        configured_at: datetime,
    ) -> dict[str, Any]:
        pass


class FortiGateClient(Protocol):
    def get_system_status(self) -> dict[str, Any]:
        pass

    def get_performance_status(self) -> dict[str, Any]:
        pass

    def get_resource_usage(self, *, resource: str | None = None) -> dict[str, Any]:
        pass

    def get_policies(self) -> list[dict[str, Any]]:
        pass

    def get_address_objects(self) -> list[dict[str, Any]]:
        pass

    def create_address_object(
        self,
        *,
        name: str,
        subnet: str,
        comment: str,
    ) -> dict[str, Any]:
        pass

    def create_firewall_policy(self, payload: dict[str, Any]) -> dict[str, Any]:
        pass

    def get_syslog_setting(self, *, slot: int = 1) -> dict[str, Any]:
        pass

    def get_syslog_filter(self, *, slot: int = 1) -> dict[str, Any]:
        pass

    def update_syslog_setting(self, payload: dict[str, Any], *, slot: int = 1) -> dict[str, Any]:
        pass

    def update_syslog_filter(self, payload: dict[str, Any], *, slot: int = 1) -> dict[str, Any]:
        pass


class FortiGateClientFactory(Protocol):
    def __call__(self, *, host: str, api_key: str, verify_tls: bool) -> FortiGateClient:
        pass


class FortiGateConnectionFailed(RuntimeError):
    pass


SYSLOG_SLOTS = (1, 2, 3, 4)
SYSLOG_TRAFFIC_FILTER_KEYS = (
    "forward-traffic",
    "local-traffic",
    "multicast-traffic",
)


class MockFortiGateIntegrationService:
    def create(
        self,
        *,
        owner_user_id: str,
        name: str,
        host: str,
        api_key: str,
        verify_tls: bool,
        collector_host: str | None = None,
        collector_port: int = 5514,
        device: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return load_fixture("fortigate_integration_created")

    def test_connection(self, *, host: str, api_key: str, verify_tls: bool) -> dict[str, Any]:
        return load_fixture("fortigate_connection_test")

    def list(self, *, owner_user_id: str) -> dict[str, Any]:
        return load_fixture("integrations_list")

    def delete(self, *, integration_id: str, owner_user_id: str) -> bool:
        return integration_id == "int_fgt_01"

    def resolve_syslog_integration_id(
        self,
        *,
        source_host: str,
        fields: dict[str, str] | None = None,
    ) -> str | None:
        return source_host

    def record_syslog_event(
        self,
        *,
        owner_user_id: str,
        integration_id: str,
        event_id: str | None,
        received_at: datetime,
    ) -> dict[str, Any]:
        return {
            "integrationId": integration_id,
            "enabled": False,
            "status": "streaming",
            "lastRunTrigger": "syslog",
            "lastEventIds": [event_id] if event_id else [],
            "updatedAt": received_at.isoformat(),
        }

    def run_health_check(self, *, integration_id: str, owner_user_id: str) -> dict[str, Any]:
        return {
            "id": "fgt_health_01",
            "integrationId": integration_id,
            "ok": True,
            "status": "connected",
            "device": load_fixture("fortigate_connection_test")["device"],
            "message": None,
            "latencyMs": 0,
            "checkedAt": "2026-04-26T20:30:00.000Z",
        }

    def list_health_checks(
        self,
        *,
        integration_id: str,
        owner_user_id: str,
        limit: int = 20,
    ) -> dict[str, Any]:
        return {
            "items": [
                self.run_health_check(
                    integration_id=integration_id,
                    owner_user_id=owner_user_id,
                )
            ]
        }

    def get_log_forwarding_status(
        self,
        *,
        integration_id: str,
        owner_user_id: str,
    ) -> dict[str, Any]:
        return {
            "integrationId": integration_id,
            "configured": False,
            "current": {
                "setting": {
                    "status": "disable",
                    "server": "",
                    "port": 514,
                    "mode": "udp",
                    "facility": "local7",
                    "format": "default",
                },
                "filter": {"severity": "information"},
            },
        }

    def apply_log_forwarding(
        self,
        *,
        integration_id: str,
        owner_user_id: str,
        collector_host: str,
        port: int = 5514,
        mode: str = "udp",
        facility: str = "local7",
        format: str = "default",
        severity: str = "information",
        confirmed: bool = False,
    ) -> dict[str, Any]:
        if not confirmed:
            raise PermissionError(
                "Explicit confirmation is required to apply FortiGate log forwarding"
            )
        return _build_log_forwarding_payload(
            integration_id=integration_id,
            collector_host=collector_host,
            port=port,
            mode=mode,
            facility=facility,
            format=format,
            severity=severity,
            current={"setting": {}, "filter": {}},
        )


class FortiGateIntegrationService:
    def __init__(
        self,
        *,
        store: FortiGateIntegrationStore,
        client_factory: FortiGateClientFactory | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.store = store
        self.client_factory = client_factory or self._default_client_factory
        self.clock = clock or (lambda: datetime.now(UTC))

    def create(
        self,
        *,
        owner_user_id: str,
        name: str,
        host: str,
        api_key: str,
        verify_tls: bool,
        collector_host: str | None = None,
        collector_port: int = 5514,
    ) -> dict[str, Any]:
        probe = self._probe_connection(host=host, api_key=api_key, verify_tls=verify_tls)
        if not probe["ok"]:
            error = probe.get("error") or {}
            raise FortiGateConnectionFailed(error.get("message") or "FortiGate connection failed")
        log_forwarding: dict[str, Any] | None = None
        if collector_host:
            client = self.client_factory(host=host, api_key=api_key, verify_tls=verify_tls)
            log_forwarding = self._ensure_log_forwarding(
                client=client,
                integration_id="",
                collector_host=collector_host,
                port=collector_port,
            )
        created = self.store.create(
            owner_user_id=owner_user_id,
            name=name,
            host=host,
            api_key=api_key,
            verify_tls=verify_tls,
            device=dict(probe.get("device") or {}),
        )
        if log_forwarding is not None:
            log_forwarding["integrationId"] = str(created["id"])
            if log_forwarding.get("configured") is True:
                self.store.mark_syslog_forwarding_configured(
                    owner_user_id=owner_user_id,
                    integration_id=str(created["id"]),
                    configured_at=self.clock(),
                )
            created["logForwarding"] = log_forwarding
        return created

    def test_connection(self, *, host: str, api_key: str, verify_tls: bool) -> dict[str, Any]:
        return self._probe_connection(host=host, api_key=api_key, verify_tls=verify_tls)

    def run_health_check(self, *, integration_id: str, owner_user_id: str) -> dict[str, Any]:
        connection = self.store.get_connection(integration_id, owner_user_id=owner_user_id)
        if connection is None:
            raise KeyError("Integration not found")
        started_at = self.clock()
        result = self._probe_connection(
            host=str(connection["host"]),
            api_key=str(connection["api_key"]),
            verify_tls=bool(connection["verify_tls"]),
        )
        finished_at = self.clock()
        latency_ms = max(0, int((finished_at - started_at).total_seconds() * 1000))
        return self.store.record_health_check(
            owner_user_id=owner_user_id,
            integration_id=integration_id,
            ok=bool(result["ok"]),
            status=str(result["status"]),
            device=dict(result.get("device") or {}),
            message=(result.get("error") or {}).get("message"),
            latency_ms=latency_ms,
            checked_at=finished_at,
        )

    def list_health_checks(
        self,
        *,
        integration_id: str,
        owner_user_id: str,
        limit: int = 20,
    ) -> dict[str, Any]:
        return self.store.list_health_checks(
            owner_user_id=owner_user_id,
            integration_id=integration_id,
            limit=limit,
        )

    def get_log_forwarding_status(
        self,
        *,
        integration_id: str,
        owner_user_id: str,
    ) -> dict[str, Any]:
        client = self._client_for_integration(
            integration_id=integration_id,
            owner_user_id=owner_user_id,
        )
        current = self._syslog_current(client)
        configured = any(
            _log_forwarding_configured(dict(slot_payload.get("setting") or {}))
            and _syslog_filter_configured(dict(slot_payload.get("filter") or {}))
            for _slot, slot_payload in _syslog_slot_items(current)
        )
        return {
            "integrationId": integration_id,
            "configured": configured,
            "current": current,
            "receiveStatus": _build_receive_status(
                self.store.get_ingestion_status(
                    owner_user_id=owner_user_id,
                    integration_id=integration_id,
                )
            ),
        }


    def apply_log_forwarding(
        self,
        *,
        integration_id: str,
        owner_user_id: str,
        collector_host: str,
        port: int = 5514,
        mode: str = "udp",
        facility: str = "local7",
        format: str = "default",
        severity: str = "information",
        confirmed: bool = False,
    ) -> dict[str, Any]:
        if not confirmed:
            raise PermissionError(
                "Explicit confirmation is required to apply FortiGate log forwarding"
            )
        client = self._client_for_integration(
            integration_id=integration_id,
            owner_user_id=owner_user_id,
        )
        current = self._syslog_current(client)
        desired_slot = _find_collector_syslog_slot(
            current=current,
            collector_host=collector_host,
            port=port,
        ) or _find_empty_syslog_slot(current)
        payload = _build_log_forwarding_payload(
            integration_id=integration_id,
            collector_host=collector_host,
            port=port,
            mode=mode,
            facility=facility,
            format=format,
            severity=severity,
            current=current,
            slot=desired_slot,
        )
        if desired_slot is None:
            return {
                **payload,
                "configured": False,
                "applied": False,
            }
        try:
            client.update_syslog_setting(payload["desired"]["setting"], slot=desired_slot)
            client.update_syslog_filter(payload["desired"]["filter"], slot=desired_slot)
        except FortiGateApiError as exc:
            raise FortiGateConnectionFailed(str(exc)) from exc
        refreshed = self._syslog_current(client)
        return {
            "integrationId": integration_id,
            "configured": _find_matching_syslog_slot(
                current=refreshed,
                collector_host=collector_host,
                port=port,
            )
            is not None,
            "current": refreshed,
            "applied": True,
            "slot": desired_slot,
            "desired": payload["desired"],
            "warnings": payload["warnings"],
        }

    def _ensure_log_forwarding(
        self,
        *,
        client: FortiGateClient,
        integration_id: str,
        collector_host: str,
        port: int = 5514,
    ) -> dict[str, Any]:
        current = self._syslog_current(client)
        matching_slot = _find_matching_syslog_slot(
            current=current,
            collector_host=collector_host,
            port=port,
        )
        if matching_slot is not None:
            return {
                "integrationId": integration_id,
                "configured": True,
                "changed": False,
                "slot": matching_slot,
                "current": current,
            }
        desired_slot = _find_collector_syslog_slot(
            current=current,
            collector_host=collector_host,
            port=port,
        ) or _find_empty_syslog_slot(current)
        payload = _build_log_forwarding_payload(
            integration_id=integration_id,
            collector_host=collector_host,
            port=port,
            mode="udp",
            facility="local7",
            format="default",
            severity="information",
            current=current,
            slot=desired_slot,
        )
        if desired_slot is None:
            return {
                **payload,
                "configured": False,
                "changed": False,
            }
        try:
            client.update_syslog_setting(payload["desired"]["setting"], slot=desired_slot)
            client.update_syslog_filter(payload["desired"]["filter"], slot=desired_slot)
        except FortiGateApiError as exc:
            raise FortiGateConnectionFailed(str(exc)) from exc
        refreshed = self._syslog_current(client)
        return {
            "integrationId": integration_id,
            "configured": _find_matching_syslog_slot(
                current=refreshed,
                collector_host=collector_host,
                port=port,
            )
            is not None,
            "changed": True,
            "slot": desired_slot,
            "current": refreshed,
        }

    def _client_for_integration(
        self,
        *,
        integration_id: str,
        owner_user_id: str,
    ) -> FortiGateClient:
        connection = self.store.get_connection(integration_id, owner_user_id=owner_user_id)
        if connection is None:
            raise KeyError("Integration not found")
        return self.client_factory(
            host=str(connection["host"]),
            api_key=str(connection["api_key"]),
            verify_tls=bool(connection["verify_tls"]),
        )

    def _syslog_current(self, client: FortiGateClient) -> dict[str, Any]:
        slots: dict[int, dict[str, dict[str, Any]]] = {}
        first_error: FortiGateApiError | None = None
        for slot in SYSLOG_SLOTS:
            try:
                slots[slot] = {
                    "setting": client.get_syslog_setting(slot=slot),
                    "filter": client.get_syslog_filter(slot=slot),
                }
            except FortiGateApiError as exc:
                if slot == 1:
                    first_error = exc
                    break
                continue
        if not slots:
            assert first_error is not None
            raise FortiGateConnectionFailed(str(first_error)) from first_error
        first_slot = slots[min(slots)]
        return {
            "setting": first_slot["setting"],
            "filter": first_slot["filter"],
            "slots": slots,
        }

    def _probe_connection(self, *, host: str, api_key: str, verify_tls: bool) -> dict[str, Any]:
        try:
            client = self.client_factory(host=host, api_key=api_key, verify_tls=verify_tls)
            system_status = normalize_system_status(
                client.get_system_status(),
                performance=client.get_performance_status(),
                resource_usage=client.get_resource_usage(resource="session"),
            )
        except FortiGateApiError as exc:
            return {
                "ok": False,
                "status": "disconnected",
                "error": {"message": str(exc)},
            }
        return {
            "ok": True,
            "status": "connected",
            "device": {
                "hostname": system_status["hostname"],
                "model": system_status["model"],
                "version": system_status["version"],
                "serial": system_status.get("serial"),
            },
        }

    def list(self, *, owner_user_id: str) -> dict[str, Any]:
        return self.store.list_public(owner_user_id=owner_user_id)

    def delete(self, *, integration_id: str, owner_user_id: str) -> bool:
        return self.store.delete(
            owner_user_id=owner_user_id,
            integration_id=integration_id,
        )

    def resolve_syslog_integration_id(
        self,
        *,
        source_host: str,
        fields: dict[str, str] | None = None,
    ) -> dict[str, Any] | None:
        return self.store.find_syslog_source(source_host, fields=fields)

    def record_syslog_event(
        self,
        *,
        owner_user_id: str,
        integration_id: str,
        event_id: str | None,
        received_at: datetime,
    ) -> dict[str, Any]:
        return self.store.record_syslog_event(
            owner_user_id=owner_user_id,
            integration_id=integration_id,
            event_id=event_id,
            received_at=received_at,
        )

    def _default_client_factory(
        self,
        *,
        host: str,
        api_key: str,
        verify_tls: bool,
    ) -> FortiGateApiClient:
        return FortiGateApiClient(host=host, api_key=api_key, verify_tls=verify_tls)


def _log_forwarding_configured(setting: dict[str, Any]) -> bool:
    return str(setting.get("status") or "").lower() == "enable" and bool(
        str(setting.get("server") or "").strip()
    )


def _syslog_slot_items(current: dict[str, Any]) -> list[tuple[int, dict[str, Any]]]:
    slots = current.get("slots")
    if isinstance(slots, dict) and slots:
        return sorted(
            (
                (int(slot), dict(value))
                for slot, value in slots.items()
                if isinstance(value, dict)
            ),
            key=lambda item: item[0],
        )
    return [
        (
            1,
            {
                "setting": dict(current.get("setting") or {}),
                "filter": dict(current.get("filter") or {}),
            },
        )
    ]


def _find_matching_syslog_slot(
    *,
    current: dict[str, Any],
    collector_host: str,
    port: int,
) -> int | None:
    slot = _find_collector_syslog_slot(
        current=current,
        collector_host=collector_host,
        port=port,
    )
    if slot is None:
        return None
    slots = dict(current.get("slots") or {})
    slot_payload = dict(slots.get(slot) or slots.get(str(slot)) or {})
    if not slot_payload:
        slot_payload = {"filter": current.get("filter") or {}}
    if not _syslog_filter_configured(dict(slot_payload.get("filter") or {})):
        return None
    return slot


def _find_collector_syslog_slot(
    *,
    current: dict[str, Any],
    collector_host: str,
    port: int,
) -> int | None:
    desired_host = collector_host.strip().lower()
    desired_port = int(port)
    for slot, slot_payload in _syslog_slot_items(current):
        setting = dict(slot_payload.get("setting") or {})
        if str(setting.get("status") or "").lower() != "enable":
            continue
        server = str(setting.get("server") or "").strip().lower()
        try:
            setting_port = int(setting.get("port") or 0)
        except (TypeError, ValueError):
            setting_port = 0
        if server == desired_host and setting_port == desired_port:
            return slot
    return None


def _syslog_filter_configured(syslog_filter: dict[str, Any]) -> bool:
    if str(syslog_filter.get("severity") or "").lower() != "information":
        return False
    for key in SYSLOG_TRAFFIC_FILTER_KEYS:
        if str(syslog_filter.get(key) or "").lower() != "enable":
            return False
    return True


def _find_empty_syslog_slot(current: dict[str, Any]) -> int | None:
    for slot, slot_payload in _syslog_slot_items(current):
        setting = dict(slot_payload.get("setting") or {})
        server = str(setting.get("server") or "").strip()
        status = str(setting.get("status") or "").lower()
        if status != "enable" or not server:
            return slot
    return None


def _build_receive_status(ingestion: dict[str, Any]) -> dict[str, Any]:
    is_syslog = (
        ingestion.get("lastRunTrigger") == "syslog"
        or ingestion.get("status") == "streaming"
    )
    return {
        "mode": "syslog" if is_syslog else "polling",
        "pollingEnabled": bool(ingestion.get("enabled")),
        "status": ingestion.get("status"),
        "lastReceivedAt": ingestion.get("lastSuccessAt") if is_syslog else None,
        "lastEventIds": ingestion.get("lastEventIds") or [],
        "lastError": ingestion.get("lastError"),
        "rawEventCount": ingestion.get("lastRawEventCount", 0),
        "createdCount": ingestion.get("lastCreatedCount", 0),
    }


def _log_forwarding_desired(
    *,
    collector_host: str,
    port: int,
    mode: str,
    facility: str,
    format: str,
    severity: str,
) -> dict[str, dict[str, Any]]:
    return {
        "setting": {
            "status": "enable",
            "server": collector_host,
            "port": port,
            "mode": mode,
            "facility": facility,
            "format": format,
        },
        "filter": {
            "severity": severity,
            **{key: "enable" for key in SYSLOG_TRAFFIC_FILTER_KEYS},
        },
    }


def _build_log_forwarding_payload(
    *,
    integration_id: str,
    collector_host: str,
    port: int,
    mode: str,
    facility: str,
    format: str,
    severity: str,
    current: dict[str, Any],
    slot: int | None = 1,
) -> dict[str, Any]:
    desired = _log_forwarding_desired(
        collector_host=collector_host,
        port=port,
        mode=mode,
        facility=facility,
        format=format,
        severity=severity,
    )
    setting = desired["setting"]
    syslog_filter = desired["filter"]
    cli_commands = [
        "config log syslogd setting",
        "    set status enable",
        f"    set server {collector_host}",
        f"    set port {port}",
        f"    set mode {mode}",
        f"    set facility {facility}",
        f"    set format {format}",
        "end",
        "config log syslogd filter",
        f"    set severity {severity}",
        "end",
    ]
    return {
        "integrationId": integration_id,
        "mode": "syslog_forwarding",
        "slot": slot,
        "configured": _log_forwarding_configured(setting),
        "current": current,
        "desired": {"setting": setting, "filter": syslog_filter},
        "cliCommands": cli_commands,
        "warnings": [
            "This changes persistent FortiGate log forwarding configuration.",
            "Review collector reachability and existing syslog settings before applying.",
            "FortiDashboard never exposes the FortiGate API key to the browser.",
        ],
    }
