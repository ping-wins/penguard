from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def csrf_headers() -> dict[str, str]:
    response = client.get("/api/auth/csrf")
    return {"X-CSRF-Token": response.json()["csrfToken"]}


def test_smoke_connection_catalog_and_widget_payloads():
    connection = client.post(
        "/api/integrations/fortigate/test",
        headers=csrf_headers(),
        json={
            "host": "https://fortigate.local",
            "apiKey": "fg_api_key_from_user",
            "verifyTls": False,
        },
    )
    catalog = client.get("/api/widget-catalog", params={"integrationType": "fortigate"})
    widget = client.get(
        "/api/widgets/fortigate-system-status/data",
        params={"integrationId": "int_fgt_01"},
    )

    assert connection.status_code == 200
    assert connection.json()["status"] == "connected"
    assert catalog.status_code == 200
    assert len(catalog.json()["items"]) >= 5
    assert widget.status_code == 200
    assert widget.json()["status"] == "ready"


def test_smoke_workspace_payload_has_canvas_render_contract():
    workspace = client.get("/api/workspaces/ws_default")
    catalog = client.get("/api/widget-catalog", params={"integrationType": "fortigate"})

    assert workspace.status_code == 200
    widget = workspace.json()["widgets"][0]
    catalog_ids = {item["id"] for item in catalog.json()["items"]}

    assert widget["catalogId"] in catalog_ids
    assert widget["integrationId"]
    assert widget["layout"].keys() >= {"x", "y", "w", "h", "z"}
