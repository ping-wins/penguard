import pytest

from app.addons.contracts import AddonError
from app.addons.registry_runtime import ConnectorRegistry


class _FakeConnector:
    def __init__(self, config):
        self.config = config

    def health_check(self):
        return {"ok": True, "config": self.config}

    def get_widget_data(self, req):
        return {}

    def ingest_events(self, since):
        return []

    def close(self):
        return None


def _factory(config):
    return _FakeConnector(config)


def test_register_and_get_instance_per_pair():
    reg = ConnectorRegistry()
    reg.register("demo", _factory)

    a = reg.get("demo", integration_id="i1", config={"a": 1})
    b = reg.get("demo", integration_id="i1", config={"a": 1})
    c = reg.get("demo", integration_id="i2", config={"a": 2})

    assert a is b
    assert a is not c
    assert c.config == {"a": 2}


def test_unregister_removes_factory_and_closes_instances():
    reg = ConnectorRegistry()
    reg.register("demo", _factory)
    reg.get("demo", integration_id="i1", config={})

    reg.unregister("demo")

    with pytest.raises(AddonError, match="demo"):
        reg.get("demo", integration_id="i1", config={})


def test_get_unknown_addon_raises():
    reg = ConnectorRegistry()
    with pytest.raises(AddonError, match="not registered"):
        reg.get("missing", integration_id="x", config={})
