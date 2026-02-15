import pytest

from integrations.google_calendar_crypto import decrypt_token, encrypt_token


def test_google_token_encryption_roundtrip(monkeypatch) -> None:
    monkeypatch.setenv("VG_GOOGLE_CALENDAR_ENC_KEY", "super-secret-key")
    plain = "refresh-token-123"
    encrypted = encrypt_token(plain)
    assert encrypted
    assert encrypted != plain
    restored = decrypt_token(encrypted)
    assert restored == plain


def test_google_token_encryption_requires_key(monkeypatch) -> None:
    monkeypatch.delenv("VG_GOOGLE_CALENDAR_ENC_KEY", raising=False)
    with pytest.raises(RuntimeError):
        encrypt_token("token")

