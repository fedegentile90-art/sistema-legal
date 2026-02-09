#!/usr/bin/env python3
"""
Performance/capacity baseline checks for SistemaLegal DB-first operations.

Focus:
- latency of core read-only queries
- capacity guardrails over core table growth
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from db.health import parse_database_url
from db.test_env import mask_dsn

RUNTIME_DATABASE_URL_ENV = "DATABASE_URL"
PERFORMANCE_GATE_MODE_ENV = "VG_PERFORMANCE_GATE_MODE"
PERFORMANCE_MODE_OFF = "off"
PERFORMANCE_MODE_WARN = "warn"
PERFORMANCE_MODE_ENFORCE = "enforce"

PERFORMANCE_MAX_SELECT1_MS_ENV = "VG_PERFORMANCE_GATE_MAX_SELECT1_MS"
PERFORMANCE_MAX_CORE_COUNTS_MS_ENV = "VG_PERFORMANCE_GATE_MAX_CORE_COUNTS_MS"
PERFORMANCE_MAX_RECENT_DOCS_MS_ENV = "VG_PERFORMANCE_GATE_MAX_RECENT_DOCS_MS"
PERFORMANCE_MAX_RECENT_CASES_MS_ENV = "VG_PERFORMANCE_GATE_MAX_RECENT_CASES_MS"
PERFORMANCE_MAX_DOCS_PER_CASE_ENV = "VG_PERFORMANCE_GATE_MAX_DOCS_PER_CASE"
PERFORMANCE_MAX_AUDIT_ROWS_ENV = "VG_PERFORMANCE_GATE_MAX_AUDIT_ROWS"

DEFAULT_MAX_SELECT1_MS = 250
DEFAULT_MAX_CORE_COUNTS_MS = 600
DEFAULT_MAX_RECENT_DOCS_MS = 800
DEFAULT_MAX_RECENT_CASES_MS = 600
DEFAULT_MAX_DOCS_PER_CASE = 300
DEFAULT_MAX_AUDIT_ROWS = 200000

VALID_PERFORMANCE_GATE_MODES = {
    PERFORMANCE_MODE_OFF,
    PERFORMANCE_MODE_WARN,
    PERFORMANCE_MODE_ENFORCE,
}
CORE_TABLES = ("clients", "cases", "documents", "tasks", "audit_log")


class C:
    OK = "\033[92m"
    FAIL = "\033[91m"
    WARN = "\033[93m"
    INFO = "\033[94m"
    RESET = "\033[0m"
    BOLD = "\033[1m"


def _parse_positive_int(value: str, default_value: int) -> int:
    raw = str(value or "").strip()
    if not raw:
        return int(default_value)
    try:
        parsed = int(raw)
    except ValueError:
        return int(default_value)
    if parsed <= 0:
        return int(default_value)
    return int(parsed)


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _resolve_mode(cli_mode: str, env: dict[str, str] | None = None) -> tuple[bool, str, str]:
    env_map = env if env is not None else os.environ
    raw = str(cli_mode or env_map.get(PERFORMANCE_GATE_MODE_ENV, PERFORMANCE_MODE_WARN)).strip().lower()
    if raw in VALID_PERFORMANCE_GATE_MODES:
        return True, raw, ""
    reason = (
        f"Modo performance gate invalido: {raw!r}. "
        f"Use {PERFORMANCE_MODE_OFF!r}, {PERFORMANCE_MODE_WARN!r} o {PERFORMANCE_MODE_ENFORCE!r}."
    )
    return False, "", reason


def load_performance_thresholds(env: dict[str, str] | None = None) -> dict[str, int]:
    env_map = env if env is not None else os.environ
    return {
        "max_select1_ms": _parse_positive_int(
            env_map.get(PERFORMANCE_MAX_SELECT1_MS_ENV, ""),
            DEFAULT_MAX_SELECT1_MS,
        ),
        "max_core_counts_ms": _parse_positive_int(
            env_map.get(PERFORMANCE_MAX_CORE_COUNTS_MS_ENV, ""),
            DEFAULT_MAX_CORE_COUNTS_MS,
        ),
        "max_recent_docs_ms": _parse_positive_int(
            env_map.get(PERFORMANCE_MAX_RECENT_DOCS_MS_ENV, ""),
            DEFAULT_MAX_RECENT_DOCS_MS,
        ),
        "max_recent_cases_ms": _parse_positive_int(
            env_map.get(PERFORMANCE_MAX_RECENT_CASES_MS_ENV, ""),
            DEFAULT_MAX_RECENT_CASES_MS,
        ),
        "max_docs_per_case": _parse_positive_int(
            env_map.get(PERFORMANCE_MAX_DOCS_PER_CASE_ENV, ""),
            DEFAULT_MAX_DOCS_PER_CASE,
        ),
        "max_audit_rows": _parse_positive_int(
            env_map.get(PERFORMANCE_MAX_AUDIT_ROWS_ENV, ""),
            DEFAULT_MAX_AUDIT_ROWS,
        ),
    }


def _timed_query(cur: Any, query: str, params: tuple[Any, ...] = (), fetch: str = "all") -> tuple[Any, float]:
    t0 = time.monotonic()
    cur.execute(query, params)
    if fetch == "one":
        payload = cur.fetchone()
    elif fetch == "none":
        payload = None
    else:
        payload = cur.fetchall()
    elapsed_ms = round((time.monotonic() - t0) * 1000.0, 1)
    return payload, elapsed_ms


def collect_performance_snapshot(runtime_dsn: str) -> tuple[bool, dict[str, Any], str]:
    normalized = parse_database_url(runtime_dsn)
    if not normalized:
        return False, {}, f"{RUNTIME_DATABASE_URL_ENV} no configurada."

    try:
        import psycopg2
    except Exception as exc:  # pragma: no cover - runtime dependency
        return False, {}, f"psycopg2 no disponible ({type(exc).__name__}: {exc})"

    try:
        conn = psycopg2.connect(normalized, connect_timeout=3)
    except Exception as exc:
        return False, {}, f"fallo de conexion ({type(exc).__name__}: {exc})"

    snapshot: dict[str, Any] = {
        "dsn_masked": mask_dsn(normalized),
        "identity": {},
        "latency_ms": {},
        "capacity": {},
        "samples": {},
    }
    try:
        with conn:
            with conn.cursor() as cur:
                identity_row, identity_ms = _timed_query(
                    cur,
                    "SELECT current_user, current_database()",
                    fetch="one",
                )
                current_user = str((identity_row or ("", ""))[0] or "")
                current_db = str((identity_row or ("", ""))[1] or "")

                _, select1_ms = _timed_query(cur, "SELECT 1", fetch="one")

                counts_row, core_counts_ms = _timed_query(
                    cur,
                    """
                    SELECT
                        (SELECT COUNT(*) FROM public.clients),
                        (SELECT COUNT(*) FROM public.cases),
                        (SELECT COUNT(*) FROM public.documents),
                        (SELECT COUNT(*) FROM public.tasks),
                        (SELECT COUNT(*) FROM public.audit_log)
                    """,
                    fetch="one",
                )
                row = counts_row or (0, 0, 0, 0, 0)
                clients_total = int(row[0] or 0)
                cases_total = int(row[1] or 0)
                documents_total = int(row[2] or 0)
                tasks_total = int(row[3] or 0)
                audit_total = int(row[4] or 0)

                docs_rows, recent_docs_ms = _timed_query(
                    cur,
                    "SELECT id FROM public.documents ORDER BY created_at DESC NULLS LAST LIMIT 200",
                    fetch="all",
                )
                cases_rows, recent_cases_ms = _timed_query(
                    cur,
                    "SELECT id FROM public.cases ORDER BY updated_at DESC NULLS LAST LIMIT 200",
                    fetch="all",
                )

        documents_per_case = round(float(documents_total) / float(cases_total), 2) if cases_total > 0 else 0.0
        snapshot["identity"] = {
            "current_user": current_user,
            "database": current_db,
        }
        snapshot["latency_ms"] = {
            "identity": identity_ms,
            "select_1": select1_ms,
            "core_counts": core_counts_ms,
            "recent_documents": recent_docs_ms,
            "recent_cases": recent_cases_ms,
        }
        snapshot["capacity"] = {
            "clients_total": clients_total,
            "cases_total": cases_total,
            "documents_total": documents_total,
            "tasks_total": tasks_total,
            "audit_log_total": audit_total,
            "documents_per_case": documents_per_case,
        }
        snapshot["samples"] = {
            "recent_documents_rows": len(docs_rows or []),
            "recent_cases_rows": len(cases_rows or []),
        }
        return True, snapshot, ""
    except Exception as exc:
        return False, {}, f"fallo consultando performance ({type(exc).__name__}: {exc})"
    finally:
        conn.close()


def evaluate_performance_capacity(
    runtime_dsn: str,
    *,
    mode: str = PERFORMANCE_MODE_WARN,
    thresholds: dict[str, int] | None = None,
) -> dict[str, Any]:
    mode_normalized = str(mode or PERFORMANCE_MODE_WARN).strip().lower()
    if mode_normalized not in VALID_PERFORMANCE_GATE_MODES:
        mode_normalized = PERFORMANCE_MODE_WARN

    if mode_normalized == PERFORMANCE_MODE_OFF:
        return {
            "status": "SKIPPED",
            "reason": "Performance gate deshabilitado por configuracion.",
            "mode": mode_normalized,
            "findings": [],
            "snapshot": {},
            "thresholds": load_performance_thresholds(),
        }

    effective_thresholds = load_performance_thresholds()
    if isinstance(thresholds, dict):
        for key, value in thresholds.items():
            if key not in effective_thresholds:
                continue
            try:
                parsed = int(value)
            except (TypeError, ValueError):
                continue
            if parsed > 0:
                effective_thresholds[key] = parsed

    findings: list[dict[str, str]] = []

    def add_finding(code: str, message: str) -> None:
        severity = "FAIL" if mode_normalized == PERFORMANCE_MODE_ENFORCE else "WARN"
        findings.append({"severity": severity, "code": code, "message": message})

    ok, snapshot, reason = collect_performance_snapshot(runtime_dsn)
    if not ok:
        add_finding("PERF-CONN-001", reason or "No se pudo auditar performance runtime.")
        status = "FAIL" if mode_normalized == PERFORMANCE_MODE_ENFORCE else "WARN"
        return {
            "status": status,
            "reason": f"No se pudo evaluar performance/capacidad (mode={mode_normalized}).",
            "mode": mode_normalized,
            "findings": findings,
            "snapshot": snapshot,
            "thresholds": effective_thresholds,
        }

    latency = snapshot.get("latency_ms", {}) if isinstance(snapshot.get("latency_ms"), dict) else {}
    capacity = snapshot.get("capacity", {}) if isinstance(snapshot.get("capacity"), dict) else {}

    select1_ms = _to_float(latency.get("select_1", 0.0))
    core_counts_ms = _to_float(latency.get("core_counts", 0.0))
    recent_docs_ms = _to_float(latency.get("recent_documents", 0.0))
    recent_cases_ms = _to_float(latency.get("recent_cases", 0.0))

    docs_per_case = _to_float(capacity.get("documents_per_case", 0.0))
    audit_rows = int(_to_float(capacity.get("audit_log_total", 0.0)))

    if select1_ms > float(effective_thresholds["max_select1_ms"]):
        add_finding(
            "PERF-LAT-001",
            (
                f"SELECT 1 alta latencia: {select1_ms}ms "
                f"(umbral {effective_thresholds['max_select1_ms']}ms)."
            ),
        )
    if core_counts_ms > float(effective_thresholds["max_core_counts_ms"]):
        add_finding(
            "PERF-LAT-002",
            (
                f"Conteo tablas core alto: {core_counts_ms}ms "
                f"(umbral {effective_thresholds['max_core_counts_ms']}ms)."
            ),
        )
    if recent_docs_ms > float(effective_thresholds["max_recent_docs_ms"]):
        add_finding(
            "PERF-LAT-003",
            (
                f"Consulta documentos recientes alta latencia: {recent_docs_ms}ms "
                f"(umbral {effective_thresholds['max_recent_docs_ms']}ms)."
            ),
        )
    if recent_cases_ms > float(effective_thresholds["max_recent_cases_ms"]):
        add_finding(
            "PERF-LAT-004",
            (
                f"Consulta casos recientes alta latencia: {recent_cases_ms}ms "
                f"(umbral {effective_thresholds['max_recent_cases_ms']}ms)."
            ),
        )
    if docs_per_case > float(effective_thresholds["max_docs_per_case"]):
        add_finding(
            "PERF-CAP-010",
            (
                f"Relacion documentos/caso elevada: {docs_per_case} "
                f"(umbral {effective_thresholds['max_docs_per_case']})."
            ),
        )
    if audit_rows > int(effective_thresholds["max_audit_rows"]):
        add_finding(
            "PERF-CAP-011",
            (
                f"Tabla audit_log con alto volumen: {audit_rows} filas "
                f"(umbral {effective_thresholds['max_audit_rows']})."
            ),
        )

    if not findings:
        identity = snapshot.get("identity", {}) if isinstance(snapshot.get("identity"), dict) else {}
        db_name = str(identity.get("database", "") or "-")
        return {
            "status": "PASS",
            "reason": f"Performance/capacidad dentro de umbral (db={db_name}).",
            "mode": mode_normalized,
            "findings": findings,
            "snapshot": snapshot,
            "thresholds": effective_thresholds,
        }

    status = "FAIL" if mode_normalized == PERFORMANCE_MODE_ENFORCE else "WARN"
    return {
        "status": status,
        "reason": (
            f"Se detectaron {len(findings)} desvio(s) de performance/capacidad "
            f"(mode={mode_normalized})."
        ),
        "mode": mode_normalized,
        "findings": findings,
        "snapshot": snapshot,
        "thresholds": effective_thresholds,
    }


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Performance/capacity baseline DB-first")
    parser.add_argument(
        "--mode",
        default="",
        help=(
            "Modo performance gate "
            f"({PERFORMANCE_MODE_OFF}|{PERFORMANCE_MODE_WARN}|{PERFORMANCE_MODE_ENFORCE})."
        ),
    )
    parser.add_argument("--runtime-dsn", default="", help="DSN runtime (default: env DATABASE_URL).")
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
    thresholds = load_performance_thresholds()

    _emit(f"\n{C.BOLD}PERFORMANCE/CAPACITY BASELINE{C.RESET}")
    _emit(f"Mode: {mode} (env {PERFORMANCE_GATE_MODE_ENV})")
    _emit(f"Runtime DSN: {mask_dsn(runtime_dsn)}")
    _emit(
        "Thresholds: "
        f"{PERFORMANCE_MAX_SELECT1_MS_ENV}={thresholds['max_select1_ms']}ms, "
        f"{PERFORMANCE_MAX_CORE_COUNTS_MS_ENV}={thresholds['max_core_counts_ms']}ms, "
        f"{PERFORMANCE_MAX_RECENT_DOCS_MS_ENV}={thresholds['max_recent_docs_ms']}ms, "
        f"{PERFORMANCE_MAX_RECENT_CASES_MS_ENV}={thresholds['max_recent_cases_ms']}ms, "
        f"{PERFORMANCE_MAX_DOCS_PER_CASE_ENV}={thresholds['max_docs_per_case']}, "
        f"{PERFORMANCE_MAX_AUDIT_ROWS_ENV}={thresholds['max_audit_rows']}"
    )

    result = evaluate_performance_capacity(
        runtime_dsn,
        mode=mode,
        thresholds=thresholds,
    )
    status = str(result.get("status", "WARN")).upper()

    snapshot = result.get("snapshot", {}) if isinstance(result.get("snapshot"), dict) else {}
    identity = snapshot.get("identity", {}) if isinstance(snapshot.get("identity"), dict) else {}
    latency = snapshot.get("latency_ms", {}) if isinstance(snapshot.get("latency_ms"), dict) else {}
    capacity = snapshot.get("capacity", {}) if isinstance(snapshot.get("capacity"), dict) else {}

    if identity:
        _emit(
            f"{C.INFO}[INFO] snapshot runtime: role={identity.get('current_user', '')} "
            f"db={identity.get('database', '')}{C.RESET}"
        )
    if latency:
        _emit(
            f"{C.INFO}[INFO] latency ms: select_1={latency.get('select_1', 0.0)} "
            f"core_counts={latency.get('core_counts', 0.0)} "
            f"recent_documents={latency.get('recent_documents', 0.0)} "
            f"recent_cases={latency.get('recent_cases', 0.0)}{C.RESET}"
        )
    if capacity:
        _emit(
            f"{C.INFO}[INFO] capacity: clients={capacity.get('clients_total', 0)} "
            f"cases={capacity.get('cases_total', 0)} "
            f"documents={capacity.get('documents_total', 0)} "
            f"tasks={capacity.get('tasks_total', 0)} "
            f"audit_log={capacity.get('audit_log_total', 0)} "
            f"docs_per_case={capacity.get('documents_per_case', 0.0)}{C.RESET}"
        )

    findings = result.get("findings", []) if isinstance(result.get("findings"), list) else []
    for finding in findings:
        if not isinstance(finding, dict):
            continue
        sev = str(finding.get("severity", "WARN")).upper()
        code = str(finding.get("code", "PERF-UNKNOWN"))
        message = str(finding.get("message", "")).strip()
        color = C.FAIL if sev == "FAIL" else C.WARN
        _emit(f"{color}[{sev}] {code}: {message}{C.RESET}")

    reason = str(result.get("reason", "") or "")
    if status == "PASS":
        _emit(f"{C.OK}[PASS] performance_capacity: {reason}{C.RESET}")
        return 0
    if status == "SKIPPED":
        _emit(f"{C.INFO}[SKIPPED] performance_capacity: {reason}{C.RESET}")
        return 0
    if status == "FAIL":
        _emit(f"{C.FAIL}[FAIL] performance_capacity: {reason}{C.RESET}")
        return 1
    _emit(f"{C.WARN}[WARN] performance_capacity: {reason}{C.RESET}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
