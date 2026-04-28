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


class FortiGateIntegrationService:
    def __init__(
        self,
        *,
        store: FortiGateIntegrationStore,
        client_factory: FortiGateClientFactory | None = None,
    ) -> None:
        self.store = store
        self.client_factory = client_factory or self._default_client_factory

    def create(
        self,
        *,
        owner_user_id: str,
        name: str,
        host: str,
        api_key: str,
        verify_tls: bool,
    ) -> dict[str, Any]:
        return self.store.create(
            owner_user_id=owner_user_id,
            name=name,
            host=host,
            api_key=api_key,
            verify_tls=verify_tls,
        )

    def test_connection(self, *, host: str, api_key: str, verify_tls: bool) -> dict[str, Any]:
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
