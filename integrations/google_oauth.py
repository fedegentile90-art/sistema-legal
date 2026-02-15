"""Flujo OAuth por usuario para Google Calendar."""

from __future__ import annotations

import os
from typing import Dict, List, Tuple

import requests
from google_auth_oauthlib.flow import Flow


GOOGLE_ENABLED_ENV = "VG_GOOGLE_CALENDAR_ENABLED"
GOOGLE_CLIENT_ID_ENV = "VG_GOOGLE_OAUTH_CLIENT_ID"
GOOGLE_CLIENT_SECRET_ENV = "VG_GOOGLE_OAUTH_CLIENT_SECRET"
GOOGLE_REDIRECT_URI_ENV = "VG_GOOGLE_OAUTH_REDIRECT_URI"

DEFAULT_SCOPES = [
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/userinfo.email",
]


def _env_bool(name: str, default: bool = False) -> bool:
    raw = str(os.environ.get(name, "")).strip().lower()
    if not raw:
        return bool(default)
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off"}:
        return False
    return bool(default)


def is_google_calendar_enabled() -> bool:
    return _env_bool(GOOGLE_ENABLED_ENV, default=False)


def oauth_is_configured() -> bool:
    return bool(
        str(os.environ.get(GOOGLE_CLIENT_ID_ENV, "")).strip()
        and str(os.environ.get(GOOGLE_CLIENT_SECRET_ENV, "")).strip()
        and str(os.environ.get(GOOGLE_REDIRECT_URI_ENV, "")).strip()
    )


def _build_client_config() -> Dict[str, Dict[str, object]]:
    client_id = str(os.environ.get(GOOGLE_CLIENT_ID_ENV, "")).strip()
    client_secret = str(os.environ.get(GOOGLE_CLIENT_SECRET_ENV, "")).strip()
    redirect_uri = str(os.environ.get(GOOGLE_REDIRECT_URI_ENV, "")).strip()
    if not (client_id and client_secret and redirect_uri):
        raise RuntimeError("OAuth Google no configurado: faltan client_id/client_secret/redirect_uri.")
    return {
        "web": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [redirect_uri],
        }
    }


def _build_flow(*, state: str | None = None, scopes: List[str] | None = None) -> Flow:
    redirect_uri = str(os.environ.get(GOOGLE_REDIRECT_URI_ENV, "")).strip()
    flow = Flow.from_client_config(
        _build_client_config(),
        scopes=scopes or list(DEFAULT_SCOPES),
        state=state,
    )
    flow.redirect_uri = redirect_uri
    return flow


def build_authorization_url(*, state: str | None = None, scopes: List[str] | None = None) -> Tuple[str, str]:
    flow = _build_flow(state=state, scopes=scopes)
    auth_url, generated_state = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
    )
    return auth_url, generated_state


def _fetch_user_email(access_token: str) -> str:
    try:
        res = requests.get(
            "https://www.googleapis.com/oauth2/v2/userinfo",
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=10,
        )
        if res.status_code >= 400:
            return ""
        payload = res.json() if res.content else {}
        return str(payload.get("email", "")).strip()
    except Exception:
        return ""


def exchange_code_for_tokens(
    *,
    code: str,
    state: str | None = None,
    scopes: List[str] | None = None,
) -> Dict[str, str]:
    auth_code = str(code or "").strip()
    if not auth_code:
        raise ValueError("Codigo OAuth vacio.")
    flow = _build_flow(state=state, scopes=scopes)
    flow.fetch_token(code=auth_code)
    creds = flow.credentials
    access_token = str(getattr(creds, "token", "") or "")
    refresh_token = str(getattr(creds, "refresh_token", "") or "")
    scopes_joined = " ".join(sorted(list(getattr(creds, "scopes", []) or [])))
    expiry = getattr(creds, "expiry", None)
    expiry_iso = expiry.isoformat() if expiry else ""
    email = _fetch_user_email(access_token)
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "scope": scopes_joined,
        "expiry": expiry_iso,
        "google_email": email,
    }

