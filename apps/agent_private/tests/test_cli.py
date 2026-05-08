from agent_private.cli import build_identity_payload


def test_build_identity_payload_has_required_fields():
    payload = build_identity_payload(
        hostname="demo-endpoint-01",
        username="SOC-DEMO\\analyst",
    )

    assert payload["hostname"] == "demo-endpoint-01"
    assert payload["username"] == "SOC-DEMO\\analyst"
    assert payload["service"] == "agent_private"
