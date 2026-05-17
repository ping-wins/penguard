import pytest
from pydantic import ValidationError

from app.addons.manifest import AddonManifest


def _base_payload() -> dict:
    return {
        "id": "demo",
        "version": "1.0.0",
        "name": "Demo",
        "vendor": "Demo Inc",
        "category": "demo",
        "description": "demo",
        "provider": {"type": "demo", "auth": {"kind": "none", "fields": []}},
    }


def test_manifest_defaults_when_entrypoint_and_requirements_absent():
    m = AddonManifest.model_validate(_base_payload())
    assert m.entrypoint == "connector"
    assert m.requirements == []


def test_manifest_accepts_explicit_entrypoint_and_requirements():
    payload = _base_payload()
    payload["entrypoint"] = "src"
    payload["requirements"] = ["httpx>=0.27,<1.0", "pydantic>=2"]
    m = AddonManifest.model_validate(payload)
    assert m.entrypoint == "src"
    assert m.requirements == ["httpx>=0.27,<1.0", "pydantic>=2"]


def test_manifest_dump_round_trips_new_fields():
    payload = _base_payload()
    payload["entrypoint"] = "src"
    payload["requirements"] = ["httpx"]
    dumped = AddonManifest.model_validate(payload).model_dump(by_alias=True)
    assert dumped["entrypoint"] == "src"
    assert dumped["requirements"] == ["httpx"]


def test_manifest_dump_includes_defaults_when_fields_absent():
    dumped = AddonManifest.model_validate(_base_payload()).model_dump(by_alias=True)
    assert dumped["entrypoint"] == "connector"
    assert dumped["requirements"] == []


def test_manifest_rejects_empty_entrypoint():
    payload = _base_payload()
    payload["entrypoint"] = ""
    with pytest.raises(ValidationError):
        AddonManifest.model_validate(payload)


def test_manifest_capabilities_defaults_all_false():
    m = AddonManifest.model_validate(_base_payload())
    assert m.capabilities.log_source is False
    assert m.capabilities.playbook_target is False
    assert m.capabilities.managed is False


def test_manifest_capabilities_round_trips_camel_case():
    payload = _base_payload()
    payload["capabilities"] = {
        "logSource": True,
        "playbookTarget": True,
        "managed": False,
    }
    dumped = AddonManifest.model_validate(payload).model_dump(by_alias=True)
    assert dumped["capabilities"] == {
        "logSource": True,
        "playbookTarget": True,
        "managed": False,
    }
