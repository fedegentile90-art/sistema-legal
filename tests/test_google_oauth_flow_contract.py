import pytest

from integrations.google_oauth import build_authorization_url, oauth_is_configured


def test_oauth_is_configured_true(monkeypatch) -> None:
    monkeypatch.setenv("VG_GOOGLE_OAUTH_CLIENT_ID", "client-id")
    monkeypatch.setenv("VG_GOOGLE_OAUTH_CLIENT_SECRET", "client-secret")
    monkeypatch.setenv("VG_GOOGLE_OAUTH_REDIRECT_URI", "http://localhost:8501")
    assert oauth_is_configured() is True


def test_build_authorization_url_returns_google_url(monkeypatch) -> None:
    monkeypatch.setenv("VG_GOOGLE_OAUTH_CLIENT_ID", "client-id.apps.googleusercontent.com")
    monkeypatch.setenv("VG_GOOGLE_OAUTH_CLIENT_SECRET", "client-secret")
    monkeypatch.setenv("VG_GOOGLE_OAUTH_REDIRECT_URI", "http://localhost:8501")
    url, state = build_authorization_url(state="abc")
    assert "accounts.google.com" in url
    assert state


def test_build_authorization_url_requires_env(monkeypatch) -> None:
    monkeypatch.delenv("VG_GOOGLE_OAUTH_CLIENT_ID", raising=False)
    monkeypatch.delenv("VG_GOOGLE_OAUTH_CLIENT_SECRET", raising=False)
    monkeypatch.delenv("VG_GOOGLE_OAUTH_REDIRECT_URI", raising=False)
    with pytest.raises(RuntimeError):
        build_authorization_url(state="x")

