"""
Auditoria integral del sistema.
"""

import csv
import json
import logging
import platform
import time
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

import config as _config
from config import CAMPOS_FINANCIEROS, RE_INVALID_WIN, SUBCARPETAS_ESTANDAR
from domain import Caso, case_status, is_blank
from repo import GestorCasos, is_db_mode, is_db_path

logger = logging.getLogger(__name__)
ANOS_ACTIVOS = getattr(_config, "AÑOS_ACTIVOS", getattr(_config, "AÃ‘OS_ACTIVOS", []))


def _utc_now_iso() -> str:
    """Timestamp UTC estable en ISO-8601 con sufijo Z."""
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

DEFAULT_INCOMPLETE_FIELDS = (
    "FECHA_TAREA",
    "TAREA_PENDIENTE",
    "EXPEDIENTE",
    "EVENTO",
    "FECHA_EVENTO",
    "RESPONSABLE",
)

DEFAULT_INCOMPLETE_WEIGHTS = {
    "RESPONSABLE": 6,
    "FECHA_TAREA": 5,
    "TAREA_PENDIENTE": 4,
    "EXPEDIENTE": 4,
    "EVENTO": 3,
    "FECHA_EVENTO": 3,
}

AUDIT_SNAPSHOT_DIR = Path(__file__).resolve().parent / "db" / "snapshots" / "audit_daily"
AUDIT_HISTORY_CSV = Path(__file__).resolve().parent / "db" / "snapshots" / "audit_history.csv"
AUDIT_HISTORY_COLUMNS = (
    "generated_at",
    "date",
    "source",
    "audit_ok",
    "errores",
    "warnings",
    "info",
    "casos",
    "kpi_fecha_tarea_pct",
    "kpi_expediente_pct",
    "kpi_evento_fecha_evento_pct",
    "kpi_cobertura_financiera_pct",
)


@dataclass
class Hallazgo:
    nivel: str          # "ERROR" | "WARN" | "INFO"
    codigo: str         # Ej: "FS-001"
    mensaje: str
    ruta: str = ""
    sugerencia: str = ""


def _safe_len_path(p: Path) -> int:
    try:
        return len(str(p))
    except Exception:
        return 0


def _get_case_field_value(caso: Caso, field: str):
    attr = str(field or "").lower()
    if hasattr(caso, attr):
        return getattr(caso, attr)
    if isinstance(caso, dict):
        return caso.get(field) or caso.get(attr)
    return None


def build_incomplete_case_queue(
    casos: List[Caso],
    top_n: int = 10,
    focus_fields: List[str] | None = None,
) -> List[Dict[str, object]]:
    """
    Ranking reusable de casos incompletos para campaÃ±a operativa.

    Output keys por fila:
      - case_ref
      - cliente
      - causa
      - missing_fields
      - missing_count
      - score
    """
    fields = [f for f in (focus_fields or list(DEFAULT_INCOMPLETE_FIELDS)) if str(f or "").strip()]
    if not fields:
        return []

    rows: List[Dict[str, object]] = []
    for caso in casos or []:
        missing_fields: List[str] = []
        for field in fields:
            if is_blank(_get_case_field_value(caso, field)):
                missing_fields.append(field)

        if not missing_fields:
            continue

        status_info = case_status(caso)
        score = sum(DEFAULT_INCOMPLETE_WEIGHTS.get(field, 1) for field in missing_fields)
        if status_info.get("missing_minimum"):
            score += 3

        rows.append({
            "case_ref": str(getattr(caso, "ruta", "")),
            "cliente": str(getattr(caso, "cliente", "") or ""),
            "causa": str(getattr(caso, "causa", "") or ""),
            "missing_fields": missing_fields,
            "missing_count": len(missing_fields),
            "score": score,
            "status": status_info.get("status", "ok"),
        })

    rows.sort(
        key=lambda item: (
            -int(item.get("score", 0)),
            -int(item.get("missing_count", 0)),
            str(item.get("cliente", "")).upper(),
            str(item.get("causa", "")).upper(),
        )
    )

    limit = max(0, int(top_n))
    if limit == 0:
        return []
    return rows[:limit]


def build_operational_kpi_snapshot(gestor: GestorCasos, casos: List[Caso]) -> Dict[str, Any]:
    """
    Snapshot operativo para seguimiento P0/P1.
    KPI objetivo:
      - FECHA_TAREA > 60%
      - EXPEDIENTE > 70%
      - EVENTO/FECHA_EVENTO > 40%
      - Cobertura financiera >= 70%
    """
    total = max(0, len(casos or []))

    def _pct(completed: int, base: int) -> float:
        if base <= 0:
            return 0.0
        return round((completed / base) * 100, 1)

    fecha_tarea_ok = 0
    expediente_ok = 0
    evento_fecha_ok = 0
    fin_ok = 0
    fin_by_case = _build_financial_map(gestor, casos or [])

    for caso in casos or []:
        if not is_blank(getattr(caso, "fecha_tarea", "")):
            fecha_tarea_ok += 1
        if not is_blank(getattr(caso, "expediente", "")):
            expediente_ok += 1
        evento_val = getattr(caso, "evento", "")
        fecha_evento_val = getattr(caso, "fecha_evento", "")
        if (not is_blank(evento_val)) and (not is_blank(fecha_evento_val)):
            evento_fecha_ok += 1

        fin_data = fin_by_case.get(str(caso.ruta), {})
        if any(not is_blank(fin_data.get(field, "")) for field in CAMPOS_FINANCIEROS):
            fin_ok += 1

    kpis = {
        "FECHA_TAREA": {
            "completed": fecha_tarea_ok,
            "total": total,
            "pct": _pct(fecha_tarea_ok, total),
            "target_pct": 60.0,
        },
        "EXPEDIENTE": {
            "completed": expediente_ok,
            "total": total,
            "pct": _pct(expediente_ok, total),
            "target_pct": 70.0,
        },
        "EVENTO_FECHA_EVENTO": {
            "completed": evento_fecha_ok,
            "total": total,
            "pct": _pct(evento_fecha_ok, total),
            "target_pct": 40.0,
        },
        "COBERTURA_FINANCIERA": {
            "completed": fin_ok,
            "total": total,
            "pct": _pct(fin_ok, total),
            "target_pct": 70.0,
        },
    }

    for metric in kpis.values():
        metric["goal_met"] = bool(metric["pct"] >= metric["target_pct"])
        metric["gap_pct"] = round(metric["pct"] - metric["target_pct"], 1)

    return {
        "generated_at": _utc_now_iso(),
        "casos_total": total,
        "kpis": kpis,
    }


def _normalize_financial_row(raw: Dict[str, object] | None) -> Dict[str, str]:
    payload = raw if isinstance(raw, dict) else {}
    return {field: str(payload.get(field, "") or "") for field in CAMPOS_FINANCIEROS}


def _build_financial_map(gestor: GestorCasos, casos: List[Caso]) -> Dict[str, Dict[str, str]]:
    out: Dict[str, Dict[str, str]] = {}
    rutas = [getattr(c, "ruta", None) for c in (casos or []) if getattr(c, "ruta", None) is not None]
    batch_data: Dict[str, Dict[str, str]] = {}

    if hasattr(gestor, "leer_datos_financieros_batch") and rutas:
        try:
            raw_batch = gestor.leer_datos_financieros_batch(rutas) or {}
            if isinstance(raw_batch, dict):
                batch_data = {str(k): _normalize_financial_row(v) for k, v in raw_batch.items()}
        except Exception as exc:
            logger.warning("audit financial batch read failed, fallback single-case mode: %s", exc)
            batch_data = {}

    fallback_errors = 0
    first_error: Exception | None = None
    for caso in casos or []:
        ref = str(caso.ruta)
        if ref in batch_data:
            out[ref] = _normalize_financial_row(batch_data.get(ref))
            continue

        fin_data: Dict[str, object] = {}
        if hasattr(gestor, "leer_datos_financieros"):
            try:
                raw_single = gestor.leer_datos_financieros(caso.ruta) or {}
                if isinstance(raw_single, dict):
                    fin_data = raw_single
            except Exception as exc:
                fallback_errors += 1
                if first_error is None:
                    first_error = exc
        out[ref] = _normalize_financial_row(fin_data)

    if fallback_errors:
        logger.warning(
            "audit financial fallback had %s error(s); first=%s",
            fallback_errors,
            first_error,
        )

    return out


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return int(default)


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def _kpi_pct(kpi_snapshot: Dict[str, Any], metric_key: str) -> float:
    kpis = (kpi_snapshot or {}).get("kpis", {}) if isinstance(kpi_snapshot, dict) else {}
    metric = kpis.get(metric_key, {}) if isinstance(kpis, dict) else {}
    return round(_safe_float(metric.get("pct", 0.0), 0.0), 1)


def _normalize_generated_at(value: str) -> str:
    raw = str(value or "").strip()
    if raw:
        return raw
    return _utc_now_iso()


def _generated_at_to_date(generated_at: str) -> str:
    raw = str(generated_at or "").strip()
    if not raw:
        return datetime.now().strftime("%Y-%m-%d")
    if "T" in raw:
        return raw.split("T", 1)[0]
    return raw[:10]


def _snapshot_filename(generated_at: str) -> str:
    raw = _normalize_generated_at(generated_at)
    token = (
        raw.replace("-", "")
        .replace(":", "")
        .replace("T", "_")
        .replace(".", "")
        .replace("Z", "")
        .replace("+", "")
    )
    return f"audit_snapshot_{token}.json"


def _build_trend_point(
    generated_at: str,
    source: str,
    audit_report: Dict[str, Any],
    kpi_snapshot: Dict[str, Any],
) -> Dict[str, Any]:
    resumen = (audit_report or {}).get("resumen", {}) if isinstance(audit_report, dict) else {}
    return {
        "generated_at": _normalize_generated_at(generated_at),
        "date": _generated_at_to_date(generated_at),
        "source": str(source or "manual"),
        "audit_ok": bool((audit_report or {}).get("ok", False)),
        "errores": _safe_int(resumen.get("errores", 0), 0),
        "warnings": _safe_int(resumen.get("warnings", 0), 0),
        "info": _safe_int(resumen.get("info", 0), 0),
        "casos": _safe_int(resumen.get("casos", 0), 0),
        "kpi_fecha_tarea_pct": _kpi_pct(kpi_snapshot, "FECHA_TAREA"),
        "kpi_expediente_pct": _kpi_pct(kpi_snapshot, "EXPEDIENTE"),
        "kpi_evento_fecha_evento_pct": _kpi_pct(kpi_snapshot, "EVENTO_FECHA_EVENTO"),
        "kpi_cobertura_financiera_pct": _kpi_pct(kpi_snapshot, "COBERTURA_FINANCIERA"),
    }


def build_daily_audit_snapshot(
    gestor: GestorCasos,
    casos: List[Caso],
    source: str = "manual",
    audit_report: Dict[str, Any] | None = None,
    kpi_snapshot: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """
    Genera un snapshot diario con:
      - resultado de auditoria integral,
      - KPI operativo,
      - punto de tendencia (errores/warnings + KPI).
    """
    report = audit_report if isinstance(audit_report, dict) else auditar_app(gestor, casos)
    kpi = kpi_snapshot if isinstance(kpi_snapshot, dict) else build_operational_kpi_snapshot(gestor, casos)
    generated_at = _normalize_generated_at((kpi or {}).get("generated_at", ""))
    trend_point = _build_trend_point(generated_at, source, report, kpi)

    return {
        "generated_at": generated_at,
        "date": _generated_at_to_date(generated_at),
        "source": str(source or "manual"),
        "backend_mode": "database" if is_db_mode() else "filesystem",
        "audit_report": report,
        "kpi_snapshot": kpi,
        "trend_point": trend_point,
    }


def save_daily_audit_snapshot(
    snapshot: Dict[str, Any],
    output_dir: Path | None = None,
    update_latest: bool = True,
) -> Path:
    target_dir = Path(output_dir) if output_dir else AUDIT_SNAPSHOT_DIR
    target_dir.mkdir(parents=True, exist_ok=True)

    generated_at = _normalize_generated_at((snapshot or {}).get("generated_at", ""))
    target = target_dir / _snapshot_filename(generated_at)
    payload = json.dumps(snapshot or {}, ensure_ascii=False, indent=2)
    target.write_text(payload, encoding="utf-8")

    if update_latest:
        (target_dir / "audit_snapshot_latest.json").write_text(payload, encoding="utf-8")

    return target


def append_daily_audit_history(
    snapshot: Dict[str, Any],
    history_path: Path | None = None,
) -> Path:
    target = Path(history_path) if history_path else AUDIT_HISTORY_CSV
    target.parent.mkdir(parents=True, exist_ok=True)

    trend = (snapshot or {}).get("trend_point", {}) if isinstance(snapshot, dict) else {}
    generated_at = _normalize_generated_at(trend.get("generated_at", ""))
    row = {
        "generated_at": generated_at,
        "date": str(trend.get("date") or _generated_at_to_date(generated_at)),
        "source": str(trend.get("source") or (snapshot or {}).get("source") or "manual"),
        "audit_ok": "1" if bool(trend.get("audit_ok", False)) else "0",
        "errores": _safe_int(trend.get("errores", 0), 0),
        "warnings": _safe_int(trend.get("warnings", 0), 0),
        "info": _safe_int(trend.get("info", 0), 0),
        "casos": _safe_int(trend.get("casos", 0), 0),
        "kpi_fecha_tarea_pct": round(_safe_float(trend.get("kpi_fecha_tarea_pct", 0.0), 0.0), 1),
        "kpi_expediente_pct": round(_safe_float(trend.get("kpi_expediente_pct", 0.0), 0.0), 1),
        "kpi_evento_fecha_evento_pct": round(_safe_float(trend.get("kpi_evento_fecha_evento_pct", 0.0), 0.0), 1),
        "kpi_cobertura_financiera_pct": round(_safe_float(trend.get("kpi_cobertura_financiera_pct", 0.0), 0.0), 1),
    }

    existing_generated_at = set()
    if target.exists():
        with target.open("r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for item in reader:
                token = str((item or {}).get("generated_at", "")).strip()
                if token:
                    existing_generated_at.add(token)

    if row["generated_at"] in existing_generated_at:
        return target

    write_header = (not target.exists()) or target.stat().st_size == 0
    with target.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(AUDIT_HISTORY_COLUMNS))
        if write_header:
            writer.writeheader()
        writer.writerow(row)

    return target


def load_daily_audit_history(
    history_path: Path | None = None,
    limit: int = 30,
    collapse_by_date: bool = True,
) -> List[Dict[str, Any]]:
    target = Path(history_path) if history_path else AUDIT_HISTORY_CSV
    if not target.exists():
        return []

    rows: List[Dict[str, Any]] = []
    with target.open("r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for item in reader:
            generated_at = _normalize_generated_at((item or {}).get("generated_at", ""))
            row = {
                "generated_at": generated_at,
                "date": str((item or {}).get("date") or _generated_at_to_date(generated_at)),
                "source": str((item or {}).get("source") or "manual"),
                "audit_ok": str((item or {}).get("audit_ok", "0")).strip().lower() in ("1", "true", "yes"),
                "errores": _safe_int((item or {}).get("errores", 0), 0),
                "warnings": _safe_int((item or {}).get("warnings", 0), 0),
                "info": _safe_int((item or {}).get("info", 0), 0),
                "casos": _safe_int((item or {}).get("casos", 0), 0),
                "kpi_fecha_tarea_pct": round(_safe_float((item or {}).get("kpi_fecha_tarea_pct", 0.0), 0.0), 1),
                "kpi_expediente_pct": round(_safe_float((item or {}).get("kpi_expediente_pct", 0.0), 0.0), 1),
                "kpi_evento_fecha_evento_pct": round(_safe_float((item or {}).get("kpi_evento_fecha_evento_pct", 0.0), 0.0), 1),
                "kpi_cobertura_financiera_pct": round(_safe_float((item or {}).get("kpi_cobertura_financiera_pct", 0.0), 0.0), 1),
            }
            rows.append(row)

    rows.sort(key=lambda r: str(r.get("generated_at", "")))

    if collapse_by_date:
        collapsed: Dict[str, Dict[str, Any]] = {}
        for row in rows:
            collapsed[str(row.get("date", ""))] = row
        rows = sorted(collapsed.values(), key=lambda r: str(r.get("generated_at", "")))

    max_items = max(0, int(limit))
    if max_items == 0:
        return rows
    return rows[-max_items:]


def build_trend_degradation_alert(
    trend_rows: List[Dict[str, Any]],
    baseline_days: int = 7,
) -> Dict[str, Any]:
    """
    Detecta degradacion de calidad comparando el ultimo dia contra
    promedio de los dias previos.

    Reglas:
    - baseline = promedio de errores/warnings de los N dias previos.
    - hay degradacion si errores o warnings del ultimo dia > baseline.
    - severidad:
      - critica: salto fuerte (ratio >= 2.0 o delta alto).
      - moderada: incremento medio (ratio >= 1.5 o delta medio).
      - leve: cualquier incremento por encima del baseline.
    """
    rows = list(trend_rows or [])
    if len(rows) < 2:
        return {
            "ready": False,
            "show_alert": False,
            "severity": "",
            "message": "",
            "suggested_actions": [],
            "current": {},
            "baseline": {},
            "delta": {},
        }

    rows.sort(key=lambda item: str((item or {}).get("date", "")))
    current = rows[-1]
    window_size = max(1, int(baseline_days))
    baseline_rows = rows[-(window_size + 1):-1]
    if not baseline_rows:
        return {
            "ready": False,
            "show_alert": False,
            "severity": "",
            "message": "",
            "suggested_actions": [],
            "current": {},
            "baseline": {},
            "delta": {},
        }

    curr_errors = _safe_int((current or {}).get("errores", 0), 0)
    curr_warnings = _safe_int((current or {}).get("warnings", 0), 0)

    baseline_errors = round(
        sum(_safe_int((row or {}).get("errores", 0), 0) for row in baseline_rows) / len(baseline_rows),
        1,
    )
    baseline_warnings = round(
        sum(_safe_int((row or {}).get("warnings", 0), 0) for row in baseline_rows) / len(baseline_rows),
        1,
    )

    delta_errors = round(curr_errors - baseline_errors, 1)
    delta_warnings = round(curr_warnings - baseline_warnings, 1)
    worsened = (delta_errors > 0) or (delta_warnings > 0)

    def _ratio(current_value: float, baseline_value: float) -> float:
        if baseline_value <= 0:
            return 9.0 if current_value > 0 else 1.0
        return float(current_value) / float(baseline_value)

    ratio_errors = _ratio(curr_errors, baseline_errors)
    ratio_warnings = _ratio(curr_warnings, baseline_warnings)
    worst_ratio = max(ratio_errors, ratio_warnings)

    if not worsened:
        return {
            "ready": True,
            "show_alert": False,
            "severity": "ok",
            "message": "",
            "suggested_actions": [],
            "current": {"date": str((current or {}).get("date", "")), "errores": curr_errors, "warnings": curr_warnings},
            "baseline": {
                "days": len(baseline_rows),
                "errores_avg": baseline_errors,
                "warnings_avg": baseline_warnings,
            },
            "delta": {"errores": delta_errors, "warnings": delta_warnings},
        }

    severity = "leve"
    if worst_ratio >= 2.0 or delta_errors >= 3 or delta_warnings >= 10:
        severity = "critica"
    elif worst_ratio >= 1.5 or delta_errors >= 2 or delta_warnings >= 5:
        severity = "moderada"

    suggestions_map = {
        "leve": [
            "Revisar los hallazgos nuevos del dia y asignar responsable.",
            "Verificar casos modificados en las ultimas 24h.",
        ],
        "moderada": [
            "Priorizar correccion de codigos mas repetidos (top WARN/ERROR).",
            "Ejecutar campana focalizada sobre casos con datos minimos faltantes.",
        ],
        "critica": [
            "Activar contencion operativa: bloquear cambios no urgentes hasta estabilizar.",
            "Ejecutar triage inmediato de hallazgos ERROR y validar release gate al cierre.",
        ],
    }

    current_date = str((current or {}).get("date", ""))
    message = (
        f"Degradacion {severity}: {current_date} vs promedio ultimos {len(baseline_rows)} dias. "
        f"Errores {curr_errors} (baseline {baseline_errors}), "
        f"warnings {curr_warnings} (baseline {baseline_warnings})."
    )

    return {
        "ready": True,
        "show_alert": True,
        "severity": severity,
        "message": message,
        "suggested_actions": suggestions_map.get(severity, []),
        "current": {"date": current_date, "errores": curr_errors, "warnings": curr_warnings},
        "baseline": {
            "days": len(baseline_rows),
            "errores_avg": baseline_errors,
            "warnings_avg": baseline_warnings,
        },
        "delta": {"errores": delta_errors, "warnings": delta_warnings},
        "ratio": {"errores": round(ratio_errors, 2), "warnings": round(ratio_warnings, 2)},
    }


def load_daily_audit_snapshots(
    snapshot_dir: Path | None = None,
    limit: int = 30,
) -> List[Dict[str, Any]]:
    """
    Carga snapshots JSON de auditoria diaria desde disco.
    """
    target_dir = Path(snapshot_dir) if snapshot_dir else AUDIT_SNAPSHOT_DIR
    if not target_dir.exists():
        return []

    files = [
        p for p in target_dir.glob("audit_snapshot_*.json")
        if p.is_file() and p.name != "audit_snapshot_latest.json"
    ]
    files.sort(key=lambda p: p.name)

    max_items = max(0, int(limit))
    if max_items > 0:
        files = files[-max_items:]

    snapshots: List[Dict[str, Any]] = []
    for path in files:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(payload, dict):
            continue

        generated_at = _normalize_generated_at(payload.get("generated_at", ""))
        payload["_snapshot_path"] = str(path)
        payload["_snapshot_generated_at"] = generated_at
        payload["_snapshot_date"] = str(payload.get("date") or _generated_at_to_date(generated_at))
        snapshots.append(payload)

    snapshots.sort(key=lambda item: str(item.get("_snapshot_generated_at", "")))
    return snapshots


def build_operational_hallazgos_rows(snapshots: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Convierte snapshots diarios en filas operativas de hallazgos exportables.
    """
    rows: List[Dict[str, Any]] = []

    for snapshot in snapshots or []:
        if not isinstance(snapshot, dict):
            continue

        generated_at = _normalize_generated_at(snapshot.get("_snapshot_generated_at") or snapshot.get("generated_at", ""))
        snapshot_date = str(snapshot.get("_snapshot_date") or snapshot.get("date") or _generated_at_to_date(generated_at))
        source = str(snapshot.get("source") or "manual")
        backend_mode = str(snapshot.get("backend_mode") or "")
        snapshot_path = str(snapshot.get("_snapshot_path") or "")

        report = snapshot.get("audit_report", {})
        if not isinstance(report, dict):
            report = {}
        resumen = report.get("resumen", {})
        if not isinstance(resumen, dict):
            resumen = {}

        hallazgos = report.get("hallazgos", [])
        if not isinstance(hallazgos, list):
            hallazgos = []

        for hallazgo in hallazgos:
            if not isinstance(hallazgo, dict):
                continue
            rows.append({
                "date": snapshot_date,
                "generated_at": generated_at,
                "source": source,
                "backend_mode": backend_mode,
                "snapshot_path": snapshot_path,
                "audit_ok": bool(report.get("ok", False)),
                "errores_total": _safe_int(resumen.get("errores", 0), 0),
                "warnings_total": _safe_int(resumen.get("warnings", 0), 0),
                "info_total": _safe_int(resumen.get("info", 0), 0),
                "casos_total": _safe_int(resumen.get("casos", 0), 0),
                "nivel": str(hallazgo.get("nivel", "")),
                "codigo": str(hallazgo.get("codigo", "")),
                "mensaje": str(hallazgo.get("mensaje", "")),
                "ruta": str(hallazgo.get("ruta", "")),
                "sugerencia": str(hallazgo.get("sugerencia", "")),
            })

    rows.sort(
        key=lambda item: (
            str(item.get("date", "")),
            str(item.get("generated_at", "")),
            str(item.get("nivel", "")),
            str(item.get("codigo", "")),
        )
    )
    return rows


def _parse_yyyy_mm_dd(value: Any) -> date | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        return datetime.strptime(raw[:10], "%Y-%m-%d").date()
    except Exception:
        return None


def filter_operational_hallazgos(
    rows: List[Dict[str, Any]],
    level: str = "Todos",
    code_query: str = "",
    date_from: str = "",
    date_to: str = "",
) -> List[Dict[str, Any]]:
    """
    Aplica filtros operativos de export:
      - nivel (ERROR/WARN/INFO),
      - codigo (substring),
      - rango de fechas [date_from, date_to].
    """
    selected_level = str(level or "Todos").strip().upper()
    query = str(code_query or "").strip().upper()
    from_date = _parse_yyyy_mm_dd(date_from)
    to_date = _parse_yyyy_mm_dd(date_to)

    out: List[Dict[str, Any]] = []
    for row in rows or []:
        if not isinstance(row, dict):
            continue

        row_level = str(row.get("nivel", "")).strip().upper()
        if selected_level not in ("", "TODOS") and row_level != selected_level:
            continue

        if query and query not in str(row.get("codigo", "")).upper():
            continue

        row_date = _parse_yyyy_mm_dd(row.get("date", ""))
        if from_date and row_date and row_date < from_date:
            continue
        if to_date and row_date and row_date > to_date:
            continue

        out.append(row)

    return out


def build_operational_hallazgos_export_payload(
    rows: List[Dict[str, Any]],
    filters: Dict[str, Any] | None = None,
    snapshots_count: int = 0,
) -> Dict[str, Any]:
    """
    Arma payload JSON exportable con metadata de snapshot/backend.
    """
    rows_list = list(rows or [])
    backend_modes = sorted({str(r.get("backend_mode", "")).strip() for r in rows_list if str(r.get("backend_mode", "")).strip()})
    dates = sorted({str(r.get("date", "")).strip() for r in rows_list if str(r.get("date", "")).strip()})

    return {
        "generated_at": _utc_now_iso(),
        "filters": dict(filters or {}),
        "summary": {
            "rows": len(rows_list),
            "snapshots": int(max(0, snapshots_count)),
            "backend_modes": backend_modes,
            "date_min": dates[0] if dates else "",
            "date_max": dates[-1] if dates else "",
        },
        "records": rows_list,
    }


def ensure_daily_audit_snapshot(
    gestor: GestorCasos,
    casos: List[Caso],
    source: str = "auto_daily",
) -> Dict[str, Any]:
    today = datetime.now().strftime("%Y-%m-%d")
    history = load_daily_audit_history(limit=400, collapse_by_date=True)

    if any(str(item.get("date", "")) == today for item in history):
        return {
            "created": False,
            "date": today,
            "snapshot_path": "",
            "history_path": str(AUDIT_HISTORY_CSV),
        }

    snapshot = build_daily_audit_snapshot(gestor, casos, source=source)
    snapshot_path = save_daily_audit_snapshot(snapshot)
    history_path = append_daily_audit_history(snapshot)
    return {
        "created": True,
        "date": today,
        "snapshot_path": str(snapshot_path),
        "history_path": str(history_path),
        "snapshot": snapshot,
    }


def auditar_app(gestor: GestorCasos, casos: List[Caso]) -> Dict:
    """
    AuditorÃ­a integral: estructura, datos, coherencia y riesgos tÃ­picos en Windows/OneDrive.
    Devuelve dict con resumen + hallazgos + mÃ©tricas de completitud.
    """
    t0 = time.time()
    hallazgos: List[Hallazgo] = []

    # --- Contexto del entorno (INFO)
    hallazgos.append(Hallazgo(
        nivel="INFO",
        codigo="CTX-001",
        mensaje=f"Entorno: {platform.system()} {platform.release()} | Python: {platform.python_version()}",
        ruta=str(gestor.ruta_base),
        sugerencia="â€”"
    ))

    # --- Test 1: ruta base accesible (solo filesystem)
    if not is_db_mode() and not gestor.ruta_base.exists():
        hallazgos.append(Hallazgo(
            nivel="ERROR",
            codigo="FS-001",
            mensaje="La ruta base no existe o no es accesible.",
            ruta=str(gestor.ruta_base),
            sugerencia="Verificar existencia, permisos y que no sea una ruta 'movida' por el sistema."
        ))
        return {
            "ok": False,
            "resumen": {"errores": 1, "warnings": 0, "info": 1, "casos": len(casos)},
            "hallazgos": [asdict(h) for h in hallazgos],
            "metricas": {}
        }

    # --- Test 2: años activos existen (solo filesystem)
    if not is_db_mode():
        for año in ANOS_ACTIVOS:
            ra = gestor.ruta_base / año
            if not ra.exists():
                hallazgos.append(Hallazgo(
                    nivel="WARN",
                    codigo="FS-010",
                    mensaje=f"Año activo configurado pero carpeta inexistente: {año}",
                    ruta=str(ra),
                    sugerencia="Si el año no se usa, retirarlo de ANOS_ACTIVOS; si se usa, crear la carpeta."
                ))

    # --- Ãndices para duplicados lÃ³gicos y consistencia
    keys = set()
    rutas_lower = set()

    # --- MÃ©tricas de completitud por campo
    campos_metricas = {
        "TIPO_PROCESO": 0, "JURISDICCION": 0, "ORGANISMO": 0, "EXPEDIENTE": 0, "CARATULA": 0,
        "RESPONSABLE": 0, "CONTROL": 0, "EVENTO": 0, "FECHA_EVENTO": 0,
        "TAREA_PENDIENTE": 0, "FECHA_TAREA": 0, "OBSERVACIONES": 0
    }

    # --- Test 3+: por caso
    for c in casos:
        status_info = case_status(c)
        ruta_es_db = is_db_path(c.ruta)
        ficha_txt = None

        # 3.1 Ruta existe
        if not ruta_es_db and not c.ruta.exists():
            hallazgos.append(Hallazgo(
                nivel="ERROR",
                codigo="FS-020",
                mensaje="Caso indexado pero la carpeta fÃ­sica no existe (caso 'perdido').",
                ruta=str(c.ruta),
                sugerencia="Verificar si se moviÃ³/renombrÃ³ manualmente o si hay sincronizaciÃ³n pendiente."
            ))
            continue

        if not ruta_es_db:
            # 3.2 Longitud de ruta (riesgo Windows)
            lp = _safe_len_path(c.ruta)
            if lp >= 240:
                hallazgos.append(Hallazgo(
                    nivel="WARN",
                    codigo="FS-030",
                    mensaje=f"Ruta muy larga ({lp} chars). Riesgo real de errores de lectura/escritura en Windows.",
                    ruta=str(c.ruta),
                    sugerencia="Acortar nombres de cliente/causa o habilitar rutas largas en Windows (polÃ­tica del sistema)."
                ))

            # 3.3 Nombres invÃ¡lidos (Windows)
            if RE_INVALID_WIN.search(c.ruta.name):
                hallazgos.append(Hallazgo(
                    nivel="ERROR",
                    codigo="FS-040",
                    mensaje="Nombre de carpeta del caso contiene caracteres invÃ¡lidos para Windows.",
                    ruta=str(c.ruta),
                    sugerencia="Renombrar eliminando caracteres: <>:\"/\\|?* o control chars."
                ))

            # 3.4 Subcarpetas estÃ¡ndar
            faltantes = []
            for sub in SUBCARPETAS_ESTANDAR:
                if not (c.ruta / sub).exists():
                    faltantes.append(sub)
            if faltantes:
                hallazgos.append(Hallazgo(
                    nivel="WARN",
                    codigo="FS-050",
                    mensaje=f"Faltan subcarpetas estÃ¡ndar: {', '.join(faltantes)}",
                    ruta=str(c.ruta),
                    sugerencia="Usar 'Reparar subcarpetas' en AuditorÃ­a o activar 'Auto-crear subcarpetas' en la barra lateral."
                ))

            # 3.5 Ficha presente
            ficha_txt = c.ruta / "ficha.txt"
            ficha_json = c.ruta / "ficha.json"
            if not ficha_txt.exists() and not ficha_json.exists():
                hallazgos.append(Hallazgo(
                    nivel="WARN",
                    codigo="DATA-010",
                    mensaje="No existe ficha.txt ni ficha.json en el caso.",
                    ruta=str(c.ruta),
                    sugerencia="Crear ficha para evitar 'casos mudos' (sin metadatos) y mejorar bÃºsqueda."
                ))

        # 3.6 Duplicados lÃ³gicos
        k = (c.año.strip(), c.estado.strip(), c.cliente.strip(), c.fuero.strip(), c.causa.strip())
        if k in keys:
            hallazgos.append(Hallazgo(
                nivel="ERROR",
                codigo="DATA-020",
                mensaje="Duplicado lÃ³gico: existe mÃ¡s de un caso con la misma clave jerÃ¡rquica.",
                ruta=str(c.ruta),
                sugerencia="Revisar si hay carpetas duplicadas o diferencias mÃ­nimas (espacios/puntos)."
            ))
        else:
            keys.add(k)

        # 3.7 Rutas duplicadas (case-insensitive, Windows)
        rl = str(c.ruta).lower()
        if rl in rutas_lower:
            hallazgos.append(Hallazgo(
                nivel="ERROR",
                codigo="DATA-025",
                mensaje="Ruta duplicada detectada (case-insensitive). Riesgo de colisiones.",
                ruta=str(c.ruta),
                sugerencia="Normalizar nombres evitando variaciones por mayÃºsculas/minÃºsculas."
            ))
        else:
            rutas_lower.add(rl)

        # 3.8 Fechas vÃ¡lidas
        if c.fecha_tarea and not is_blank(c.fecha_tarea):
            if c._parsear_fecha(c.fecha_tarea) is None:
                hallazgos.append(Hallazgo(
                    nivel="WARN",
                    codigo="DATA-030",
                    mensaje=f"FECHA_TAREA invÃ¡lida (no parseable): {c.fecha_tarea}",
                    ruta=str(c.ruta),
                    sugerencia="Usar DD/MM/YYYY o YYYY-MM-DD; evitar texto libre."
                ))
        if c.fecha_evento and not is_blank(c.fecha_evento):
            if c._parsear_fecha(c.fecha_evento) is None:
                hallazgos.append(Hallazgo(
                    nivel="WARN",
                    codigo="DATA-031",
                    mensaje=f"FECHA_EVENTO invÃ¡lida (no parseable): {c.fecha_evento}",
                    ruta=str(c.ruta),
                    sugerencia="Usar DD/MM/YYYY o YYYY-MM-DD; evitar texto libre."
                ))

        # 3.9 SeÃ±ales tÃ­picas de encoding roto
        if ficha_txt:
            try:
                if ficha_txt.exists():
                    raw = gestor._leer_contenido_ficha(ficha_txt)
                    if "ï¿½" in raw:
                        hallazgos.append(Hallazgo(
                            nivel="WARN",
                            codigo="DATA-040",
                            mensaje="Posible corrupciÃ³n de encoding detectada (carÃ¡cter de reemplazo 'ï¿½').",
                            ruta=str(ficha_txt),
                            sugerencia="Reguardar contenido y reescribir en UTF-8 desde el formulario del ERP."
                        ))
            except Exception:
                logger.warning("No se pudo leer ficha_txt para validacion de encoding: %s", ficha_txt)

        # 3.10 Completitud y campos obligatorios (AUDITORÃA FLEXIBLE)
        for key_m in campos_metricas.keys():
            attr = key_m.lower()
            # Compatibilidad dict / objeto
            val = getattr(c, attr, None) if hasattr(c, attr) else c.get(key_m, None) if isinstance(c, dict) else None
            if is_blank(val):
                campos_metricas[key_m] += 1

        missing_minimum = status_info["missing_minimum"]
        missing_quality = status_info["missing_quality"]

        if missing_minimum:
            hallazgos.append(Hallazgo(
                nivel="ERROR",
                codigo="DATA-050",
                mensaje=f"Campos mÃ­nimos faltantes: {', '.join(sorted(set(missing_minimum)))}",
                ruta=str(c.ruta),
                sugerencia="Completar mÃ­nimos desde la app para habilitar operaciÃ³n (agenda/control)."
            ))

        elif status_info["status"] == "legacy_incomplete" and missing_quality:
            hallazgos.append(Hallazgo(
                nivel="WARN",
                codigo="DATA-051",
                mensaje=f"Campos de calidad faltantes (legacy): {', '.join(sorted(set(missing_quality)))}",
                ruta=str(c.ruta),
                sugerencia="Completar progresivamente la ficha desde la app; mejora bÃºsqueda, reportes y auditorÃ­a."
            ))

    # --- Resumen + mÃ©tricas
    errores = sum(1 for h in hallazgos if h.nivel == "ERROR")
    warns = sum(1 for h in hallazgos if h.nivel == "WARN")
    infos = sum(1 for h in hallazgos if h.nivel == "INFO")

    total = max(1, len(casos))
    metricas = {
        "casos_total": len(casos),
        "tiempo_auditoria_seg": round(time.time() - t0, 3),
        "completitud": {
            k: {
                "vacios_o_sd": v,
                "completos": total - v,
                "pct_completos": round(((total - v) / total) * 100, 1)
            } for k, v in campos_metricas.items()
        }
    }

    ok = errores == 0
    return {
        "ok": ok,
        "resumen": {"errores": errores, "warnings": warns, "info": infos, "casos": len(casos)},
        "hallazgos": [asdict(h) for h in hallazgos],
        "metricas": metricas
    }
