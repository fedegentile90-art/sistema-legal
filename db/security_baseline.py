#!/usr/bin/env python3
"""
Security baseline checks for SistemaLegal DB-first operations.

Focus:
- auth/roles posture (superuser, create role/db)
- least privilege over core tables
- optional role split between runtime and test DB
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from db.health import parse_database_url
from db.test_env import TEST_DATABASE_URL_ENV, mask_dsn

RUNTIME_DATABASE_URL_ENV = "DATABASE_URL"
SECURITY_GATE_MODE_ENV = "VG_SECURITY_GATE_MODE"
SECURITY_MODE_OFF = "off"
SECURITY_MODE_WARN = "warn"
SECURITY_MODE_ENFORCE = "enforce"
DB_APP_ROLE_ENV = "VG_DB_APP_ROLE"
DB_TEST_ROLE_ENV = "VG_DB_TEST_ROLE"
SECURITY_REQUIRE_TEST_ROLE_SPLIT_ENV = "VG_SECURITY_GATE_REQUIRE_TEST_ROLE_SPLIT"

VALID_SECURITY_GATE_MODES = {SECURITY_MODE_OFF, SECURITY_MODE_WARN, SECURITY_MODE_ENFORCE}
CORE_TABLES = ("clients", "cases", "documents", "tasks", "audit_log")
REQUIRED_TABLE_PRIVS = ("SELECT", "INSERT", "UPDATE", "DELETE")


class C:
    OK = "\033[92m"
    FAIL = "\033[91m"
    WARN = "\033[93m"
    INFO = "\033[94m"
    RESET = "\033[0m"
    BOLD = "\033[1m"


def _parse_bool(value: str, default: bool = False) -> bool:
    raw = str(value or "").strip().lower()
    if not raw:
        return bool(default)
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off"}:
        return False
    return bool(default)


def _resolve_mode(cli_mode: str, env: dict[str, str] | None = None) -> tuple[bool, str, str]:
    env_map = env if env is not None else os.environ
    raw = str(cli_mode or env_map.get(SECURITY_GATE_MODE_ENV, SECURITY_MODE_WARN)).strip().lower()
    if raw in VALID_SECURITY_GATE_MODES:
        return True, raw, ""
    reason = (
        f"Modo security gate invalido: {raw!r}. "
        f"Use {SECURITY_MODE_OFF!r}, {SECURITY_MODE_WARN!r} o {SECURITY_MODE_ENFORCE!r}."
    )
    return False, "", reason


def collect_role_security_snapshot(dsn: str, label: str) -> tuple[bool, dict[str, Any], str]:
    normalized = parse_database_url(dsn)
    if not normalized:
        return False, {}, f"{label}: DSN no configurada."

    try:
        import psycopg2
    except Exception as exc:  # pragma: no cover - runtime dependency
        return False, {}, f"{label}: psycopg2 no disponible ({type(exc).__name__}: {exc})"

    try:
        conn = psycopg2.connect(normalized, connect_timeout=3)
    except Exception as exc:
        return False, {}, f"{label}: fallo de conexion ({type(exc).__name__}: {exc})"

    snapshot: dict[str, Any] = {
        "label": label,
        "dsn_masked": mask_dsn(normalized),
        "identity": {},
        "role_flags": {},
        "schema_privileges": {},
        "tables": {},
    }
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute("SELECT current_user, session_user, current_database()")
                current_user, session_user, database_name = cur.fetchone()
                snapshot["identity"] = {
                    "current_user": str(current_user or ""),
                    "session_user": str(session_user or ""),
                    "database": str(database_name or ""),
                }

                cur.execute(
                    """
                    SELECT
                        r.rolsuper,
                        r.rolcreaterole,
                        r.rolcreatedb,
                        r.rolcanlogin
                    FROM pg_roles r
                    WHERE r.rolname = current_user
                    """
                )
                role_row = cur.fetchone() or (False, False, False, False)
                snapshot["role_flags"] = {
                    "superuser": bool(role_row[0]),
                    "create_role": bool(role_row[1]),
                    "create_db": bool(role_row[2]),
                    "can_login": bool(role_row[3]),
                }

                cur.execute(
                    """
                    SELECT
                        has_schema_privilege(current_user, 'public', 'USAGE'),
                        has_schema_privilege(current_user, 'public', 'CREATE')
                    """
                )
                usage, create = cur.fetchone() or (False, False)
                snapshot["schema_privileges"] = {
                    "usage": bool(usage),
                    "create": bool(create),
                }

                tables: dict[str, Any] = {}
                for table_name in CORE_TABLES:
                    fq_table = f"public.{table_name}"
                    cur.execute("SELECT to_regclass(%s)", (fq_table,))
                    exists = cur.fetchone()[0] is not None
                    table_info: dict[str, Any] = {"exists": bool(exists), "privileges": {}}
                    if exists:
                        privs: dict[str, bool] = {}
                        for priv in REQUIRED_TABLE_PRIVS:
                            cur.execute(
                                "SELECT has_table_privilege(current_user, %s, %s)",
                                (fq_table, priv),
                            )
                            privs[priv] = bool(cur.fetchone()[0])
                        cur.execute(
                            "SELECT has_table_privilege(current_user, %s, 'TRUNCATE')",
                            (fq_table,),
                        )
                        privs["TRUNCATE"] = bool(cur.fetchone()[0])
                        table_info["privileges"] = privs
                    tables[table_name] = table_info
                snapshot["tables"] = tables
    except Exception as exc:
        return False, {}, f"{label}: fallo consultando privilegios ({type(exc).__name__}: {exc})"
    finally:
        conn.close()

    return True, snapshot, ""


def evaluate_security_baseline(
    runtime_dsn: str,
    *,
    mode: str = SECURITY_MODE_WARN,
    app_role: str = "",
    test_dsn: str = "",
    test_role: str = "",
    require_test_role_split: bool = False,
) -> dict[str, Any]:
    mode_normalized = str(mode or SECURITY_MODE_WARN).strip().lower()
    if mode_normalized not in VALID_SECURITY_GATE_MODES:
        mode_normalized = SECURITY_MODE_WARN

    if mode_normalized == SECURITY_MODE_OFF:
        return {
            "status": "SKIPPED",
            "reason": "Security gate deshabilitado por configuracion.",
            "mode": mode_normalized,
            "findings": [],
            "snapshots": [],
        }

    findings: list[dict[str, str]] = []
    snapshots: list[dict[str, Any]] = []

    def add_finding(code: str, message: str) -> None:
        severity = "FAIL" if mode_normalized == SECURITY_MODE_ENFORCE else "WARN"
        findings.append({"severity": severity, "code": code, "message": message})

    def evaluate_snapshot(snapshot: dict[str, Any], expected_role: str, label: str) -> None:
        identity = snapshot.get("identity", {}) if isinstance(snapshot.get("identity"), dict) else {}
        role_flags = snapshot.get("role_flags", {}) if isinstance(snapshot.get("role_flags"), dict) else {}
        schema_privs = (
            snapshot.get("schema_privileges", {})
            if isinstance(snapshot.get("schema_privileges"), dict)
            else {}
        )
        tables = snapshot.get("tables", {}) if isinstance(snapshot.get("tables"), dict) else {}

        current_user = str(identity.get("current_user", "") or "")
        if expected_role and current_user != expected_role:
            add_finding(
                "SEC-ROLE-001",
                (
                    f"{label}: rol actual {current_user!r} no coincide con "
                    f"rol esperado {expected_role!r}."
                ),
            )

        if bool(role_flags.get("superuser", False)):
            add_finding("SEC-ROLE-010", f"{label}: rol con superuser activo.")
        if bool(role_flags.get("create_role", False)):
            add_finding("SEC-ROLE-011", f"{label}: rol con CREATEROLE activo.")
        if bool(role_flags.get("create_db", False)):
            add_finding("SEC-ROLE-012", f"{label}: rol con CREATEDB activo.")
        if not bool(role_flags.get("can_login", True)):
            add_finding("SEC-ROLE-013", f"{label}: rol sin LOGIN.")

        if not bool(schema_privs.get("usage", False)):
            add_finding("SEC-SCHEMA-001", f"{label}: rol sin USAGE en schema public.")
        if bool(schema_privs.get("create", False)):
            add_finding("SEC-SCHEMA-002", f"{label}: rol con CREATE en schema public.")

        for table_name, table_data in tables.items():
            info = table_data if isinstance(table_data, dict) else {}
            exists = bool(info.get("exists", False))
            if not exists:
                add_finding("SEC-TABLE-001", f"{label}: tabla requerida ausente: {table_name}.")
                continue
            privs = info.get("privileges", {}) if isinstance(info.get("privileges"), dict) else {}
            missing = [p for p in REQUIRED_TABLE_PRIVS if not bool(privs.get(p, False))]
            if missing:
                add_finding(
                    "SEC-TABLE-010",
                    f"{label}: faltan privilegios {','.join(missing)} en tabla {table_name}.",
                )
            if bool(privs.get("TRUNCATE", False)):
                add_finding(
                    "SEC-TABLE-011",
                    f"{label}: privilegio TRUNCATE activo en tabla {table_name}.",
                )

    runtime_ok, runtime_snapshot, runtime_reason = collect_role_security_snapshot(
        runtime_dsn,
        label="runtime",
    )
    if not runtime_ok:
        add_finding("SEC-CONN-001", runtime_reason or "runtime: no se pudo auditar seguridad.")
    else:
        snapshots.append(runtime_snapshot)
        evaluate_snapshot(runtime_snapshot, app_role.strip(), "runtime")

    if str(test_dsn or "").strip():
        test_ok, test_snapshot, test_reason = collect_role_security_snapshot(test_dsn, label="test")
        if not test_ok:
            add_finding("SEC-CONN-002", test_reason or "test: no se pudo auditar seguridad.")
        else:
            snapshots.append(test_snapshot)
            evaluate_snapshot(test_snapshot, test_role.strip(), "test")

    if require_test_role_split and len(snapshots) >= 2:
        runtime_user = str(snapshots[0].get("identity", {}).get("current_user", "") or "")
        test_user = str(snapshots[1].get("identity", {}).get("current_user", "") or "")
        if runtime_user and test_user and runtime_user == test_user:
            add_finding(
                "SEC-SPLIT-001",
                (
                    "runtime y test usan el mismo rol DB. "
                    "Defina roles separados para reducir blast radius."
                ),
            )

    if not findings:
        role_txt = ", ".join(
            f"{snap.get('label')}={snap.get('identity', {}).get('current_user', '-')}"
            for snap in snapshots
            if isinstance(snap, dict)
        )
        return {
            "status": "PASS",
            "reason": f"Baseline de seguridad sin desvio ({role_txt or 'sin snapshot'}).",
            "mode": mode_normalized,
            "findings": findings,
            "snapshots": snapshots,
        }

    status = "FAIL" if mode_normalized == SECURITY_MODE_ENFORCE else "WARN"
    reason = (
        f"Se detectaron {len(findings)} desvio(s) de seguridad "
        f"(mode={mode_normalized})."
    )
    return {
        "status": status,
        "reason": reason,
        "mode": mode_normalized,
        "findings": findings,
        "snapshots": snapshots,
    }


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Security baseline DB-first")
    parser.add_argument(
        "--mode",
        default="",
        help=f"Modo security gate ({SECURITY_MODE_OFF}|{SECURITY_MODE_WARN}|{SECURITY_MODE_ENFORCE}).",
    )
    parser.add_argument("--runtime-dsn", default="", help="DSN runtime (default: env DATABASE_URL).")
    parser.add_argument(
        "--test-dsn",
        default="",
        help=f"DSN test opcional (default: env {TEST_DATABASE_URL_ENV}).",
    )
    parser.add_argument(
        "--app-role",
        default="",
        help=f"Rol esperado para runtime (default: env {DB_APP_ROLE_ENV}).",
    )
    parser.add_argument(
        "--test-role",
        default="",
        help=f"Rol esperado para test (default: env {DB_TEST_ROLE_ENV}).",
    )
    parser.add_argument(
        "--require-test-role-split",
        action="store_true",
        help=(
            "Exige rol distinto entre runtime y test. "
            f"(default por env {SECURITY_REQUIRE_TEST_ROLE_SPLIT_ENV})"
        ),
    )
    return parser.parse_args(argv)


def _emit(msg: str = "") -> None:
    print(msg, flush=True)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    mode_ok, mode, mode_reason = _resolve_mode(args.mode)
    if not mode_ok:
        _emit(f"{C.FAIL}[FAIL] {mode_reason}{C.RESET}")
        return 2

    runtime_dsn = str(args.runtime_dsn or os.environ.get(RUNTIME_DATABASE_URL_ENV, "")).strip()
    test_dsn = str(args.test_dsn or os.environ.get(TEST_DATABASE_URL_ENV, "")).strip()
    app_role = str(args.app_role or os.environ.get(DB_APP_ROLE_ENV, "")).strip()
    test_role = str(args.test_role or os.environ.get(DB_TEST_ROLE_ENV, "")).strip()
    require_split_env = _parse_bool(
        os.environ.get(SECURITY_REQUIRE_TEST_ROLE_SPLIT_ENV, ""),
        default=False,
    )
    require_split = bool(args.require_test_role_split or require_split_env)

    _emit(f"\n{C.BOLD}SECURITY BASELINE{C.RESET}")
    _emit(f"Mode: {mode} (env {SECURITY_GATE_MODE_ENV})")
    _emit(f"Runtime DSN: {mask_dsn(runtime_dsn)}")
    if test_dsn:
        _emit(f"Test DSN: {mask_dsn(test_dsn)}")
    else:
        _emit("Test DSN: (not set)")

    result = evaluate_security_baseline(
        runtime_dsn,
        mode=mode,
        app_role=app_role,
        test_dsn=test_dsn,
        test_role=test_role,
        require_test_role_split=require_split,
    )
    status = str(result.get("status", "WARN")).upper()

    snapshots = result.get("snapshots", []) if isinstance(result.get("snapshots"), list) else []
    for snap in snapshots:
        if not isinstance(snap, dict):
            continue
        label = str(snap.get("label", "-"))
        identity = snap.get("identity", {}) if isinstance(snap.get("identity"), dict) else {}
        role = str(identity.get("current_user", "") or "")
        db_name = str(identity.get("database", "") or "")
        _emit(f"{C.INFO}[INFO] snapshot {label}: role={role} db={db_name}{C.RESET}")

    findings = result.get("findings", []) if isinstance(result.get("findings"), list) else []
    for finding in findings:
        if not isinstance(finding, dict):
            continue
        sev = str(finding.get("severity", "WARN")).upper()
        code = str(finding.get("code", "SEC-UNKNOWN"))
        msg = str(finding.get("message", "")).strip()
        color = C.FAIL if sev == "FAIL" else C.WARN
        _emit(f"{color}[{sev}] {code}: {msg}{C.RESET}")

    reason = str(result.get("reason", "") or "")
    if status == "PASS":
        _emit(f"{C.OK}[PASS] security_baseline: {reason}{C.RESET}")
        return 0
    if status == "SKIPPED":
        _emit(f"{C.INFO}[SKIPPED] security_baseline: {reason}{C.RESET}")
        return 0
    if status == "FAIL":
        _emit(f"{C.FAIL}[FAIL] security_baseline: {reason}{C.RESET}")
        return 1
    _emit(f"{C.WARN}[WARN] security_baseline: {reason}{C.RESET}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
