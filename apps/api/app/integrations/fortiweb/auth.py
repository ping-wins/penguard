import json
from base64 import b64encode

FORTIWEB_AUTH_SCHEME = "fortiweb-v2-authorization"


def build_fortiweb_authorization(*, username: str, password: str, vdom: str) -> str:
    normalized_username = username.strip()
    normalized_password = password.strip()
    normalized_vdom = (vdom or "root").strip() or "root"
    if not normalized_username:
        raise ValueError("username is required")
    if not normalized_password:
        raise ValueError("password is required")

    payload = {
        "username": normalized_username,
        "password": normalized_password,
        "vdom": normalized_vdom,
    }
    compact = json.dumps(payload, separators=(",", ":"))
    return b64encode(compact.encode("utf-8")).decode("ascii")


def fortiweb_runtime_auth(auth: dict) -> dict:
    """Return connector/persistence auth with generated Authorization value.

    Backward-compatible `apiKey` configs are preserved for already-installed
    legacy rows/packages, but username/password submissions are converted and
    the plaintext password is dropped before the config leaves the BFF boundary.
    """
    if auth.get("apiKey"):
        return dict(auth)

    authorization = build_fortiweb_authorization(
        username=str(auth.get("username") or ""),
        password=str(auth.get("password") or ""),
        vdom=str(auth.get("vdom") or "root"),
    )
    runtime = {key: value for key, value in auth.items() if key != "password"}
    runtime["apiKey"] = authorization
    runtime["authorization"] = authorization
    runtime["authScheme"] = FORTIWEB_AUTH_SCHEME
    runtime["vdom"] = str(runtime.get("vdom") or "root")
    return runtime
