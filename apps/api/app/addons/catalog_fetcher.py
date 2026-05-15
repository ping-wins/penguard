import json
import logging
import time
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class CatalogFetchError(RuntimeError):
    pass


class CatalogFetcher:
    def __init__(
        self,
        *,
        repo: str,
        token: str | None,
        transport: httpx.BaseTransport | None = None,
        ttl_seconds: float = 300.0,
        timeout_seconds: float = 10.0,
    ) -> None:
        self._repo = repo
        self._token = token
        self._transport = transport
        self._ttl = ttl_seconds
        self._timeout = timeout_seconds
        self._cached: dict[str, Any] | None = None
        self._cached_at: float = 0.0

    def fetch(self) -> dict[str, Any]:
        now = time.monotonic()
        if self._cached is not None and (now - self._cached_at) <= self._ttl:
            return self._cached

        url = f"https://api.github.com/repos/{self._repo}/contents/catalog.json"
        headers = {"Accept": "application/vnd.github.raw+json"}
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"

        try:
            with httpx.Client(
                transport=self._transport,
                timeout=self._timeout,
            ) as client:
                response = client.get(url, headers=headers)
        except httpx.RequestError as exc:
            raise CatalogFetchError(f"catalog request failed: {exc}") from exc

        if response.status_code != 200:
            raise CatalogFetchError(
                f"catalog fetch returned HTTP {response.status_code}"
            )

        try:
            payload = response.json()
        except json.JSONDecodeError as exc:
            raise CatalogFetchError("catalog response was not valid JSON") from exc

        if not isinstance(payload, dict) or "addons" not in payload:
            raise CatalogFetchError("catalog payload missing 'addons' key")

        self._cached = payload
        self._cached_at = now
        logger.info("catalog_fetched repo=%s addons=%s", self._repo, len(payload["addons"]))
        return payload

    def invalidate(self) -> None:
        self._cached = None
        self._cached_at = 0.0
