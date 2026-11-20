"""Runtime connection configuration; Render secret files take precedence."""
import os
import json
from pathlib import Path

DATABASE_URL_FILE = Path("/etc/secrets/database_url")

def get_database_url():
    try:
        with DATABASE_URL_FILE.open("r", encoding="utf-8-sig") as source:
            value = source.read(16385).strip()
        if not value or len(value) > 16384:
            raise RuntimeError("La configuración de PostgreSQL está vacía o no es válida.")
        if value.startswith(("{", "[")):
            try:
                record = json.loads(value)
                if isinstance(record, list) and len(record) == 1:
                    record = record[0]
                value = record.get("database_url") if isinstance(record, dict) else None
            except (ValueError, TypeError):
                value = None
            if not isinstance(value, str) or not value.strip():
                raise RuntimeError("La configuración de PostgreSQL no contiene una conexión válida.")
            value = value.strip()
        return value
    except FileNotFoundError:
        return os.environ.get("DATABASE_URL", "").strip()
    except (OSError, UnicodeError):
        raise RuntimeError("No se pudo leer la configuración de PostgreSQL.") from None
