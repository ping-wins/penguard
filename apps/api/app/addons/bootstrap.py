import logging

from sqlalchemy.orm import Session

from app.addons.installed_store import list_installed
from app.addons.loader import AddonLoader
from app.addons.registry_runtime import ConnectorRegistry

logger = logging.getLogger(__name__)


def bootstrap_installed_addons(
    *, session: Session, loader: AddonLoader, registry: ConnectorRegistry
) -> None:
    records = list_installed(session)
    for record in records:
        try:
            factory = loader.load(record)
        except Exception as exc:
            logger.exception(
                "addon_bootstrap_failed id=%s version=%s err=%s",
                record.id,
                record.version,
                exc,
            )
            continue
        registry.register(record.id, factory)
    logger.info("addon_bootstrap_loaded count=%s", len(records))
