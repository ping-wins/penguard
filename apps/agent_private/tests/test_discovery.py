import json

from agent_private.discovery import (
    DISCOVERY_RESPONSE_TYPE,
    broadcast_targets,
    candidate_api_urls,
    parse_discovery_response,
)


def test_parse_discovery_response_builds_api_url_from_udp_source():
    response = json.dumps(
        {
            "type": DISCOVERY_RESPONSE_TYPE,
            "nonce": "nonce-01",
            "apiScheme": "http",
            "apiPort": 8000,
        }
    ).encode("utf-8")

    result = parse_discovery_response(response, ("192.168.56.1", 8764), nonce="nonce-01")

    assert result is not None
    assert result.api_url == "http://192.168.56.1:8000"
    assert result.source_host == "192.168.56.1"


def test_parse_discovery_response_rejects_wrong_nonce():
    response = json.dumps(
        {
            "type": DISCOVERY_RESPONSE_TYPE,
            "nonce": "other",
            "apiScheme": "http",
            "apiPort": 8000,
        }
    ).encode("utf-8")

    assert parse_discovery_response(response, ("192.168.56.1", 8764), nonce="nonce-01") is None


def test_broadcast_targets_include_limited_broadcast_and_interface_broadcast(monkeypatch):
    row = type(
        "Address",
        (),
        {
            "family": 2,
            "address": "192.168.56.101",
            "netmask": "255.255.255.0",
        },
    )()
    monkeypatch.setattr("agent_private.discovery.psutil.net_if_addrs", lambda: {"vmnet": [row]})

    targets = broadcast_targets(8764)

    assert ("255.255.255.255", 8764) in targets
    assert ("192.168.56.255", 8764) in targets


def test_candidate_api_urls_include_vmware_host_addresses(monkeypatch):
    row = type(
        "Address",
        (),
        {
            "family": 2,
            "address": "192.168.56.101",
            "netmask": "255.255.255.0",
        },
    )()
    monkeypatch.setattr("agent_private.discovery.psutil.net_if_addrs", lambda: {"vmnet": [row]})

    assert candidate_api_urls(8000) == [
        "http://192.168.56.1:8000",
        "http://192.168.56.2:8000",
    ]
