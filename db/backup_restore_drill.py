#!/usr/bin/env python3
"""
Backup + restore drill (DB-first, non-destructive by default).

Uso:
  python db/backup_restore_drill.py
  python db/backup_restore_drill.py --backup-only
  python db/backup_restore_drill.py --restore-only --backup-file db/snapshots/db_backup/db_backup_YYYYMMDD_HHMMSS.json

Contrato:
- Backup: exporta tablas core de runtime DB a JSON.
- Restore drill: restaura backup en schema temporal de DB test y valida conteos.
- Default: limpia schema temporal al finalizar.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from db.health import parse_database_url
from db.test_env import (
    RUNTIME_DATABASE_URL_ENV,
    TEST_DATABASE_URL_ENV,
    mask_dsn,
    validate_isolated_test_database_url,
)

CORE_TABLES = ("clients", "cases", "documents", "tasks", "audit_log")
DEFAULT_BACKUP_DIR = ROOT / "db" / "snapshots" / "db_backup"
RUN_ID_ENV = "VG_RUN_ID"
BACKUP_DIR_ENV = "VG_BACKUP_DIR"
DRILL_SCHEMA_PREFIX_ENV = "VG_BACKUP_DRILL_SCHEMA_PREFIX"


class C:
    OK = "\033[92m"
    FAIL = "\033[91m"
    WARN = "\033[93m"
    INFO = "\033[94m"
    RESET = "\033[0m"
    BOLD = "\033[1m"


def _emit(msg: str = "") -> None:
    print(msg, flush=True)


def _section(title: str) -> None:
    _emit(f"\n{C.BOLD}{'=' * 72}")
    _emit(f"  {title}")
    _emit(f"{'=' * 72}{C.RESET}")


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _resolve_run_id() -> str:
    raw = str(os.environ.get(RUN_ID_ENV, "")).strip()
    if raw:
        return raw
    stamp = time.strftime("%Y%m%d%H%M%S", time.gmtime())
    return f"bdr-{stamp}-{uuid.uuid4().hex[:8]}"


def _emit_obs(run_id: str, stage: str, status: str, detail: str = "", table: str = "") -> None:
    payload = {
        "ts": _utc_now_iso(),
        "run_id": str(run_id).strip() or "unknown",
        "stage": str(stage).strip() or "-",
        "suite": "backup_restore_drill",
        "status": str(status).strip() or "INFO",
    }
    if detail:
        payload["detail"] = str(detail).strip()
    if table:
        payload["table"] = str(table).strip()
    _emit("[OBS] " + json.dumps(payload, ensure_ascii=True, sort_keys=True))


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Backup + restore drill DB-first")
    parser.add_argument("--backup-only", action="store_true", help="Exporta backup y no ejecuta restore drill.")
    parser.add_argument("--restore-only", action="store_true", help="No exporta backup; solo restaura backup-file.")
    parser.add_argument("--backup-file", default="", help="Ruta del backup JSON a usar/crear.")
    parser.add_argument(
        "--backup-dir",
        default="",
        help=f"Directorio de backups (default env {BACKUP_DIR_ENV} o {DEFAULT_BACKUP_DIR}).",
    )
    parser.add_argument("--runtime-dsn", default="", help="DSN runtime (default env DATABASE_URL).")
    parser.add_argument(
        "--test-dsn",
        default="",
        help=f"DSN test (default env {TEST_DATABASE_URL_ENV}).",
    )
    parser.add_argument(
        "--schema-prefix",
        default="",
        help=f"Prefijo schema drill (default env {DRILL_SCHEMA_PREFIX_ENV} o restore_drill).",
    )
    parser.add_argument("--keep-schema", action="store_true", help="No elimina schema temporal de restore.")
    return parser.parse_args(argv)


def _normalize_schema_prefix(raw: str) -> str:
    value = str(raw or "").strip().lower()
    if not value:
        return "restore_drill"
    value = re.sub(r"[^a-z0-9_]+", "_", value)
    value = re.sub(r"_+", "_", value).strip("_")
    if not value:
        return "restore_drill"
    if value[0].isdigit():
        value = f"r_{value}"
    return value[:40]


def _resolve_backup_path(args: argparse.Namespace) -> Path:
    if str(args.backup_file).strip():
        return Path(str(args.backup_file).strip())
    env_dir = str(os.environ.get(BACKUP_DIR_ENV, "")).strip()
    backup_dir = (
        Path(str(args.backup_dir).strip())
        if str(args.backup_dir).strip()
        else (Path(env_dir) if env_dir else DEFAULT_BACKUP_DIR)
    )
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return backup_dir / f"db_backup_{ts}.json"


def _connect(dsn: str):
    import psycopg2

    normalized = parse_database_url(dsn)
    if not normalized:
        raise ValueError("DSN vacia o invalida.")
    return psycopg2.connect(normalized, connect_timeout=5)


def _fetch_identity(conn) -> dict[str, str]:
    with conn.cursor() as cur:
        cur.execute("SELECT current_user, current_database()")
        user, dbname = cur.fetchone()
    return {"user": str(user or ""), "database": str(dbname or "")}


def _export_runtime_backup(runtime_dsn: str, backup_path: Path, run_id: str) -> dict[str, Any]:
    if not parse_database_url(runtime_dsn):
        raise RuntimeError(f"{RUNTIME_DATABASE_URL_ENV} no configurada.")

    backup_path.parent.mkdir(parents=True, exist_ok=True)
    _emit_obs(run_id, stage="backup_start", status="RUN", detail=f"file={backup_path}")
    with _connect(runtime_dsn) as conn:
        identity = _fetch_identity(conn)
        tables_payload: dict[str, Any] = {}
        with conn.cursor() as cur:
            for table_name in CORE_TABLES:
                _emit(f"{C.INFO}[RUN] Exportando tabla {table_name}...{C.RESET}")
                query_rows = (
                    "SELECT COALESCE(json_agg(row_to_json(t)), '[]'::json) "
                    f"FROM (SELECT * FROM public.{table_name}) t"
                )
                cur.execute(query_rows)
                rows = cur.fetchone()[0] or []
                cur.execute(f"SELECT count(*) FROM public.{table_name}")
                row_count = int(cur.fetchone()[0] or 0)
                tables_payload[table_name] = {
                    "row_count": row_count,
                    "rows": rows,
                }
                _emit_obs(
                    run_id,
                    stage="backup_table",
                    status="PASS",
                    detail=f"rows={row_count}",
                    table=table_name,
                )

    payload = {
        "generated_at": _utc_now_iso(),
        "run_id": run_id,
        "source": {
            "dsn_masked": mask_dsn(runtime_dsn),
            "database": identity.get("database", ""),
            "role": identity.get("user", ""),
        },
        "tables": tables_payload,
    }
    backup_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    _emit(f"{C.OK}[PASS] Backup guardado: {backup_path}{C.RESET}")
    _emit_obs(run_id, stage="backup_saved", status="PASS", detail=f"path={backup_path}")
    return payload


def _load_backup_payload(backup_path: Path) -> dict[str, Any]:
    if not backup_path.exists():
        raise FileNotFoundError(f"Backup no encontrado: {backup_path}")
    data = json.loads(backup_path.read_text(encoding="utf-8", errors="replace"))
    if not isinstance(data, dict):
        raise RuntimeError("Formato de backup invalido (root no es objeto JSON).")
    return data


def _validate_test_dsn(runtime_dsn: str, test_dsn: str) -> str:
    ok, normalized, reason = validate_isolated_test_database_url(
        test_dsn=test_dsn,
        runtime_reference_dsn=runtime_dsn,
        runtime_source_label=RUNTIME_DATABASE_URL_ENV,
    )
    if not ok:
        raise RuntimeError(reason or f"{TEST_DATABASE_URL_ENV} invalida.")
    return normalized


def _restore_drill(payload: dict[str, Any], runtime_dsn: str, test_dsn: str, schema_prefix: str, keep_schema: bool, run_id: str) -> dict[str, Any]:
    from psycopg2 import sql

    normalized_test = _validate_test_dsn(runtime_dsn=runtime_dsn, test_dsn=test_dsn)
    schema_name = f"{schema_prefix}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    tables_data = payload.get("tables", {}) if isinstance(payload.get("tables"), dict) else {}
    if not tables_data:
        raise RuntimeError("Backup sin tablas para restaurar.")

    _emit_obs(run_id, stage="restore_start", status="RUN", detail=f"schema={schema_name}")
    _emit(f"{C.INFO}[INFO] Restore drill en DB test: {mask_dsn(normalized_test)}{C.RESET}")
    _emit(f"{C.INFO}[INFO] Schema temporal: {schema_name}{C.RESET}")

    summary: dict[str, Any] = {"schema": schema_name, "tables": {}, "ok": True}
    with _connect(normalized_test) as conn:
        conn.autocommit = False
        try:
            with conn.cursor() as cur:
                cur.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema_name)))
                for table_name in CORE_TABLES:
                    table_block = tables_data.get(table_name, {})
                    expected = int(table_block.get("row_count", 0) or 0) if isinstance(table_block, dict) else 0
                    rows = table_block.get("rows", []) if isinstance(table_block, dict) else []
                    if not isinstance(rows, list):
                        rows = []

                    cur.execute(
                        sql.SQL("CREATE TABLE {}.{} (LIKE public.{})").format(
                            sql.Identifier(schema_name),
                            sql.Identifier(table_name),
                            sql.Identifier(table_name),
                        )
                    )
                    if rows:
                        rows_json = json.dumps(rows, ensure_ascii=False)
                        cur.execute(
                            sql.SQL(
                                "INSERT INTO {}.{} "
                                "SELECT * FROM json_populate_recordset(NULL::{}.{} , %s::json)"
                            ).format(
                                sql.Identifier(schema_name),
                                sql.Identifier(table_name),
                                sql.Identifier(schema_name),
                                sql.Identifier(table_name),
                            ),
                            (rows_json,),
                        )
                    cur.execute(
                        sql.SQL("SELECT count(*) FROM {}.{}").format(
                            sql.Identifier(schema_name),
                            sql.Identifier(table_name),
                        )
                    )
                    restored = int(cur.fetchone()[0] or 0)
                    ok = restored == expected
                    summary["tables"][table_name] = {
                        "expected_rows": expected,
                        "restored_rows": restored,
                        "ok": ok,
                    }
                    if not ok:
                        summary["ok"] = False
                    status = "PASS" if ok else "FAIL"
                    detail = f"expected={expected} restored={restored}"
                    _emit_obs(run_id, stage="restore_table", status=status, detail=detail, table=table_name)
                    if ok:
                        _emit(f"{C.OK}[PASS] {table_name}: {detail}{C.RESET}")
                    else:
                        _emit(f"{C.FAIL}[FAIL] {table_name}: {detail}{C.RESET}")
        finally:
            if keep_schema:
                conn.commit()
            else:
                with conn.cursor() as cur:
                    cur.execute(
                        sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(sql.Identifier(schema_name))
                    )
                conn.commit()

    if keep_schema:
        _emit(f"{C.WARN}[WARN] Schema temporal conservado: {schema_name}{C.RESET}")
    else:
        _emit(f"{C.INFO}[INFO] Schema temporal eliminado: {schema_name}{C.RESET}")

    status = "PASS" if bool(summary.get("ok", False)) else "FAIL"
    _emit_obs(run_id, stage="restore_end", status=status, detail=f"schema={schema_name}")
    return summary


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    if args.backup_only and args.restore_only:
        _emit(f"{C.FAIL}[FAIL] --backup-only y --restore-only no pueden usarse juntos.{C.RESET}")
        return 2

    run_id = _resolve_run_id()
    os.environ[RUN_ID_ENV] = run_id
    runtime_dsn = str(args.runtime_dsn or os.environ.get(RUNTIME_DATABASE_URL_ENV, "")).strip()
    test_dsn = str(args.test_dsn or os.environ.get(TEST_DATABASE_URL_ENV, "")).strip()
    schema_prefix = _normalize_schema_prefix(
        str(args.schema_prefix or os.environ.get(DRILL_SCHEMA_PREFIX_ENV, "")).strip()
    )
    backup_path = _resolve_backup_path(args)

    _section("BACKUP + RESTORE DRILL")
    _emit(f"Run ID: {run_id} (env {RUN_ID_ENV})")
    _emit(f"Runtime DSN: {mask_dsn(runtime_dsn)}")
    if args.restore_only:
        _emit(f"Modo: restore-only (backup-file={backup_path})")
    elif args.backup_only:
        _emit(f"Modo: backup-only (backup-file={backup_path})")
    else:
        _emit(f"Modo: full drill (backup + restore) (backup-file={backup_path})")

    _emit_obs(run_id, stage="drill_start", status="RUN")

    try:
        if args.restore_only:
            payload = _load_backup_payload(backup_path)
        else:
            payload = _export_runtime_backup(runtime_dsn=runtime_dsn, backup_path=backup_path, run_id=run_id)

        if args.backup_only:
            _emit_obs(run_id, stage="drill_end", status="PASS", detail="backup_only")
            _emit(f"{C.OK}{C.BOLD}BACKUP RESTORE DRILL: PASS (backup-only){C.RESET}")
            return 0

        restore_summary = _restore_drill(
            payload=payload,
            runtime_dsn=runtime_dsn,
            test_dsn=test_dsn,
            schema_prefix=schema_prefix,
            keep_schema=bool(args.keep_schema),
            run_id=run_id,
        )
        if not bool(restore_summary.get("ok", False)):
            _emit_obs(run_id, stage="drill_end", status="FAIL", detail="restore_mismatch")
            _emit(f"{C.FAIL}{C.BOLD}BACKUP RESTORE DRILL: FAIL{C.RESET}")
            return 1

        _emit_obs(run_id, stage="drill_end", status="PASS")
        _emit(f"{C.OK}{C.BOLD}BACKUP RESTORE DRILL: PASS{C.RESET}")
        return 0
    except Exception as exc:
        _emit_obs(run_id, stage="drill_end", status="FAIL", detail=f"{type(exc).__name__}: {exc}")
        _emit(f"{C.FAIL}[FAIL] {type(exc).__name__}: {exc}{C.RESET}")
        _emit(f"{C.FAIL}{C.BOLD}BACKUP RESTORE DRILL: FAIL{C.RESET}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
