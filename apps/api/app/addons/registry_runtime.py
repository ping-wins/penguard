import logging
from collections.abc import Callable

from app.addons.contracts import AddonConnector, AddonError

logger = logging.getLogger(__name__)


class ConnectorRegistry:
    def __init__(self) -> None:
        self._factories: dict[str, Callable[[dict], AddonConnector]] = {}
        self._instances: dict[tuple[str, str], AddonConnector] = {}

    def register(
        self, addon_id: str, factory: Callable[[dict], AddonConnector]
    ) -> None:
        self._factories[addon_id] = factory
        logger.info("connector_registered addon_id=%s", addon_id)

    def unregister(self, addon_id: str) -> None:
        self._factories.pop(addon_id, None)
        for key in list(self._instances.keys()):
            if key[0] == addon_id:
                instance = self._instances.pop(key)
                try:
                    instance.close()
                except Exception as exc:
                    logger.warning(
                        "connector_close_failed addon_id=%s err=%s", addon_id, exc
                    )
        logger.info("connector_unregistered addon_id=%s", addon_id)

    def get(
        self, addon_id: str, *, integration_id: str, config: dict
    ) -> AddonConnector:
        factory = self._factories.get(addon_id)
        if factory is None:
            raise AddonError(f"connector not registered: {addon_id}")

        key = (addon_id, integration_id)
        if key not in self._instances:
            self._instances[key] = factory(config)
        return self._instances[key]
