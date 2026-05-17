from app.auth.permissions import VALID_PERMISSION_SLUGS


def test_policy_manager_permission_is_registered() -> None:
    assert "policies.manage" in VALID_PERMISSION_SLUGS
