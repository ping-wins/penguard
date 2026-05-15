from functools import lru_cache

from app.addons.catalog_fetcher import CatalogFetcher
from app.addons.install_service import InstallService
from app.addons.loader import AddonLoader
from app.addons.registry_runtime import ConnectorRegistry
from app.core.config import get_settings
from app.db.session import SessionLocal


@lru_cache(maxsize=1)
def get_loader() -> AddonLoader:
    return AddonLoader()


@lru_cache(maxsize=1)
def get_connector_registry() -> ConnectorRegistry:
    return ConnectorRegistry()


@lru_cache(maxsize=1)
def get_catalog_fetcher() -> CatalogFetcher:
    settings = get_settings()
    return CatalogFetcher(
        repo=settings.marketplace_registry_repo,
        token=settings.marketplace_gh_token,
    )


@lru_cache(maxsize=1)
def get_install_service() -> InstallService:
    settings = get_settings()
    return InstallService(
        session_factory=lambda: SessionLocal(),
        storage_dir=settings.addons_storage_dir,
        repo=settings.marketplace_registry_repo,
        token=settings.marketplace_gh_token,
        loader=get_loader(),
    )
