import base64
import hashlib
import json
from typing import Any

from cryptography.fernet import Fernet


class TokenCipher:
    def __init__(self, key: str) -> None:
        self._fernet = Fernet(key.encode("utf-8"))

    @classmethod
    def from_secret(cls, secret: str) -> "TokenCipher":
        digest = hashlib.sha256(secret.encode("utf-8")).digest()
        key = base64.urlsafe_b64encode(digest).decode("utf-8")
        return cls(key)

    def encrypt(self, payload: dict[str, Any]) -> str:
        body = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
        return self._fernet.encrypt(body).decode("utf-8")

    def decrypt(self, token_blob: str) -> dict[str, Any]:
        body = self._fernet.decrypt(token_blob.encode("utf-8"))
        return json.loads(body)
