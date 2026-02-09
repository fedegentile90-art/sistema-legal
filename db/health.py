"""
Healthcheck helpers para PostgreSQL en modo DB-first.
"""

from __future__ import annotations

import re
import time
from typing import Dict, Tuple


_DSN_SECRET_RE = re.compile(r"://([^:/?#]+):([^@]+)@")


def _mask_dsn(dsn: str) -> str:
    """Oculta password en DSN para logs/diagnostico."""
    if not dsn:
        return ""
    return _DSN_SECRET_RE.sub(r"://\1:***@", dsn)


def parse_database_url(dsn: str) -> str:
    """
    Normaliza DATABASE_URL para psycopg2.
    Acepta postgresql:// y postgres://.
    """
    value = (dsn or "").strip()
    if value.startswith("postgres://"):
        return value.replace("postgres://", "postgresql://", 1)
    return value


def check_db_connection(dsn: str, connect_timeout: int = 3) -> Tuple[bool, Dict[str, object]]:
    """
    Prueba conexion ejecutando SELECT 1.
    Retorna (ok, info) para diagnostico.
    """
    normalized = parse_database_url(dsn)
    info: Dict[str, object] = {
        "ok": False,
        "dsn_set": bool(normalized),
        "dsn_masked": _mask_dsn(normalized),
        "stage": "init",
        "error_type": "",
        "last_error": "",
    }

    if not normalized:
        info["error_type"] = "MissingDSN"
        info["last_error"] = "DATABASE_URL no esta configurada."
        return False, info

    try:
        import psycopg2

        try:
            conn = psycopg2.connect(normalized, connect_timeout=connect_timeout)
        except Exception as exc:
            info["stage"] = "connect"
            info["error_type"] = type(exc).__name__
            info["last_error"] = str(exc)
            return False, info
        try:
            with conn.cursor() as cur:
                try:
                    cur.execute("SELECT 1")
                    cur.fetchone()
                except Exception as exc:
                    info["stage"] = "query"
                    info["error_type"] = type(exc).__name__
                    info["last_error"] = str(exc)
                    return False, info
        finally:
            conn.close()
        info["ok"] = True
        return True, info
    except Exception as exc:  # pragma: no cover - depende de runtime
        info["error_type"] = type(exc).__name__
        info["last_error"] = str(exc)
        return False, info


def wait_for_db(dsn: str, attempts: int = 3, backoff: float = 0.5, connect_timeout: int = 3) -> Dict[str, object]:
    """
    Reintenta healthcheck de DB con backoff corto.
    """
    total = max(1, int(attempts))
    delay = max(0.0, float(backoff))
    last_info: Dict[str, object] = {}

    for attempt in range(1, total + 1):
        ok, info = check_db_connection(dsn, connect_timeout=connect_timeout)
        info["attempt"] = attempt
        info["attempts"] = total
        last_info = info
        if ok:
            return info
        if attempt < total and delay > 0:
            time.sleep(delay)

    return last_info
