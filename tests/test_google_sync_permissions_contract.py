from security import ROLE_PERMISSIONS


def test_google_calendar_permissions_assigned_to_operational_roles() -> None:
    for role in ("admin", "abogado", "asistente"):
        perms = ROLE_PERMISSIONS.get(role, set())
        assert "calendar:connect" in perms or "*" in perms
        assert "calendar:sync" in perms or "*" in perms
        assert "tasks:write" in perms or "*" in perms

