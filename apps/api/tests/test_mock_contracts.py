from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_create_fortigate_integration_never_returns_api_key():
    response = client.post(
        "/api/integrations/fortigate",
        json={
            "name": "FortiGate Lab",
            "host": "https://fortigate.local",
            "apiKey": "fg_api_key_from_user",
            "verifyTls": False,
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload == {
        "id": "int_fgt_01",
        "type": "fortigate",
        "name": "FortiGate Lab",
        "status": "connected",
        "capabilities": ["system", "interfaces", "policies", "threat_logs"],
        "lastCheckedAt": "2026-04-26T20:30:00.000Z",
    }
    assert "apiKey" not in payload


def test_test_fortigate_connection_returns_device_metadata():
    response = client.post(
        "/api/integrations/fortigate/test",
        json={
            "host": "https://fortigate.local",
            "apiKey": "fg_api_key_from_user",
            "verifyTls": False,
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "ok": True,
        "status": "connected",
        "device": {
            "hostname": "FGT-VM",
            "model": "FortiGate-VM64",
            "version": "v7.4.x",
        },
    }


def test_list_integrations_omits_api_key():
    response = client.get("/api/integrations")

    assert response.status_code == 200
    payload = response.json()
    assert payload == {
        "items": [
            {
                "id": "int_fgt_01",
                "type": "fortigate",
                "name": "FortiGate Lab",
                "host": "https://fortigate.local",
                "status": "connected",
                "lastCheckedAt": "2026-04-26T20:30:00.000Z",
            }
        ]
    }
    assert "apiKey" not in payload["items"][0]


def test_widget_catalog_filters_to_fortigate_widgets():
    response = client.get("/api/widget-catalog", params={"integrationType": "fortigate"})

    assert response.status_code == 200
    payload = response.json()
    assert [item["id"] for item in payload["items"]] == [
        "fortigate-system-status",
        "fortigate-network-traffic",
        "fortigate-kpi-sessions",
        "fortigate-firewall-policies",
        "fortigate-top-threats",
    ]
    assert payload["items"][0]["defaultSize"] == {"w": 3, "h": 2}


def test_widget_data_returns_normalized_system_status():
    response = client.get(
        "/api/widgets/fortigate-system-status/data",
        params={"integrationId": "int_fgt_01"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "widgetId": "fortigate-system-status",
        "integrationId": "int_fgt_01",
        "refreshedAt": "2026-04-26T20:31:00.000Z",
        "status": "ready",
        "data": {
            "cpu": 12,
            "memory": 54,
            "sessions": 3812,
            "uptimeSeconds": 92420,
        },
        "meta": {
            "source": "fortigate",
            "cacheTtlSeconds": 30,
        },
    }


def test_workspace_round_trip_contract():
    get_response = client.get("/api/workspaces/ws_default")

    assert get_response.status_code == 200
    assert get_response.json() == {
        "id": "ws_default",
        "name": "SOC Overview",
        "widgets": [
            {
                "instanceId": "w_01",
                "catalogId": "fortigate-system-status",
                "integrationId": "int_fgt_01",
                "layout": {"x": 0, "y": 0, "w": 3, "h": 2, "z": 10},
            }
        ],
    }

    put_response = client.put(
        "/api/workspaces/ws_default",
        json={
            "name": "SOC Overview",
            "widgets": [
                {
                    "instanceId": "w_01",
                    "catalogId": "fortigate-system-status",
                    "integrationId": "int_fgt_01",
                    "layout": {"x": 0, "y": 0, "w": 3, "h": 2, "z": 10},
                }
            ],
        },
    )

    assert put_response.status_code == 200
    assert put_response.json() == {
        "id": "ws_default",
        "version": 2,
        "updatedAt": "2026-04-26T20:32:00.000Z",
    }
