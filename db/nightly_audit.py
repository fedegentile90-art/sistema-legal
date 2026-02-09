#!/usr/bin/env python3
"""
Auditoria diaria/nocturna con persistencia de historial y tendencia.

Uso:
  python db/nightly_audit.py
  python db/nightly_audit.py --print-json
  python db/nightly_audit.py --no-save
  python db/nightly_audit.py --source task_scheduler
  python db/nightly_audit.py --snapshot-dir db/snapshots/audit_daily --history-csv db/snapshots/audit_history.csv
"""

import argparse
import io
import json
import os
import sys
import time
import uuid
from pathlib import Path

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from audit import (  # noqa: E402
    build_daily_audit_snapshot,
    save_daily_audit_snapshot,
    append_daily_audit_history,
    load_daily_audit_history,
)
from db.health import wait_for_db  # noqa: E402
from repo import GestorCasos, get_backend_info, is_db_mode  # noqa: E402


class C:
    OK = "\033[92m"
    FAIL = "\033[91m"
    INFO = "\033[94m"
    WARN = "\033[93m"
    RESET = "\033[0m"
    BOLD = "\033[1m"

RUN_ID_ENV = "VG_RUN_ID"


def info(msg: str):
    print(f"{C.INFO}[INFO] {msg}{C.RESET}")


def ok(msg: str):
    print(f"{C.OK}[OK] {msg}{C.RESET}")


def warn(msg: str):
    print(f"{C.WARN}[WARN] {msg}{C.RESET}")


def fail(msg: str):
    print(f"{C.FAIL}[FAIL] {msg}{C.RESET}")


def _utc_now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _resolve_run_id() -> str:
    raw = str(os.environ.get(RUN_ID_ENV, "")).strip()
    if raw:
        return raw
    stamp = time.strftime("%Y%m%d%H%M%S", time.gmtime())
    return f"na-{stamp}-{uuid.uuid4().hex[:8]}"


def _emit_obs(run_id: str, stage: str, suite: str, status: str, detail: str = "") -> None:
    payload: dict[str, str] = {
        "ts": _utc_now_iso(),
        "run_id": str(run_id).strip() or "unknown",
        "stage": str(stage).strip() or "-",
        "suite": str(suite).strip() or "-",
        "status": str(status).strip() or "INFO",
    }
    if detail:
        payload["detail"] = str(detail).strip()
    print("[OBS] " + json.dumps(payload, ensure_ascii=True, sort_keys=True), flush=True)


def _preflight_db(run_id: str) -> tuple[bool, dict[str, object]]:
    health = wait_for_db(
        os.environ.get("DATABASE_URL", ""),
        attempts=3,
        backoff=0.6,
        connect_timeout=3,
    )
    if bool(health.get("ok", False)):
        ok("Preflight DB: OK")
        _emit_obs(
            run_id,
            stage="db_preflight",
            suite="nightly_audit",
            status="PASS",
            detail="DATABASE_URL reachable",
        )
        return True, health

    stage = str(health.get("stage", "init"))
    detail = str(health.get("last_error") or "Sin detalle tecnico.")
    fail(f"Preflight DB fallido (stage={stage}): {detail}")
    _emit_obs(
        run_id,
        stage="db_preflight",
        suite="nightly_audit",
        status="FAIL",
        detail=f"health_stage={stage} detail={detail}",
    )
    if not bool(health.get("dsn_set", False)):
        warn("DATABASE_URL no configurada.")
    else:
        masked = str(health.get("dsn_masked") or "")
        if masked:
            info(f"DATABASE_URL: {masked}")
    return False, health


def _print_summary(snapshot: dict):
    trend = snapshot.get("trend_point", {}) if isinstance(snapshot, dict) else {}
    generated_at = trend.get("generated_at", snapshot.get("generated_at", ""))
    print(f"\n{C.BOLD}============================================================")
    print("  NIGHTLY AUDIT - SISTEMALEGAL")
    print(f"============================================================{C.RESET}\n")

    backend = get_backend_info()
    info(f"Backend: {backend.get('mode')} ({backend.get('backend_class')})")
    info(f"Generado: {generated_at}")
    info(f"Casos auditados: {trend.get('casos', 0)}")
    info(
        "Resumen: "
        f"errores={trend.get('errores', 0)} "
        f"warnings={trend.get('warnings', 0)} "
        f"info={trend.get('info', 0)}"
    )

    ok_audit = bool(trend.get("audit_ok", False))
    (ok if ok_audit else warn)(f"Audit OK: {'SI' if ok_audit else 'NO'}")

    info(
        "KPI %: "
        f"FECHA_TAREA={trend.get('kpi_fecha_tarea_pct', 0.0)} | "
        f"EXPEDIENTE={trend.get('kpi_expediente_pct', 0.0)} | "
        f"EVENTO/FECHA_EVENTO={trend.get('kpi_evento_fecha_evento_pct', 0.0)} | "
        f"COBERTURA_FINANCIERA={trend.get('kpi_cobertura_financiera_pct', 0.0)}"
    )


def run() -> int:
    parser = argparse.ArgumentParser(description="Ejecuta auditoria diaria/nocturna y guarda tendencia")
    parser.add_argument("--source", default="nightly_cli", help="Etiqueta de origen para el historial")
    parser.add_argument("--no-save", action="store_true", help="No guarda snapshot ni historial")
    parser.add_argument("--print-json", action="store_true", help="Imprime snapshot JSON completo")
    parser.add_argument("--history-limit", type=int, default=14, help="Cantidad de dias mostrados en tendencia")
    parser.add_argument("--snapshot-dir", default="", help="Directorio de salida para snapshots JSON")
    parser.add_argument("--history-csv", default="", help="Ruta CSV para historial de tendencia")
    args = parser.parse_args()
    run_id = _resolve_run_id()
    os.environ[RUN_ID_ENV] = run_id
    info(f"Run ID: {run_id} (env {RUN_ID_ENV})")
    _emit_obs(
        run_id,
        stage="nightly_start",
        suite="nightly_audit",
        status="RUN",
        detail=f"source={args.source}",
    )

    if is_db_mode():
        preflight_ok, _ = _preflight_db(run_id=run_id)
        if not preflight_ok:
            _emit_obs(
                run_id,
                stage="nightly_end",
                suite="nightly_audit",
                status="FAIL",
                detail="db_preflight_failed",
            )
            return 2

    try:
        gestor = GestorCasos()
        casos = gestor.escanear_casos()
    except Exception as e:
        fail(f"No se pudieron cargar casos: {e}")
        _emit_obs(
            run_id,
            stage="load_cases",
            suite="nightly_audit",
            status="FAIL",
            detail=f"{type(e).__name__}: {e}",
        )
        _emit_obs(run_id, stage="nightly_end", suite="nightly_audit", status="FAIL", detail="load_cases_failed")
        return 1
    _emit_obs(
        run_id,
        stage="load_cases",
        suite="nightly_audit",
        status="PASS",
        detail=f"casos={len(casos)}",
    )

    try:
        snapshot = build_daily_audit_snapshot(gestor, casos, source=args.source)
    except Exception as e:
        fail(f"No se pudo construir snapshot de auditoria: {e}")
        _emit_obs(
            run_id,
            stage="build_snapshot",
            suite="nightly_audit",
            status="FAIL",
            detail=f"{type(e).__name__}: {e}",
        )
        _emit_obs(run_id, stage="nightly_end", suite="nightly_audit", status="FAIL", detail="build_snapshot_failed")
        return 1
    _emit_obs(run_id, stage="build_snapshot", suite="nightly_audit", status="PASS")

    _print_summary(snapshot)

    if args.print_json:
        print("\nJSON:\n")
        print(json.dumps(snapshot, ensure_ascii=False, indent=2))

    snapshot_dir = Path(args.snapshot_dir) if args.snapshot_dir else None
    history_csv = Path(args.history_csv) if args.history_csv else None
    history_path = history_csv

    if not args.no_save:
        try:
            saved_path = save_daily_audit_snapshot(snapshot, output_dir=snapshot_dir)
            history_path = append_daily_audit_history(snapshot, history_path=history_csv)
        except Exception as e:
            fail(f"No se pudo guardar auditoria diaria: {e}")
            _emit_obs(
                run_id,
                stage="persist_snapshot",
                suite="nightly_audit",
                status="FAIL",
                detail=f"{type(e).__name__}: {e}",
            )
            _emit_obs(run_id, stage="nightly_end", suite="nightly_audit", status="FAIL", detail="persist_failed")
            return 1

        ok(f"Snapshot diario: {saved_path}")
        ok(f"Historial tendencia: {history_path}")
        _emit_obs(
            run_id,
            stage="persist_snapshot",
            suite="nightly_audit",
            status="PASS",
            detail=f"snapshot={saved_path}",
        )
    else:
        warn("Ejecucion sin persistencia (--no-save)")
        _emit_obs(
            run_id,
            stage="persist_snapshot",
            suite="nightly_audit",
            status="SKIPPED",
            detail="--no-save",
        )

    try:
        history = load_daily_audit_history(history_path=history_csv, limit=max(0, int(args.history_limit)))
    except Exception as e:
        warn(f"No se pudo leer historial de tendencia: {e}")
        history = []

    if history:
        print("\nTendencia (ultimos dias):")
        for row in history:
            print(
                f"  {row.get('date')} | "
                f"E={row.get('errores', 0)} W={row.get('warnings', 0)} I={row.get('info', 0)} | "
                f"FT={row.get('kpi_fecha_tarea_pct', 0.0)}% "
                f"EXP={row.get('kpi_expediente_pct', 0.0)}%"
            )
    else:
        warn("No hay historial de tendencia disponible todavia.")
    _emit_obs(
        run_id,
        stage="history",
        suite="nightly_audit",
        status="PASS",
        detail=f"rows={len(history)}",
    )
    _emit_obs(run_id, stage="nightly_end", suite="nightly_audit", status="PASS")

    return 0


if __name__ == "__main__":
    raise SystemExit(run())
