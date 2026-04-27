import httpx
import pytest

from app.integrations.fortigate.client import FortiGateApiClient, FortiGateApiError
from app.integrations.fortigate.normalizers import (
    normalize_interfaces,
    normalize_policies,
    normalize_system_status,
    normalize_threat_logs,
)


def test_fortigate_client_uses_bearer_token_and_unwraps_results():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == "Bearer secret-token"
        assert request.url.path == "/api/v2/monitor/system/status"
        return httpx.Response(
            200,
            json={
                "status": "success",
                "serial": "FGVMTEST",
                "version": "v7.6.6",
                "build": 3652,
                "results": {
                    "hostname": "FGT-VM",
                    "model_name": "FortiGate-VM64",
                },
            },
        )

    client = FortiGateApiClient(
        host="https://fortigate.local",
        api_key="secret-token",
        verify_tls=False,
        transport=httpx.MockTransport(handler),
    )

    assert client.get_system_status() == {
        "hostname": "FGT-VM",
        "model_name": "FortiGate-VM64",
        "serial": "FGVMTEST",
        "version": "v7.6.6",
        "build": 3652,
    }


def test_fortigate_client_does_not_merge_envelope_metadata_into_interface_status():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v2/monitor/system/interface"
        return httpx.Response(
            200,
            json={
                "status": "success",
                "serial": "FGVMTEST",
                "version": "v7.6.6",
                "results": {
                    "port1": {
                        "id": "port1",
                        "name": "port1",
                        "ip": "192.168.0.118",
                        "link": True,
                    }
                },
            },
        )

    client = FortiGateApiClient(
        host="https://fortigate.local",
        api_key="secret-token",
        verify_tls=False,
        transport=httpx.MockTransport(handler),
    )

    assert client.get_interface_status() == {
        "port1": {
            "id": "port1",
            "name": "port1",
            "ip": "192.168.0.118",
            "link": True,
        }
    }


def test_fortigate_client_raises_for_fortios_error_status():
    client = FortiGateApiClient(
        host="https://fortigate.local",
        api_key="secret-token",
        verify_tls=False,
        transport=httpx.MockTransport(
            lambda _request: httpx.Response(
                200,
                json={"status": "error", "http_status": 403, "error": -3},
            )
        ),
    )

    with pytest.raises(FortiGateApiError, match="FortiGate API returned error status"):
        client.get_system_status()


def test_fortigate_client_rejects_empty_api_key_before_network_call():
    with pytest.raises(ValueError, match="api_key is required"):
        FortiGateApiClient(
            host="https://fortigate.local",
            api_key="",
            verify_tls=False,
        )


def test_normalize_system_status_for_widget_and_connection_payloads():
    normalized = normalize_system_status(
        {
            "hostname": "FGT-VM",
            "model_name": "FortiGate-VM64",
            "version": "v7.4.3",
            "serial": "FGVMTEST",
            "cpu": 7,
            "mem": 48,
            "current_sessions": 3812,
            "uptime": 92420,
        }
    )

    assert normalized == {
        "hostname": "FGT-VM",
        "model": "FortiGate-VM64",
        "version": "v7.4.3",
        "serial": "FGVMTEST",
        "cpu": 7,
        "memory": 48,
        "sessions": 3812,
        "uptimeSeconds": 92420,
    }


def test_normalize_system_status_accepts_real_fortios_performance_payloads():
    normalized = normalize_system_status(
        {
            "hostname": "FGVMEVJAOUIR5F07",
            "model": "FGVM64",
            "model_name": "FortiGate",
            "model_number": "VM64",
            "serial": "FGVMEVJAOUIR5F07",
            "version": "v7.6.6",
            "build": 3652,
        },
        performance={
            "cpu": {"idle": 97, "iowait": 0, "nice": 0, "system": 1, "user": 2},
            "mem": {
                "free": 758415360,
                "freeable": 383713280,
                "total": 2091188224,
                "used": 949059584,
            },
        },
        resource_usage={"session": [{"current": 15}]},
    )

    assert normalized == {
        "hostname": "FGVMEVJAOUIR5F07",
        "model": "FortiGate",
        "version": "v7.6.6",
        "serial": "FGVMEVJAOUIR5F07",
        "build": 3652,
        "cpu": 3,
        "memory": 45,
        "sessions": 15,
        "uptimeSeconds": None,
    }


def test_normalize_interfaces_policies_and_threat_logs():
    assert normalize_interfaces(
        [
            {
                "name": "port1",
                "alias": "WAN",
                "status": "up",
                "ip": "192.168.0.118 255.255.255.0",
                "role": "wan",
                "type": "physical",
            }
        ]
    ) == [
        {
            "id": "port1",
            "name": "port1",
            "alias": "WAN",
            "status": "up",
            "ip": "192.168.0.118",
            "role": "wan",
            "type": "physical",
            "rxBytes": 0,
            "txBytes": 0,
            "rxPackets": 0,
            "txPackets": 0,
        }
    ]

    assert normalize_policies(
        [
            {
                "policyid": 1,
                "name": "LAN to WAN",
                "status": "enable",
                "action": "accept",
                "srcintf": [{"name": "lan"}],
                "dstintf": [{"name": "wan"}],
                "service": [{"name": "HTTPS"}],
                "schedule": "always",
            }
        ]
    ) == [
        {
            "id": "1",
            "name": "LAN to WAN",
            "status": "enabled",
            "action": "accept",
            "sourceInterfaces": ["lan"],
            "destinationInterfaces": ["wan"],
            "services": ["HTTPS"],
            "schedule": "always",
        }
    ]

    assert normalize_threat_logs(
        [
            {
                "itime": 1777234800,
                "type": "utm",
                "subtype": "ips",
                "severity": "high",
                "srcip": "10.0.0.10",
                "dstip": "203.0.113.10",
                "action": "blocked",
                "msg": "IPS signature matched",
            }
        ]
    ) == [
        {
            "id": "1777234800-10.0.0.10-203.0.113.10-ips",
            "timestamp": "2026-04-26T20:20:00Z",
            "type": "utm",
            "subtype": "ips",
            "severity": "high",
            "sourceIp": "10.0.0.10",
            "destinationIp": "203.0.113.10",
            "action": "blocked",
            "message": "IPS signature matched",
        }
    ]
