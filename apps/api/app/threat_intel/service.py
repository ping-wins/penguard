from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from app.threat_intel.models import Indicator, ThreatIntelEnrichment
from app.threat_intel.providers import ThreatIntelProvider


@dataclass
class _CacheEntry:
    result: ThreatIntelEnrichment
    expires_at: datetime


class ThreatIntelService:
    def __init__(
        self,
        *,
        provider: ThreatIntelProvider | None,
        cache_ttl_seconds: int,
        now=None,
    ) -> None:
        self.provider = provider
        self.cache_ttl_seconds = cache_ttl_seconds
        self.now = now or (lambda: datetime.now(UTC))
        self._cache: dict[tuple[str, str], _CacheEntry] = {}

    @property
    def provider_name(self) -> str:
        return self.provider.name if self.provider is not None else "unconfigured"

    @property
    def configured(self) -> bool:
        return self.provider is not None

    def enrich_indicators(self, indicators: list[Indicator]) -> list[ThreatIntelEnrichment]:
        if self.provider is None:
            return [
                ThreatIntelEnrichment(
                    indicator=indicator,
                    provider="unconfigured",
                    verdict="unknown",
                    score=0,
                    checkedAt=self.now(),
                    error="Threat Intel provider is not configured",
                )
                for indicator in indicators
            ]
        results: list[ThreatIntelEnrichment] = []
        for indicator in indicators:
            cached = self._cache.get(indicator.cache_key())
            now = self.now()
            if cached is not None and cached.expires_at > now:
                results.append(cached.result.model_copy(update={"cached": True}))
                continue
            result = self.provider.enrich(indicator)
            result = result.model_copy(update={"cached": False})
            self._cache[indicator.cache_key()] = _CacheEntry(
                result=result,
                expires_at=now + timedelta(seconds=self.cache_ttl_seconds),
            )
            results.append(result)
        return results
