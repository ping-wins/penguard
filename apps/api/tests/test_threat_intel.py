from datetime import UTC, datetime, timedelta

import httpx

from app.threat_intel.extractors import extract_indicators_from_incident, sanitize_url_indicator
from app.threat_intel.models import Indicator, ThreatIntelEnrichment
from app.threat_intel.providers import VirusTotalProvider
from app.threat_intel.service import ThreatIntelService


def test_extract_indicators_from_incident_deduplicates_ip_domain_and_sanitized_url():
    incident = {
        "entities": {
            "sourceIp": "192.0.2.50",
            "destinationIp": "198.51.100.20",
            "domain": "Suspicious.Example",
            "url": "https://suspicious.example/path?token=secret#frag",
        },
        "attributes": {
            "destinationIp": "198.51.100.20",
            "queryName": "suspicious.example",
            "url": "https://suspicious.example/other?apikey=must-not-leak",
            "ioc": {"type": "domain", "value": "suspicious.example"},
        },
    }

    indicators = extract_indicators_from_incident(incident)

    assert indicators == [
        Indicator(type="ip", value="192.0.2.50"),
        Indicator(type="ip", value="198.51.100.20"),
        Indicator(type="domain", value="suspicious.example"),
        Indicator(type="url", value="https://suspicious.example"),
    ]


def test_sanitize_url_indicator_removes_path_query_and_fragment():
    assert (
        sanitize_url_indicator("https://Example.COM:8443/download?id=secret#section")
        == "https://example.com:8443"
    )


def test_virustotal_provider_normalizes_malicious_ip_response():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v3/ip_addresses/198.51.100.20"
        assert request.headers["x-apikey"] == "vt-test-key"
        return httpx.Response(
            200,
            json={
                "data": {
                    "id": "198.51.100.20",
                    "type": "ip_address",
                    "attributes": {
                        "last_analysis_stats": {
                            "harmless": 20,
                            "malicious": 3,
                            "suspicious": 1,
                            "undetected": 40,
                        },
                        "reputation": -12,
                    },
                }
            },
        )

    provider = VirusTotalProvider(
        api_key="vt-test-key",
        base_url="https://www.virustotal.com",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    result = provider.enrich(Indicator(type="ip", value="198.51.100.20"))

    assert result.provider == "virustotal"
    assert result.verdict == "malicious"
    assert result.score == 4
    assert result.stats == {
        "harmless": 20,
        "malicious": 3,
        "suspicious": 1,
        "undetected": 40,
    }
    assert result.reference_url == "https://www.virustotal.com/gui/ip-address/198.51.100.20"


def test_threat_intel_service_reuses_cached_result_without_provider_call():
    calls: list[Indicator] = []
    checked_at = datetime(2026, 5, 19, 12, 0, tzinfo=UTC)

    class Provider:
        name = "fake-ti"

        def enrich(self, indicator: Indicator) -> ThreatIntelEnrichment:
            calls.append(indicator)
            return ThreatIntelEnrichment(
                indicator=indicator,
                provider=self.name,
                verdict="suspicious",
                score=1,
                stats={"malicious": 0, "suspicious": 1},
                checked_at=checked_at,
            )

    service = ThreatIntelService(
        provider=Provider(),
        cache_ttl_seconds=3600,
        now=lambda: checked_at,
    )
    indicator = Indicator(type="domain", value="suspicious.example")

    first = service.enrich_indicators([indicator])[0]
    second = service.enrich_indicators([indicator])[0]

    assert len(calls) == 1
    assert first.cached is False
    assert second.cached is True

    later = checked_at + timedelta(seconds=3601)
    service.now = lambda: later
    third = service.enrich_indicators([indicator])[0]

    assert len(calls) == 2
    assert third.cached is False
