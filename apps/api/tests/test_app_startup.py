import os
import subprocess
import sys
from pathlib import Path


def test_api_application_imports_without_mock_mode() -> None:
    api_root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env.update(
        {
            "FORTIDASHBOARD_MOCK_MODE": "false",
            "FORTIDASHBOARD_SECRET_KEY": "test-secret-key-not-default",
            "FORTIDASHBOARD_TOKEN_ENCRYPTION_KEY": "test-token-encryption-key-not-default",
            "FORTIDASHBOARD_KEYCLOAK_CLIENT_SECRET": "test-keycloak-secret-not-default",
        }
    )

    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "from app.main import app\n"
                "from app.core.config import get_settings\n"
                "assert get_settings().mock_mode is False\n"
                "assert app.title\n"
            ),
        ],
        cwd=api_root,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
