import base64
import json

import pytest

from app.integrations.fortiweb.auth import build_fortiweb_authorization


def test_build_fortiweb_authorization_uses_compact_base64_payload() -> None:
    token = build_fortiweb_authorization(
        username="penguard-api",
        password="secret",
        vdom="root",
    )

    decoded = json.loads(base64.b64decode(token).decode("utf-8"))
    assert decoded == {
        "username": "penguard-api",
        "password": "secret",
        "vdom": "root",
    }
    assert " " not in base64.b64decode(token).decode("utf-8")


def test_build_fortiweb_authorization_requires_credentials() -> None:
    with pytest.raises(ValueError, match="username"):
        build_fortiweb_authorization(username="", password="secret", vdom="root")
    with pytest.raises(ValueError, match="password"):
        build_fortiweb_authorization(username="user", password="", vdom="root")
