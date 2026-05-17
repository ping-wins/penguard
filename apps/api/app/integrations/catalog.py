import json
import logging
from pathlib import Path
from typing import Any

from app.addons.installed_store import InstalledAddonRecord
from app.addons.manifest import AddonManifest

logger = logging.getLogger(__name__)


def build_catalog(records: list[InstalledAddonRecord]) -> list[dict[str, Any]]:
    """Build wizard catalog entries from installed package manifests."""
    catalog: list[dict[str, Any]] = []
    for rec in records:
        manifest_path = Path(rec.path) / "addon.json"
        if not manifest_path.is_file():
            logger.warning("catalog_manifest_missing id=%s path=%s", rec.id, manifest_path)
            continue
        try:
            manifest = AddonManifest.model_validate(
                json.loads(manifest_path.read_text(encoding="utf-8"))
            )
        except Exception as exc:
            logger.exception("catalog_manifest_invalid id=%s err=%s", rec.id, exc)
            continue
        versions = (
            manifest.compatibility.tested_versions
            if manifest.compatibility and manifest.compatibility.tested_versions
            else [manifest.version]
        )
        catalog.append(
            {
                "addonId": manifest.id,
                "name": manifest.name,
                "vendor": manifest.vendor,
                "category": manifest.category,
                "icon": manifest.icon,
                "providerType": manifest.provider.type,
                "versions": list(versions),
                "authFields": _auth_fields(
                    manifest.provider.type,
                    [field.model_dump(by_alias=True) for field in manifest.provider.auth.fields],
                ),
                "capabilities": manifest.capabilities.model_dump(by_alias=True),
            }
        )
    return catalog


def _auth_fields(provider_type: str, fields: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if provider_type == "fortiweb":
        return [
            {
                "id": "host",
                "label": "FortiWeb URL",
                "type": "url",
                "required": True,
                "placeholder": "https://fortiweb.example.local",
            },
            {
                "id": "username",
                "label": "Username",
                "type": "text",
                "required": True,
            },
            {
                "id": "password",
                "label": "Password",
                "type": "secret",
                "required": True,
            },
            {"id": "vdom", "label": "VDOM", "type": "text", "default": "root"},
            {
                "id": "verifyTls",
                "label": "Verify TLS",
                "type": "boolean",
                "default": False,
            },
            {
                "id": "targetServerPolicy",
                "label": "Target server policy",
                "type": "text",
                "default": "lab-waf-policy",
            },
            {
                "id": "managedIpListPolicy",
                "label": "Managed IP list policy",
                "type": "text",
                "default": "FD_IP_BLOCKLIST",
            },
        ]
    return fields
