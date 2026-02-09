#!/usr/bin/env python3
"""
Snapshot KPI operativo para seguimiento P0/P1.

Uso:
  python db/kpi_snapshot.py
  python db/kpi_snapshot.py --no-save
  python db/kpi_snapshot.py --print-json
  python db/kpi_snapshot.py --json-out db/snapshots/mi_snapshot.json --csv-out db/snapshots/mi_snapshot.csv
"""

import argparse
import csv
import json
import sys
import io
from datetime import datetime
from pathlib import Path

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from audit import build_operational_kpi_snapshot  # noqa: E402
from repo import GestorCasos, get_backend_info, is_db_mode  # noqa: E402


class C:
    OK = "\033[92m"
    FAIL = "\033[91m"
    INFO = "\033[94m"
    WARN = "\033[93m"
    RESET = "\033[0m"
    BOLD = "\033[1m"


def info(msg: str):
    print(f"{C.INFO}[INFO] {msg}{C.RESET}")


def ok(msg: str):
    print(f"{C.OK}[OK] {msg}{C.RESET}")


def warn(msg: str):
    print(f"{C.WARN}[WARN] {msg}{C.RESET}")


def fail(msg: str):
    print(f"{C.FAIL}[FAIL] {msg}{C.RESET}")


def _default_output_paths() -> tuple[Path, Path]:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    base = ROOT / "db" / "snapshots"
    return base / f"kpi_snapshot_{ts}.json", base / f"kpi_snapshot_{ts}.csv"


def _save_json(path: Path, payload: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _save_csv(path: Path, payload: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    for metric_name, data in (payload.get("kpis") or {}).items():
        rows.append({
            "generated_at": payload.get("generated_at", ""),
            "casos_total": payload.get("casos_total", 0),
            "metric": metric_name,
            "completed": data.get("completed", 0),
            "total": data.get("total", 0),
            "pct": data.get("pct", 0.0),
            "target_pct": data.get("target_pct", 0.0),
            "gap_pct": data.get("gap_pct", 0.0),
            "goal_met": data.get("goal_met", False),
        })

    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "generated_at",
                "casos_total",
                "metric",
                "completed",
                "total",
                "pct",
                "target_pct",
                "gap_pct",
                "goal_met",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)


def _print_summary(snapshot: dict):
    print(f"\n{C.BOLD}============================================================")
    print("  KPI SNAPSHOT - SISTEMALEGAL")
    print(f"============================================================{C.RESET}\n")

    backend = get_backend_info()
    info(f"Backend: {backend.get('mode')} ({backend.get('backend_class')})")
    info(f"Casos evaluados: {snapshot.get('casos_total', 0)}")
    info(f"Generado: {snapshot.get('generated_at')}")

    print("\nMétricas objetivo:")
    for metric_name, metric in (snapshot.get("kpis") or {}).items():
        status = ok if metric.get("goal_met") else warn
        status(
            f"{metric_name}: {metric.get('pct', 0.0)}% "
            f"({metric.get('completed', 0)}/{metric.get('total', 0)}) "
            f"| objetivo {metric.get('target_pct', 0.0)}% "
            f"| gap {metric.get('gap_pct', 0.0)}"
        )


def run() -> int:
    parser = argparse.ArgumentParser(description="Genera snapshot KPI operativo")
    parser.add_argument("--no-save", action="store_true", help="No guarda archivos en disco")
    parser.add_argument("--print-json", action="store_true", help="Imprime JSON completo en stdout")
    parser.add_argument("--json-out", default="", help="Ruta de salida para JSON")
    parser.add_argument("--csv-out", default="", help="Ruta de salida para CSV")
    args = parser.parse_args()

    try:
        gestor = GestorCasos()
        casos = gestor.escanear_casos()
    except Exception as e:
        fail(f"No se pudo cargar casos: {e}")
        return 1

    snapshot = build_operational_kpi_snapshot(gestor, casos)
    _print_summary(snapshot)

    if args.print_json:
        print("\nJSON:\n")
        print(json.dumps(snapshot, ensure_ascii=False, indent=2))

    if not args.no_save:
        default_json, default_csv = _default_output_paths()
        json_path = Path(args.json_out) if args.json_out else default_json
        csv_path = Path(args.csv_out) if args.csv_out else default_csv

        try:
            _save_json(json_path, snapshot)
            _save_csv(csv_path, snapshot)
        except Exception as e:
            fail(f"No se pudo guardar snapshot: {e}")
            return 1

        ok(f"Snapshot JSON: {json_path}")
        ok(f"Snapshot CSV:  {csv_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(run())
