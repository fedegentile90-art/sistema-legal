"""
Factory de repositorio.

Backend unico: PostgreSQL (repo_db.GestorCasosDB).
La UI importa desde aqui sin preocuparse del backend.
"""

import os
from pathlib import Path
from typing import Dict

from repo_db import GestorCasosDB as _GestorBackend

DATABASE_URL = os.environ.get("DATABASE_URL", "")
USE_DB = True  # backend fijo: DB

# Re-exportar la clase con el nombre original para compatibilidad con la UI
GestorCasos = _GestorBackend


def is_db_mode() -> bool:
    """Retorna True: el backend es siempre DB."""
    return True


def is_fs_mode() -> bool:
    """Compatibilidad: el backend de filesystem ya no se usa."""
    return False


def get_backend_info() -> Dict[str, str]:
    """Informacion del backend activo (para debug/diagnostico)."""
    return {
        "mode": "database",
        "backend_class": _GestorBackend.__name__,
        "database_url_set": "yes" if DATABASE_URL else "no",
        "ruta_base": "N/A (DB mode)",
    }


def is_db_path(path: Path) -> bool:
    """Verifica si un path es un pseudo-path de base de datos (db://...)."""
    if path is None:
        return False
    s = str(path)
    s_norm = s.replace("\\", "/").lower()
    return s_norm.startswith("db://") or s_norm.startswith("db:/") or s_norm.startswith("db:")


if os.environ.get("VG_DEBUG") == "1":
    _info = get_backend_info()
    print(f"[repo.py] Backend: {_info['mode']} ({_info['backend_class']})")
