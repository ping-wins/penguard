import ipaddress
from typing import Any
from urllib.parse import urlparse

from app.threat_intel.models import Indicator

IP_KEYS = {
    "ip",
    "sourceip",
    "destinationip",
    "remoteip",
    "dstip",
    "observedsourceip",
}
DOMAIN_KEYS = {
    "domain",
    "hostname",
    "destinationhostname",
    "queryname",
}
URL_KEYS = {"url", "uri"}


def sanitize_url_indicator(value: str) -> str | None:
    candidate = value.strip()
    if not candidate:
        return None
    parsed = urlparse(candidate if "://" in candidate else f"https://{candidate}")
    if not parsed.hostname:
        return None
    scheme = parsed.scheme.lower() if parsed.scheme in {"http", "https"} else "https"
    host = parsed.hostname.casefold()
    port = f":{parsed.port}" if parsed.port else ""
    return f"{scheme}://{host}{port}"


def extract_indicators_from_incident(incident: dict[str, Any]) -> list[Indicator]:
    indicators: list[Indicator] = []
    for container in _walk_dicts(incident):
        for key, value in container.items():
            normalized_key = str(key).replace("_", "").replace("-", "").casefold()
            indicators.extend(_indicator_from_key_value(normalized_key, value))
            if normalized_key == "ioc":
                indicators.extend(_indicator_from_ioc(value))
    return _dedupe(indicators)


def _indicator_from_key_value(key: str, value: Any) -> list[Indicator]:
    if isinstance(value, list):
        out: list[Indicator] = []
        for item in value:
            out.extend(_indicator_from_key_value(key, item))
        return out
    if not isinstance(value, str) or not value.strip():
        return []
    if key in IP_KEYS or key.endswith("ip"):
        ip_value = _normalize_ip(value)
        return [Indicator(type="ip", value=ip_value)] if ip_value else []
    if key in DOMAIN_KEYS or key.endswith("hostname") or key.endswith("domain"):
        domain = _normalize_domain(value)
        return [Indicator(type="domain", value=domain)] if domain else []
    if key in URL_KEYS or key.endswith("url"):
        sanitized = sanitize_url_indicator(value)
        return [Indicator(type="url", value=sanitized)] if sanitized else []
    return []


def _indicator_from_ioc(value: Any) -> list[Indicator]:
    if isinstance(value, list):
        out: list[Indicator] = []
        for item in value:
            out.extend(_indicator_from_ioc(item))
        return out
    if not isinstance(value, dict):
        return []
    ioc_type = str(value.get("type") or "").casefold()
    raw_value = value.get("value")
    if not isinstance(raw_value, str):
        return []
    if ioc_type == "ip":
        normalized = _normalize_ip(raw_value)
        return [Indicator(type="ip", value=normalized)] if normalized else []
    if ioc_type == "domain":
        normalized = _normalize_domain(raw_value)
        return [Indicator(type="domain", value=normalized)] if normalized else []
    if ioc_type == "url":
        normalized = sanitize_url_indicator(raw_value)
        return [Indicator(type="url", value=normalized)] if normalized else []
    return []


def _walk_dicts(value: Any) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    if isinstance(value, dict):
        found.append(value)
        for nested in value.values():
            found.extend(_walk_dicts(nested))
    elif isinstance(value, list):
        for item in value:
            found.extend(_walk_dicts(item))
    return found


def _normalize_ip(value: str) -> str | None:
    try:
        return str(ipaddress.ip_address(value.strip()))
    except ValueError:
        return None


def _normalize_domain(value: str) -> str | None:
    candidate = value.strip().rstrip(".").casefold()
    if not candidate or "/" in candidate or "\\" in candidate:
        return None
    if _normalize_ip(candidate):
        return None
    if "." not in candidate:
        return None
    return candidate


def _dedupe(indicators: list[Indicator]) -> list[Indicator]:
    seen: set[tuple[str, str]] = set()
    out: list[Indicator] = []
    for indicator in indicators:
        key = indicator.cache_key()
        if key in seen:
            continue
        seen.add(key)
        out.append(indicator)
    return out
