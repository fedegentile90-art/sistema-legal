#!/usr/bin/env python3
"""
Release QA Gate - VACA & GENTILE ERP

Entrada unica:
  python db/release_gate.py
  python db/release_gate.py --mode read_only
  python db/release_gate.py --mode full
  python db/release_gate.py --kpi-mode off|warn|enforce
  python db/release_gate.py --security-mode off|warn|enforce
  python db/release_gate.py --performance-mode off|warn|enforce

Suites core:
  - python db/contract_test.py
  - python db/ux_gestion_regression_test.py
  - python db/ux_phase2_test.py
  - python db/smoke_test.py

Quality gate KPI:
  - calcula KPI operativo sobre DATABASE_URL runtime.
  - usa objetivos historicos: FECHA_TAREA 60%, EXPEDIENTE 70%,
    EVENTO/FECHA_EVENTO 40%, COBERTURA_FINANCIERA 70%.
  - modo configurable (env/CLI): off | warn | enforce.
  - en modo warn informa desvio sin bloquear release.
  - en modo enforce bloquea release si KPI objetivo no se cumple.

Security gate base:
  - audita auth/roles/least-privilege sobre runtime/test DB.
  - detecta superuser, CREATE en schema public y TRUNCATE en tablas core.
  - modo configurable (env/CLI): off | warn | enforce.
  - en warn informa desvio sin bloquear release.
  - en enforce bloquea release ante desvio.

Performance/capacidad gate:
  - audita latencia de queries core read-only sobre DATABASE_URL runtime.
  - verifica umbrales de capacidad (docs/caso y volumen de audit_log).
  - modo configurable (env/CLI): off | warn | enforce.
  - en warn informa desvio sin bloquear release.
  - en enforce bloquea release ante desvio.

Modos de ejecucion:
  - full: corre todas las suites core (incluye suites DB).
  - read_only: corre solo suites de lectura. Las suites DB quedan SKIPPED.

Politica de aislamiento DB:
  - contract_test siempre se ejecuta.
  - ux_gestion_regression_test, ux_phase2_test y smoke_test requieren VG_TEST_DATABASE_URL.
  - VG_TEST_DATABASE_URL debe apuntar a una DB de pruebas dedicada.
  - Si falta/viola el contrato, esas suites quedan BLOCKED y el gate finaliza en FAIL.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from db.health import wait_for_db
from db.test_env import (
    TEST_DATABASE_URL_ENV,
    build_isolated_suite_env,
)
from db.security_baseline import (
    SECURITY_GATE_MODE_ENV,
    SECURITY_MODE_OFF,
    SECURITY_MODE_WARN,
    SECURITY_MODE_ENFORCE,
    DB_APP_ROLE_ENV,
    DB_TEST_ROLE_ENV,
    SECURITY_REQUIRE_TEST_ROLE_SPLIT_ENV,
    evaluate_security_baseline,
)
from db.performance_capacity import (
    PERFORMANCE_GATE_MODE_ENV,
    PERFORMANCE_MODE_OFF,
    PERFORMANCE_MODE_WARN,
    PERFORMANCE_MODE_ENFORCE,
    evaluate_performance_capacity,
)
from config import CAMPOS_FINANCIEROS
from domain import is_blank
from repo import GestorCasos

RELEASE_GATE_MODE_ENV = "VG_RELEASE_GATE_MODE"
RELEASE_MODE_READ_ONLY = "read_only"
RELEASE_MODE_FULL = "full"
RUN_ID_ENV = "VG_RUN_ID"
QUALITY_GATE_KPI_MODE_ENV = "VG_QUALITY_GATE_KPI_MODE"
QUALITY_GATE_KPI_MIN_CASES_ENV = "VG_QUALITY_GATE_KPI_MIN_CASES"
KPI_MODE_OFF = "off"
KPI_MODE_WARN = "warn"
KPI_MODE_ENFORCE = "enforce"

KPI_TARGETS = {
    "FECHA_TAREA": 60.0,
    "EXPEDIENTE": 70.0,
    "EVENTO_FECHA_EVENTO": 40.0,
    "COBERTURA_FINANCIERA": 70.0,
}


class C:
    OK = "\033[92m"
    FAIL = "\033[91m"
    WARN = "\033[93m"
    INFO = "\033[94m"
    RESET = "\033[0m"
    BOLD = "\033[1m"


@dataclass(frozen=True)
class Suite:
    name: str
    command: list[str]
    requires_test_database: bool = False


def _emit(msg: str = "") -> None:
    print(msg, flush=True)


def _section(title: str) -> None:
    _emit(f"\n{C.BOLD}{'=' * 72}")
    _emit(f"  {title}")
    _emit(f"{'=' * 72}{C.RESET}")


def _utc_now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _resolve_run_id(env: dict[str, str] | None = None) -> str:
    env_map = env if env is not None else os.environ
    raw = str(env_map.get(RUN_ID_ENV, "")).strip()
    if raw:
        return raw
    stamp = time.strftime("%Y%m%d%H%M%S", time.gmtime())
    return f"rg-{stamp}-{uuid.uuid4().hex[:8]}"


def _emit_obs(
    run_id: str,
    stage: str,
    suite: str,
    status: str,
    detail: str = "",
) -> None:
    event: dict[str, str] = {
        "ts": _utc_now_iso(),
        "run_id": str(run_id).strip() or "unknown",
        "stage": str(stage).strip() or "-",
        "suite": str(suite).strip() or "-",
        "status": str(status).strip() or "INFO",
    }
    if detail:
        event["detail"] = str(detail).strip()
    _emit("[OBS] " + json.dumps(event, ensure_ascii=True, sort_keys=True))


def _env_int(name: str, default: int) -> int:
    raw = str(os.environ.get(name, "")).strip()
    if not raw:
        return int(default)
    try:
        value = int(raw)
    except ValueError:
        return int(default)
    if value <= 0:
        return int(default)
    return value


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Release QA gate")
    parser.add_argument(
        "--mode",
        default="",
        help=(
            "Modo de ejecucion del gate: "
            f"{RELEASE_MODE_READ_ONLY}|{RELEASE_MODE_FULL} "
            f"(env fallback: {RELEASE_GATE_MODE_ENV}, default: {RELEASE_MODE_FULL})"
        ),
    )
    parser.add_argument(
        "--kpi-mode",
        default="",
        help=(
            "Modo de quality gate KPI: "
            f"{KPI_MODE_OFF}|{KPI_MODE_WARN}|{KPI_MODE_ENFORCE} "
            f"(env fallback: {QUALITY_GATE_KPI_MODE_ENV}, default: {KPI_MODE_WARN})"
        ),
    )
    parser.add_argument(
        "--kpi-min-cases",
        default="",
        help=(
            "Minimo de casos para evaluar KPI gate (entero >= 0). "
            f"(env fallback: {QUALITY_GATE_KPI_MIN_CASES_ENV}, default: 1)"
        ),
    )
    parser.add_argument(
        "--security-mode",
        default="",
        help=(
            "Modo security gate: "
            f"{SECURITY_MODE_OFF}|{SECURITY_MODE_WARN}|{SECURITY_MODE_ENFORCE} "
            f"(env fallback: {SECURITY_GATE_MODE_ENV}, default: {SECURITY_MODE_WARN})"
        ),
    )
    parser.add_argument(
        "--performance-mode",
        default="",
        help=(
            "Modo performance gate: "
            f"{PERFORMANCE_MODE_OFF}|{PERFORMANCE_MODE_WARN}|{PERFORMANCE_MODE_ENFORCE} "
            f"(env fallback: {PERFORMANCE_GATE_MODE_ENV}, default: {PERFORMANCE_MODE_WARN})"
        ),
    )
    return parser.parse_args(argv)


def _resolve_release_mode(cli_value: str, env: dict[str, str] | None = None) -> tuple[bool, str, str]:
    env_map = env if env is not None else os.environ
    raw = str(cli_value or env_map.get(RELEASE_GATE_MODE_ENV, RELEASE_MODE_FULL)).strip().lower()
    if raw in {RELEASE_MODE_READ_ONLY, RELEASE_MODE_FULL}:
        return True, raw, ""
    reason = (
        f"Modo invalido: {raw!r}. "
        f"Use {RELEASE_MODE_READ_ONLY!r} o {RELEASE_MODE_FULL!r} "
        f"(arg --mode o env {RELEASE_GATE_MODE_ENV})."
    )
    return False, "", reason


def _resolve_kpi_mode(cli_value: str, env: dict[str, str] | None = None) -> tuple[bool, str, str]:
    env_map = env if env is not None else os.environ
    raw = str(cli_value or env_map.get(QUALITY_GATE_KPI_MODE_ENV, KPI_MODE_WARN)).strip().lower()
    if raw in {KPI_MODE_OFF, KPI_MODE_WARN, KPI_MODE_ENFORCE}:
        return True, raw, ""
    reason = (
        f"Modo KPI invalido: {raw!r}. "
        f"Use {KPI_MODE_OFF!r}, {KPI_MODE_WARN!r} o {KPI_MODE_ENFORCE!r} "
        f"(arg --kpi-mode o env {QUALITY_GATE_KPI_MODE_ENV})."
    )
    return False, "", reason


def _resolve_kpi_min_cases(cli_value: str, env: dict[str, str] | None = None) -> tuple[bool, int, str]:
    env_map = env if env is not None else os.environ
    raw = str(cli_value or env_map.get(QUALITY_GATE_KPI_MIN_CASES_ENV, "1")).strip()
    if not raw:
        return True, 1, ""
    try:
        value = int(raw)
    except ValueError:
        return False, 0, f"{QUALITY_GATE_KPI_MIN_CASES_ENV} debe ser entero >= 0 (valor={raw!r})."
    if value < 0:
        return False, 0, f"{QUALITY_GATE_KPI_MIN_CASES_ENV} debe ser >= 0 (valor={value})."
    return True, value, ""


def _resolve_security_mode(cli_value: str, env: dict[str, str] | None = None) -> tuple[bool, str, str]:
    env_map = env if env is not None else os.environ
    raw = str(cli_value or env_map.get(SECURITY_GATE_MODE_ENV, SECURITY_MODE_WARN)).strip().lower()
    if raw in {SECURITY_MODE_OFF, SECURITY_MODE_WARN, SECURITY_MODE_ENFORCE}:
        return True, raw, ""
    reason = (
        f"Modo security gate invalido: {raw!r}. "
        f"Use {SECURITY_MODE_OFF!r}, {SECURITY_MODE_WARN!r} o {SECURITY_MODE_ENFORCE!r} "
        f"(arg --security-mode o env {SECURITY_GATE_MODE_ENV})."
    )
    return False, "", reason


def _resolve_performance_mode(cli_value: str, env: dict[str, str] | None = None) -> tuple[bool, str, str]:
    env_map = env if env is not None else os.environ
    raw = str(cli_value or env_map.get(PERFORMANCE_GATE_MODE_ENV, PERFORMANCE_MODE_WARN)).strip().lower()
    if raw in {PERFORMANCE_MODE_OFF, PERFORMANCE_MODE_WARN, PERFORMANCE_MODE_ENFORCE}:
        return True, raw, ""
    reason = (
        f"Modo performance gate invalido: {raw!r}. "
        f"Use {PERFORMANCE_MODE_OFF!r}, {PERFORMANCE_MODE_WARN!r} o {PERFORMANCE_MODE_ENFORCE!r} "
        f"(arg --performance-mode o env {PERFORMANCE_GATE_MODE_ENV})."
    )
    return False, "", reason


def _env_bool(name: str, default: bool = False) -> bool:
    raw = str(os.environ.get(name, "")).strip().lower()
    if not raw:
        return bool(default)
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off"}:
        return False
    return bool(default)


def _run_suite(
    suite: Suite,
    timeout_sec: int,
    run_id: str,
    env: dict[str, str] | None = None,
) -> dict[str, object]:
    cmd_text = " ".join(suite.command)
    _emit_obs(
        run_id,
        stage="suite_start",
        suite=suite.name,
        status="RUN",
        detail=f"timeout_sec={int(timeout_sec)} cmd={cmd_text}",
    )
    _emit(
        f"{C.INFO}[RUN] {suite.name}: {cmd_text} "
        f"(timeout={int(timeout_sec)}s){C.RESET}"
    )
    t0 = time.monotonic()
    try:
        result = subprocess.run(
            suite.command,
            cwd=str(ROOT),
            env=env,
            timeout=max(1, int(timeout_sec)),
        )
        duration_sec = round(time.monotonic() - t0, 2)
        if result.returncode == 0:
            _emit(f"{C.OK}[PASS] {suite.name} ({duration_sec}s){C.RESET}")
            _emit_obs(
                run_id,
                stage="suite_end",
                suite=suite.name,
                status="PASS",
                detail=f"code=0 duration_sec={duration_sec}",
            )
            return {"status": "PASS", "code": 0, "reason": "", "duration_sec": duration_sec}
        _emit(
            f"{C.FAIL}[FAIL] {suite.name} "
            f"(exit={result.returncode}, {duration_sec}s){C.RESET}"
        )
        _emit_obs(
            run_id,
            stage="suite_end",
            suite=suite.name,
            status="FAIL",
            detail=f"code={int(result.returncode)} duration_sec={duration_sec}",
        )
        return {
            "status": "FAIL",
            "code": int(result.returncode),
            "reason": "",
            "duration_sec": duration_sec,
        }
    except subprocess.TimeoutExpired:
        duration_sec = round(time.monotonic() - t0, 2)
        reason = f"timeout>{int(timeout_sec)}s"
        _emit(
            f"{C.FAIL}[TIMEOUT] {suite.name} "
            f"(>{int(timeout_sec)}s, elapsed={duration_sec}s){C.RESET}"
        )
        _emit_obs(
            run_id,
            stage="suite_end",
            suite=suite.name,
            status="TIMEOUT",
            detail=f"timeout_sec={int(timeout_sec)} duration_sec={duration_sec}",
        )
        return {"status": "TIMEOUT", "code": 124, "reason": reason, "duration_sec": duration_sec}


def _run_db_preflight(database_url: str) -> dict[str, object]:
    return wait_for_db(database_url, attempts=3, backoff=0.6, connect_timeout=3)


def _pct(completed: int, total: int) -> float:
    if total <= 0:
        return 0.0
    return round((float(completed) / float(total)) * 100.0, 1)


def _build_runtime_kpi_snapshot() -> dict[str, object]:
    gestor = GestorCasos()
    casos = list(gestor.escanear_casos() or [])
    total = max(0, len(casos))

    fecha_tarea_ok = 0
    expediente_ok = 0
    evento_fecha_ok = 0
    fin_ok = 0

    for caso in casos:
        if not is_blank(getattr(caso, "fecha_tarea", "")):
            fecha_tarea_ok += 1
        if not is_blank(getattr(caso, "expediente", "")):
            expediente_ok += 1
        if (not is_blank(getattr(caso, "evento", ""))) and (not is_blank(getattr(caso, "fecha_evento", ""))):
            evento_fecha_ok += 1

        fin_data = {}
        if hasattr(gestor, "leer_datos_financieros"):
            try:
                fin_data = gestor.leer_datos_financieros(caso.ruta) or {}
            except Exception:
                fin_data = {}
        if any(not is_blank(fin_data.get(field, "")) for field in CAMPOS_FINANCIEROS):
            fin_ok += 1

    metric_raw = {
        "FECHA_TAREA": fecha_tarea_ok,
        "EXPEDIENTE": expediente_ok,
        "EVENTO_FECHA_EVENTO": evento_fecha_ok,
        "COBERTURA_FINANCIERA": fin_ok,
    }
    kpis: dict[str, dict[str, object]] = {}
    for metric, completed in metric_raw.items():
        target = float(KPI_TARGETS.get(metric, 0.0))
        pct_value = _pct(int(completed), int(total))
        kpis[metric] = {
            "completed": int(completed),
            "total": int(total),
            "pct": pct_value,
            "target_pct": target,
            "goal_met": bool(pct_value >= target),
            "gap_pct": round(pct_value - target, 1),
        }

    return {
        "casos_total": int(total),
        "kpis": kpis,
    }


def _evaluate_quality_gate_kpi(
    run_id: str,
    kpi_mode: str,
    kpi_min_cases: int,
) -> dict[str, object]:
    _section("QUALITY GATE KPI")
    _emit(
        f"Modo KPI gate: {kpi_mode} (env {QUALITY_GATE_KPI_MODE_ENV}) | "
        f"min_cases={int(kpi_min_cases)} (env {QUALITY_GATE_KPI_MIN_CASES_ENV})"
    )

    if kpi_mode == KPI_MODE_OFF:
        reason = "Quality gate KPI deshabilitado por configuracion."
        _emit(f"{C.INFO}[SKIPPED] quality_gate_kpi: {reason}{C.RESET}")
        _emit_obs(run_id, stage="kpi_gate", suite="quality_gate_kpi", status="SKIPPED", detail=reason)
        return {
            "status": "SKIPPED",
            "reason": reason,
            "mode": kpi_mode,
            "casos_total": 0,
            "failed_metrics": [],
        }

    try:
        snapshot = _build_runtime_kpi_snapshot()
    except Exception as exc:
        reason = f"No se pudo calcular KPI runtime: {type(exc).__name__}: {exc}"
        if kpi_mode == KPI_MODE_ENFORCE:
            _emit(f"{C.FAIL}[FAIL] quality_gate_kpi: {reason}{C.RESET}")
            _emit_obs(run_id, stage="kpi_gate", suite="quality_gate_kpi", status="FAIL", detail=reason)
            return {
                "status": "FAIL",
                "reason": reason,
                "mode": kpi_mode,
                "casos_total": 0,
                "failed_metrics": [],
            }
        _emit(f"{C.WARN}[WARN] quality_gate_kpi: {reason}{C.RESET}")
        _emit_obs(run_id, stage="kpi_gate", suite="quality_gate_kpi", status="WARN", detail=reason)
        return {
            "status": "WARN",
            "reason": reason,
            "mode": kpi_mode,
            "casos_total": 0,
            "failed_metrics": [],
        }

    casos_total = int(snapshot.get("casos_total", 0) or 0)
    kpis = snapshot.get("kpis", {}) if isinstance(snapshot.get("kpis"), dict) else {}

    if casos_total < int(kpi_min_cases):
        reason = f"Muestra insuficiente para evaluar KPI (casos={casos_total}, min={int(kpi_min_cases)})."
        _emit(f"{C.INFO}[SKIPPED] quality_gate_kpi: {reason}{C.RESET}")
        _emit_obs(run_id, stage="kpi_gate", suite="quality_gate_kpi", status="SKIPPED", detail=reason)
        return {
            "status": "SKIPPED",
            "reason": reason,
            "mode": kpi_mode,
            "casos_total": casos_total,
            "failed_metrics": [],
        }

    failed_metrics: list[str] = []
    for metric_name, metric in kpis.items():
        if not isinstance(metric, dict):
            continue
        completed = int(metric.get("completed", 0) or 0)
        total = int(metric.get("total", 0) or 0)
        pct_value = float(metric.get("pct", 0.0) or 0.0)
        target = float(metric.get("target_pct", 0.0) or 0.0)
        gap = float(metric.get("gap_pct", pct_value - target) or 0.0)
        goal_met = bool(metric.get("goal_met", False))
        if goal_met:
            _emit(
                f"{C.OK}[PASS] KPI {metric_name}: {pct_value}% ({completed}/{total}) "
                f"objetivo={target}% gap={gap}{C.RESET}"
            )
        else:
            failed_metrics.append(metric_name)
            color = C.FAIL if kpi_mode == KPI_MODE_ENFORCE else C.WARN
            label = "FAIL" if kpi_mode == KPI_MODE_ENFORCE else "WARN"
            _emit(
                f"{color}[{label}] KPI {metric_name}: {pct_value}% ({completed}/{total}) "
                f"objetivo={target}% gap={gap}{C.RESET}"
            )

    if not failed_metrics:
        reason = f"KPI operativo en objetivo ({casos_total} casos evaluados)."
        _emit(f"{C.OK}[PASS] quality_gate_kpi: {reason}{C.RESET}")
        _emit_obs(run_id, stage="kpi_gate", suite="quality_gate_kpi", status="PASS", detail=reason)
        return {
            "status": "PASS",
            "reason": reason,
            "mode": kpi_mode,
            "casos_total": casos_total,
            "failed_metrics": failed_metrics,
        }

    failed_text = ", ".join(failed_metrics)
    reason = f"KPI fuera de objetivo: {failed_text} (casos={casos_total})."
    if kpi_mode == KPI_MODE_ENFORCE:
        _emit(f"{C.FAIL}[FAIL] quality_gate_kpi: {reason}{C.RESET}")
        _emit_obs(run_id, stage="kpi_gate", suite="quality_gate_kpi", status="FAIL", detail=reason)
        return {
            "status": "FAIL",
            "reason": reason,
            "mode": kpi_mode,
            "casos_total": casos_total,
            "failed_metrics": failed_metrics,
        }

    _emit(f"{C.WARN}[WARN] quality_gate_kpi: {reason} (modo warn, no bloquea release){C.RESET}")
    _emit_obs(run_id, stage="kpi_gate", suite="quality_gate_kpi", status="WARN", detail=reason)
    return {
        "status": "WARN",
        "reason": reason,
        "mode": kpi_mode,
        "casos_total": casos_total,
        "failed_metrics": failed_metrics,
    }


def _evaluate_security_gate(
    run_id: str,
    security_mode: str,
    release_mode: str,
    suites_env_ok: bool,
    suites_env: dict[str, str],
) -> dict[str, object]:
    _section("SECURITY GATE")
    _emit(
        f"Modo security gate: {security_mode} "
        f"(env {SECURITY_GATE_MODE_ENV}, default={SECURITY_MODE_WARN})"
    )

    runtime_dsn = str(os.environ.get("DATABASE_URL", "")).strip()
    test_dsn = ""
    if release_mode == RELEASE_MODE_FULL and suites_env_ok:
        test_dsn = str(suites_env.get("DATABASE_URL", "")).strip()

    app_role = str(os.environ.get(DB_APP_ROLE_ENV, "")).strip()
    test_role = str(os.environ.get(DB_TEST_ROLE_ENV, "")).strip()
    require_role_split = _env_bool(SECURITY_REQUIRE_TEST_ROLE_SPLIT_ENV, default=False)

    result = evaluate_security_baseline(
        runtime_dsn,
        mode=security_mode,
        app_role=app_role,
        test_dsn=test_dsn,
        test_role=test_role,
        require_test_role_split=require_role_split,
    )

    snapshots = result.get("snapshots", []) if isinstance(result.get("snapshots"), list) else []
    for snap in snapshots:
        if not isinstance(snap, dict):
            continue
        label = str(snap.get("label", "-"))
        identity = snap.get("identity", {}) if isinstance(snap.get("identity"), dict) else {}
        role = str(identity.get("current_user", "") or "")
        database = str(identity.get("database", "") or "")
        _emit(f"{C.INFO}[INFO] security snapshot {label}: role={role} db={database}{C.RESET}")

    findings = result.get("findings", []) if isinstance(result.get("findings"), list) else []
    for finding in findings:
        if not isinstance(finding, dict):
            continue
        sev = str(finding.get("severity", "WARN")).upper()
        code = str(finding.get("code", "SEC-UNKNOWN"))
        message = str(finding.get("message", "")).strip()
        if sev == "FAIL":
            _emit(f"{C.FAIL}[FAIL] {code}: {message}{C.RESET}")
        else:
            _emit(f"{C.WARN}[WARN] {code}: {message}{C.RESET}")

    status = str(result.get("status", "SKIPPED")).upper()
    reason = str(result.get("reason", "") or "")
    if status == "PASS":
        _emit(f"{C.OK}[PASS] security_gate: {reason}{C.RESET}")
    elif status == "FAIL":
        _emit(f"{C.FAIL}[FAIL] security_gate: {reason}{C.RESET}")
    elif status == "SKIPPED":
        _emit(f"{C.INFO}[SKIPPED] security_gate: {reason}{C.RESET}")
    else:
        _emit(f"{C.WARN}[WARN] security_gate: {reason}{C.RESET}")

    _emit_obs(run_id, stage="security_gate", suite="security_gate", status=status, detail=reason)
    return result


def _evaluate_performance_gate(
    run_id: str,
    performance_mode: str,
) -> dict[str, object]:
    _section("PERFORMANCE/CAPACITY GATE")
    _emit(
        f"Modo performance gate: {performance_mode} "
        f"(env {PERFORMANCE_GATE_MODE_ENV}, default={PERFORMANCE_MODE_WARN})"
    )

    runtime_dsn = str(os.environ.get("DATABASE_URL", "")).strip()
    result = evaluate_performance_capacity(runtime_dsn, mode=performance_mode)

    snapshot = result.get("snapshot", {}) if isinstance(result.get("snapshot"), dict) else {}
    identity = snapshot.get("identity", {}) if isinstance(snapshot.get("identity"), dict) else {}
    latency = snapshot.get("latency_ms", {}) if isinstance(snapshot.get("latency_ms"), dict) else {}
    capacity = snapshot.get("capacity", {}) if isinstance(snapshot.get("capacity"), dict) else {}

    if identity:
        _emit(
            f"{C.INFO}[INFO] performance snapshot runtime: "
            f"role={identity.get('current_user', '')} db={identity.get('database', '')}{C.RESET}"
        )

    if latency:
        _emit(
            f"{C.INFO}[INFO] latency ms: "
            f"select_1={latency.get('select_1', 0.0)} "
            f"core_counts={latency.get('core_counts', 0.0)} "
            f"recent_documents={latency.get('recent_documents', 0.0)} "
            f"recent_cases={latency.get('recent_cases', 0.0)}{C.RESET}"
        )

    if capacity:
        _emit(
            f"{C.INFO}[INFO] capacity: "
            f"clients={capacity.get('clients_total', 0)} "
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
        if sev == "FAIL":
            _emit(f"{C.FAIL}[FAIL] {code}: {message}{C.RESET}")
        else:
            _emit(f"{C.WARN}[WARN] {code}: {message}{C.RESET}")

    status = str(result.get("status", "SKIPPED")).upper()
    reason = str(result.get("reason", "") or "")
    if status == "PASS":
        _emit(f"{C.OK}[PASS] performance_gate: {reason}{C.RESET}")
    elif status == "FAIL":
        _emit(f"{C.FAIL}[FAIL] performance_gate: {reason}{C.RESET}")
    elif status == "SKIPPED":
        _emit(f"{C.INFO}[SKIPPED] performance_gate: {reason}{C.RESET}")
    else:
        _emit(f"{C.WARN}[WARN] performance_gate: {reason}{C.RESET}")

    _emit_obs(run_id, stage="performance_gate", suite="performance_gate", status=status, detail=reason)
    return result


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    mode_ok, release_mode, mode_reason = _resolve_release_mode(args.mode)
    kpi_mode_ok, kpi_mode, kpi_mode_reason = _resolve_kpi_mode(args.kpi_mode)
    kpi_min_ok, kpi_min_cases, kpi_min_reason = _resolve_kpi_min_cases(args.kpi_min_cases)
    security_mode_ok, security_mode, security_mode_reason = _resolve_security_mode(args.security_mode)
    performance_mode_ok, performance_mode, performance_mode_reason = _resolve_performance_mode(
        args.performance_mode
    )
    run_id = _resolve_run_id()
    os.environ[RUN_ID_ENV] = run_id

    _section("RELEASE QA GATE")
    _emit(f"Run ID: {run_id} (env {RUN_ID_ENV})")
    _emit_obs(
        run_id,
        stage="gate_start",
        suite="release_gate",
        status="RUN",
        detail=f"mode_arg={args.mode or '-'}",
    )
    if not mode_ok:
        _emit(f"{C.FAIL}[FAIL] {mode_reason}{C.RESET}")
        _emit_obs(run_id, stage="gate_init", suite="release_gate", status="FAIL", detail=mode_reason)
        return 2
    if not kpi_mode_ok:
        _emit(f"{C.FAIL}[FAIL] {kpi_mode_reason}{C.RESET}")
        _emit_obs(run_id, stage="gate_init", suite="release_gate", status="FAIL", detail=kpi_mode_reason)
        return 2
    if not kpi_min_ok:
        _emit(f"{C.FAIL}[FAIL] {kpi_min_reason}{C.RESET}")
        _emit_obs(run_id, stage="gate_init", suite="release_gate", status="FAIL", detail=kpi_min_reason)
        return 2
    if not security_mode_ok:
        _emit(f"{C.FAIL}[FAIL] {security_mode_reason}{C.RESET}")
        _emit_obs(run_id, stage="gate_init", suite="release_gate", status="FAIL", detail=security_mode_reason)
        return 2
    if not performance_mode_ok:
        _emit(f"{C.FAIL}[FAIL] {performance_mode_reason}{C.RESET}")
        _emit_obs(run_id, stage="gate_init", suite="release_gate", status="FAIL", detail=performance_mode_reason)
        return 2

    _emit(f"Modo de ejecucion: {release_mode} (env {RELEASE_GATE_MODE_ENV})")
    _emit(
        f"Modo KPI quality gate: {kpi_mode} (env {QUALITY_GATE_KPI_MODE_ENV}, "
        f"default={KPI_MODE_WARN})"
    )
    _emit(
        f"Modo security gate: {security_mode} "
        f"(env {SECURITY_GATE_MODE_ENV}, default={SECURITY_MODE_WARN})"
    )
    _emit(
        f"Modo performance gate: {performance_mode} "
        f"(env {PERFORMANCE_GATE_MODE_ENV}, default={PERFORMANCE_MODE_WARN})"
    )
    _emit(
        f"Min casos KPI gate: {kpi_min_cases} "
        f"(env {QUALITY_GATE_KPI_MIN_CASES_ENV}, default=1)"
    )
    _emit_obs(
        run_id,
        stage="gate_init",
        suite="release_gate",
        status="PASS",
        detail=(
            f"mode={release_mode} kpi_mode={kpi_mode} kpi_min_cases={kpi_min_cases} "
            f"security_mode={security_mode} performance_mode={performance_mode}"
        ),
    )
    _emit("Politica DB de pruebas:")
    if release_mode == RELEASE_MODE_FULL:
        _emit(f"  - Suites DB sin {TEST_DATABASE_URL_ENV} => BLOCKED (no se ejecutan).")
        _emit(f"  - {TEST_DATABASE_URL_ENV} debe ser una DB dedicada (aislada).")
        _emit("  - BLOCKED cuenta como FAIL para release.")
    else:
        _emit("  - read_only: suites DB quedan SKIPPED por seguridad.")
        _emit("  - full: ejecutar para validar suites DB en DB de pruebas aislada.")
    suite_timeout_sec = _env_int("VG_SUITE_TIMEOUT_SEC", 900)
    _emit(f"Timeout por suite: {suite_timeout_sec}s (env VG_SUITE_TIMEOUT_SEC)")

    suites_env_ok = False
    suites_env = os.environ.copy()
    suites_env_reason = ""
    test_database_url = ""

    suites = [
        Suite("contract_test", [sys.executable, "db/contract_test.py"]),
        Suite(
            "ux_gestion_regression_test",
            [sys.executable, "db/ux_gestion_regression_test.py"],
            requires_test_database=True,
        ),
        Suite(
            "ux_phase2_test",
            [sys.executable, "db/ux_phase2_test.py"],
            requires_test_database=True,
        ),
        Suite(
            "smoke_test",
            [sys.executable, "db/smoke_test.py"],
            requires_test_database=True,
        ),
    ]

    db_preflight = {"ok": False, "stage": "init", "last_error": ""}

    if release_mode == RELEASE_MODE_FULL:
        suites_env_ok, suites_env, suites_env_reason = build_isolated_suite_env(os.environ.copy())
        test_database_url = str(suites_env.get("DATABASE_URL", "")).strip() if suites_env_ok else ""
        if suites_env_ok:
            _emit_obs(
                run_id,
                stage="env_contract",
                suite="release_gate",
                status="PASS",
                detail=f"{TEST_DATABASE_URL_ENV} valida",
            )
        else:
            _emit_obs(
                run_id,
                stage="env_contract",
                suite="release_gate",
                status="FAIL",
                detail=suites_env_reason or f"{TEST_DATABASE_URL_ENV} no configurada",
            )
    else:
        _emit_obs(
            run_id,
            stage="env_contract",
            suite="release_gate",
            status="SKIPPED",
            detail="mode=read_only",
        )

    if release_mode == RELEASE_MODE_FULL and suites_env_ok:
        _section("DB PREFLIGHT")
        db_preflight = _run_db_preflight(test_database_url)
        if bool(db_preflight.get("ok", False)):
            _emit(f"{C.OK}[PASS] DB de pruebas disponible para suites DB{C.RESET}")
            _emit_obs(
                run_id,
                stage="db_preflight",
                suite="release_gate",
                status="PASS",
                detail="DB de pruebas disponible",
            )
        else:
            stage = str(db_preflight.get("stage", "init"))
            detail = str(db_preflight.get("last_error") or "Sin detalle tecnico.")
            _emit(
                f"{C.WARN}[BLOCKED] DB de pruebas no disponible para suites DB "
                f"(stage={stage}): {detail}{C.RESET}"
            )
            _emit_obs(
                run_id,
                stage="db_preflight",
                suite="release_gate",
                status="BLOCKED",
                detail=f"health_stage={stage} detail={detail}",
            )

    results: list[dict[str, object]] = []
    blocked_any = False
    failed_any = False
    timeout_any = False
    blocked_by_test_env_contract = False
    blocked_by_test_db_unavailable = False
    kpi_result: dict[str, object] = {
        "status": "SKIPPED",
        "reason": "No evaluado.",
        "mode": kpi_mode,
        "casos_total": 0,
        "failed_metrics": [],
    }
    kpi_failed = False
    security_result: dict[str, object] = {
        "status": "SKIPPED",
        "reason": "No evaluado.",
        "mode": security_mode,
        "findings": [],
    }
    security_failed = False
    performance_result: dict[str, object] = {
        "status": "SKIPPED",
        "reason": "No evaluado.",
        "mode": performance_mode,
        "findings": [],
    }
    performance_failed = False

    for suite in suites:
        if suite.requires_test_database and release_mode == RELEASE_MODE_READ_ONLY:
            reason = "Modo read_only: suite DB deshabilitada por seguridad."
            _emit(f"{C.INFO}[SKIPPED] {suite.name}: {reason}{C.RESET}")
            _emit_obs(
                run_id,
                stage="suite_decision",
                suite=suite.name,
                status="SKIPPED",
                detail=reason,
            )
            results.append({"name": suite.name, "status": "SKIPPED", "code": None, "reason": reason})
            continue

        if suite.requires_test_database and not suites_env_ok:
            reason = suites_env_reason or f"{TEST_DATABASE_URL_ENV} no configurada."
            _emit(
                f"{C.WARN}[BLOCKED] {suite.name}: {reason} "
                f"No se ejecuta y bloquea release.{C.RESET}"
            )
            _emit_obs(
                run_id,
                stage="suite_decision",
                suite=suite.name,
                status="BLOCKED",
                detail=reason,
            )
            results.append({"name": suite.name, "status": "BLOCKED", "code": None, "reason": reason})
            blocked_any = True
            blocked_by_test_env_contract = True
            continue

        if suite.requires_test_database and not bool(db_preflight.get("ok", False)):
            stage = str(db_preflight.get("stage", "init"))
            detail = str(db_preflight.get("last_error") or "Sin detalle tecnico.")
            reason = f"DB de pruebas no disponible (stage={stage}): {detail}"
            _emit(
                f"{C.WARN}[BLOCKED] {suite.name}: {reason} "
                f"No se ejecuta y bloquea release.{C.RESET}"
            )
            _emit_obs(
                run_id,
                stage="suite_decision",
                suite=suite.name,
                status="BLOCKED",
                detail=reason,
            )
            results.append({"name": suite.name, "status": "BLOCKED", "code": None, "reason": reason})
            blocked_any = True
            blocked_by_test_db_unavailable = True
            continue

        run_result = _run_suite(
            suite,
            suite_timeout_sec,
            run_id=run_id,
            env=suites_env if suite.requires_test_database else None,
        )
        status = str(run_result.get("status", "FAIL"))
        code = run_result.get("code", None)
        reason = str(run_result.get("reason", "") or "")
        duration = run_result.get("duration_sec", None)
        results.append(
            {
                "name": suite.name,
                "status": status,
                "code": code,
                "reason": reason,
                "duration_sec": duration,
            }
        )
        if status == "TIMEOUT":
            timeout_any = True
            failed_any = True
        elif status == "FAIL":
            failed_any = True

    if release_mode == RELEASE_MODE_READ_ONLY:
        reason = "Modo read_only: quality gate KPI omitido."
        _emit_obs(run_id, stage="kpi_gate", suite="quality_gate_kpi", status="SKIPPED", detail=reason)
        kpi_result = {
            "status": "SKIPPED",
            "reason": reason,
            "mode": kpi_mode,
            "casos_total": 0,
            "failed_metrics": [],
        }
    else:
        kpi_result = _evaluate_quality_gate_kpi(
            run_id=run_id,
            kpi_mode=kpi_mode,
            kpi_min_cases=kpi_min_cases,
        )
        if str(kpi_result.get("status", "")).upper() == "FAIL":
            kpi_failed = True
            failed_any = True

    security_result = _evaluate_security_gate(
        run_id=run_id,
        security_mode=security_mode,
        release_mode=release_mode,
        suites_env_ok=suites_env_ok,
        suites_env=suites_env,
    )
    if str(security_result.get("status", "")).upper() == "FAIL":
        security_failed = True
        failed_any = True

    performance_result = _evaluate_performance_gate(
        run_id=run_id,
        performance_mode=performance_mode,
    )
    if str(performance_result.get("status", "")).upper() == "FAIL":
        performance_failed = True
        failed_any = True

    _section("RESUMEN RELEASE GATE")
    for result in results:
        name = str(result.get("name", "suite"))
        status = str(result.get("status", ""))
        code = result.get("code", None)
        reason = str(result.get("reason", "") or "")
        duration = result.get("duration_sec", None)
        duration_text = f" ({duration}s)" if duration is not None else ""
        if status == "PASS":
            _emit(f"  {name:30} [{C.OK}PASS{C.RESET}]{duration_text}")
        elif status == "TIMEOUT":
            _emit(
                f"  {name:30} [{C.FAIL}TIMEOUT{C.RESET}] "
                f"{reason}{duration_text}"
            )
        elif status == "FAIL":
            _emit(f"  {name:30} [{C.FAIL}FAIL{C.RESET}] exit={code}{duration_text}")
        elif status == "SKIPPED":
            _emit(f"  {name:30} [{C.INFO}SKIPPED{C.RESET}] {reason}")
        else:
            _emit(f"  {name:30} [{C.WARN}BLOCKED{C.RESET}] {reason}")

    kpi_status = str(kpi_result.get("status", "SKIPPED")).upper()
    kpi_reason = str(kpi_result.get("reason", "") or "")
    kpi_name = "quality_gate_kpi"
    if kpi_status == "PASS":
        _emit(f"  {kpi_name:30} [{C.OK}PASS{C.RESET}] {kpi_reason}")
    elif kpi_status == "FAIL":
        _emit(f"  {kpi_name:30} [{C.FAIL}FAIL{C.RESET}] {kpi_reason}")
    elif kpi_status == "WARN":
        _emit(f"  {kpi_name:30} [{C.WARN}WARN{C.RESET}] {kpi_reason}")
    else:
        _emit(f"  {kpi_name:30} [{C.INFO}SKIPPED{C.RESET}] {kpi_reason}")

    security_status = str(security_result.get("status", "SKIPPED")).upper()
    security_reason = str(security_result.get("reason", "") or "")
    security_name = "security_gate"
    if security_status == "PASS":
        _emit(f"  {security_name:30} [{C.OK}PASS{C.RESET}] {security_reason}")
    elif security_status == "FAIL":
        _emit(f"  {security_name:30} [{C.FAIL}FAIL{C.RESET}] {security_reason}")
    elif security_status == "WARN":
        _emit(f"  {security_name:30} [{C.WARN}WARN{C.RESET}] {security_reason}")
    else:
        _emit(f"  {security_name:30} [{C.INFO}SKIPPED{C.RESET}] {security_reason}")

    performance_status = str(performance_result.get("status", "SKIPPED")).upper()
    performance_reason = str(performance_result.get("reason", "") or "")
    performance_name = "performance_gate"
    if performance_status == "PASS":
        _emit(f"  {performance_name:30} [{C.OK}PASS{C.RESET}] {performance_reason}")
    elif performance_status == "FAIL":
        _emit(f"  {performance_name:30} [{C.FAIL}FAIL{C.RESET}] {performance_reason}")
    elif performance_status == "WARN":
        _emit(f"  {performance_name:30} [{C.WARN}WARN{C.RESET}] {performance_reason}")
    else:
        _emit(f"  {performance_name:30} [{C.INFO}SKIPPED{C.RESET}] {performance_reason}")

    _emit()
    if not blocked_any and not failed_any:
        _emit_obs(
            run_id,
            stage="gate_end",
            suite="release_gate",
            status="PASS",
            detail=f"suites={len(results)}",
        )
        _emit(f"{C.OK}{C.BOLD}RELEASE QA GATE: PASS{C.RESET}")
        return 0

    if blocked_any:
        if blocked_by_test_env_contract and not blocked_by_test_db_unavailable:
            reason = (
                f"Motivo: contrato de entorno invalido para suites DB "
                f"({TEST_DATABASE_URL_ENV})."
            )
        elif blocked_by_test_db_unavailable:
            stage = str(db_preflight.get("stage", "init"))
            detail = str(db_preflight.get("last_error") or "Sin detalle tecnico.")
            reason = f"Motivo: DB de pruebas no disponible para suites DB (stage={stage}). {detail}"
        else:
            reason = "Motivo: suites DB bloqueadas por preflight."
        _emit(
            f"{C.FAIL}{C.BOLD}RELEASE QA GATE: FAIL{C.RESET}\n"
            f"{reason}"
        )
        _emit_obs(run_id, stage="gate_end", suite="release_gate", status="FAIL", detail=reason)
        return 2

    if timeout_any:
        timeout_reason = (
            "Motivo: al menos una suite excedio el timeout "
            f"(VG_SUITE_TIMEOUT_SEC={suite_timeout_sec})."
        )
        _emit(
            f"{C.FAIL}{C.BOLD}RELEASE QA GATE: FAIL{C.RESET}\n"
            f"{timeout_reason}"
        )
        _emit_obs(run_id, stage="gate_end", suite="release_gate", status="FAIL", detail=timeout_reason)
        return 1

    if kpi_failed:
        kpi_reason = str(kpi_result.get("reason", "") or "KPI operativo fuera de objetivo.")
        kpi_fail_reason = f"Motivo: quality gate KPI en FAIL. {kpi_reason}"
        _emit(
            f"{C.FAIL}{C.BOLD}RELEASE QA GATE: FAIL{C.RESET}\n"
            f"{kpi_fail_reason}"
        )
        _emit_obs(run_id, stage="gate_end", suite="release_gate", status="FAIL", detail=kpi_fail_reason)
        return 1

    if security_failed:
        security_reason = str(
            security_result.get("reason", "") or "Security gate en FAIL por desviaciones de privilegios."
        )
        security_fail_reason = f"Motivo: security gate en FAIL. {security_reason}"
        _emit(
            f"{C.FAIL}{C.BOLD}RELEASE QA GATE: FAIL{C.RESET}\n"
            f"{security_fail_reason}"
        )
        _emit_obs(run_id, stage="gate_end", suite="release_gate", status="FAIL", detail=security_fail_reason)
        return 1

    if performance_failed:
        performance_reason = str(
            performance_result.get("reason", "")
            or "Performance gate en FAIL por desviaciones de latencia/capacidad."
        )
        performance_fail_reason = f"Motivo: performance gate en FAIL. {performance_reason}"
        _emit(
            f"{C.FAIL}{C.BOLD}RELEASE QA GATE: FAIL{C.RESET}\n"
            f"{performance_fail_reason}"
        )
        _emit_obs(run_id, stage="gate_end", suite="release_gate", status="FAIL", detail=performance_fail_reason)
        return 1

    _emit_obs(run_id, stage="gate_end", suite="release_gate", status="FAIL", detail="fallo en al menos una suite")
    _emit(f"{C.FAIL}{C.BOLD}RELEASE QA GATE: FAIL{C.RESET}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
