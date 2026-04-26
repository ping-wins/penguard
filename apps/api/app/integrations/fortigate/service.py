from typing import Any, Protocol

from app.core.fixtures import load_fixture


class FortiGateIntegrationStore(Protocol):
    def create(
        self,
        *,
        name: str,
        host: str,
        api_key: str,
        verify_tls: bool,
    ) -> dict[str, Any]:
        pass

    def list_public(self) -> dict[str, list[dict[str, Any]]]:
        pass


class MockFortiGateIntegrationService:
    def create(
        self,
        *,
        name: str,
        host: str,
        api_key: str,
        verify_tls: bool,
    ) -> dict[str, Any]:
        return load_fixture("fortigate_integration_created")

    def test_connection(self, *, host: str, api_key: str, verify_tls: bool) -> dict[str, Any]:
        return load_fixture("fortigate_connection_test")

    def list(self) -> dict[str, Any]:
        return load_fixture("integrations_list")


class FortiGateIntegrationService:
    def __init__(self, *, store: FortiGateIntegrationStore) -> None:
        self.store = store

    def create(
        self,
        *,
        name: str,
        host: str,
        api_key: str,
        verify_tls: bool,
    ) -> dict[str, Any]:
        return self.store.create(name=name, host=host, api_key=api_key, verify_tls=verify_tls)

    def test_connection(self, *, host: str, api_key: str, verify_tls: bool) -> dict[str, Any]:
        return load_fixture("fortigate_connection_test")

    def list(self) -> dict[str, Any]:
        return self.store.list_public()
