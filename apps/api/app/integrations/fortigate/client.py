from typing import Any

import httpx


class FortiGateApiError(RuntimeError):
    pass


class FortiGateApiClient:
    def __init__(
        self,
        *,
        host: str,
        api_key: str,
        verify_tls: bool,
        timeout_seconds: float = 10.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        if not api_key.strip():
            raise ValueError("api_key is required")
        self.host = host.rstrip("/")
        self.api_key = api_key.strip()
        self.verify_tls = verify_tls
        self.timeout_seconds = timeout_seconds
        self.transport = transport

    def get_system_status(self) -> dict[str, Any]:
        results = self._get("/api/v2/monitor/system/status", include_metadata=True)
        if not isinstance(results, dict):
            raise FortiGateApiError("FortiGate system status response was not an object")
        return results

    def get_performance_status(self) -> dict[str, Any]:
        results = self._get("/api/v2/monitor/system/performance/status")
        if not isinstance(results, dict):
            raise FortiGateApiError("FortiGate performance status response was not an object")
        return results

    def get_resource_usage(self, *, resource: str | None = None) -> dict[str, Any]:
        params = {"resource": resource} if resource else None
        results = self._get("/api/v2/monitor/system/resource/usage", params=params)
        if not isinstance(results, dict):
            raise FortiGateApiError("FortiGate resource usage response was not an object")
        return results

    def get_web_ui_state(self) -> dict[str, Any]:
        results = self._get("/api/v2/monitor/web-ui/state")
        if not isinstance(results, dict):
            raise FortiGateApiError("FortiGate web UI state response was not an object")
        return results

    def get_interfaces(self) -> list[dict[str, Any]]:
        return self._get_list("/api/v2/cmdb/system/interface")

    def get_interface_status(self) -> dict[str, Any]:
        results = self._get("/api/v2/monitor/system/interface")
        if not isinstance(results, dict):
            raise FortiGateApiError("FortiGate interface status response was not an object")
        return results

    def get_policies(self) -> list[dict[str, Any]]:
        return self._get_list("/api/v2/cmdb/firewall/policy")

    def get_threat_logs(self, *, limit: int = 25) -> list[dict[str, Any]]:
        return self._get_list("/api/v2/log/memory/ips", params={"count": limit})

    def get_admin_login_failures(self, *, limit: int = 50) -> list[dict[str, Any]]:
        return self._get_list(
            "/api/v2/log/memory/event/system",
            params=[
                ("count", limit),
                ("filter", "action==login"),
                ("filter", "status==failed"),
            ],
        )

    def _get_list(
        self,
        path: str,
        *,
        params: dict[str, Any] | list[tuple[str, Any]] | None = None,
    ) -> list[dict[str, Any]]:
        results = self._get(path, params=params)
        if isinstance(results, list):
            return [item for item in results if isinstance(item, dict)]
        if isinstance(results, dict):
            for key in ("logs", "items", "data"):
                value = results.get(key)
                if isinstance(value, list):
                    return [item for item in value if isinstance(item, dict)]
        raise FortiGateApiError(f"FortiGate {path} response was not a list")

    def _get(
        self,
        path: str,
        *,
        params: dict[str, Any] | list[tuple[str, Any]] | None = None,
        include_metadata: bool = False,
    ) -> Any:
        try:
            with httpx.Client(
                base_url=self.host,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Accept": "application/json",
                },
                verify=self.verify_tls,
                timeout=self.timeout_seconds,
                transport=self.transport,
            ) as client:
                response = client.get(path, params=params)
                response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            status_code = exc.response.status_code
            if status_code in (401, 403):
                raise FortiGateApiError(
                    "FortiGate rejected the API key (invalid or insufficient permissions)"
                ) from exc
            if status_code == 404:
                raise FortiGateApiError(
                    "FortiGate API endpoint not found "
                    f"({path}); check host URL and firmware version"
                ) from exc
            raise FortiGateApiError(
                f"FortiGate API request failed with HTTP {status_code}"
            ) from exc
        except httpx.RequestError as exc:
            raise FortiGateApiError(f"FortiGate API request failed: {exc}") from exc

        payload = self._decode_json(response)
        if isinstance(payload, dict) and payload.get("status") not in (None, "success"):
            raise FortiGateApiError("FortiGate API returned error status")
        if isinstance(payload, dict) and "results" in payload and include_metadata:
            return self._merge_envelope_metadata(payload)
        if isinstance(payload, dict) and "results" in payload:
            return payload["results"]
        return payload

    def _decode_json(self, response: httpx.Response) -> Any:
        try:
            return response.json()
        except ValueError as exc:
            raise FortiGateApiError("FortiGate API returned non-JSON response") from exc

    def _merge_envelope_metadata(self, payload: dict[str, Any]) -> Any:
        results = payload["results"]
        if not isinstance(results, dict):
            return results
        merged = dict(results)
        for key in ("serial", "version", "build", "uptime", "uptime_seconds", "uptimeSeconds"):
            if key in payload and key not in merged:
                merged[key] = payload[key]
        return merged
