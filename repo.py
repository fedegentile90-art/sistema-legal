"""
Factory de repositorio conmutable.

Si DATABASE_URL esta configurada -> usa PostgreSQL (repo_db.py)
Si NO esta configurada -> usa filesystem (fs_repo.py)

La UI importa desde aqui sin saber que backend se usa.
"""

import os
from pathlib import Path
from typing import List, Dict, Tuple, Optional, TYPE_CHECKING

from config import RUTA_BASE
from domain import Caso

# ══════════════════════════════════════════════════════════════════════════════
# DETECCION DE MODO
# ══════════════════════════════════════════════════════════════════════════════

DATABASE_URL = os.environ.get("DATABASE_URL", "")
USE_DB = bool(DATABASE_URL)

# ══════════════════════════════════════════════════════════════════════════════
# IMPORT CONDICIONAL DEL BACKEND
# ══════════════════════════════════════════════════════════════════════════════

if USE_DB:
    from repo_db import GestorCasosDB as _GestorBackend
else:
    from fs_repo import GestorCasos as _GestorBackend


# ══════════════════════════════════════════════════════════════════════════════
# ALIAS PARA COMPATIBILIDAD
# ══════════════════════════════════════════════════════════════════════════════

# Re-exportar la clase con el nombre original para que la UI no cambie
GestorCasos = _GestorBackend


# ══════════════════════════════════════════════════════════════════════════════
# HELPERS PARA VERIFICAR MODO
# ══════════════════════════════════════════════════════════════════════════════

def is_db_mode() -> bool:
    """Retorna True si estamos usando PostgreSQL."""
    return USE_DB


def is_fs_mode() -> bool:
    """Retorna True si estamos usando filesystem."""
    return not USE_DB


def get_backend_info() -> Dict[str, str]:
    """Retorna informacion del backend activo (para debug/diagnostico)."""
    return {
        "mode": "database" if USE_DB else "filesystem",
        "backend_class": _GestorBackend.__name__,
        "database_url_set": "yes" if DATABASE_URL else "no",
        "ruta_base": str(RUTA_BASE) if not USE_DB else "N/A (DB mode)",
    }


def is_db_path(path: Path) -> bool:
    """Verifica si un path es un pseudo-path de base de datos (db://...)."""
    if path is None:
        return False
    return str(path).startswith("db://")


# ══════════════════════════════════════════════════════════════════════════════
# MENSAJE DE INICIO (solo en modo debug)
# ══════════════════════════════════════════════════════════════════════════════

if os.environ.get("VG_DEBUG") == "1":
    _info = get_backend_info()
    print(f"[repo.py] Backend: {_info['mode']} ({_info['backend_class']})")
