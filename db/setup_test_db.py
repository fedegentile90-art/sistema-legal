#!/usr/bin/env python3
"""
Bootstrap seguro de VG_TEST_DATABASE_URL para suites DB aisladas.

Objetivo:
- crear DB de pruebas si no existe;
- aplicar schema base en DB de pruebas;
- persistir VG_TEST_DATABASE_URL en .env (opcional);
- no tocar datos de runtime, salvo CREATE DATABASE en el mismo cluster.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Tuple
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from db.health import check_db_connection, parse_database_url
from db.test_env import (
    RUNTIME_DATABASE_URL_ENV,
    TEST_DATABASE_URL_ENV,
    extract_database_name,
    mask_dsn,
    validate_isolated_test_database_url,
)


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Setup de DB de pruebas aislada")
    parser.add_argument(
        "--runtime-dsn",
        default="",
        help=f"DSN runtime (default: env {RUNTIME_DATABASE_URL_ENV})",
    )
    parser.add_argument(
        "--test-dsn",
        default="",
        help=f"DSN test (default: env {TEST_DATABASE_URL_ENV} o derivada de runtime)",
    )
    parser.add_argument(
        "--schema-path",
        default=str(ROOT / "db" / "schema.sql"),
        help="Ruta al schema SQL a aplicar en DB de pruebas.",
    )
    parser.add_argument(
        "--skip-schema",
        action="store_true",
        help="No aplicar schema SQL.",
    )
    parser.add_argument(
        "--write-dotenv",
        action="store_true",
        help="Persistir VG_TEST_DATABASE_URL en archivo .env del repo.",
    )
    return parser.parse_args(argv)


def _derive_test_dsn(runtime_dsn: str) -> str:
    parsed = urlparse(runtime_dsn)
    runtime_db = extract_database_name(runtime_dsn) or "sistemalegal"
    test_db = f"{runtime_db}_test"
    return parsed._replace(path=f"/{test_db}").geturl()


def _update_env_file(env_path: Path, key: str, value: str) -> None:
    lines: list[str] = []
    if env_path.exists():
        lines = env_path.read_text(encoding="utf-8", errors="replace").splitlines()

    prefix = f"{key}="
    replaced = False
    new_lines: list[str] = []
    for raw in lines:
        line = str(raw)
        if line.strip().startswith(prefix):
            new_lines.append(f"{key}={value}")
            replaced = True
        else:
            new_lines.append(line)
    if not replaced:
        if new_lines and new_lines[-1].strip():
            new_lines.append("")
        new_lines.append(f"{key}={value}")
    env_path.write_text("\n".join(new_lines).rstrip() + "\n", encoding="utf-8")


def _connect(dsn: str):
    import psycopg2

    normalized = parse_database_url(dsn)
    if not normalized:
        raise ValueError("DSN vacia")
    conn = psycopg2.connect(normalized, connect_timeout=5)
    conn.autocommit = True
    return conn


def _ensure_test_database(runtime_dsn: str, test_dsn: str) -> Tuple[bool, str]:
    test_db = extract_database_name(test_dsn)
    if not test_db:
        return False, "No se pudo determinar nombre de DB de pruebas."

    try:
        from psycopg2 import sql
    except Exception as exc:
        return False, f"psycopg2 no disponible ({type(exc).__name__}: {exc})"

    try:
        with _connect(runtime_dsn) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (test_db,))
                exists = cur.fetchone() is not None
                if not exists:
                    cur.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(test_db)))
                    return True, f"DB de pruebas creada: {test_db}"
                return True, f"DB de pruebas ya existe: {test_db}"
    except Exception as exc:
        return False, f"No se pudo crear/verificar DB de pruebas ({type(exc).__name__}: {exc})"


def _apply_schema(test_dsn: str, schema_path: Path) -> Tuple[bool, str]:
    if not schema_path.exists():
        return False, f"Schema no encontrado: {schema_path}"
    sql_text = schema_path.read_text(encoding="utf-8", errors="replace").strip()
    if not sql_text:
        return False, f"Schema vacio: {schema_path}"
    try:
        with _connect(test_dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(sql_text)
        return True, f"Schema aplicado: {schema_path}"
    except Exception as exc:
        return False, f"No se pudo aplicar schema ({type(exc).__name__}: {exc})"


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)

    runtime_dsn = parse_database_url(args.runtime_dsn or os.environ.get(RUNTIME_DATABASE_URL_ENV, ""))
    if not runtime_dsn:
        print(f"[FAIL] {RUNTIME_DATABASE_URL_ENV} no configurada.", flush=True)
        return 2

    test_dsn = parse_database_url(args.test_dsn or os.environ.get(TEST_DATABASE_URL_ENV, ""))
    if not test_dsn:
        test_dsn = _derive_test_dsn(runtime_dsn)
        print(f"[INFO] {TEST_DATABASE_URL_ENV} no definida. Se deriva: {mask_dsn(test_dsn)}", flush=True)

    ok_isolated, normalized_test, reason = validate_isolated_test_database_url(
        test_dsn=test_dsn,
        runtime_reference_dsn=runtime_dsn,
        runtime_source_label=RUNTIME_DATABASE_URL_ENV,
    )
    if not ok_isolated:
        print(f"[FAIL] {reason}", flush=True)
        return 2

    print(f"[OK] Runtime DSN: {mask_dsn(runtime_dsn)}", flush=True)
    print(f"[OK] Test DSN: {mask_dsn(normalized_test)}", flush=True)

    ok_db, msg_db = _ensure_test_database(runtime_dsn, normalized_test)
    if not ok_db:
        print(f"[FAIL] {msg_db}", flush=True)
        return 1
    print(f"[OK] {msg_db}", flush=True)

    if not args.skip_schema:
        ok_schema, msg_schema = _apply_schema(normalized_test, Path(args.schema_path))
        if not ok_schema:
            print(f"[FAIL] {msg_schema}", flush=True)
            return 1
        print(f"[OK] {msg_schema}", flush=True)
    else:
        print("[INFO] Schema omitido (--skip-schema).", flush=True)

    ok_conn, info = check_db_connection(normalized_test, connect_timeout=3)
    if not ok_conn:
        detail = str((info or {}).get("last_error", "sin detalle"))
        print(f"[FAIL] Preflight DB test fallo: {detail}", flush=True)
        return 1
    print("[OK] Preflight DB test: PASS (SELECT 1).", flush=True)

    if args.write_dotenv:
        env_path = ROOT / ".env"
        try:
            _update_env_file(env_path, TEST_DATABASE_URL_ENV, normalized_test)
            print(f"[OK] {TEST_DATABASE_URL_ENV} persistida en {env_path}.", flush=True)
        except Exception as exc:
            print(f"[FAIL] No se pudo actualizar .env ({type(exc).__name__}: {exc})", flush=True)
            return 1

    print(f"[DONE] Setup DB test listo. Export sugerido: {TEST_DATABASE_URL_ENV}={mask_dsn(normalized_test)}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
