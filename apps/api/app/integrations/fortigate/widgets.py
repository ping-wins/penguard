from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any, Protocol

from app.core.fixtures import load_fixture
from app.integrations.fortigate.client import FortiGateApiClient, FortiGateApiError
from app.integrations.fortigate.normalizers import (
    normalize_interfaces,
    normalize_policies,
    normalize_system_status,
    normalize_threat_logs,
)

CACHE_TTL_SECONDS = 30
SYSTEM_STATUS_SNAPSHOT_CACHE_KEY = "__system_status_snapshot"


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

    def get_interface_status(self) -> dict[str, Any]:
        pass

    def get_policies(self) -> list[dict[str, Any]]:
        pass

    def get_threat_logs(self, *, limit: int = 25) -> list[dict[str, Any]]:
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
        data = load_fixture("widget_data_fortigate_system_status")
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
        if cached is not None:
            cached_at, payload = cached
            if (now - cached_at).total_seconds() < CACHE_TTL_SECONDS:
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
                case _:
                    raise KeyError("Widget data not found")
        except FortiGateApiError as exc:
            payload = self._error_payload(widget_id, integration_id, str(exc), refreshed_at=now)
            self._cache[cache_key] = (now, payload)
            return payload

        payload = {
            "widgetId": widget_id,
            "integrationId": integration_id,
            "refreshedAt": self._format_datetime(now),
            "status": "ready",
            "data": data,
            "meta": {"source": "fortigate", "cacheTtlSeconds": CACHE_TTL_SECONDS},
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
    ) -> dict[str, Any]:
        return {
            "widgetId": widget_id,
            "integrationId": integration_id,
            "refreshedAt": self._format_datetime(refreshed_at),
            "status": "error",
            "data": {},
            "meta": {
                "source": "fortigate",
                "cacheTtlSeconds": CACHE_TTL_SECONDS,
                "error": {"message": message},
            },
        }

    def _system_status_data(self, client: FortiGateWidgetClient) -> dict[str, Any]:
        return normalize_system_status(
            client.get_system_status(),
            performance=client.get_performance_status(),
            resource_usage=client.get_resource_usage(resource="session"),
        )

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
        if cached is not None:
            cached_at, data = cached
            if (now - cached_at).total_seconds() < CACHE_TTL_SECONDS:
                return data

        data = self._system_status_data(client)
        self._cache[cache_key] = (now, data)
        return data

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
