import json as jsonlib
import re
from typing import Any

import httpx


class FortiWebApiError(RuntimeError):
    pass


def _response_error_excerpt(response: httpx.Response, *, max_length: int = 240) -> str:
    text = response.text.strip()
    if not text:
        return ""
    try:
        payload = response.json()
    except ValueError:
        excerpt = text
    else:
        excerpt = jsonlib.dumps(payload, sort_keys=True, separators=(",", ":"))
    return excerpt[:max_length]


def _http_status_error_message(response: httpx.Response) -> str:
    message = f"FortiWeb API request failed with HTTP {response.status_code}"
    detail = _response_error_excerpt(response)
    if detail:
        return f"{message}: {detail}"
    return message


class FortiWebApiClient:
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
            raise ValueError("FortiWeb authorization is required")
        self.host = host.rstrip("/")
        self.api_key = api_key.strip()
        self.verify_tls = verify_tls
        self.timeout_seconds = timeout_seconds
        self.transport = transport

    def get_system_status(self) -> dict[str, Any]:
        results = self._get("/api/v2.0/system/status", include_metadata=True)
        if not isinstance(results, dict):
            raise FortiWebApiError("FortiWeb system status response was not an object")
        return results

    def get_server_policy(self, name: str) -> dict[str, Any]:
        results = self._get(
            "/api/v2.0/cmdb/server-policy/policy",
            params={"mkey": name},
        )
        results = self._named_object(results, name, "FortiWeb server policy")
        if not isinstance(results, dict):
            raise FortiWebApiError("FortiWeb server policy response was not an object")
        return results

    def update_server_policy(self, name: str, payload: dict[str, Any]) -> dict[str, Any]:
        results = self._put(
            "/api/v2.0/cmdb/server-policy/policy",
            params={"mkey": name},
            json={"data": payload},
        )
        results = self._single_object(results, "FortiWeb server policy update")
        if not isinstance(results, dict):
            raise FortiWebApiError("FortiWeb server policy update response was not an object")
        return results

    def get_inline_protection_profile(self, name: str) -> dict[str, Any]:
        results = self._get(
            "/api/v2.0/cmdb/waf/web-protection-profile.inline-protection",
            params={"mkey": name},
        )
        results = self._named_object(results, name, "FortiWeb inline protection")
        if not isinstance(results, dict):
            raise FortiWebApiError("FortiWeb inline protection response was not an object")
        return results

    def update_inline_protection_profile(
        self,
        name: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        results = self._put(
            "/api/v2.0/cmdb/waf/web-protection-profile.inline-protection",
            params={"mkey": name},
            json={"data": payload},
        )
        results = self._single_object(results, "FortiWeb inline protection update")
        if not isinstance(results, dict):
            raise FortiWebApiError("FortiWeb inline protection update response was not an object")
        return results

    def create_inline_protection_profile(self, payload: dict[str, Any]) -> dict[str, Any]:
        results = self._post(
            "/api/v2.0/cmdb/waf/web-protection-profile.inline-protection",
            json={"data": payload},
        )
        results = self._single_object(results, "FortiWeb inline protection create")
        if not isinstance(results, dict):
            raise FortiWebApiError("FortiWeb inline protection create response was not an object")
        return results

    def get_application_layer_dos_prevention(self, name: str) -> dict[str, Any]:
        results = self._get(
            "/api/v2.0/cmdb/waf/application-layer-dos-prevention",
            params={"mkey": name},
        )
        results = self._named_object(results, name, "FortiWeb DoS prevention policy")
        if not isinstance(results, dict):
            raise FortiWebApiError("FortiWeb DoS prevention response was not an object")
        return results

    def get_ip_list(self, name: str) -> dict[str, Any]:
        results = self._get(f"/api/v2.0/cmdb/waf/ip-list/{name}")
        if not isinstance(results, dict):
            raise FortiWebApiError("FortiWeb IP list response was not an object")
        return results

    def create_ip_list(self, payload: dict[str, Any]) -> dict[str, Any]:
        results = self._post("/api/v2.0/cmdb/waf/ip-list", json=payload)
        if not isinstance(results, dict):
            raise FortiWebApiError("FortiWeb IP list create response was not an object")
        return results

    def update_ip_list(self, name: str, payload: dict[str, Any]) -> dict[str, Any]:
        results = self._put(f"/api/v2.0/cmdb/waf/ip-list/{name}", json=payload)
        if not isinstance(results, dict):
            raise FortiWebApiError("FortiWeb IP list update response was not an object")
        return results

    def _get(
        self,
        path: str,
        *,
        params: dict[str, Any] | list[tuple[str, Any]] | None = None,
        include_metadata: bool = False,
    ) -> Any:
        return self._request("GET", path, params=params, include_metadata=include_metadata)

    def _post(
        self,
        path: str,
        *,
        params: dict[str, Any] | list[tuple[str, Any]] | None = None,
        json: dict[str, Any],
    ) -> Any:
        return self._request("POST", path, params=params, json=json)

    def _put(
        self,
        path: str,
        *,
        params: dict[str, Any] | list[tuple[str, Any]] | None = None,
        json: dict[str, Any],
    ) -> Any:
        return self._request("PUT", path, params=params, json=json)

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | list[tuple[str, Any]] | None = None,
        json: dict[str, Any] | None = None,
        include_metadata: bool = False,
    ) -> Any:
        try:
            with httpx.Client(
                base_url=self.host,
                headers=self._headers(json_body=json is not None),
                verify=self.verify_tls,
                timeout=self.timeout_seconds,
                transport=self.transport,
            ) as client:
                response = client.request(method, path, params=params, json=json)
                response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            status_code = exc.response.status_code
            if status_code in (401, 403):
                raise FortiWebApiError(
                    "FortiWeb credentials invalid or insufficient permissions"
                ) from exc
            if status_code == 404:
                raise FortiWebApiError(
                    "FortiWeb API endpoint not found "
                    f"({path}); check host URL and firmware version"
                ) from exc
            raise FortiWebApiError(_http_status_error_message(exc.response)) from exc
        except httpx.RequestError as exc:
            raise FortiWebApiError(f"FortiWeb API request failed: {exc}") from exc

        payload = self._decode_json(response)
        if isinstance(payload, dict) and payload.get("status") not in (None, "success"):
            raise FortiWebApiError("FortiWeb API returned error status")
        if isinstance(payload, dict) and "results" in payload and include_metadata:
            return self._merge_envelope_metadata(payload)
        if isinstance(payload, dict) and "results" in payload:
            return payload["results"]
        return payload

    def _headers(self, *, json_body: bool) -> dict[str, str]:
        headers = {
            "Authorization": self.api_key,
            "Accept": "application/json",
        }
        if json_body:
            headers["Content-Type"] = "application/json"
        return headers

    def _decode_json(self, response: httpx.Response) -> Any:
        try:
            return response.json()
        except ValueError as exc:
            loose_payload = _decode_loose_status_payload(response.text)
            if loose_payload is not None:
                return loose_payload
            raise FortiWebApiError("FortiWeb API returned non-JSON response") from exc

    def _merge_envelope_metadata(self, payload: dict[str, Any]) -> Any:
        results = payload["results"]
        if not isinstance(results, dict):
            return results
        merged = dict(results)
        for key in ("serial", "version", "build", "hostname", "model", "model_name"):
            if key in payload and key not in merged:
                merged[key] = payload[key]
        return merged

    def _single_object(self, payload: Any, label: str) -> Any:
        if isinstance(payload, list):
            if len(payload) == 1 and isinstance(payload[0], dict):
                return payload[0]
            raise FortiWebApiError(f"{label} response did not contain exactly one object")
        return payload

    def _named_object(self, payload: Any, name: str, label: str) -> Any:
        if isinstance(payload, list):
            for item in payload:
                if isinstance(item, dict) and _matches_fortiweb_name(item, name):
                    return item
            if len(payload) == 1 and isinstance(payload[0], dict):
                return payload[0]
            raise FortiWebApiError(f"{label} response did not contain object named {name}")
        return payload


def _matches_fortiweb_name(item: dict[str, Any], name: str) -> bool:
    candidate = item.get("name") or item.get("q_origin_key")
    return str(candidate) == name


def _decode_loose_status_payload(text: str) -> dict[str, Any] | None:
    stripped = text.strip()
    if not (stripped.startswith("{") and stripped.endswith("}")):
        return None
    pairs = re.findall(r"([A-Za-z_][A-Za-z0-9_]*)\s*:\s*([^{}\s]+)", stripped)
    if not pairs:
        return None
    return {key: _coerce_loose_value(value) for key, value in pairs}


def _coerce_loose_value(value: str) -> Any:
    cleaned = value.strip().strip(",").strip("\"'")
    if cleaned.lower() == "true":
        return True
    if cleaned.lower() == "false":
        return False
    try:
        return int(cleaned)
    except ValueError:
        pass
    try:
        return float(cleaned)
    except ValueError:
        return cleaned
