from security import (
    UserIdentity,
    authenticate_local_user,
    has_permission,
    hash_password,
    verify_password,
)


def test_hash_password_roundtrip() -> None:
    username = "abogado1"
    raw_password = "Secreto-123!"
    digest = hash_password(raw_password, username)
    assert digest.startswith("pbkdf2_sha256$")
    assert verify_password(raw_password, username, digest) is True
    assert verify_password("bad-password", username, digest) is False


def test_has_permission_respects_strict_mode(monkeypatch) -> None:
    monkeypatch.setenv("VG_RBAC_STRICT", "1")
    auditor = UserIdentity(
        user_id="u-auditor",
        username="auditor",
        role="auditor",
        display_name="Auditor",
    )
    assert has_permission("auditoria:view", auditor) is True
    assert has_permission("cases:create", auditor) is False


def test_authenticate_local_user_fallback(monkeypatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("VG_AUTH_FALLBACK_USER", "localadmin")
    monkeypatch.setenv("VG_AUTH_FALLBACK_PASSWORD", "localpass")
    monkeypatch.setenv("VG_AUTH_FALLBACK_ROLE", "admin")
    user, reason = authenticate_local_user("localadmin", "localpass")
    assert reason == ""
    assert user is not None
    assert user.role == "admin"
