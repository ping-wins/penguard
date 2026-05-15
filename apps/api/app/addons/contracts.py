"""Contracts that bound the dashboard <-> add-on package interface.

Add-on packages do NOT import this module — the `AddonConnector` Protocol
is duck-typed. Anything in the dashboard that calls an add-on imports
from here.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol


class AddonError(RuntimeError):
    """Base for errors raised by the add-on subsystem."""


class AddonLoadError(AddonError):
    """Raised when loader cannot import or register an installed package."""


class AddonInstallError(AddonError):
    """Raised when install service cannot fetch / extract / validate a package."""


@dataclass
class HealthCheckResult:
    ok: bool
    status: str
    device: dict[str, Any]
    message: str | None = None
    latency_ms: int | None = None


@dataclass
class WidgetDataRequest:
    widget_id: str
    integration_id: str
    config: dict[str, Any]
    since: datetime | None = None


@dataclass
class SiemEvent:
    event_type: str
    occurred_at: datetime
    severity: str
    payload: dict[str, Any]


class AddonConnector(Protocol):
    def health_check(self) -> dict[str, Any]: ...
    def get_widget_data(self, req: dict[str, Any]) -> dict[str, Any]: ...
    def ingest_events(self, since: datetime | None) -> list[dict[str, Any]]: ...
    def close(self) -> None: ...
