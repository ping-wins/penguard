from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any, Protocol

from app.core.fixtures import load_fixture
from app.integrations.fortigate.client import FortiGateApiClient, FortiGateApiError
from app.integrations.fortigate.normalizers import (
    normalize_admin_login_failures,
    normalize_interfaces,
    normalize_policies,
    normalize_system_status,
    normalize_threat_logs,
)

DEFAULT_REFRESH_INTERVAL_SECONDS = 10
WIDGET_REFRESH_INTERVAL_SECONDS = {
    "fortigate-system-status": 2,
    "fortigate-kpi-sessions": 2,
    "fortigate-network-traffic": 2,
    "fortigate-top-threats": 5,
    "fortigate-firewall-policies": 15,
    "fortigate-risk-posture": 5,
    "fortigate-interface-health": 2,
    "fortigate-recent-events": 5,
    "fortigate-anomaly-highlights": 5,
}
SYSTEM_STATUS_SNAPSHOT_CACHE_KEY = "__system_status_snapshot"

MOCK_WIDGET_FIXTURES = {
    "fortigate-system-status": "widget_data_fortigate_system_status",
    "fortigate-risk-posture": "widget_data_fortigate_risk_posture",
    "fortigate-interface-health": "widget_data_fortigate_interface_health",
    "fortigate-recent-events": "widget_data_fortigate_recent_events",
    "fortigate-anomaly-highlights": "widget_data_fortigate_anomaly_highlights",
}


class FortiGateConnectionStore(Protocol):
    def get_connection(self, integration_id: str, *, owner_user_id: str) -> dict[str, Any] | None:
        pass


class FortiGateWidgetClient(Protocol):
    def get_system_status(self) -> dict[str, Any]:
        pass

    def get_performance_status(self) -> dict[str, Any]:
        pass

    def get_resource_usage(self, *, resource: str | None = None) -> dict[str, Any]:
        pass

    def get_web_ui_state(self) -> dict[str, Any]:
        pass

    def get_interface_status(self) -> dict[str, Any]:
        pass

    def get_policies(self) -> list[dict[str, Any]]:
        pass

    def get_threat_logs(self, *, limit: int = 25) -> list[dict[str, Any]]:
        pass

    def get_admin_login_failures(self, *, limit: int = 50) -> list[dict[str, Any]]:
        pass


class FortiGateWidgetClientFactory(Protocol):
    def __call__(self, *, host: str, api_key: str, verify_tls: bool) -> FortiGateWidgetClient:
        pass


class MockFortiGateWidgetDataService:
    def get_widget_data(
        self,
        widget_id: str,
        integration_id: str,
        *,
        owner_user_id: str,
    ) -> dict[str, Any]:
        fixture_name = MOCK_WIDGET_FIXTURES.get(widget_id)
        if fixture_name is None:
            raise KeyError("Widget data not found")
        data = load_fixture(fixture_name)
        if widget_id != data["widgetId"] or integration_id != data["integrationId"]:
            raise KeyError("Widget data not found")
        return data


class FortiGateWidgetDataService:
    def __init__(
        self,
        *,
        store: FortiGateConnectionStore,
        client_factory: FortiGateWidgetClientFactory | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.store = store
        self.client_factory = client_factory or self._default_client_factory
        self.clock = clock or (lambda: datetime.now(UTC))
        self._cache: dict[tuple[str, str, str], tuple[datetime, dict[str, Any]]] = {}

    def get_widget_data(
        self,
        widget_id: str,
        integration_id: str,
        *,
        owner_user_id: str,
    ) -> dict[str, Any]:
        cache_key = (owner_user_id, integration_id, widget_id)
        cached = self._cache.get(cache_key)
        now = self.clock()
        cache_ttl_seconds = self._cache_ttl_seconds(widget_id)
        if cached is not None:
            cached_at, payload = cached
            if (now - cached_at).total_seconds() < cache_ttl_seconds:
                return payload

        client = self._client_for_integration(integration_id, owner_user_id=owner_user_id)
        try:
            match widget_id:
                case "fortigate-system-status":
                    data = self._cached_system_status_data(
                        client,
                        owner_user_id=owner_user_id,
                        integration_id=integration_id,
                        now=now,
                    )
                case "fortigate-kpi-sessions":
                    system_status = self._cached_system_status_data(
                        client,
                        owner_user_id=owner_user_id,
                        integration_id=integration_id,
                        now=now,
                    )
                    data = {"sessions": system_status["sessions"]}
                case "fortigate-network-traffic":
                    data = {"interfaces": normalize_interfaces(client.get_interface_status())}
                case "fortigate-firewall-policies":
                    data = {"policies": normalize_policies(client.get_policies())}
                case "fortigate-top-threats":
                    data = {"threats": normalize_threat_logs(client.get_threat_logs(limit=25))}
                case "fortigate-risk-posture":
                    data = self._risk_posture_data(
                        client,
                        owner_user_id=owner_user_id,
                        integration_id=integration_id,
                        now=now,
                    )
                case "fortigate-interface-health":
                    data = self._interface_health_data(client)
                case "fortigate-recent-events":
                    data = self._recent_events_data(client)
                case "fortigate-anomaly-highlights":
                    data = self._anomaly_highlights_data(
                        client,
                        owner_user_id=owner_user_id,
                        integration_id=integration_id,
                        now=now,
                    )
                case _:
                    raise KeyError("Widget data not found")
        except FortiGateApiError as exc:
            payload = self._error_payload(
                widget_id,
                integration_id,
                str(exc),
                refreshed_at=now,
                cache_ttl_seconds=cache_ttl_seconds,
            )
            self._cache[cache_key] = (now, payload)
            return payload

        payload = {
            "widgetId": widget_id,
            "integrationId": integration_id,
            "refreshedAt": self._format_datetime(now),
            "status": "ready",
            "data": data,
            "meta": self._meta(widget_id, cache_ttl_seconds=cache_ttl_seconds),
        }
        self._cache[cache_key] = (now, payload)
        return payload

    def _error_payload(
        self,
        widget_id: str,
        integration_id: str,
        message: str,
        *,
        refreshed_at: datetime,
        cache_ttl_seconds: int,
    ) -> dict[str, Any]:
        return {
            "widgetId": widget_id,
            "integrationId": integration_id,
            "refreshedAt": self._format_datetime(refreshed_at),
            "status": "error",
            "data": {},
            "meta": {
                "source": "fortigate",
                "cacheTtlSeconds": cache_ttl_seconds,
                "refreshIntervalSeconds": self._refresh_interval_seconds(widget_id),
                "error": {"message": message},
            },
        }

    def _system_status_data(self, client: FortiGateWidgetClient) -> dict[str, Any]:
        web_ui_state = None
        try:
            web_ui_state = client.get_web_ui_state()
        except FortiGateApiError:
            web_ui_state = None
        return normalize_system_status(
            client.get_system_status(),
            performance=client.get_performance_status(),
            resource_usage=client.get_resource_usage(resource="session"),
            web_ui_state=web_ui_state,
        )

    def _risk_posture_data(
        self,
        client: FortiGateWidgetClient,
        *,
        owner_user_id: str,
        integration_id: str,
        now: datetime,
    ) -> dict[str, Any]:
        system_status = self._cached_system_status_data(
            client,
            owner_user_id=owner_user_id,
            integration_id=integration_id,
            now=now,
        )
        interfaces = normalize_interfaces(client.get_interface_status())
        policies = normalize_policies(client.get_policies())
        signals = _risk_signals(system_status, interfaces, policies)
        return {
            "score": _risk_score(signals),
            "level": _risk_level(signals),
            "signals": signals,
            "summary": _risk_summary(signals),
        }

    def _interface_health_data(self, client: FortiGateWidgetClient) -> dict[str, Any]:
        interfaces = normalize_interfaces(client.get_interface_status())
        return {
            "interfaces": interfaces,
            "summary": _interface_summary(interfaces),
        }

    def _recent_events_data(self, client: FortiGateWidgetClient) -> dict[str, Any]:
        threats = normalize_threat_logs(client.get_threat_logs(limit=25))
        admin_failures: list[dict[str, Any]] = []
        fetch_failures = getattr(client, "get_admin_login_failures", None)
        if callable(fetch_failures):
            try:
                admin_failures = normalize_admin_login_failures(fetch_failures(limit=50))
            except FortiGateApiError:
                admin_failures = []
        events = [*threats, *admin_failures]
        return {
            "events": events,
            "summary": _event_summary(events),
        }

    def _anomaly_highlights_data(
        self,
        client: FortiGateWidgetClient,
        *,
        owner_user_id: str,
        integration_id: str,
        now: datetime,
    ) -> dict[str, Any]:
        system_status = self._cached_system_status_data(
            client,
            owner_user_id=owner_user_id,
            integration_id=integration_id,
            now=now,
        )
        interfaces = normalize_interfaces(client.get_interface_status())
        anomalies = _anomalies(system_status, interfaces)
        severity_order = {"none": 0, "healthy": 1, "warning": 2, "critical": 3}
        highest = "none"
        for anomaly in anomalies:
            if severity_order[anomaly["severity"]] > severity_order[highest]:
                highest = anomaly["severity"]
        return {
            "anomalies": anomalies,
            "summary": {
                "count": len(anomalies),
                "highestSeverity": highest,
            },
        }

    def _cached_system_status_data(
        self,
        client: FortiGateWidgetClient,
        *,
        owner_user_id: str,
        integration_id: str,
        now: datetime,
    ) -> dict[str, Any]:
        cache_key = (owner_user_id, integration_id, SYSTEM_STATUS_SNAPSHOT_CACHE_KEY)
        cached = self._cache.get(cache_key)
        cache_ttl_seconds = self._cache_ttl_seconds("fortigate-system-status")
        if cached is not None:
            cached_at, data = cached
            if (now - cached_at).total_seconds() < cache_ttl_seconds:
                return data

        data = self._system_status_data(client)
        self._cache[cache_key] = (now, data)
        return data

    def _meta(self, widget_id: str, *, cache_ttl_seconds: int) -> dict[str, Any]:
        return {
            "source": "fortigate",
            "cacheTtlSeconds": cache_ttl_seconds,
            "refreshIntervalSeconds": self._refresh_interval_seconds(widget_id),
        }

    def _cache_ttl_seconds(self, widget_id: str) -> int:
        return self._refresh_interval_seconds(widget_id)

    def _refresh_interval_seconds(self, widget_id: str) -> int:
        return WIDGET_REFRESH_INTERVAL_SECONDS.get(widget_id, DEFAULT_REFRESH_INTERVAL_SECONDS)

    def _client_for_integration(
        self,
        integration_id: str,
        *,
        owner_user_id: str,
    ) -> FortiGateWidgetClient:
        connection = self.store.get_connection(integration_id, owner_user_id=owner_user_id)
        if connection is None:
            raise KeyError("Integration not found")
        return self.client_factory(
            host=str(connection["host"]),
            api_key=str(connection["api_key"]),
            verify_tls=bool(connection["verify_tls"]),
        )

    def _default_client_factory(
        self,
        *,
        host: str,
        api_key: str,
        verify_tls: bool,
    ) -> FortiGateApiClient:
        return FortiGateApiClient(host=host, api_key=api_key, verify_tls=verify_tls)

    def _format_datetime(self, value: datetime) -> str:
        return value.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _risk_signals(
    system_status: dict[str, Any],
    interfaces: list[dict[str, Any]],
    policies: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    signals = []
    cpu = _optional_int(system_status.get("cpu"))
    memory = _optional_int(system_status.get("memory"))
    down_interfaces = [interface for interface in interfaces if interface.get("status") != "up"]
    disabled_policies = [policy for policy in policies if policy.get("status") == "disabled"]

    if cpu is not None:
        if cpu >= 85:
            signals.append(
                {
                    "id": "system.cpu",
                    "label": "High CPU usage",
                    "severity": "critical",
                    "value": cpu,
                    "unit": "percent",
                    "description": "FortiGate CPU usage is above 85%.",
                }
            )
        else:
            signals.append(
                {
                    "id": "system.cpu",
                    "label": "CPU within expected range",
                    "severity": "healthy",
                    "value": cpu,
                    "unit": "percent",
                    "description": "FortiGate CPU usage is below SOC attention thresholds.",
                }
            )

    if memory is not None:
        if memory >= 85:
            signals.append(
                {
                    "id": "system.memory",
                    "label": "High memory usage",
                    "severity": "critical",
                    "value": memory,
                    "unit": "percent",
                    "description": "FortiGate memory usage is above 85%.",
                }
            )
        else:
            signals.append(
                {
                    "id": "system.memory",
                    "label": "Memory within expected range",
                    "severity": "healthy",
                    "value": memory,
                    "unit": "percent",
                    "description": "FortiGate memory usage is below SOC attention thresholds.",
                }
            )

    if down_interfaces:
        signals.append(
            {
                "id": "interfaces.down",
                "label": "Interfaces down",
                "severity": "warning",
                "value": len(down_interfaces),
                "unit": "count",
                "description": "One or more FortiGate interfaces report link down.",
            }
        )
    else:
        signals.append(
            {
                "id": "interfaces.down",
                "label": "Interfaces passing traffic",
                "severity": "healthy",
                "value": 0,
                "unit": "count",
                "description": "All observed FortiGate interfaces report link up.",
            }
        )

    if disabled_policies:
        signals.append(
            {
                "id": "policies.disabled",
                "label": "Disabled firewall policies",
                "severity": "warning",
                "value": len(disabled_policies),
                "unit": "count",
                "description": "One or more firewall policies are disabled.",
            }
        )
    else:
        signals.append(
            {
                "id": "policies.enabled",
                "label": "Firewall policies enabled",
                "severity": "healthy",
                "value": len(policies),
                "unit": "count",
                "description": "Observed firewall policies are enabled.",
            }
        )

    return signals


def _risk_score(signals: list[dict[str, Any]]) -> int:
    score = 100
    for signal in signals:
        if signal["severity"] == "critical":
            score -= 20
        elif signal["severity"] == "warning":
            score -= 6
    return max(0, min(100, score))


def _risk_level(signals: list[dict[str, Any]]) -> str:
    summary = _risk_summary(signals)
    if summary["critical"] > 0:
        return "high"
    if summary["warning"] > 0:
        return "medium"
    return "low"


def _risk_summary(signals: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "critical": sum(1 for signal in signals if signal["severity"] == "critical"),
        "warning": sum(1 for signal in signals if signal["severity"] == "warning"),
        "healthy": sum(1 for signal in signals if signal["severity"] == "healthy"),
    }


def _interface_summary(interfaces: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "total": len(interfaces),
        "up": sum(1 for interface in interfaces if interface.get("status") == "up"),
        "down": sum(1 for interface in interfaces if interface.get("status") != "up"),
        "totalRxBytes": sum(
            _optional_int(interface.get("rxBytes")) or 0 for interface in interfaces
        ),
        "totalTxBytes": sum(
            _optional_int(interface.get("txBytes")) or 0 for interface in interfaces
        ),
    }


def _event_summary(events: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "total": len(events),
        "blocked": sum(1 for event in events if str(event.get("action", "")).lower() == "blocked"),
        "highSeverity": sum(
            1 for event in events if str(event.get("severity", "")).lower() in {"high", "critical"}
        ),
    }


def _anomalies(
    system_status: dict[str, Any],
    interfaces: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    anomalies = []
    cpu = _optional_int(system_status.get("cpu"))
    memory = _optional_int(system_status.get("memory"))
    down_count = sum(1 for interface in interfaces if interface.get("status") != "up")

    if cpu is not None and cpu >= 85:
        anomalies.append(
            {
                "id": "cpu-critical",
                "title": "CPU pressure above normal SOC threshold",
                "severity": "critical",
                "metric": "system.cpu",
                "value": cpu,
                "unit": "percent",
                "description": "Sustained CPU pressure can delay inspection and logging.",
            }
        )
    if memory is not None and memory >= 85:
        anomalies.append(
            {
                "id": "memory-critical",
                "title": "Memory pressure above normal SOC threshold",
                "severity": "critical",
                "metric": "system.memory",
                "value": memory,
                "unit": "percent",
                "description": "High memory usage can indicate overloaded inspection or logging.",
            }
        )
    if down_count > 0:
        anomalies.append(
            {
                "id": "interfaces-down",
                "title": "Interface link down",
                "severity": "warning",
                "metric": "interfaces.down",
                "value": down_count,
                "unit": "count",
                "description": "One or more FortiGate interfaces are not passing traffic.",
            }
        )
    return anomalies


def _optional_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
