from fastapi.testclient import TestClient

from app.auth import dependencies as auth_dependencies
from app.main import app

client = TestClient(app)


def csrf_headers() -> dict[str, str]:
    response = client.get("/api/auth/csrf")
    return {"X-CSRF-Token": response.json()["csrfToken"]}


def test_create_fortiweb_integration_never_returns_api_key():
    response = client.post(
        "/api/integrations/fortiweb",
        headers=csrf_headers(),
        json={
            "name": "FortiWeb Lab",
            "host": "https://fortiweb.local",
            "username": "fortidashboard-api",
            "password": "secret",
            "vdom": "root",
            "verifyTls": False,
            "targetServerPolicy": "lab-waf-policy",
            "managedIpListPolicy": "FD_IP_BLOCKLIST",
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload == {
        "id": "int_fweb_01",
        "type": "fortiweb",
        "name": "FortiWeb Lab",
        "status": "connected",
        "capabilities": ["system", "waf_events", "ip_blocklist", "dos_response"],
        "targetServerPolicy": "lab-waf-policy",
        "managedIpListPolicy": "FD_IP_BLOCKLIST",
        "lastCheckedAt": "2026-05-17T12:00:00.000Z",
    }
    assert "apiKey" not in payload


def test_test_fortiweb_connection_returns_device_metadata():
    response = client.post(
        "/api/integrations/fortiweb/test",
        headers=csrf_headers(),
        json={
            "host": "https://fortiweb.local",
            "username": "fortidashboard-api",
            "password": "secret",
            "vdom": "root",
            "verifyTls": False,
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "ok": True,
        "status": "connected",
        "device": {
            "hostname": "FWB-VM",
            "model": "FortiWeb-VM",
            "version": "v8.0.x",
            "serial": "FWBVMTEST",
        },
    }


def test_delete_fortiweb_integration_returns_contract_payload():
    response = client.delete(
        "/api/integrations/int_fweb_01",
        headers=csrf_headers(),
    )

    assert response.status_code == 200
    assert response.json() == {"deleted": True, "id": "int_fweb_01"}


def test_fortiweb_block_review_apply_and_remove_contract():
    app.dependency_overrides[auth_dependencies.require_admin_user] = lambda: {
        "id": "usr_admin",
        "email": "admin@example.com",
        "displayName": "SOC Admin",
        "roles": ["admin"],
    }
    try:
        review_response = client.post(
            "/api/integrations/fortiweb/int_fweb_01/blocks/review",
            headers=csrf_headers(),
            json={
                "sourceIp": "10.10.10.10",
                "incidentId": "inc_dos_01",
                "reason": "DoS lab attack source",
            },
        )

        assert review_response.status_code == 201
        review = review_response.json()
        assert review["id"] == "fweb_block_01"
        assert review["status"] == "pending_review"
        assert review["sourceIp"] == "10.10.10.10"
        assert review["intent"]["action"] == "block_source_ip"
        assert "expiresAt" not in review["intent"]

        apply_response = client.post(
            "/api/integrations/fortiweb/int_fweb_01/blocks/fweb_block_01/apply",
            headers=csrf_headers(),
            json={
                "reviewHash": review["reviewHash"],
                "confirmed": True,
            },
        )

        assert apply_response.status_code == 200
        applied = apply_response.json()
        assert applied["id"] == "fweb_block_01"
        assert applied["status"] == "active"

        remove_response = client.delete(
            "/api/integrations/fortiweb/int_fweb_01/blocks/fweb_block_01",
            headers=csrf_headers(),
        )

        assert remove_response.status_code == 200
        assert remove_response.json()["status"] == "removed"
    finally:
        app.dependency_overrides.pop(auth_dependencies.require_admin_user, None)
