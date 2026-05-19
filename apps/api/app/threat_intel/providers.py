import base64
from datetime import UTC, datetime
from typing import Any, Protocol

import httpx

from app.threat_intel.models import Indicator, ThreatIntelEnrichment


class ThreatIntelProvider(Protocol):
    name: str

    def enrich(self, indicator: Indicator) -> ThreatIntelEnrichment: ...


class VirusTotalProvider:
    name = "virustotal"

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str = "https://www.virustotal.com",
        http_client: httpx.Client | None = None,
        timeout_seconds: float = 8.0,
    ) -> None:
        self.api_key = api_key.strip()
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.http_client = http_client or httpx.Client(timeout=timeout_seconds)

    def enrich(self, indicator: Indicator) -> ThreatIntelEnrichment:
        if not self.api_key:
            return _error_result(indicator, self.name, "VirusTotal API key is not configured")
        path = self._path_for_indicator(indicator)
        response = self.http_client.get(
            f"{self.base_url}{path}",
            headers={"x-apikey": self.api_key},
            timeout=self.timeout_seconds,
        )
        if response.status_code == 404:
            return ThreatIntelEnrichment(
                indicator=indicator,
                provider=self.name,
                verdict="unknown",
                score=0,
                stats={},
                checkedAt=datetime.now(UTC),
                referenceUrl=self._reference_url(indicator),
            )
        if response.status_code == 429:
            return _error_result(indicator, self.name, "VirusTotal quota exceeded")
        response.raise_for_status()
        payload = response.json()
        attributes = payload.get("data", {}).get("attributes", {})
        stats = _int_stats(attributes.get("last_analysis_stats"))
        score = stats.get("malicious", 0) + stats.get("suspicious", 0)
        return ThreatIntelEnrichment(
            indicator=indicator,
            provider=self.name,
            verdict=_verdict_from_stats(stats),
            score=score,
            stats=stats,
            categories=_string_dict(attributes.get("categories")),
            checkedAt=datetime.now(UTC),
            referenceUrl=self._reference_url(indicator),
        )

    def _path_for_indicator(self, indicator: Indicator) -> str:
        if indicator.type == "ip":
            return f"/api/v3/ip_addresses/{indicator.value}"
        if indicator.type == "domain":
            return f"/api/v3/domains/{indicator.value}"
        return f"/api/v3/urls/{_vt_url_id(indicator.value)}"

    def _reference_url(self, indicator: Indicator) -> str:
        if indicator.type == "ip":
            return f"https://www.virustotal.com/gui/ip-address/{indicator.value}"
        if indicator.type == "domain":
            return f"https://www.virustotal.com/gui/domain/{indicator.value}"
        return f"https://www.virustotal.com/gui/url/{_vt_url_id(indicator.value)}"


def _vt_url_id(value: str) -> str:
    encoded = base64.urlsafe_b64encode(value.encode("utf-8")).decode("ascii")
    return encoded.rstrip("=")


def _verdict_from_stats(stats: dict[str, int]) -> str:
    if stats.get("malicious", 0) > 0:
        return "malicious"
    if stats.get("suspicious", 0) > 0:
        return "suspicious"
    if stats:
        return "clean"
    return "unknown"


def _int_stats(value: Any) -> dict[str, int]:
    if not isinstance(value, dict):
        return {}
    out: dict[str, int] = {}
    for key in ("harmless", "malicious", "suspicious", "timeout", "undetected"):
        raw = value.get(key)
        if isinstance(raw, int):
            out[key] = raw
    return out


def _string_dict(value: Any) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    return {str(key): str(item) for key, item in value.items() if item is not None}


def _error_result(indicator: Indicator, provider: str, message: str) -> ThreatIntelEnrichment:
    return ThreatIntelEnrichment(
        indicator=indicator,
        provider=provider,
        verdict="unknown",
        score=0,
        checkedAt=datetime.now(UTC),
        error=message,
    )
