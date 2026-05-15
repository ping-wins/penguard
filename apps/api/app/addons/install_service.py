import hashlib
import io
import json
import logging
import shutil
import tarfile
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import httpx

from app.addons.contracts import AddonConnector, AddonInstallError
from app.addons.installed_store import (
    InstalledAddonRecord,
    delete_installed,
    get_installed,
    upsert_installed,
)
from app.addons.loader import AddonLoader
from app.addons.manifest import AddonManifest

logger = logging.getLogger(__name__)


class InstallService:
    def __init__(
        self,
        *,
        session_factory: Callable[[], object],
        storage_dir: Path,
        repo: str,
        token: str | None,
        loader: AddonLoader,
        transport: httpx.BaseTransport | None = None,
        timeout_seconds: float = 60.0,
    ) -> None:
        self._session_factory = session_factory
        self._storage = Path(storage_dir)
        self._repo = repo
        self._token = token
        self._loader = loader
        self._transport = transport
        self._timeout = timeout_seconds

    def install(
        self, addon_id: str, *, version: str
    ) -> Callable[[dict], AddonConnector]:
        tag = f"{addon_id}-v{version}"
        tarball = self._fetch_tarball(tag)
        sha = hashlib.sha256(tarball).hexdigest()

        staging = self._storage / ".tmp" / uuid.uuid4().hex
        staging.mkdir(parents=True, exist_ok=True)
        try:
            self._extract(tarball, staging)
            source = self._locate_package(staging, addon_id, version)
            self._validate_manifest(source, addon_id, version)

            self._evict_previous_version(addon_id, keep_version=version)

            target = self._storage / addon_id / version
            self._move_into_place(source, target)

            record = InstalledAddonRecord(
                id=addon_id,
                version=version,
                path=str(target),
                tag=tag,
                sha256=sha,
                status="active",
                installed_at=datetime.now(UTC),
            )
            self._write_install_metadata(target, record)

            session = self._session_factory()
            upsert_installed(session, record)

            factory = self._loader.load(record)
            logger.info(
                "addon_installed id=%s version=%s tag=%s", addon_id, version, tag
            )
            return factory
        except AddonInstallError:
            raise
        except Exception as exc:
            raise AddonInstallError(
                f"install failed for {addon_id}@{version}: {exc}"
            ) from exc
        finally:
            shutil.rmtree(staging, ignore_errors=True)

    def uninstall(self, addon_id: str) -> None:
        session = self._session_factory()
        record = get_installed(session, addon_id)
        if record is None:
            raise AddonInstallError(f"add-on not installed: {addon_id}")

        path = Path(record.path)
        if path.is_dir():
            ts = int(datetime.now(UTC).timestamp())
            trash = self._storage / ".trash" / addon_id / f"{record.version}-{ts}"
            trash.parent.mkdir(parents=True, exist_ok=True)
            path.rename(trash)

        delete_installed(session, addon_id)
        self._loader.unload(addon_id)
        logger.info("addon_uninstalled id=%s", addon_id)

    def _fetch_tarball(self, tag: str) -> bytes:
        url = f"https://api.github.com/repos/{self._repo}/tarball/{tag}"
        headers: dict[str, str] = {}
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"

        try:
            with httpx.Client(
                transport=self._transport,
                timeout=self._timeout,
                follow_redirects=True,
            ) as client:
                response = client.get(url, headers=headers)
        except httpx.RequestError as exc:
            raise AddonInstallError(f"tarball request failed: {exc}") from exc

        if response.status_code != 200:
            raise AddonInstallError(
                f"tarball fetch returned HTTP {response.status_code}"
            )

        return response.content

    def _extract(self, payload: bytes, dest: Path) -> None:
        try:
            with tarfile.open(fileobj=io.BytesIO(payload), mode="r:gz") as tar:
                for member in tar.getmembers():
                    name = member.name
                    if name.startswith("/") or ".." in Path(name).parts:
                        raise AddonInstallError(f"unsafe tarball member: {name}")
                tar.extractall(dest)
        except tarfile.TarError as exc:
            raise AddonInstallError(f"invalid tarball: {exc}") from exc

    def _locate_package(self, staging: Path, addon_id: str, version: str) -> Path:
        candidates = list(staging.iterdir())
        if len(candidates) != 1 or not candidates[0].is_dir():
            raise AddonInstallError(
                "tarball top-level layout unexpected: need exactly one root directory"
            )
        root = candidates[0]
        package = root / addon_id / version
        if not package.is_dir():
            raise AddonInstallError(
                f"package not found at expected path {addon_id}/{version} inside tarball"
            )
        return package

    def _validate_manifest(self, package: Path, addon_id: str, version: str) -> None:
        manifest_path = package / "addon.json"
        if not manifest_path.is_file():
            raise AddonInstallError("addon.json missing from package")

        try:
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise AddonInstallError(f"addon.json is not valid JSON: {exc}") from exc

        try:
            manifest = AddonManifest.model_validate(payload)
        except Exception as exc:
            raise AddonInstallError(
                f"addon.json failed schema validation: {exc}"
            ) from exc

        if manifest.id != addon_id:
            raise AddonInstallError(
                f"manifest id '{manifest.id}' does not match requested '{addon_id}'"
            )
        if manifest.version != version:
            raise AddonInstallError(
                f"manifest version '{manifest.version}' does not match requested '{version}'"
            )

        entry = (package / manifest.entrypoint).resolve()
        try:
            entry.relative_to(package.resolve())
        except ValueError as exc:
            raise AddonInstallError(
                f"entrypoint '{manifest.entrypoint}' escapes package root"
            ) from exc
        if not entry.is_dir() or not (entry / "__init__.py").is_file():
            raise AddonInstallError(
                f"entrypoint '{manifest.entrypoint}' is not a Python package"
            )

    def _evict_previous_version(self, addon_id: str, *, keep_version: str) -> None:
        """One active version per add-on. Trash any previously installed dir
        whose version differs from the one being installed."""
        session = self._session_factory()
        existing = get_installed(session, addon_id)
        if existing is None or existing.version == keep_version:
            return

        old_path = Path(existing.path)
        if old_path.is_dir():
            ts = int(datetime.now(UTC).timestamp())
            trash = (
                self._storage / ".trash" / addon_id / f"{existing.version}-{ts}"
            )
            trash.parent.mkdir(parents=True, exist_ok=True)
            old_path.rename(trash)

        self._loader.unload(addon_id)

    def _move_into_place(self, source: Path, target: Path) -> None:
        if target.exists():
            ts = int(datetime.now(UTC).timestamp())
            trash = (
                self._storage / ".trash" / target.parent.name / f"{target.name}-{ts}"
            )
            trash.parent.mkdir(parents=True, exist_ok=True)
            target.rename(trash)

        target.parent.mkdir(parents=True, exist_ok=True)
        source.rename(target)

    def _write_install_metadata(
        self, target: Path, record: InstalledAddonRecord
    ) -> None:
        (target / ".install.json").write_text(
            json.dumps(
                {
                    "id": record.id,
                    "version": record.version,
                    "tag": record.tag,
                    "sha256": record.sha256,
                    "installed_at": record.installed_at.isoformat(),
                },
                indent=2,
            ),
            encoding="utf-8",
        )
