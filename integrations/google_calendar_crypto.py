"""Cifrado de refresh tokens para Google Calendar."""

from __future__ import annotations

import base64
import hashlib
import os

from cryptography.fernet import Fernet


ENC_KEY_ENV = "VG_GOOGLE_CALENDAR_ENC_KEY"


def _derive_fernet_key(raw: str) -> bytes:
    text = str(raw or "").strip().encode("utf-8")
    digest = hashlib.sha256(text).digest()
    return base64.urlsafe_b64encode(digest)


def _build_fernet() -> Fernet:
    raw = str(os.environ.get(ENC_KEY_ENV, "")).strip()
    if not raw:
        raise RuntimeError(f"Falta variable de entorno {ENC_KEY_ENV}.")
    try:
        key = raw.encode("utf-8")
        # Si no es un fernet key valido, derivar desde passphrase.
        Fernet(key)
    except Exception:
        key = _derive_fernet_key(raw)
    return Fernet(key)


def has_encryption_key() -> bool:
    return bool(str(os.environ.get(ENC_KEY_ENV, "")).strip())


def encrypt_token(raw_token: str) -> str:
    token = str(raw_token or "").strip()
    if not token:
        return ""
    f = _build_fernet()
    return f.encrypt(token.encode("utf-8")).decode("utf-8")


def decrypt_token(encrypted_token: str) -> str:
    text = str(encrypted_token or "").strip()
    if not text:
        return ""
    f = _build_fernet()
    return f.decrypt(text.encode("utf-8")).decode("utf-8")

