from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

IndicatorType = Literal["ip", "domain", "url"]
ThreatIntelVerdict = Literal["clean", "unknown", "suspicious", "malicious"]


class Indicator(BaseModel):
    type: IndicatorType
    value: str

    def cache_key(self) -> tuple[str, str]:
        return (self.type, self.value.casefold())


class ThreatIntelEnrichment(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    indicator: Indicator
    provider: str
    verdict: ThreatIntelVerdict
    score: int = 0
    confidence: str = "medium"
    stats: dict[str, int] = Field(default_factory=dict)
    categories: dict[str, str] = Field(default_factory=dict)
    reference_url: str | None = Field(default=None, alias="referenceUrl")
    checked_at: datetime = Field(alias="checkedAt")
    cached: bool = False
    error: str | None = None
