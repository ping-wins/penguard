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
    ) -> dict[str, Any]:
        pass

    def list_public(self, *, owner_user_id: str) -> dict[str, list[dict[str, Any]]]:
        pass

    def get_connection(self, integration_id: str, *, owner_user_id: str) -> dict[str, Any] | None:
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


class FortiGateClient(Protocol):
    def get_system_status(self) -> dict[str, Any]:
        pass

    def get_performance_status(self) -> dict[str, Any]:
        pass

    def get_resource_usage(self, *, resource: str | None = None) -> dict[str, Any]:
        pass


class FortiGateClientFactory(Protocol):
    def __call__(self, *, host: str, api_key: str, verify_tls: bool) -> FortiGateClient:
        pass


class FortiGateConnectionFailed(RuntimeError):
    pass


class MockFortiGateIntegrationService:
    def create(
        self,
        *,
        owner_user_id: str,
        name: str,
        host: str,
        api_key: str,
        verify_tls: bool,
    ) -> dict[str, Any]:
        return load_fixture("fortigate_integration_created")

    def test_connection(self, *, host: str, api_key: str, verify_tls: bool) -> dict[str, Any]:
        return load_fixture("fortigate_connection_test")

    def list(self, *, owner_user_id: str) -> dict[str, Any]:
        return load_fixture("integrations_list")

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
    ) -> dict[str, Any]:
        probe = self._probe_connection(host=host, api_key=api_key, verify_tls=verify_tls)
        if not probe["ok"]:
            error = probe.get("error") or {}
            raise FortiGateConnectionFailed(error.get("message") or "FortiGate connection failed")
        return self.store.create(
            owner_user_id=owner_user_id,
            name=name,
            host=host,
            api_key=api_key,
            verify_tls=verify_tls,
        )

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
            },
        }

    def list(self, *, owner_user_id: str) -> dict[str, Any]:
        return self.store.list_public(owner_user_id=owner_user_id)

    def _default_client_factory(
        self,
        *,
        host: str,
        api_key: str,
        verify_tls: bool,
    ) -> FortiGateApiClient:
        return FortiGateApiClient(host=host, api_key=api_key, verify_tls=verify_tls)
