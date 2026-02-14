"""
Vistas principales: Dashboard, Gestion (Casos/Clientes), Agenda, Finanzas, Auditoria, Config.
Sprint 2: Dashboard con KPIs reales
Sprint 3: Gestion maestro-detalle
Sprint 4: Auditoria sin CSV crudo
"""

import csv
import hashlib
import html
import io
import json
import logging
import os
import re
import subprocess
import sys
import unicodedata
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd
import streamlit as st

from audit import (
    DEFAULT_INCOMPLETE_FIELDS,
    DEFAULT_INCOMPLETE_WEIGHTS,
    append_daily_audit_history,
    auditar_app,
    build_daily_audit_snapshot,
    build_incomplete_case_queue,
    build_operational_hallazgos_export_payload,
    build_operational_hallazgos_rows,
    build_operational_kpi_snapshot,
    build_trend_degradation_alert,
    ensure_daily_audit_snapshot,
    filter_operational_hallazgos,
    load_daily_audit_history,
    load_daily_audit_snapshots,
    save_daily_audit_snapshot,
)
from config import (
    CAMPOS_FICHA,
    ESTADOS_DISPONIBLES,
    ESTADOS_PAGO,
    FUEROS_DISPONIBLES,
)
from domain import Caso, case_status, is_blank
from exports import build_export_metadata, df_to_xlsx_bytes, payload_to_json_bytes
from grids import render_aggrid
from repo import GestorCasos, is_db_mode
from security import build_actor_context, can_access_route, can_export, has_permission, is_rbac_strict
from ui import (
    _ensure_bool_state,
    _swap,
    _ui_toast,
    audit_status_badge,
    card_begin,
    card_end,
    detail_shell,
    grid_shell,
    kpi_card,
    open_path,
    page_header,
    pill,
    progress_row,
    render_module_frame,
    is_ui_revamp_enabled,
    section_header,
    start_ui_block_order,
    mark_ui_block,
    ui_centro_ayuda_content,
    vg_empty_state,
    vg_modebar,
    vg_toolbar,
)

UUID_RE = re.compile(r"^[0-9a-fA-F-]{36}$")
DB_CASE_RE = re.compile(r"db[:/\\\\]+cases[:/\\\\]+([0-9a-fA-F-]{36})", re.IGNORECASE)
FIN_CSV_COL_ALIASES = {
    "CASE_REF": ["_RUTA", "RUTA", "CASE_REF", "CASE_ID", "ID_CASO", "UUID", "ID"],
    "MONTO_DEMANDADO": ["MONTO_DEMANDADO", "MONTO DEMANDADO", "MONTO"],
    "HONORARIOS_PACTADOS": ["HONORARIOS_PACTADOS", "HONORARIOS PACTADOS", "HONORARIOS"],
    "ESTADO_PAGO": ["ESTADO_PAGO", "ESTADO PAGO"],
}
FIN_CSV_FIN_COLS = ("MONTO_DEMANDADO", "HONORARIOS_PACTADOS", "ESTADO_PAGO")
AUTO_SAVE_CHANGES_ENV = "VG_AUTO_SAVE_CHANGES"
AUTO_SAVE_OVERRIDE_KEY = "ui.auto_save.enabled"


@st.cache_data(show_spinner=False)
def _csv_bytes(df: pd.DataFrame) -> bytes:
    return df.to_csv(index=False).encode("utf-8-sig")


@st.cache_data(show_spinner=False)
def _xlsx_bytes(df: pd.DataFrame, sheet_name: str = "Reporte") -> bytes:
    return df_to_xlsx_bytes(df, sheet_name=sheet_name)


def _get_export_ts(name: str) -> str:
    """Timestamp estable por sesiÃ³n para file_name de descargas."""
    key = f"export_ts_{name}"
    if key not in st.session_state:
        st.session_state[key] = datetime.now().strftime("%Y%m%d_%H%M%S")
    return st.session_state[key]


def _regen_export_ts(names: List[str]):
    """Actualiza los timestamps de exportes (botÃ³n 'Regenerar')."""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    for name in names:
        st.session_state[f"export_ts_{name}"] = ts


def _contar_status(casos: List[Caso]) -> Dict[str, int]:
    """Cuenta casos por estado de datos usando case_status()."""
    counts = {"ok": 0, "legacy_incomplete": 0, "error": 0}
    for c in casos:
        status = case_status(c).get("status", "ok")
        counts[status] = counts.get(status, 0) + 1
    return counts


def _completitud_basica(casos: List[Caso]) -> Dict[str, Dict[str, float]]:
    """Calcula completitud por campo usando la misma lÃ³gica que auditorÃ­a."""
    total = len(casos)
    if total == 0:
        return {}

    metricas = {}
    for campo in CAMPOS_FICHA:
        attr = campo.lower()
        completos = 0
        for c in casos:
            val = getattr(c, attr, None) if hasattr(c, attr) else None
            if not is_blank(val):
                completos += 1
        metricas[campo] = {
            "vacios_o_sd": total - completos,
            "completos": completos,
            "pct_completos": round((completos / total) * 100, 1)
        }
    return metricas


def _go_route(route: str, mode: str = "listado", item_id: str | None = None):
    """NavegaciÃ³n interna sin depender de nav.navigate_to."""
    st.session_state["_nav_target"] = route
    st.session_state["nav_route"] = route
    if route == "Gestion":
        _go(mode=mode, case_id=item_id, rerun=False)
    else:
        st.session_state["route_mode"] = _normalize_mode(mode)
        if item_id is not None:
            canonical = _canonical_case_ref(item_id)
            st.session_state["selected_item_id"] = canonical or str(item_id).strip()
    st.rerun()


def _route_enabled(route: str) -> tuple[bool, str]:
    """
    Determina si una ruta es navegable para la sesion actual.
    Se usa para deshabilitar CTAs y evitar sensacion de botones rotos.
    """
    route_name = str(route or "").strip()
    if not can_access_route(route_name):
        return False, "Sin permisos para esta seccion."
    if is_db_mode() and not st.session_state.get("db_ready", True):
        if route_name in {"Gestion", "Agenda", "Finanzas"}:
            return False, "Requiere base de datos disponible."
    return True, ""


def _render_route_quick_nav(
    prefix_key: str,
    routes: List[tuple[str, str, str]],
    *,
    title: str = "Navegacion rapida",
    subtitle: str = "Saltos directos entre modulos",
    group_in_more_actions: bool = False,
):
    """Renderiza una grilla compacta de botones de navegacion entre rutas primarias."""
    if not routes:
        return
    use_more_actions = bool(group_in_more_actions and is_ui_revamp_enabled())
    holder = st.expander("Mas acciones", expanded=False) if use_more_actions else st.container()
    with holder:
        card_begin(title, subtitle=subtitle, variant="tight")
        cols = st.columns(len(routes))
        for idx, (route, label, mode) in enumerate(routes):
            enabled, reason = _route_enabled(route)
            with cols[idx]:
                if st.button(
                    label,
                    key=f"{prefix_key}.nav.{route.lower()}",
                    width="stretch",
                    type="secondary",
                    disabled=not enabled,
                    help=reason or None,
                ):
                    _go_route(route, mode=mode)
        card_end()


def _debug_selected_case_id(stage: str, value):
    """Debug puntual para diagnosticar deformacion URI->Path en Windows."""
    if os.environ.get("VG_DEBUG") != "1":
        return
    valor = value
    valor_str = str(valor)
    path_str = str(Path(valor_str))
    startswith_before = valor_str.startswith("db://")
    startswith_after = path_str.startswith("db://")
    print(f"[VG_DEBUG] {stage} | selected_case_id={valor!r} | type={type(valor).__name__} | valor_str={valor_str!r} | path_str={path_str!r} | startswith_db_before={startswith_before} | startswith_db_after={startswith_after}")


def _dbg(label: str, **kvs):
    if os.environ.get("VG_DEBUG") == "1":
        print("[VG]", label, kvs)


def _env_bool(name: str, default: bool = False) -> bool:
    raw = str(os.environ.get(name, "")).strip().lower()
    if not raw:
        return bool(default)
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off"}:
        return False
    return bool(default)


def _auto_save_changes_enabled() -> bool:
    if AUTO_SAVE_OVERRIDE_KEY in st.session_state:
        return bool(st.session_state.get(AUTO_SAVE_OVERRIDE_KEY))
    return _env_bool(AUTO_SAVE_CHANGES_ENV, default=True)


def _create_desktop_shortcut() -> tuple[bool, str]:
    if os.name != "nt":
        return False, "El acceso directo de escritorio solo aplica en Windows."
    repo_dir = Path(__file__).resolve().parent
    script_path = repo_dir / "CREATE_DESKTOP_SHORTCUT.ps1"
    if not script_path.exists():
        return False, f"No se encontro script de acceso directo: {script_path}"

    cmd = [
        "powershell",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(script_path),
        "-Force",
    ]
    try:
        result = subprocess.run(
            cmd,
            cwd=str(repo_dir),
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except Exception as exc:
        return False, f"Error ejecutando instalador de acceso directo: {exc}"

    output = (result.stdout or "").strip()
    err = (result.stderr or "").strip()
    if result.returncode != 0:
        detail = err or output or f"exit={result.returncode}"
        return False, f"No se pudo crear acceso directo ({detail})"
    if output.startswith("CREATED::"):
        return True, f"Acceso directo creado: {output.split('::', 1)[1]}"
    if output.startswith("EXISTS::"):
        return True, f"Acceso directo actualizado: {output.split('::', 1)[1]}"
    if output:
        return True, output
    return True, "Acceso directo creado en el Escritorio."


def _setup_test_database_from_ui() -> tuple[bool, str]:
    repo_dir = Path(__file__).resolve().parent
    script_path = repo_dir / "db" / "setup_test_db.py"
    if not script_path.exists():
        return False, f"No se encontro script setup_test_db: {script_path}"

    cmd = [
        sys.executable,
        str(script_path),
        "--write-dotenv",
    ]
    try:
        result = subprocess.run(
            cmd,
            cwd=str(repo_dir),
            capture_output=True,
            text=True,
            timeout=90,
            check=False,
        )
    except Exception as exc:
        return False, f"Error ejecutando setup DB test: {exc}"

    out = (result.stdout or "").strip()
    err = (result.stderr or "").strip()
    if result.returncode != 0:
        detail = out or err or f"exit={result.returncode}"
        return False, detail
    return True, out or "Setup DB test completado."


GESTION_SECTIONS = {
    "casos": "Casos",
    "clientes": "Clientes",
    "agenda": "Agenda",
    "finanzas": "Finanzas",
}
# Secciones visibles dentro de Gestion (Agenda/Finanzas salen a rutas primarias).
GESTION_WORK_SECTIONS = {
    "casos": "Casos",
    "clientes": "Clientes",
}
# Alias de compatibilidad para estado legacy.
GESTION_SECTION_ALIASES = {
    "casos": "casos",
    "caso": "casos",
    "cliente": "clientes",
    "clientes": "clientes",
    "agenda": "agenda",
    "finanzas": "finanzas",
}
# Compatibilidad con el nombre historico.
GESTION_TABS = GESTION_WORK_SECTIONS
GESTION_MODES = ("listado", "detalle", "editar")
GESTION_MODE_LABELS = {"listado": "Listado", "detalle": "Detalle", "editar": "Editar"}
GESTION_SECTION_SELECTED_KEYS = {
    "casos": "case_id",
    "clientes": "client_id",
    "agenda": "agenda_id",
    "finanzas": "fin_id",
}
GESTION_SECTION_ENTITY = {
    "casos": "case",
    "clientes": "client",
    "agenda": "agenda",
    "finanzas": "fin",
}

GESTION_FILTER_DEFAULTS = {
    "busqueda": "",
    "anio": "Todos",
    "estado": "Todos",
    "cliente": "Todos",
    "fuero": "Todos",
    "semaforo": "Todos",
    "atajo": "Ninguno",
    "priorizar_urgentes": True,
    "modo": "Tabla",
    "densidad": "Compacta",
    "wrap": False,
}
GESTION_SECTION_FILTER_DEFAULTS = {
    "casos": GESTION_FILTER_DEFAULTS,
    "clientes": {"busqueda": "", "estado": "Todos"},
    "agenda": {"ver": "Todas", "solo_activos": True},
    "finanzas": {"estado_pago": "Todos"},
}

GESTION_FILTER_LEGACY_KEYS = {
    "busqueda": "busqueda_global",
    "anio": "filtro_aÃ±o",
    "estado": "filtro_estado",
    "cliente": "filtro_cliente",
    "fuero": "filtro_fuero",
    "semaforo": "filtro_semaforo",
    "atajo": "filtro_atajo",
    "priorizar_urgentes": "priorizar_urgentes",
    "modo": "planilla_modo",
    "densidad": "planilla_densidad",
    "wrap": "planilla_wrap",
}

GESTION_FILTER_LEGACY_ALIASES = {
    "anio": ["filtro_aÃ±o", "filtro_a\u00c3\u00b1o"],
}

SEMAFORO_ICONS = {
    "Vencidos": "ðŸ”´",
    "PrÃ³ximos": "ðŸŸ¡",
    "En tiempo": "ðŸŸ¢",
    "Sin tarea": "âšª",
}

SEMAFORO_REVERSE = {v: k for k, v in SEMAFORO_ICONS.items()}

logger = logging.getLogger(__name__)


def _actor_ctx() -> Dict[str, str]:
    return build_actor_context()


def _enforce_permission(permission: str, denied_message: str) -> bool:
    if has_permission(permission):
        return True
    st.error(denied_message)
    if is_rbac_strict():
        logger.warning("permission denied permission=%s", permission)
    return False


def _legacy_badge_html(raw_value: str) -> str:
    safe = html.escape(str(raw_value or ""))
    return f"<span class='vg-badge vg-badge-warn'>{safe}</span>"


def _gk(*parts) -> str:
    clean = [str(p).strip(".") for p in parts if str(p).strip(".")]
    if not clean:
        return "gestion"
    return "gestion." + ".".join(clean)


def _gget(key: str, default=None):
    full = key if str(key).startswith("gestion.") else _gk(key)
    return st.session_state.get(full, default)


def _gset(key: str, value):
    full = key if str(key).startswith("gestion.") else _gk(key)
    try:
        st.session_state[full] = value
    except Exception as exc:
        if "cannot be modified after the widget with key" in str(exc):
            _dbg("gestion:state:set:skipped_locked_widget", key=full, value=value)
            return st.session_state.get(full, value)
        raise
    return value


def _normalize_section(section_value, fallback: str = "casos") -> str:
    raw = str(section_value or "").strip().lower()
    if raw in GESTION_SECTION_ALIASES:
        return GESTION_SECTION_ALIASES[raw]
    for key, label in GESTION_SECTIONS.items():
        if raw == label.lower():
            return key
    return fallback


def _normalize_tab(tab_value, fallback: str = "casos") -> str:
    return _normalize_section(tab_value, fallback=fallback)


def _normalize_mode(mode_value, fallback: str = "listado") -> str:
    raw = str(mode_value or "").strip().lower()
    return raw if raw in GESTION_MODES else fallback


def _tab_mode_key(tab_name: str) -> str:
    section = _normalize_section(tab_name, fallback=str(tab_name or "").strip().lower())
    if section == "clientes":
        return "gestion_mode_cliente"
    return f"gestion_mode_{section}"


def _legacy_tab_label(section: str) -> str:
    return GESTION_SECTIONS.get(section, "Casos")


def _legacy_mode_keys(section: str) -> List[str]:
    if section == "clientes":
        return ["gestion_mode_clientes", "gestion_mode_cliente"]
    return [f"gestion_mode_{section}"]


def _legacy_mode_key(section: str) -> str:
    return _legacy_mode_keys(section)[0]


def _gestion_filter_key(name: str) -> str:
    # Clave legacy de widgets de Casos para no romper estado existente.
    return _gk("casos", "filters", name)


def _selected_state_key(section: str) -> str:
    sec = _normalize_section(section)
    return _gk("selected", GESTION_SECTION_SELECTED_KEYS.get(sec, "case_id"))


def _section_filter_state_key(section: str) -> str:
    return _gk("filters", _normalize_section(section))


def _section_filter_defaults(section: str) -> dict:
    sec = _normalize_section(section)
    defaults = GESTION_SECTION_FILTER_DEFAULTS.get(sec, {})
    return dict(defaults)


def _selected_value_for_section(section: str):
    sec = _normalize_section(section)
    return _gget(_selected_state_key(sec), "")


def _has_selection_for_section(section: str) -> bool:
    sec = _normalize_section(section)
    selected = _selected_value_for_section(sec)
    if not selected:
        return False
    if sec == "clientes":
        return bool(str(selected).strip())
    return bool(_canonical_case_ref(selected))


def _set_selected_for_section(section: str, value, stage: str = "set") -> str:
    sec = _normalize_section(section)
    if sec == "clientes":
        selected = _normalize_text_value(value)
    else:
        selected = _canonical_case_ref(value)
        if is_db_mode() and selected and not DB_CASE_RE.search(selected):
            _dbg("gestion:selected:invalid_in_db_mode", section=sec, stage=stage, value=value, canonical=selected)
            selected = ""

    _gset(_selected_state_key(sec), selected)
    if sec == "casos":
        _gset(_gk("casos", "selected_case_id"), selected)
        st.session_state["selected_case_id"] = selected or None
        _debug_selected_case_id(f"{stage}:set", selected)
    return selected


def _get_section_filters_snapshot(section: str) -> dict:
    sec = _normalize_section(section)
    defaults = _section_filter_defaults(sec)
    if not defaults:
        return {}

    current = _gget(_section_filter_state_key(sec), {})
    if not isinstance(current, dict):
        current = {}

    snap = {}
    for name, default in defaults.items():
        if sec == "casos":
            key = _gestion_filter_key(name)
            value = st.session_state.get(key, current.get(name, default))
        elif sec == "agenda":
            alias_map = {"ver": "gestion.agenda.filtro.ver", "solo_activos": "gestion.agenda.filtro.activos"}
            alias = alias_map.get(name)
            value = current.get(name, st.session_state.get(alias, default)) if alias else current.get(name, default)
        elif sec == "finanzas":
            alias_map = {"estado_pago": "gestion.finanzas.filtro_pago"}
            alias = alias_map.get(name)
            value = current.get(name, st.session_state.get(alias, default)) if alias else current.get(name, default)
        else:
            value = current.get(name, default)
        snap[name] = value

    _gset(_section_filter_state_key(sec), snap)
    return snap


def _get_casos_filters_snapshot() -> dict:
    return _get_section_filters_snapshot("casos")


def _sync_filters_alias_from_dict(section: str):
    sec = _normalize_section(section)
    filters = _get_section_filters_snapshot(sec)
    if sec == "casos":
        for name, default in GESTION_FILTER_DEFAULTS.items():
            _gset(_gestion_filter_key(name), filters.get(name, default))
    elif sec == "agenda":
        _gset("gestion.agenda.filtro.ver", filters.get("ver", "Todas"))
        _gset("gestion.agenda.filtro.activos", bool(filters.get("solo_activos", True)))
    elif sec == "finanzas":
        _gset("gestion.finanzas.filtro_pago", filters.get("estado_pago", "Todos"))


def _save_tab_snapshot(section: str):
    sec = _normalize_section(section)
    selected = _selected_value_for_section(sec)
    snap = {
        "mode": _gget(_gk("mode", sec), "listado"),
        "selected_id": selected,
        "selected_case_id": selected if sec == "casos" else "",
        "filters": _get_section_filters_snapshot(sec),
    }
    _gset(_gk("snapshots", sec), snap)
    if sec == "clientes":
        # Legacy snapshot key.
        _gset(_gk("snapshots", "cliente"), snap)
    _dbg("gestion:snapshot:save", section=sec, snapshot=snap)


def _restore_tab_snapshot(section: str):
    sec = _normalize_section(section)
    snap = _gget(_gk("snapshots", sec), {})
    if sec == "clientes" and not snap:
        snap = _gget(_gk("snapshots", "cliente"), {})
    snap = snap or {}
    if not isinstance(snap, dict):
        return
    if "mode" in snap:
        snap_mode = _normalize_mode(snap.get("mode"), fallback="listado")
        _gset(_gk("mode", sec), snap_mode)

    if "selected_id" in snap or "selected_case_id" in snap:
        selected = snap.get("selected_id", snap.get("selected_case_id", ""))
        _set_selected_for_section(sec, selected, stage=f"restore_snapshot:{sec}")

    filters = snap.get("filters")
    if isinstance(filters, dict):
        defaults = _section_filter_defaults(sec)
        normalized = {name: filters.get(name, default) for name, default in defaults.items()}
        _gset(_section_filter_state_key(sec), normalized)
        _sync_filters_alias_from_dict(sec)


def _sync_legacy_from_namespace():
    section = _normalize_section(
        _gget(_gk("section"), _gget(_gk("tab"), "casos")),
        fallback="casos",
    )
    st.session_state["gestion_tab"] = _legacy_tab_label(section)
    _gset(_gk("tab"), section)  # Legacy namespaced alias.
    mode_key = _gk("mode", section)
    st.session_state["route_mode"] = _normalize_mode(_gget(mode_key, "listado"))
    for sec in GESTION_SECTIONS:
        mode_value = _normalize_mode(_gget(_gk("mode", sec), "listado"))
        for legacy_mode_key in _legacy_mode_keys(sec):
            st.session_state[legacy_mode_key] = mode_value

    selected = _canonical_case_ref(_gget(_selected_state_key("casos"), ""))
    _gset(_gk("casos", "selected_case_id"), selected)
    st.session_state["selected_case_id"] = selected or None

    for name, legacy_key in GESTION_FILTER_LEGACY_KEYS.items():
        if legacy_key:
            value = _gget(_gestion_filter_key(name), GESTION_FILTER_DEFAULTS[name])
            st.session_state[legacy_key] = value
            for alias in GESTION_FILTER_LEGACY_ALIASES.get(name, []):
                st.session_state[alias] = value
    snap = _get_casos_filters_snapshot()
    legacy_snap = dict(snap)
    for name, legacy_key in GESTION_FILTER_LEGACY_KEYS.items():
        if legacy_key:
            legacy_snap[legacy_key] = snap.get(name)
    st.session_state["casos_filters"] = legacy_snap


def _sync_namespace_from_legacy():
    legacy_section = _normalize_section(
        st.session_state.get("gestion.section") or st.session_state.get("gestion.tab") or st.session_state.get("gestion_tab", "Casos"),
        fallback="casos",
    )
    if _gget(_gk("section")) is None:
        _gset(_gk("section"), legacy_section)
    if _gget(_gk("tab")) is None:
        _gset(_gk("tab"), legacy_section)

    legacy_mode = _normalize_mode(st.session_state.get("route_mode", "listado"))
    for sec in GESTION_SECTIONS:
        mode_key = _gk("mode", sec)
        if _gget(mode_key) is None:
            legacy_specific = None
            for mode_legacy_key in _legacy_mode_keys(sec):
                if mode_legacy_key in st.session_state:
                    legacy_specific = st.session_state.get(mode_legacy_key)
                    break
            fallback_mode = _normalize_mode(legacy_specific, fallback=legacy_mode if sec == legacy_section else "listado")
            _gset(mode_key, fallback_mode)

    selected = _canonical_case_ref(_gget(_selected_state_key("casos"), ""))
    if not selected:
        selected = _canonical_case_ref(_gget(_gk("casos", "selected_case_id"), ""))
    if not selected:
        selected = _canonical_case_ref(st.session_state.get("selected_case_id"))
    _set_selected_for_section("casos", selected, stage="sync_legacy")

    for sec in GESTION_SECTIONS:
        selected_key = _selected_state_key(sec)
        if _gget(selected_key) is None:
            _gset(selected_key, "")

    for sec in GESTION_SECTIONS:
        defaults = _section_filter_defaults(sec)
        current = _gget(_section_filter_state_key(sec), {})
        if not isinstance(current, dict):
            current = {}
        merged = dict(defaults)
        merged.update({k: current.get(k, default) for k, default in defaults.items()})
        _gset(_section_filter_state_key(sec), merged)

    legacy_snapshot = st.session_state.get("casos_filters") or {}
    for name, default in GESTION_FILTER_DEFAULTS.items():
        key = _gestion_filter_key(name)
        if _gget(key) is None:
            legacy_key = GESTION_FILTER_LEGACY_KEYS.get(name, "")
            legacy_aliases = GESTION_FILTER_LEGACY_ALIASES.get(name, [])
            if isinstance(legacy_snapshot, dict) and name in legacy_snapshot:
                source_value = legacy_snapshot.get(name, default)
            elif isinstance(legacy_snapshot, dict) and legacy_key in legacy_snapshot:
                source_value = legacy_snapshot.get(legacy_key, default)
            elif isinstance(legacy_snapshot, dict) and any(alias in legacy_snapshot for alias in legacy_aliases):
                alias = next(alias for alias in legacy_aliases if alias in legacy_snapshot)
                source_value = legacy_snapshot.get(alias, default)
            elif legacy_key in st.session_state:
                source_value = st.session_state.get(legacy_key, default)
            elif any(alias in st.session_state for alias in legacy_aliases):
                alias = next(alias for alias in legacy_aliases if alias in st.session_state)
                source_value = st.session_state.get(alias, default)
            else:
                source_value = default
            _gset(key, source_value)
    _sync_filters_alias_from_dict("agenda")
    _sync_filters_alias_from_dict("finanzas")


def _ginit_defaults():
    _sync_namespace_from_legacy()

    section = _normalize_section(
        _gget(_gk("section"), _gget(_gk("tab"), "casos")),
        fallback="casos",
    )
    _gset(_gk("section"), section)
    _gset(_gk("tab"), section)
    for sec in GESTION_SECTIONS:
        mode_key = _gk("mode", sec)
        _gset(mode_key, _normalize_mode(_gget(mode_key, "listado")))
        _gset(_gk("snapshots", sec), _gget(_gk("snapshots", sec), {}))
    _gset(_gk("snapshots", "cliente"), _gget(_gk("snapshots", "cliente"), {}))

    _set_selected_for_section("casos", _gget(_selected_state_key("casos"), ""), stage="ginit")
    _gset(_selected_state_key("clientes"), _normalize_text_value(_gget(_selected_state_key("clientes"), "")))
    _gset(_selected_state_key("agenda"), _canonical_case_ref(_gget(_selected_state_key("agenda"), "")))
    _gset(_selected_state_key("finanzas"), _canonical_case_ref(_gget(_selected_state_key("finanzas"), "")))

    for name, default in GESTION_FILTER_DEFAULTS.items():
        key = _gestion_filter_key(name)
        val = _gget(key, default)
        if name in {"priorizar_urgentes", "wrap"}:
            val = bool(val)
        elif name in {"modo"} and val not in ("Tabla", "Tarjetas"):
            val = default
        elif name in {"densidad"} and val not in ("Compacta", "Confort"):
            val = default
        _gset(key, val)
    _gset(_section_filter_state_key("casos"), _get_casos_filters_snapshot())
    for sec in ("clientes", "agenda", "finanzas"):
        defaults = _section_filter_defaults(sec)
        current = _gget(_section_filter_state_key(sec), {})
        if not isinstance(current, dict):
            current = {}
        normalized = {}
        for name, default in defaults.items():
            value = current.get(name, default)
            if sec == "agenda" and name == "solo_activos":
                value = bool(value)
            normalized[name] = value
        _gset(_section_filter_state_key(sec), normalized)
        _sync_filters_alias_from_dict(sec)

    _sync_legacy_from_namespace()


def _current_gestion_section() -> str:
    _ginit_defaults()
    return _normalize_section(_gget(_gk("section"), _gget(_gk("tab"), "casos")))


def _current_gestion_tab() -> str:
    return _current_gestion_section()


def _current_gestion_mode(section: str | None = None) -> str:
    _ginit_defaults()
    sec = _normalize_section(section or _gget(_gk("section"), _gget(_gk("tab"), "casos")))
    return _normalize_mode(_gget(_gk("mode", sec), "listado"))


def _has_valid_selected_case() -> bool:
    ref = _canonical_case_ref(_gget(_selected_state_key("casos"), _gget(_gk("casos", "selected_case_id"), "")))
    if not ref:
        return False
    if ref.startswith("db://cases/"):
        return bool(DB_CASE_RE.search(ref))
    return not is_db_mode()


def _go(
    section: str | None = None,
    mode: str | None = None,
    selected_id: str | None = None,
    rerun: bool = True,
    tab: str | None = None,  # Legacy alias.
    case_id: str | None = None,  # Legacy alias.
):
    _ginit_defaults()
    requested_section = section if section is not None else tab
    requested_selected = selected_id if selected_id is not None else case_id

    current_section = _normalize_section(_gget(_gk("section"), _gget(_gk("tab"), "casos")))
    _save_tab_snapshot(current_section)

    next_section = _normalize_section(requested_section, fallback=current_section) if requested_section is not None else current_section
    if requested_section is not None and _normalize_section(requested_section, fallback="casos") != next_section:
        _dbg("gestion:go:fallback_section", requested=requested_section, fallback=next_section)
    if next_section != current_section:
        _restore_tab_snapshot(next_section)

    if requested_selected is not None:
        normalized_selected = _set_selected_for_section(next_section, requested_selected, stage="go")
        if not normalized_selected and requested_selected:
            _dbg("gestion:go:selected_empty", section=next_section, requested=requested_selected)

    if mode is None:
        snap = _gget(_gk("snapshots", next_section), {}) or {}
        candidate = snap.get("mode") if isinstance(snap, dict) else None
        next_mode = _normalize_mode(candidate or _gget(_gk("mode", next_section), "listado"))
    else:
        next_mode = _normalize_mode(mode, fallback="listado")
        if next_mode != str(mode).strip().lower():
            _dbg("gestion:go:fallback_mode", requested=mode, fallback=next_mode, section=next_section)

    _gset(_gk("section"), next_section)
    _gset(_gk("tab"), next_section)  # Legacy namespaced alias.
    _gset(_gk("mode", next_section), next_mode)
    st.session_state[_gk("pending", "tabbar", "label")] = GESTION_SECTIONS.get(next_section, "Casos")
    st.session_state[_gk("pending", "modebar", next_section, "label")] = GESTION_MODE_LABELS.get(next_mode, "Listado")
    _sync_legacy_from_namespace()
    _save_tab_snapshot(next_section)
    _dbg(
        "gestion:go",
        section=next_section,
        mode=next_mode,
        selected_case_id=_gget(_selected_state_key("casos"), ""),
    )
    if rerun:
        st.rerun()


def _extract_ruta_value(value) -> str:
    """Extrae ruta de una seleccion de grilla (str/dict AgGrid)."""
    if value is None:
        return ""
    if isinstance(value, (str, Path)):
        return str(value).strip()
    if UUID_RE.fullmatch(str(value).strip()):
        return str(value).strip()
    if isinstance(value, dict):
        if value.get("_RUTA"):
            return str(value.get("_RUTA")).strip()
        rows = value.get("selected_rows")
        if isinstance(rows, list) and rows:
            row0 = rows[0]
            if isinstance(row0, dict):
                for k in ("_RUTA", "ruta", "RUTA", "path", "PATH", "id", "ID"):
                    if row0.get(k):
                        return str(row0.get(k)).strip()
        return ""
    # Compatibilidad con st_aggrid.AgGridReturn
    rows_attr = getattr(value, "selected_rows", None)
    if rows_attr is not None:
        rows = rows_attr
        if hasattr(rows, "to_dict"):
            try:
                rows = rows.to_dict("records")
            except Exception:
                rows = None
        if isinstance(rows, list) and rows:
            row0 = rows[0]
            if isinstance(row0, dict):
                for k in ("_RUTA", "ruta", "RUTA", "path", "PATH", "id", "ID"):
                    if row0.get(k):
                        return str(row0.get(k)).strip()
        return ""
    if hasattr(value, "to_dict"):
        try:
            d = value.to_dict()
            if isinstance(d, dict):
                return _extract_ruta_value(d)
        except Exception:
            return ""
    return ""


def _canonical_case_ref(value) -> str:
    """Normaliza identificadores de caso al formato db://cases/<uuid> cuando aplica."""
    raw = _extract_ruta_value(value)
    if not raw:
        return ""
    m = DB_CASE_RE.search(raw)
    if m:
        return f"db://cases/{m.group(1).lower()}"
    if UUID_RE.fullmatch(raw):
        return f"db://cases/{raw.lower()}"
    return raw


def _set_selected_case_id(value, stage: str = "set") -> str:
    """Setea selected_case_id en formato canÃ³nico en estado namespaced + legacy."""
    return _set_selected_for_section("casos", value, stage=stage)


def _same_case_ref(a, b) -> bool:
    """Compara rutas/ids de caso tolerando variaciones de separadores."""
    ca = _canonical_case_ref(a)
    cb = _canonical_case_ref(b)
    return bool(ca and cb and ca == cb)


def _is_windows_fs_path(path_str: str) -> bool:
    """Heuristica minima para rutas FS en Windows."""
    if not path_str:
        return False
    if path_str.lower().startswith("db:"):
        return False
    if path_str.startswith("\\\\"):
        return True
    return bool(re.match(r"^[A-Za-z]:[\\\\/]", path_str))


def _to_repo_path(value):
    """
    Evita Path() sobre URIs db://.
    Solo convierte a Path cuando parece ruta FS real de Windows.
    """
    path_str = _canonical_case_ref(value)
    if not path_str:
        return ""
    if path_str.lower().startswith("db:"):
        return path_str
    if _is_windows_fs_path(path_str):
        return Path(path_str)
    return path_str


def _entity_from_section(section: str) -> str:
    sec = _normalize_section(section)
    return GESTION_SECTION_ENTITY.get(sec, "case")


def _entity_to_section(entity: str) -> str:
    raw = str(entity or "").strip().lower()
    if raw in {"case", "caso", "casos"}:
        return "casos"
    if raw in {"client", "cliente", "clientes"}:
        return "clientes"
    if raw in {"agenda", "task", "tarea"}:
        return "agenda"
    if raw in {"fin", "finanzas", "finance"}:
        return "finanzas"
    return "casos"


def _validate_selected_for_section(section: str, value) -> str:
    sec = _normalize_section(section)
    if sec == "clientes":
        text = _normalize_text_value(value)
        return text
    canonical = _canonical_case_ref(value)
    if not canonical:
        return ""
    if canonical.startswith("db://cases/"):
        if not DB_CASE_RE.search(canonical):
            return ""
        match = DB_CASE_RE.search(canonical)
        if match:
            return f"db://cases/{match.group(1).lower()}"
    if is_db_mode() and not canonical.startswith("db://cases/"):
        return ""
    return canonical


def _require_selected(entity: str) -> str:
    """Valida seleccion por entidad y devuelve el id normalizado."""
    sec = _entity_to_section(entity)
    mode = _current_gestion_mode(sec)
    key = _selected_state_key(sec)
    fallback = ""
    if sec == "casos":
        fallback = _gget(_gk("casos", "selected_case_id"), st.session_state.get("selected_case_id", ""))
    raw = _gget(key, fallback)

    normalized = _validate_selected_for_section(sec, raw)
    if not normalized:
        _dbg("gestion:guard:selected_invalid", section=sec, mode=mode, raw=raw)
        msg_map = {
            "casos": "No hay un caso seleccionado para continuar.",
            "clientes": "No hay un cliente seleccionado para continuar.",
            "agenda": "No hay una tarea/evento seleccionado para continuar.",
            "finanzas": "No hay un registro financiero seleccionado para continuar.",
        }
        vg_empty_state(
            msg_map.get(sec, "No hay un elemento seleccionado para continuar."),
            "Ir a listado",
            lambda: _go(section=sec, mode="listado"),
            key=f"gestion.empty.guard.{sec}.{mode}",
        )
        return ""

    _set_selected_for_section(sec, normalized, stage=f"require:{entity}")
    return normalized


def _require_selected_case_id(context: str, tab: str = "casos") -> str:
    """Compat: guarda antigua delegada al contrato namespaced por entidad."""
    sec = _normalize_section(tab)
    if sec == "clientes":
        return _require_selected("client")
    if sec == "agenda":
        return _require_selected("agenda")
    if sec == "finanzas":
        return _require_selected("fin")
    return _require_selected("case")


# Ã¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢Â
# SPRINT 2: DASHBOARD (Centro de mando con KPIs)
# Ã¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢Â

def _normalize_date_value(value) -> str:
    """Normaliza fechas a DD/MM/YYYY para comparar/guardar consistentemente."""
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.strftime("%d/%m/%Y")
    if isinstance(value, date):
        return value.strftime("%d/%m/%Y")

    text = str(value).strip()
    if not text or text.upper() == "S/D":
        return ""

    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y", "%d.%m.%Y"):
        try:
            return datetime.strptime(text, fmt).strftime("%d/%m/%Y")
        except ValueError:
            continue
    return text


def _normalize_text_value(value) -> str:
    """Normaliza texto para dirty-state y payload de guardado."""
    if value is None:
        return ""
    text = str(value).strip()
    if text.upper() == "S/D":
        return ""
    return text


def _is_valid_supported_date(value: str) -> bool:
    """
    Valida formato de fecha admitido por el backend.
    Acepta DD/MM/YYYY, YYYY-MM-DD, DD-MM-YYYY y DD.MM.YYYY.
    """
    text = _normalize_text_value(value)
    if not text:
        return True
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y", "%d.%m.%Y"):
        try:
            datetime.strptime(text, fmt)
            return True
        except ValueError:
            continue
    return False


def _gestion_filter_debug_values() -> Dict[str, object]:
    return {
        name: _gget(_gestion_filter_key(name), default)
        for name, default in GESTION_FILTER_DEFAULTS.items()
    }


def _restore_casos_filter_state(force: bool = False):
    """Restaura filtros de Casos desde snapshot namespaced y mantiene legacy sincronizado."""
    snap = _gget(_gk("snapshots", "casos"), {}) or {}
    snap_filters = snap.get("filters", {}) if isinstance(snap, dict) else {}
    _dbg(
        "casos:filters:restore:call",
        force=force,
        has_snapshot=bool(snap_filters),
        snapshot_keys=sorted(list(snap_filters.keys())) if isinstance(snap_filters, dict) else [],
    )
    restored = []
    for name, default in GESTION_FILTER_DEFAULTS.items():
        key = _gestion_filter_key(name)
        if force or key not in st.session_state:
            _gset(key, snap_filters.get(name, default))
            restored.append(name)
    _gset(_section_filter_state_key("casos"), _get_casos_filters_snapshot())
    _sync_legacy_from_namespace()
    _dbg(
        "casos:filters:restore:done",
        force=force,
        restored_keys=restored,
        **_gestion_filter_debug_values(),
    )


def _persist_casos_filter_state():
    """Persiste filtros de Casos para sobrevivir reruns y cambios de tab/modo."""
    snapshot = _gget(_gk("snapshots", "casos"), {}) or {}
    if not isinstance(snapshot, dict):
        snapshot = {}
    snapshot["filters"] = _get_casos_filters_snapshot()
    snapshot["mode"] = _normalize_mode(_gget(_gk("mode", "casos"), st.session_state.get("route_mode", "listado")))
    snapshot["selected_id"] = _gget(_selected_state_key("casos"), "")
    snapshot["selected_case_id"] = snapshot["selected_id"]
    _gset(_gk("snapshots", "casos"), snapshot)
    _gset(_section_filter_state_key("casos"), snapshot["filters"])
    _sync_legacy_from_namespace()


def _anio_col(df: pd.DataFrame) -> str:
    """Resuelve nombre de columna de aÃ±o tolerando variantes de encoding."""
    return _resolve_col(df, "AÑO")


def _semaforo_col(df: pd.DataFrame) -> str:
    """Resuelve nombre de columna de semÃ¡foro tolerando variantes de encoding."""
    return _resolve_col(df, "SEMÁFORO")


def _norm_col_token(value: str) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    return re.sub(r"[^A-Z0-9]", "", text.upper())


def _resolve_col(df: pd.DataFrame, expected: str) -> str:
    expected_norm = _norm_col_token(expected)
    for col in df.columns:
        if _norm_col_token(col) == expected_norm:
            return col
    return expected


def _resolve_any_col(df: pd.DataFrame, aliases: List[str]) -> str:
    for alias in aliases:
        col = _resolve_col(df, alias)
        if col in df.columns:
            return col
    return ""


def _read_uploaded_csv(uploaded_file) -> tuple[pd.DataFrame | None, str]:
    if uploaded_file is None:
        return None, "No se recibio archivo CSV."

    raw_bytes = uploaded_file.getvalue()
    if not raw_bytes:
        return None, "El archivo CSV esta vacio."

    text = ""
    for encoding in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            text = raw_bytes.decode(encoding)
            break
        except UnicodeDecodeError:
            continue

    if not text.strip():
        return None, "El archivo CSV no contiene datos legibles."

    delimiter = ","
    sample = text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;|\t")
        delimiter = dialect.delimiter
    except Exception:
        if sample.count(";") > sample.count(","):
            delimiter = ";"

    try:
        df = pd.read_csv(
            io.StringIO(text),
            sep=delimiter,
            dtype=str,
            keep_default_na=False,
        )
    except Exception as e:
        return None, f"No se pudo leer el CSV: {e}"

    if df is None or df.empty:
        return None, "El CSV no tiene filas de datos."

    df.columns = [str(col).strip() for col in df.columns]
    for col in df.columns:
        df[col] = df[col].map(_normalize_text_value)
    return df, ""


def _parse_decimal_strict(raw_value, field_label: str) -> tuple[Decimal | None, str]:
    text = _normalize_text_value(raw_value)
    if not text:
        return None, ""

    cleaned = text
    for token in ("$", "ARS", "USD"):
        cleaned = cleaned.replace(token, "")
    cleaned = cleaned.replace(" ", "")

    if cleaned.startswith("(") and cleaned.endswith(")"):
        cleaned = f"-{cleaned[1:-1]}"

    sign = ""
    if cleaned and cleaned[0] in "+-":
        sign = cleaned[0]
        cleaned = cleaned[1:]

    if not cleaned:
        return None, f"{field_label}: valor vacio."

    sep_total = cleaned.count(".") + cleaned.count(",")
    last_dot = cleaned.rfind(".")
    last_comma = cleaned.rfind(",")
    sep_idx = max(last_dot, last_comma)

    if sep_idx >= 0:
        lhs_digits = re.sub(r"[.,]", "", cleaned[:sep_idx])
        rhs_digits = re.sub(r"[.,]", "", cleaned[sep_idx + 1 :])
        thousands_only = sep_total == 1 and len(rhs_digits) == 3 and len(lhs_digits) >= 1
        if thousands_only:
            normalized = f"{sign}{lhs_digits}{rhs_digits}"
        else:
            normalized = f"{sign}{lhs_digits}.{rhs_digits}" if rhs_digits else f"{sign}{lhs_digits}"
    else:
        normalized = f"{sign}{re.sub(r'[.,]', '', cleaned)}"

    if not re.fullmatch(r"[+-]\d+(\.\d+)", normalized):
        return None, f"{field_label}: '{text}' no es numerico valido."

    try:
        return Decimal(normalized), ""
    except InvalidOperation:
        return None, f"{field_label}: '{text}' no es numerico valido."


def _parse_decimal_loose(raw_value) -> Decimal | None:
    value, err = _parse_decimal_strict(raw_value, "valor")
    if err:
        return None
    return value


def _decimal_to_storage_text(value: Decimal) -> str:
    return format(value.quantize(Decimal("0.01")), "f")


def _same_money_value(a: Decimal | None, b: Decimal | None) -> bool:
    if a is None or b is None:
        return False
    return a.quantize(Decimal("0.01")) == b.quantize(Decimal("0.01"))


def _normalize_estado_pago_csv(raw_value) -> tuple[str, str]:
    text = _normalize_text_value(raw_value)
    if not text:
        return "", ""

    allowed: Dict[str, str] = {}
    for item in ESTADOS_PAGO:
        key = _norm_col_token(item)
        if key:
            allowed[key] = item
    allowed["PROBONO"] = "Pro bono"

    token = _norm_col_token(text)
    if token in allowed:
        return allowed[token], ""

    valid_values = ", ".join([x for x in ESTADOS_PAGO if x])
    return "", f"ESTADO_PAGO invalido '{text}'. Valores permitidos: {valid_values}."


def _extract_case_uuid(case_ref: str) -> str:
    match = DB_CASE_RE.search(str(case_ref or ""))
    if match:
        return match.group(1).lower()
    return ""


def _build_fin_case_lookup(df_fin: pd.DataFrame) -> Dict[str, Dict[str, Dict[str, str]]]:
    by_ref: Dict[str, Dict[str, str]] = {}
    by_uuid: Dict[str, Dict[str, str]] = {}

    if df_fin is None or df_fin.empty or "_RUTA" not in df_fin.columns:
        return {"by_ref": by_ref, "by_uuid": by_uuid}

    for _, row in df_fin.iterrows():
        case_ref = _canonical_case_ref(row.get("_RUTA", ""))
        if not case_ref:
            continue
        meta = {
            "case_ref": case_ref,
            "cliente": _normalize_text_value(row.get("Cliente", "")),
            "causa": _normalize_text_value(row.get("Causa", "")),
            "monto": _normalize_text_value(row.get("Monto Demandado", "")),
            "honorarios": _normalize_text_value(row.get("Honorarios Pactados", "")),
            "estado_pago": _normalize_text_value(row.get("Estado Pago", "")),
        }
        by_ref[case_ref] = meta
        case_uuid = _extract_case_uuid(case_ref)
        if case_uuid:
            by_uuid[case_uuid] = meta

    return {"by_ref": by_ref, "by_uuid": by_uuid}


def _resolve_case_from_csv(raw_identifier, lookup: Dict[str, Dict[str, Dict[str, str]]]) -> Dict[str, str] | None:
    raw_text = _normalize_text_value(raw_identifier)
    if not raw_text:
        return None

    by_ref = lookup.get("by_ref", {})
    by_uuid = lookup.get("by_uuid", {})

    canonical = _canonical_case_ref(raw_text)
    if canonical in by_ref:
        return by_ref[canonical]

    case_uuid = _extract_case_uuid(canonical)
    if case_uuid and case_uuid in by_uuid:
        return by_uuid[case_uuid]

    raw_uuid = raw_text.lower()
    if UUID_RE.fullmatch(raw_uuid):
        return by_uuid.get(raw_uuid)

    return None


def _build_finanzas_import_plan(df_csv: pd.DataFrame, df_fin: pd.DataFrame) -> Dict[str, object]:
    identifier_col = _resolve_any_col(df_csv, FIN_CSV_COL_ALIASES["CASE_REF"])
    resolved_fin_cols = {
        field: _resolve_any_col(df_csv, FIN_CSV_COL_ALIASES[field])
        for field in FIN_CSV_FIN_COLS
    }

    missing = []
    if not identifier_col:
        missing.append("identificador de caso (_RUTA/CASE_ID/UUID)")
    for field, col in resolved_fin_cols.items():
        if not col:
            missing.append(field)
    if missing:
        return {
            "fatal_error": "Columnas requeridas faltantes en CSV.",
            "missing_columns": missing,
        }

    lookup = _build_fin_case_lookup(df_fin)
    if not lookup.get("by_ref"):
        return {
            "fatal_error": "No hay casos cargados para validar el CSV de Finanzas.",
            "missing_columns": [],
        }

    plan_rows: List[Dict[str, object]] = []
    apply_rows: List[Dict[str, object]] = []
    seen_case_refs = set()

    for idx, row in df_csv.iterrows():
        fila = int(idx) + 2
        raw_id = row.get(identifier_col, "")
        case_meta = _resolve_case_from_csv(raw_id, lookup)
        case_ref = case_meta.get("case_ref", "") if case_meta else ""
        cliente = case_meta.get("cliente", "") if case_meta else ""
        causa = case_meta.get("causa", "") if case_meta else ""

        row_errors: List[str] = []
        if not _normalize_text_value(raw_id):
            row_errors.append("Identificador de caso vacio.")
        if not case_meta:
            row_errors.append(f"Caso no encontrado para identificador '{raw_id}'.")

        monto_raw = row.get(resolved_fin_cols["MONTO_DEMANDADO"], "")
        honorarios_raw = row.get(resolved_fin_cols["HONORARIOS_PACTADOS"], "")
        estado_raw = row.get(resolved_fin_cols["ESTADO_PAGO"], "")

        monto_dec, monto_err = _parse_decimal_strict(monto_raw, "MONTO_DEMANDADO")
        honorarios_dec, honorarios_err = _parse_decimal_strict(honorarios_raw, "HONORARIOS_PACTADOS")
        estado_norm, estado_err = _normalize_estado_pago_csv(estado_raw)

        if monto_err:
            row_errors.append(monto_err)
        if honorarios_err:
            row_errors.append(honorarios_err)
        if estado_err:
            row_errors.append(estado_err)

        if row_errors:
            plan_rows.append({
                "Fila": fila,
                "Caso": case_ref,
                "Cliente": cliente,
                "Causa": causa,
                "Estado": "ERROR",
                "Detalle": " | ".join(row_errors),
            })
            continue

        if case_ref and case_ref in seen_case_refs:
            plan_rows.append({
                "Fila": fila,
                "Caso": case_ref,
                "Cliente": cliente,
                "Causa": causa,
                "Estado": "OMITIDA",
                "Detalle": "Caso duplicado en CSV (se toma la primera aparicion).",
            })
            continue

        seen_case_refs.add(case_ref)

        current_monto = _parse_decimal_loose(case_meta.get("monto", ""))
        current_honorarios = _parse_decimal_loose(case_meta.get("honorarios", ""))
        current_estado = _normalize_text_value(case_meta.get("estado_pago", ""))

        changes: Dict[str, str] = {}
        changed_fields: List[str] = []

        if monto_dec is not None and not _same_money_value(monto_dec, current_monto):
            changes["MONTO_DEMANDADO"] = _decimal_to_storage_text(monto_dec)
            changed_fields.append("MONTO_DEMANDADO")

        if honorarios_dec is not None and not _same_money_value(honorarios_dec, current_honorarios):
            changes["HONORARIOS_PACTADOS"] = _decimal_to_storage_text(honorarios_dec)
            changed_fields.append("HONORARIOS_PACTADOS")

        if estado_norm and estado_norm != current_estado:
            changes["ESTADO_PAGO"] = estado_norm
            changed_fields.append("ESTADO_PAGO")

        if not changes:
            plan_rows.append({
                "Fila": fila,
                "Caso": case_ref,
                "Cliente": cliente,
                "Causa": causa,
                "Estado": "OMITIDA",
                "Detalle": "Sin cambios aplicables para el caso.",
            })
            continue

        plan_rows.append({
            "Fila": fila,
            "Caso": case_ref,
            "Cliente": cliente,
            "Causa": causa,
            "Estado": "ACTUALIZAR",
            "Detalle": ", ".join(changed_fields),
        })
        apply_rows.append({
            "Fila": fila,
            "case_ref": case_ref,
            "cliente": cliente,
            "causa": causa,
            "datos_fin": changes,
            "detalle": ", ".join(changed_fields),
        })

    summary = {
        "total": len(plan_rows),
        "to_update": len(apply_rows),
        "omitted": sum(1 for r in plan_rows if r.get("Estado") == "OMITIDA"),
        "errors": sum(1 for r in plan_rows if r.get("Estado") == "ERROR"),
    }

    return {
        "fatal_error": "",
        "missing_columns": [],
        "identifier_column": identifier_col,
        "resolved_columns": resolved_fin_cols,
        "rows": plan_rows,
        "apply_rows": apply_rows,
        "summary": summary,
    }


def _apply_finanzas_import_plan(plan: Dict[str, object], gestor: GestorCasos) -> Dict[str, object]:
    base_rows = plan.get("rows", []) if isinstance(plan, dict) else []
    apply_rows = plan.get("apply_rows", []) if isinstance(plan, dict) else []

    result_rows = [dict(row) for row in base_rows if isinstance(row, dict)]
    row_index = {int(row.get("Fila", -1)): row for row in result_rows if "Fila" in row}
    updated = 0
    if not _enforce_permission("finance:write", "No tiene permiso para importar datos financieros."):
        for row in row_index.values():
            row["Estado"] = "ERROR"
            row["Detalle"] = "Permiso denegado para escritura financiera."
        final_rows = sorted(row_index.values(), key=lambda r: int(r.get("Fila", 0)))
        return {
            "summary": {
                "total": len(final_rows),
                "updated": 0,
                "omitted": 0,
                "errors": len(final_rows),
            },
            "rows": final_rows,
        }

    for row in apply_rows:
        if not isinstance(row, dict):
            continue
        fila = int(row.get("Fila", -1))
        case_ref = row.get("case_ref", "")
        datos_fin = row.get("datos_fin", {})
        current = row_index.get(fila, {
            "Fila": fila,
            "Caso": case_ref,
            "Cliente": row.get("cliente", ""),
            "Causa": row.get("causa", ""),
        })

        try:
            ok = gestor.guardar_datos_financieros(
                _to_repo_path(case_ref),
                datos_fin,
                actor_ctx=_actor_ctx(),
            )
        except ValueError as e:
            current["Estado"] = "ERROR"
            current["Detalle"] = str(e)
            row_index[fila] = current
            continue

        if ok:
            updated += 1
            current["Estado"] = "ACTUALIZADA"
            current["Detalle"] = row.get("detalle", "")
        else:
            current["Estado"] = "OMITIDA"
            current["Detalle"] = "No se pudo guardar en base de datos."
        row_index[fila] = current

    final_rows = sorted(row_index.values(), key=lambda r: int(r.get("Fila", 0)))
    result = {
        "summary": {
            "total": len(final_rows),
            "updated": updated,
            "omitted": sum(1 for r in final_rows if r.get("Estado") == "OMITIDA"),
            "errors": sum(1 for r in final_rows if r.get("Estado") == "ERROR"),
        },
        "rows": final_rows,
    }
    return result


def _render_finanzas_csv_import_panel(df_fin: pd.DataFrame, gestor: GestorCasos):
    prefix = "gestion.finanzas.csv"
    hash_key = f"{prefix}.file_hash"
    plan_key = f"{prefix}.plan"
    result_key = f"{prefix}.result"
    confirm_key = f"{prefix}.confirm_apply"

    with st.expander("Carga masiva inicial (CSV)", expanded=False):
        st.caption(
            "Columnas requeridas: identificador de caso (_RUTA/CASE_ID/UUID), "
            "MONTO_DEMANDADO, HONORARIOS_PACTADOS, ESTADO_PAGO."
        )
        template_df = pd.DataFrame([{
            "_RUTA": "db://cases/00000000-0000-0000-0000-000000000000",
            "MONTO_DEMANDADO": "100000.00",
            "HONORARIOS_PACTADOS": "15000.00",
            "ESTADO_PAGO": "Pendiente",
        }])
        st.download_button(
            "Descargar plantilla CSV",
            data=_csv_bytes(template_df),
            file_name="plantilla_finanzas_import.csv",
            mime="text/csv",
            key=f"{prefix}.template",
            width="stretch",
        )

        uploaded = st.file_uploader(
            "Archivo CSV de finanzas",
            type=["csv"],
            key=f"{prefix}.file",
        )
        if not uploaded:
            return

        file_hash = hashlib.sha1(uploaded.getvalue()).hexdigest()
        if st.session_state.get(hash_key) != file_hash:
            st.session_state[hash_key] = file_hash
            st.session_state.pop(plan_key, None)
            st.session_state.pop(result_key, None)
            st.session_state.pop(confirm_key, None)

        df_csv, parse_error = _read_uploaded_csv(uploaded)
        if parse_error:
            st.error(parse_error)
            return

        st.caption(f"Filas detectadas: {len(df_csv)}")
        st.dataframe(df_csv.head(10), width="stretch", hide_index=True)

        if st.button("Ejecutar dry-run", key=f"{prefix}.dry_run", width="stretch", type="secondary"):
            st.session_state[plan_key] = _build_finanzas_import_plan(df_csv, df_fin)
            st.session_state.pop(result_key, None)

        plan = st.session_state.get(plan_key)
        if not isinstance(plan, dict):
            return

        if plan.get("fatal_error"):
            st.error(str(plan.get("fatal_error")))
            missing_cols = plan.get("missing_columns") or []
            if missing_cols:
                st.caption(f"Faltan columnas: {', '.join(missing_cols)}")
            return

        summary = plan.get("summary", {}) if isinstance(plan.get("summary", {}), dict) else {}
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Total filas", int(summary.get("total", 0)))
        c2.metric("Para actualizar", int(summary.get("to_update", 0)))
        c3.metric("Omitidas", int(summary.get("omitted", 0)))
        c4.metric("Errores", int(summary.get("errors", 0)))

        st.caption("Resultado dry-run por fila")
        dry_rows = plan.get("rows", [])
        if dry_rows:
            st.dataframe(pd.DataFrame(dry_rows), width="stretch", hide_index=True)

        error_rows = [row for row in dry_rows if row.get("Estado") == "ERROR"]
        if error_rows:
            st.caption("Errores detectados en dry-run")
            st.dataframe(pd.DataFrame(error_rows), width="stretch", hide_index=True)

        st.checkbox(
            "Confirmo aplicar la importacion en base de datos",
            key=confirm_key,
            value=False,
        )
        can_apply = bool(summary.get("to_update", 0)) and bool(st.session_state.get(confirm_key, False))
        if st.button(
            "Aplicar importacion",
            key=f"{prefix}.apply",
            width="stretch",
            disabled=not can_apply,
        ):
            st.session_state[result_key] = _apply_finanzas_import_plan(plan, gestor)
            st.cache_data.clear()
            st.session_state.pop("df_full", None)
            if hasattr(gestor, "_cache_casos"):
                gestor._cache_casos = []
            st.rerun()

        result = st.session_state.get(result_key)
        if isinstance(result, dict) and result.get("rows"):
            result_summary = result.get("summary", {}) if isinstance(result.get("summary", {}), dict) else {}
            st.markdown("**Resultado final de aplicacion**")
            st.caption(
                f"Total filas: {int(result_summary.get('total', 0))} | "
                f"Actualizadas: {int(result_summary.get('updated', 0))} | "
                f"Omitidas: {int(result_summary.get('omitted', 0))} | "
                f"Errores: {int(result_summary.get('errors', 0))}"
            )
            st.dataframe(pd.DataFrame(result["rows"]), width="stretch", hide_index=True)


def render_dashboard(gestor: GestorCasos, casos: List[Caso]):
    """Dashboard real: KPIs + acciones rapidas. Sin tablas."""
    start_ui_block_order("Dashboard")
    total = len(casos)
    status_counts = _contar_status(casos) if casos else {"ok": 0, "legacy_incomplete": 0, "error": 0}
    can_gestion, reason_gestion = _route_enabled("Gestion")
    can_agenda, reason_agenda = _route_enabled("Agenda")
    can_finanzas, reason_finanzas = _route_enabled("Finanzas")
    can_auditoria, reason_auditoria = _route_enabled("Auditoria")
    header_meta = [
        f"{total} caso{'s' if total != 1 else ''}",
        f"{status_counts.get('legacy_incomplete', 0)} advertencias",
        f"{status_counts.get('error', 0)} errores",
    ]
    mark_ui_block("Dashboard", "summary")
    section_header("Dashboard", subtitle="Centro de mando", meta=header_meta)

    if not casos:
        mark_ui_block("Dashboard", "actions")
        st.info("No hay casos cargados. Use Gestion para crear el primer caso.")
        if st.button(
            "Ir a Gestion",
            width="stretch",
            key="dash_empty_go_gestion",
            disabled=not can_gestion,
            help=reason_gestion or None,
        ):
            _go_route("Gestion")
        mark_ui_block("Dashboard", "work")
        return

    casos_error = status_counts.get("error", 0)
    casos_legacy_warn = status_counts.get("legacy_incomplete", 0)
    casos_validos = max(0, total - casos_error - casos_legacy_warn)

    cols = st.columns(3)
    with cols[0]:
        kpi_card("Casos vÃ¡lidos", casos_validos, status="OK", tone="good")
    with cols[1]:
        kpi_card("Legacy incompletos", casos_legacy_warn, status="AtenciÃ³n", tone="warn")
    with cols[2]:
        kpi_card("Casos con error", casos_error, status="Revisar", tone="bad")

    mark_ui_block("Dashboard", "actions")
    # Acciones rapidas
    card_begin("Acciones rÃ¡pidas", subtitle="Atajos principales", variant="tight")
    a1, a2, a3, a4 = st.columns(4)

    with a1:
        if st.button(
            "Ir a Gestion (Casos)",
            width="stretch",
            key="dash_go_gestion",
            type="secondary",
            disabled=not can_gestion,
            help=reason_gestion or None,
        ):
            _go_route("Gestion")

    with a2:
        if st.button(
            "Ir a Agenda",
            width="stretch",
            key="dash_go_agenda",
            type="secondary",
            disabled=not can_agenda,
            help=reason_agenda or None,
        ):
            _go_route("Agenda")

    with a3:
        if st.button(
            "Ir a Finanzas",
            width="stretch",
            key="dash_go_finanzas",
            type="secondary",
            disabled=not can_finanzas,
            help=reason_finanzas or None,
        ):
            _go_route("Finanzas")

    with a4:
        if st.button(
            "Ejecutar Auditoria",
            width="stretch",
            key="dash_go_audit",
            type="secondary",
            disabled=not can_auditoria,
            help=reason_auditoria or None,
        ):
            _go_route("Auditoria")

    repair_allowed = has_permission("cases:write")
    with st.container():
        if st.button(
            "Reparar subcarpetas",
            width="stretch",
            key="dash_repair",
            type="secondary",
            disabled=not repair_allowed,
            help="" if repair_allowed else "Sin permiso para estructura de carpetas.",
        ):
            total_creadas = 0
            pb = st.progress(0)
            for i, c in enumerate(casos, start=1):
                total_creadas += gestor.ensure_case_structure(c.ruta)
                pb.progress(int((i / max(1, len(casos))) * 100))
            st.success(f"Reparacion finalizada. Subcarpetas creadas: {total_creadas}.")
            st.cache_data.clear()
    card_end()

    mark_ui_block("Dashboard", "work")
    queue = build_incomplete_case_queue(casos, top_n=10)
    card_begin("Top casos incompletos", subtitle="Prioridad operativa", variant="tight")
    if queue:
        for idx, item in enumerate(queue, start=1):
            missing = ", ".join(item.get("missing_fields", []))
            c_left, c_right = st.columns([0.78, 0.22])
            with c_left:
                st.markdown(
                    f"**{idx}. {item.get('cliente', '')}** - {item.get('causa', '')}  "
                    f"(score {item.get('score', 0)})"
                )
                st.caption(f"Faltantes: {missing}")
            with c_right:
                if st.button(
                    "Abrir",
                    key=f"dash_incomplete_open_{idx}",
                    width="stretch",
                    disabled=not can_gestion,
                    help=reason_gestion or None,
                ):
                    _go_route("Gestion", mode="detalle", item_id=item.get("case_ref", ""))
        if st.button(
            "Ver todos en Gestion",
            key="dash_incomplete_gestion",
            type="secondary",
            width="stretch",
            disabled=not can_gestion,
            help=reason_gestion or None,
        ):
            _go_route("Gestion", mode="listado")
    else:
        st.success("No hay casos con faltantes en los campos objetivo.")
    card_end()

    kpi_snapshot = build_operational_kpi_snapshot(gestor, casos)
    campaign_rows = _campaign_kpi_rows(kpi_snapshot)
    metas_cumplidas = sum(1 for row in campaign_rows if row.get("Cumple"))
    total_metas = len(campaign_rows)
    trend_rows = _load_daily_audit_trend_rows(limit=21)
    weekly_df = _build_weekly_campaign_df(trend_rows)

    card_begin("Campaña de completitud", subtitle="Avance semanal vs metas", variant="tight")
    s1, s2, s3 = st.columns(3)
    with s1:
        kpi_card("Metas cumplidas", f"{metas_cumplidas}/{total_metas}", status="Seguimiento", tone="good" if metas_cumplidas == total_metas else "warn")
    with s2:
        avg_actual = round(sum(float(row.get("Actual %", 0.0)) for row in campaign_rows) / max(1, total_metas), 1)
        kpi_card("Promedio actual", f"{avg_actual}%", status="Actual", tone="good" if avg_actual >= 60 else "warn")
    with s3:
        avg_delta = round(sum(float(row.get("Delta %", 0.0)) for row in campaign_rows) / max(1, total_metas), 1)
        kpi_card("Delta promedio", f"{avg_delta:+.1f} pp", status="Meta", tone="good" if avg_delta >= 0 else "bad")

    if campaign_rows:
        df_campaign = pd.DataFrame(campaign_rows)[["KPI", "Actual %", "Meta %", "Delta %", "Cumple", "Completos", "Total"]]
        df_campaign["Cumple"] = df_campaign["Cumple"].map(lambda v: "Si" if bool(v) else "No")
        st.dataframe(df_campaign, width="stretch", hide_index=True)
    else:
        st.info("No hay datos para calcular avance de campaña.")

    if not weekly_df.empty:
        st.caption("Tendencia semanal (ultimos 7 dias) por KPI de completitud.")
        chart_df = weekly_df.set_index("Fecha")[["FECHA_TAREA", "EXPEDIENTE", "EVENTO/FECHA_EVENTO", "COBERTURA_FINANCIERA"]]
        st.line_chart(chart_df, width="stretch")

        with st.expander("Detalle semanal (metas y brechas)", expanded=False):
            st.dataframe(weekly_df, width="stretch", hide_index=True)
    else:
        st.caption("Sin historial semanal aun. Se alimenta desde auditoria diaria/nocturna.")
    card_end()

    # Actividad / prÃ³ximos vencimientos (compacto, max 5)
    card_begin("Actividad", subtitle="PrÃ³ximos vencimientos (7 dÃ­as)", variant="tight")

    hoy = datetime.now().date()
    tareas_prox = []
    for c in casos:
        fecha = c._parsear_fecha(c.fecha_tarea)
        if fecha and (fecha - hoy).days <= 7:
            tareas_prox.append(c)
    tareas_prox.sort(key=lambda c: c._parsear_fecha(c.fecha_tarea) or hoy)

    if tareas_prox:
        for c in tareas_prox[:5]:
            fecha = c._parsear_fecha(c.fecha_tarea)
            delta_dias = (fecha - hoy).days if fecha else None
            pill_kind = "danger" if delta_dias is not None and delta_dias < 0 else "warn" if delta_dias is not None and delta_dias <= 2 else "default"
            left, right = st.columns([0.8, 0.2])
            with left:
                status_icon = c.semaforo or "â€¢"
                st.markdown(f"{status_icon} **{c.cliente or ''}** - {c.causa or ''}")
                st.caption(c.tarea_pendiente or "Sin tarea registrada")
            with right:
                pill(c.fecha_tarea or "s/d", kind=pill_kind)
        if len(tareas_prox) > 5:
            st.caption(f"... y {len(tareas_prox) - 5} mas. Ver en Agenda.")
    else:
        st.success("Sin vencimientos en los proximos 7 dias.")
    card_end()

    # CTA a AuditorÃ­a (secundario)
    card_begin("Control de datos", subtitle="DiagnÃ³stico completo en AuditorÃ­a", variant="tight")
    st.caption("Salud de datos se revisa en Auditoria.")
    if st.button(
        "Ir a Auditoria de datos",
        key="go_audit_from_dash",
        type="secondary",
        width="stretch",
        disabled=not can_auditoria,
        help=reason_auditoria or None,
    ):
        _go_route("Auditoria")
    card_end()


def _cargar_metricas_auditoria(gestor: GestorCasos, casos: List[Caso]) -> dict:
    """Carga metricas de auditoria desde session_state o calcula basicas."""
    # Si hay resultado reciente en session_state, usarlo
    if "ultimo_resultado_auditoria" in st.session_state:
        metricas_cache = st.session_state["ultimo_resultado_auditoria"].get("metricas", {})
        if metricas_cache:
            return metricas_cache

    # Calcular metricas basicas inline (sin auditoria completa)
    total = len(casos)
    if total == 0:
        return {"casos_total": 0, "completitud": {}}
    return {"casos_total": total, "completitud": _completitud_basica(casos)}


def _persist_daily_audit_snapshot(
    gestor: GestorCasos,
    casos: List[Caso],
    reporte: dict,
    kpi_snapshot: dict,
    source: str,
) -> dict:
    snapshot = build_daily_audit_snapshot(
        gestor,
        casos,
        source=source,
        audit_report=reporte,
        kpi_snapshot=kpi_snapshot,
    )
    snapshot_path = save_daily_audit_snapshot(snapshot)
    history_path = append_daily_audit_history(snapshot)
    return {
        "snapshot": snapshot,
        "snapshot_path": str(snapshot_path),
        "history_path": str(history_path),
        "created": True,
        "date": snapshot.get("date", ""),
    }


def _ensure_daily_audit_snapshot_ui(gestor: GestorCasos, casos: List[Caso]) -> dict:
    today = datetime.now().strftime("%Y-%m-%d")
    check_key = "audit.daily.auto_check_date"
    result_key = "audit.daily.auto_result"
    if st.session_state.get(check_key) == today:
        return st.session_state.get(result_key, {}) or {}

    try:
        result = ensure_daily_audit_snapshot(gestor, casos, source="ui_auto_daily")
    except Exception as exc:
        result = {
            "created": False,
            "date": today,
            "snapshot_path": "",
            "history_path": "",
            "error": str(exc),
        }

    st.session_state[check_key] = today
    st.session_state[result_key] = result
    return result


def _load_daily_audit_trend_rows(limit: int = 14) -> List[Dict]:
    try:
        return load_daily_audit_history(limit=max(0, int(limit)), collapse_by_date=True)
    except Exception:
        return []


def _campaign_kpi_rows(kpi_snapshot: dict) -> List[Dict]:
    kpi_data = kpi_snapshot.get("kpis", {}) if isinstance(kpi_snapshot, dict) else {}
    metric_labels = [
        ("FECHA_TAREA", "FECHA_TAREA"),
        ("EXPEDIENTE", "EXPEDIENTE"),
        ("EVENTO_FECHA_EVENTO", "EVENTO/FECHA_EVENTO"),
        ("COBERTURA_FINANCIERA", "COBERTURA_FINANCIERA"),
    ]
    rows = []
    for metric_key, label in metric_labels:
        metric = kpi_data.get(metric_key, {}) or {}
        actual = float(metric.get("pct", 0.0))
        target = float(metric.get("target_pct", 0.0))
        gap = float(metric.get("gap_pct", actual - target))
        rows.append({
            "metric_key": metric_key,
            "KPI": label,
            "Actual %": round(actual, 1),
            "Meta %": round(target, 1),
            "Delta %": round(gap, 1),
            "Cumple": bool(metric.get("goal_met", actual >= target)),
            "Completos": int(metric.get("completed", 0)),
            "Total": int(metric.get("total", 0)),
        })
    return rows


def _build_weekly_campaign_df(trend_rows: List[Dict]) -> pd.DataFrame:
    if not trend_rows:
        return pd.DataFrame()

    window = []
    for row in trend_rows[-7:]:
        window.append({
            "Fecha": str(row.get("date", "")),
            "FECHA_TAREA": float(row.get("kpi_fecha_tarea_pct", 0.0)),
            "EXPEDIENTE": float(row.get("kpi_expediente_pct", 0.0)),
            "EVENTO/FECHA_EVENTO": float(row.get("kpi_evento_fecha_evento_pct", 0.0)),
            "COBERTURA_FINANCIERA": float(row.get("kpi_cobertura_financiera_pct", 0.0)),
            "Errores": int(row.get("errores", 0)),
            "Warnings": int(row.get("warnings", 0)),
        })

    df = pd.DataFrame(window).sort_values("Fecha")
    return df


# Ã¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢Â
# SPRINT 3: GESTION (Maestro-detalle)
# Ã¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢Â

def render_gestion(gestor: GestorCasos, casos: List[Caso], df: pd.DataFrame | None):
    """Gestion: pipeline fijo (header > seccion > modo > toolbar > cuerpo)."""
    start_ui_block_order("Gestion")
    st.markdown("<style>.main .block-container { max-width: 100% !important; }</style>", unsafe_allow_html=True)

    if not st.session_state.get("db_ready", True):
        mark_ui_block("Gestion", "summary")
        health = st.session_state.get("db_health", {}) or {}
        detail = health.get("last_error") or "No se pudo validar conexiÃ³n."
        st.error("GestiÃ³n no disponible: base de datos fuera de lÃ­nea.")
        st.caption(f"Detalle: {detail}")
        mark_ui_block("Gestion", "actions")
        if st.button("Reintentar conexiÃ³n", key="gestion.retry.db", width="stretch"):
            st.session_state["db_ready"] = None
            st.session_state["db_health"] = {}
            st.rerun()
        mark_ui_block("Gestion", "work")
        st.stop()

    _ginit_defaults()
    section = _current_gestion_section()
    mode = _current_gestion_mode(section)
    if section not in GESTION_WORK_SECTIONS:
        fallback_mode = _normalize_mode(_gget(_gk("mode", "casos"), "listado"))
        _go(section="casos", mode=fallback_mode)
        return
    _save_tab_snapshot(section)

    _dbg(
        "gestion:render:start",
        section=section,
        mode=mode,
        selected_case_id=_gget(_selected_state_key("casos"), ""),
        **_gestion_filter_debug_values(),
    )

    # (i) Header del modulo.
    selected_for_section = _selected_value_for_section(section)
    header_meta = [
        f"{len(casos)} casos",
        f"Seccion {GESTION_WORK_SECTIONS.get(section, 'Casos')}",
        f"Modo {GESTION_MODE_LABELS.get(mode, 'Listado')}",
        f"Seleccion {selected_for_section or 'ninguna'}",
    ]
    mark_ui_block("Gestion", "summary")
    section_header("Gestion", subtitle="Operacion diaria de casos y clientes", meta=header_meta)

    # (ii) Barra primaria de seccion.
    mark_ui_block("Gestion", "actions")
    tab_label_key = _gk("widgets", "tabbar", "label")
    pending_tab_label = st.session_state.pop(_gk("pending", "tabbar", "label"), None)
    valid_tab_labels = set(GESTION_WORK_SECTIONS.values())
    if pending_tab_label in valid_tab_labels:
        st.session_state[tab_label_key] = pending_tab_label
    elif st.session_state.get(tab_label_key) not in valid_tab_labels:
        st.session_state[tab_label_key] = GESTION_WORK_SECTIONS.get(section, "Casos")

    selected_section = vg_toolbar(
        list(GESTION_WORK_SECTIONS.items()),
        section,
        key=_gk("widgets", "tabbar"),
        label="Seccion",
    )
    if selected_section != section:
        _go(section=selected_section)
        return

    # (iii) Barra secundaria de modo.
    mode_label_key = _gk("widgets", "modebar", section, "label")
    pending_mode_label = st.session_state.pop(_gk("pending", "modebar", section, "label"), None)
    valid_mode_labels = set(GESTION_MODE_LABELS.values())
    if pending_mode_label in valid_mode_labels:
        st.session_state[mode_label_key] = pending_mode_label
    elif st.session_state.get(mode_label_key) not in valid_mode_labels:
        st.session_state[mode_label_key] = GESTION_MODE_LABELS.get(mode, "Listado")

    selected_mode = vg_modebar(
        [("listado", "Listado"), ("detalle", "Detalle"), ("editar", "Editar")],
        mode,
        key=_gk("widgets", "modebar", section),
        label="Modo",
    )
    if selected_mode in {"detalle", "editar"} and not _has_selection_for_section(section):
        st.info("Seleccione un registro en Listado para pasar a Detalle o Editar.")
        _go(section=section, mode="listado")
        return
    if selected_mode != mode:
        _go(section=section, mode=selected_mode)
        return

    mode = selected_mode

    # (iv) Toolbar contextual.
    _render_gestion_context_toolbar(section, mode)

    # (v) Cuerpo exclusivo de seccion + modo.
    mark_ui_block("Gestion", "work")
    if section == "casos":
        if df is not None and not df.empty:
            if st.session_state.get("gestion.casos.show_new_form", False) and mode != "editar":
                _render_crear_caso(gestor)
            render_modulo_casos(df, gestor, mode)
        else:
            vg_empty_state(
                "No hay casos cargados todavÃ­a.",
                "Nuevo caso",
                lambda: st.session_state.__setitem__("gestion.casos.show_new_form", True),
                key="gestion.empty.casos.crear",
            )
            _render_crear_caso(gestor)
    elif section == "clientes":
        if casos:
            render_modulo_cliente(gestor, casos, mode)
        else:
            vg_empty_state(
                "No hay clientes disponibles porque aÃºn no existen casos.",
                "Ir a Casos",
                lambda: _go(section="casos", mode="listado"),
                key="gestion.empty.clientes",
            )
    else:
        _go(section="casos", mode="listado")
        return

    _save_tab_snapshot(section)
    _dbg(
        "gestion:render:end",
        section=section,
        mode=_current_gestion_mode(section),
        selected_case_id=_gget(_selected_state_key("casos"), ""),
        **_gestion_filter_debug_values(),
    )


def _prepare_standalone_section(section: str) -> tuple[str, str]:
    sec = _normalize_section(section)
    _ginit_defaults()

    route_mode = _normalize_mode(
        st.session_state.get("route_mode", _gget(_gk("mode", sec), "listado")),
        fallback="listado",
    )
    incoming_raw = st.session_state.pop("selected_item_id", None)
    incoming = _canonical_case_ref(incoming_raw) if incoming_raw is not None else ""
    if incoming:
        _set_selected_for_section(sec, incoming, stage=f"route:{sec}")

    current_section = _current_gestion_section()
    current_mode = _current_gestion_mode(sec)
    if current_section != sec or current_mode != route_mode or incoming:
        _go(section=sec, mode=route_mode, selected_id=incoming or None, rerun=False)

    mode = _current_gestion_mode(sec)
    return sec, mode


def _render_standalone_modebar(section: str, mode: str) -> str:
    mode_label_key = _gk("widgets", "modebar", section, "label")
    pending_mode_label = st.session_state.pop(_gk("pending", "modebar", section, "label"), None)
    valid_mode_labels = set(GESTION_MODE_LABELS.values())
    if pending_mode_label in valid_mode_labels:
        st.session_state[mode_label_key] = pending_mode_label
    elif st.session_state.get(mode_label_key) not in valid_mode_labels:
        st.session_state[mode_label_key] = GESTION_MODE_LABELS.get(mode, "Listado")

    selected_mode = vg_modebar(
        [("listado", "Listado"), ("detalle", "Detalle"), ("editar", "Editar")],
        mode,
        key=_gk("widgets", "modebar", section),
        label="Modo",
    )
    if selected_mode in {"detalle", "editar"} and not _has_selection_for_section(section):
        st.info("Primero seleccione un registro desde Listado.")
        _go(section=section, mode="listado")
        return ""
    if selected_mode != mode:
        _go(section=section, mode=selected_mode)
        return ""
    return selected_mode


def render_agenda(gestor: GestorCasos, casos: List[Caso]):
    st.markdown("<style>.main .block-container { max-width: 100% !important; }</style>", unsafe_allow_html=True)
    section, mode = _prepare_standalone_section("agenda")

    total_tareas = 0
    tareas_7d = 0
    hoy = datetime.now().date()
    for caso in casos:
        fecha = caso._parsear_fecha(caso.fecha_tarea)
        if not fecha:
            continue
        total_tareas += 1
        if 0 <= (fecha - hoy).days <= 7:
            tareas_7d += 1
    mode_state = {"selected": ""}

    def _summary() -> None:
        section_header(
            "Agenda",
            subtitle="Planificacion de tareas y vencimientos",
            meta=[f"Tareas {total_tareas}", f"Proximas 7 dias {tareas_7d}", f"Modo {GESTION_MODE_LABELS.get(mode, 'Listado')}"],
        )

    def _actions() -> None:
        selected_mode = _render_standalone_modebar(section, mode)
        mode_state["selected"] = selected_mode
        if not selected_mode:
            return
        _render_gestion_context_toolbar(section, selected_mode)

    def _work() -> None:
        selected_mode = mode_state.get("selected", "")
        if not selected_mode:
            return
        if casos:
            render_modulo_agenda(gestor, casos, selected_mode)
        else:
            vg_empty_state(
                "No hay tareas para mostrar en Agenda.",
                "Ir a Casos",
                lambda: _go_route("Gestion", mode="listado"),
                key="agenda.route.empty",
            )
        _save_tab_snapshot(section)

    render_module_frame("Agenda", _summary, _actions, _work)


def render_finanzas(gestor: GestorCasos, casos: List[Caso]):
    st.markdown("<style>.main .block-container { max-width: 100% !important; }</style>", unsafe_allow_html=True)
    section, mode = _prepare_standalone_section("finanzas")

    mode_state = {"selected": ""}

    def _summary() -> None:
        section_header(
            "Finanzas",
            subtitle="Resumen economico y estado de cobros",
            meta=[
                f"Casos {len(casos)}",
                f"Modo {GESTION_MODE_LABELS.get(mode, 'Listado')}",
                f"Auto-guardado {'ON' if _auto_save_changes_enabled() else 'OFF'}",
            ],
        )

    def _actions() -> None:
        selected_mode = _render_standalone_modebar(section, mode)
        mode_state["selected"] = selected_mode
        if not selected_mode:
            return
        _render_gestion_context_toolbar(section, selected_mode)

    def _work() -> None:
        selected_mode = mode_state.get("selected", "")
        if not selected_mode:
            return
        if casos:
            render_modulo_finanzas(gestor, casos, selected_mode)
        else:
            vg_empty_state(
                "No hay datos financieros porque aun no existen casos.",
                "Ir a Casos",
                lambda: _go_route("Gestion", mode="listado"),
                key="finanzas.route.empty",
            )
        _save_tab_snapshot(section)

    render_module_frame("Finanzas", _summary, _actions, _work)


def _render_gestion_context_toolbar(section: str, mode: str):
    sec = _normalize_section(section)
    card_begin("Contexto", subtitle=f"{GESTION_SECTIONS.get(sec, 'Casos')} Â· {GESTION_MODE_LABELS.get(mode, 'Listado')}", variant="tight")
    selected_ref = _selected_value_for_section(sec)
    c1, c2, c3, c4 = st.columns([1.1, 1.1, 1.1, 2.2])
    with c1:
        if sec == "casos" and mode != "editar":
            if st.button("Nuevo Caso", key="gestion.context.casos.nuevo", width="stretch", type="secondary"):
                st.session_state["gestion.casos.show_new_form"] = True
                if mode != "listado":
                    _go(section="casos", mode="listado")
        elif mode != "listado":
            if st.button("Ir a Listado", key=f"gestion.context.{sec}.listado", width="stretch", type="secondary"):
                _go(section=sec, mode="listado")
    with c2:
        if sec in {"casos", "clientes"}:
            can_agenda, reason_agenda = _route_enabled("Agenda")
            if st.button(
                "Ir a Agenda",
                key=f"gestion.context.{sec}.go_agenda",
                width="stretch",
                type="secondary",
                disabled=not can_agenda,
                help=reason_agenda or None,
            ):
                _go_route("Agenda", mode="listado")
        else:
            can_gestion, reason_gestion = _route_enabled("Gestion")
            target_mode = "detalle" if _canonical_case_ref(selected_ref) else "listado"
            if st.button(
                "Ir a Gestion",
                key=f"gestion.context.{sec}.go_gestion",
                width="stretch",
                type="secondary",
                disabled=not can_gestion,
                help=reason_gestion or None,
            ):
                _go_route("Gestion", mode=target_mode, item_id=selected_ref or None)
    with c3:
        if sec in {"agenda", "finanzas"}:
            canonical = _canonical_case_ref(selected_ref)
            can_open = bool(canonical)
            if st.button(
                "Abrir caso",
                key=f"gestion.context.{sec}.open_case",
                width="stretch",
                type="secondary",
                disabled=not can_open,
                help=None if can_open else "Seleccione un registro para abrir el caso.",
            ):
                _go_route("Gestion", mode="detalle", item_id=canonical)
            can_dashboard, reason_dashboard = _route_enabled("Dashboard")
            if st.button(
                "Ir a Dashboard",
                key=f"gestion.context.{sec}.go_dashboard",
                width="stretch",
                type="secondary",
                disabled=not can_dashboard,
                help=reason_dashboard or None,
            ):
                _go_route("Dashboard", mode="listado")
        else:
            can_dashboard, reason_dashboard = _route_enabled("Dashboard")
            if st.button(
                "Ir a Dashboard",
                key=f"gestion.context.{sec}.go_dashboard",
                width="stretch",
                type="secondary",
                disabled=not can_dashboard,
                help=reason_dashboard or None,
            ):
                _go_route("Dashboard", mode="listado")
    with c4:
        if mode == "listado":
            st.caption("Modo de exploracion activa.")
        else:
            st.caption("Modo de trabajo sobre seleccion activa.")
        if sec == "casos":
            sel = _gget(_selected_state_key("casos"), "")
            st.caption(f"Caso seleccionado: {sel or 'Ninguno'}")
        elif sec == "clientes":
            sel = _gget(_selected_state_key("clientes"), "")
            st.caption(f"Cliente seleccionado: {sel or 'Ninguno'}")
        elif sec == "agenda":
            sel = _gget(_selected_state_key("agenda"), "")
            st.caption(f"Tarea seleccionada: {sel or 'Ninguna'}")
        else:
            sel = _gget(_selected_state_key("finanzas"), "")
            st.caption(f"Registro seleccionado: {sel or 'Ninguno'}")
    card_end()


def _render_crear_caso(gestor: GestorCasos):
    """Formulario contextual para crear caso."""
    with st.expander("Nuevo caso", expanded=True):
        formulario_nuevo_caso(st, gestor)
        if st.button("Ocultar formulario", key="gestion.casos.nuevo.ocultar", width="stretch", type="secondary"):
            st.session_state["gestion.casos.show_new_form"] = False
            st.rerun()


# Ã¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢Â
# ORDENAMIENTO Y FILTROS
# Ã¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢Â

def ordenar_por_urgencia(df: pd.DataFrame) -> pd.DataFrame:
    """Ordena casos priorizando urgentes y fecha de tarea."""
    df2 = df.copy()
    orden = {
        SEMAFORO_ICONS["Vencidos"]: 0,
        SEMAFORO_ICONS["PrÃ³ximos"]: 1,
        SEMAFORO_ICONS["En tiempo"]: 2,
        SEMAFORO_ICONS["Sin tarea"]: 3,
    }
    anio_col = _anio_col(df2)
    semaforo_col = _semaforo_col(df2)
    df2["_ORD_SEM"] = df2[semaforo_col].map(orden).fillna(99)
    df2["_FECHA_TAREA_DT"] = pd.to_datetime(df2["FECHA TAREA"], errors="coerce", dayfirst=True)
    sort_cols = ["_ORD_SEM", "_FECHA_TAREA_DT", "CLIENTE", "FUERO", "CAUSA"]
    if anio_col in df2.columns:
        sort_cols.insert(2, anio_col)
    asc_map = {
        "_ORD_SEM": True,
        "_FECHA_TAREA_DT": True,
        anio_col: False,
        "CLIENTE": True,
        "FUERO": True,
        "CAUSA": True,
    }
    asc_values = [asc_map.get(col, True) for col in sort_cols]
    df2 = df2.sort_values(
        by=sort_cols,
        ascending=asc_values,
        kind="mergesort",
        na_position="last",
    )
    return df2.drop(columns=["_ORD_SEM", "_FECHA_TAREA_DT"])


def mostrar_metricas(casos: List[Caso]):
    """Muestra metricas resumidas en la parte superior."""
    total = len(casos)
    activos = sum(1 for c in casos if "Activo" in c.estado or "Activos" in c.estado)
    vencidos = sum(1 for c in casos if c.semaforo == SEMAFORO_ICONS["Vencidos"])
    proximos = sum(1 for c in casos if c.semaforo == SEMAFORO_ICONS["PrÃ³ximos"])

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric("Total Casos", total)
    with col2:
        st.metric("Activos", activos)
    with col3:
        st.metric("Vencidos", vencidos)
    with col4:
        st.metric("PrÃ³ximos", proximos)


def _reset_filtros_casos():
    """Restaura filtros y controles de la vista Gestion > Casos."""
    for name, default in GESTION_FILTER_DEFAULTS.items():
        _gset(_gestion_filter_key(name), default)
    _persist_casos_filter_state()
    _dbg("gestion:filters:reset", **_gestion_filter_debug_values())


def _reset_filtros_agenda():
    """Restaura filtros de Agenda a su estado por defecto."""
    defaults = _section_filter_defaults("agenda")
    if not isinstance(defaults, dict):
        defaults = {"ver": "Todas", "solo_activos": True}
    _gset(_section_filter_state_key("agenda"), defaults)
    _gset("gestion.agenda.filtro.ver", defaults.get("ver", "Todas"))
    _gset("gestion.agenda.filtro.activos", bool(defaults.get("solo_activos", True)))


def mostrar_filtros(df: pd.DataFrame) -> pd.DataFrame:
    """Filtros compactos para Casos (estado namespaced)."""
    _restore_casos_filter_state()
    _ginit_defaults()
    anio_col = _anio_col(df)
    semaforo_col = _semaforo_col(df)

    card_begin("Filtros", subtitle="BÃºsqueda y segmentaciÃ³n", variant="tight")

    busqueda = st.text_input(
        "BÃºsqueda global",
        placeholder="Cliente, causa, expediente, carÃ¡tula...",
        help="Filtra en todos los campos visibles de la tabla",
        key=_gestion_filter_key("busqueda"),
    )

    col1, col2, col3, col4, col5 = st.columns(5)
    with col1:
        anios = ["Todos"] + sorted([v for v in df[anio_col].unique().tolist() if str(v)], reverse=True)
        anio_sel = st.selectbox("AÃ±o", anios, key=_gestion_filter_key("anio"))
    with col2:
        estados = ["Todos"] + ESTADOS_DISPONIBLES
        estado_sel = st.selectbox("Estado", estados, key=_gestion_filter_key("estado"))
    with col3:
        clientes = ["Todos"] + sorted([v for v in df["CLIENTE"].unique().tolist() if str(v)])
        cliente_sel = st.selectbox("Cliente", clientes, key=_gestion_filter_key("cliente"))
    with col4:
        fueros = ["Todos"] + FUEROS_DISPONIBLES
        fuero_sel = st.selectbox("Fuero", fueros, key=_gestion_filter_key("fuero"))
    with col5:
        semaforos = ["Todos", "Vencidos", "PrÃ³ximos", "En tiempo", "Sin tarea"]
        semaforo_sel = st.selectbox("SemÃ¡foro", semaforos, key=_gestion_filter_key("semaforo"))

    ctrl1, ctrl2, ctrl3, ctrl4 = st.columns([1.15, 1, 1, 1])
    with ctrl1:
        st.checkbox("Priorizar urgentes", key=_gestion_filter_key("priorizar_urgentes"))
    with ctrl2:
        st.selectbox("Modo", ["Tabla", "Tarjetas"], key=_gestion_filter_key("modo"))
    with ctrl3:
        st.selectbox("Densidad", ["Compacta", "Confort"], key=_gestion_filter_key("densidad"))
    with ctrl4:
        atajo = st.selectbox(
            "Atajos",
            ["Ninguno", "Solo vencidos", "PrÃ³ximos 7 dÃ­as", "PrÃ³ximos 30 dÃ­as"],
            key=_gestion_filter_key("atajo"),
        )
    if st.button("Limpiar filtros", key="gestion.casos.filters.limpiar", width="stretch", type="secondary"):
        _reset_filtros_casos()
        st.rerun()

    card_end()

    df_filtrado = df.copy()

    if busqueda:
        mask = df_filtrado["_SEARCH"].str.contains(busqueda.strip().lower(), na=False)
        df_filtrado = df_filtrado[mask]

    if anio_sel != "Todos":
        df_filtrado = df_filtrado[df_filtrado[anio_col] == anio_sel]
    if estado_sel != "Todos":
        df_filtrado = df_filtrado[df_filtrado["ESTADO"] == estado_sel]
    if cliente_sel != "Todos":
        df_filtrado = df_filtrado[df_filtrado["CLIENTE"] == cliente_sel]
    if fuero_sel != "Todos":
        df_filtrado = df_filtrado[df_filtrado["FUERO"] == fuero_sel]
    if semaforo_sel != "Todos":
        emoji_map = {
            "Vencidos": SEMAFORO_ICONS["Vencidos"],
            "PrÃ³ximos": SEMAFORO_ICONS["PrÃ³ximos"],
            "En tiempo": SEMAFORO_ICONS["En tiempo"],
            "Sin tarea": SEMAFORO_ICONS["Sin tarea"],
        }
        emoji = emoji_map.get(semaforo_sel, "")
        if emoji:
            df_filtrado = df_filtrado[df_filtrado[semaforo_col] == emoji]

    if atajo == "Solo vencidos":
        df_filtrado = df_filtrado[df_filtrado[semaforo_col] == SEMAFORO_ICONS["Vencidos"]]
    elif atajo in ("PrÃ³ximos 7 dÃ­as", "PrÃ³ximos 30 dÃ­as"):
        try:
            dias = 7 if atajo == "PrÃ³ximos 7 dÃ­as" else 30
            ft = pd.to_datetime(df_filtrado["FECHA TAREA"], errors="coerce", dayfirst=True)
            hoy = pd.Timestamp.now().normalize()
            limite = hoy + pd.Timedelta(days=dias)
            df_filtrado = df_filtrado[(ft >= hoy) & (ft <= limite)]
        except Exception as exc:
            logger.warning("filtro de atajo agenda fallo atajo=%s err=%s", atajo, exc)

    _persist_casos_filter_state()
    return df_filtrado


# Ã¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢Â
# DOCUMENTOS RECIENTES
# Ã¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢Â

def mostrar_documentos_recientes(gestor: GestorCasos, ruta_caso: Path, key_suffix: str = ""):
    """Muestra los ultimos documentos modificados del caso."""
    docs = gestor.listar_documentos_recientes(ruta_caso)
    with st.expander(f"Documentos recientes ({len(docs)})", expanded=False):
        if not docs:
            st.caption("Sin documentos recientes")
            return
        for idx, doc in enumerate(docs):
            c1, c2 = st.columns([6, 2])
            with c1:
                st.caption(f"{doc['filename']}  â€¢  {doc['updated_at']}")
            with c2:
                target = doc.get("open_target")
                if target:
                    if st.button("Abrir", key=f"doc_{key_suffix}_{idx}", width="stretch"):
                        open_path(target)
                else:
                    st.button("Abrir", key=f"doc_{key_suffix}_{idx}", width="stretch", disabled=True, help="Archivo no disponible")


# Ã¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢Â
# ACCIONES
# Ã¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢Â

def accion_guardar_campos(gestor: GestorCasos, ruta_caso: Path, cambios: dict, accion: str):
    """Accion unificada: guardar cambios en ficha, loguear, limpiar cache y rerun."""
    if not _enforce_permission("cases:write", "No tiene permiso para modificar casos."):
        return
    try:
        ok = gestor.actualizar_campos_ficha(ruta_caso, cambios, actor_ctx=_actor_ctx())
    except ValueError as e:
        st.error(str(e))
        return
    if ok:
        st.cache_data.clear()
        # DATA-001: forzar recarga de valores desde disco en proximo render
        for k in list(st.session_state.keys()):
            if k.startswith("gestion.qe."):
                st.session_state.pop(k, None)
        st.success("Actualizacion guardada.")
        _ui_toast("Guardado")
        st.rerun()
    else:
        st.error("No se pudo guardar la actualizacion.")


def accion_completar_tarea(gestor: GestorCasos, ruta_caso: Path):
    """Accion unificada: marcar tarea como completada."""
    cambios = {
        "TAREA_PENDIENTE": "",
        "FECHA_TAREA": "",
        "CONTROL": "Tarea completada",
    }
    accion_guardar_campos(gestor, ruta_caso, cambios, "Tarea completada")


def render_minimum_completion_wizard(gestor: GestorCasos, ruta_caso, case_ref: str, caso_row: dict | None = None):
    """
    Wizard de completitud minima para casos legacy/incompletos.
    Prioriza campos objetivo definidos para recuperacion operativa.
    """
    try:
        ficha = gestor._leer_ficha(ruta_caso)
    except ValueError as e:
        st.error(str(e))
        return

    status_payload = {campo: ficha.get(campo, "") for campo in CAMPOS_FICHA}
    if isinstance(caso_row, dict):
        if "is_legacy" in caso_row:
            status_payload["is_legacy"] = bool(caso_row.get("is_legacy"))
        if "fs_path" in caso_row and caso_row.get("fs_path"):
            status_payload["fs_path"] = str(caso_row.get("fs_path"))

    status_info = case_status(status_payload)
    missing_minimum = [f for f in status_info.get("missing_minimum", []) if f in DEFAULT_INCOMPLETE_FIELDS]
    missing_quality = [f for f in status_info.get("missing_quality", []) if f in DEFAULT_INCOMPLETE_FIELDS]
    wizard_fields = missing_minimum + [f for f in missing_quality if f not in missing_minimum]

    card_begin("Wizard: Completar mÃ­nimos", subtitle="Campos objetivo del caso", variant="tight")

    if not wizard_fields:
        st.success("Este caso no tiene faltantes en los campos objetivo.")
        card_end()
        return

    labels = {
        "RESPONSABLE": "Responsable",
        "EXPEDIENTE": "Expediente",
        "EVENTO": "Ãšltimo evento",
        "FECHA_EVENTO": "Fecha evento",
        "TAREA_PENDIENTE": "Tarea pendiente",
        "FECHA_TAREA": "Fecha tarea",
    }
    date_fields = {"FECHA_EVENTO", "FECHA_TAREA"}
    if missing_minimum:
        st.warning("Faltan campos mÃ­nimos obligatorios. Complete este bloque para normalizar el caso.")
    else:
        st.info("El mÃ­nimo obligatorio estÃ¡ cubierto. Puede completar faltantes de calidad para mejorar agenda/reportes.")

    st.caption(f"Pendientes: {', '.join(wizard_fields)}")
    st.caption("Fechas admitidas: DD/MM/YYYY, YYYY-MM-DD, DD-MM-YYYY o DD.MM.YYYY.")

    safe_case = re.sub(r"[^a-zA-Z0-9]+", "_", str(case_ref or "case")).strip("_")
    safe_case = safe_case[-80:] if safe_case else "case"
    prefix = f"gestion.casos.minwizard.{safe_case}"
    case_key = f"{prefix}.case_ref"

    if st.session_state.get(case_key) != case_ref:
        st.session_state[case_key] = case_ref
        for field in wizard_fields:
            state_key = f"{prefix}.{field.lower()}"
            value = ficha.get(field, "")
            if field in date_fields:
                st.session_state[state_key] = _normalize_date_value(value)
            else:
                st.session_state[state_key] = _normalize_text_value(value)

    save_clicked = False
    reset_clicked = False
    with st.form(f"{prefix}.form", clear_on_submit=False):
        for field in wizard_fields:
            state_key = f"{prefix}.{field.lower()}"
            label = labels.get(field, field.replace("_", " ").title())
            if field in date_fields:
                st.text_input(f"{label} (DD/MM/YYYY)", key=state_key)
            else:
                st.text_input(label, key=state_key)

        b1, b2 = st.columns(2)
        with b1:
            save_clicked = st.form_submit_button(
                "Guardar mÃ­nimos",
                key=f"{prefix}.save",
                width="stretch",
            )
        with b2:
            reset_clicked = st.form_submit_button(
                "Restaurar valores",
                key=f"{prefix}.reset",
                width="stretch",
                type="secondary",
            )

    if reset_clicked:
        for field in wizard_fields:
            state_key = f"{prefix}.{field.lower()}"
            value = ficha.get(field, "")
            if field in date_fields:
                st.session_state[state_key] = _normalize_date_value(value)
            else:
                st.session_state[state_key] = _normalize_text_value(value)
        st.rerun()
        return

    if save_clicked:
        cambios = {}
        baseline = {}
        invalid_dates: List[str] = []

        for field in wizard_fields:
            state_key = f"{prefix}.{field.lower()}"
            new_raw = st.session_state.get(state_key, "")
            old_raw = ficha.get(field, "")

            if field in date_fields:
                if not _is_valid_supported_date(new_raw):
                    invalid_dates.append(labels.get(field, field))
                    continue
                cambios[field] = _normalize_date_value(new_raw)
                baseline[field] = _normalize_date_value(old_raw)
            else:
                cambios[field] = _normalize_text_value(new_raw)
                baseline[field] = _normalize_text_value(old_raw)

        if invalid_dates:
            st.error(f"Formato de fecha invÃ¡lido en: {', '.join(invalid_dates)}.")
            card_end()
            return

        if cambios == baseline:
            st.info("Sin cambios para guardar en el wizard.")
            card_end()
            return

        try:
            ok = gestor.actualizar_campos_ficha(ruta_caso, cambios, actor_ctx=_actor_ctx())
        except ValueError as e:
            st.error(str(e))
            card_end()
            return

        if not ok:
            st.error("No se pudo guardar la actualizaciÃ³n de mÃ­nimos.")
            card_end()
            return

        st.cache_data.clear()
        st.session_state.pop("df_full", None)
        if hasattr(gestor, "_cache_casos"):
            gestor._cache_casos = []
        _ui_toast("MÃ­nimos actualizados")
        st.success("Campos mÃ­nimos guardados.")
        _go(section="casos", mode="detalle", selected_id=case_ref)

    card_end()


def render_quick_edit(gestor: GestorCasos, ruta_caso: Path, key_suffix: str):
    """EdiciÃ³n rÃ¡pida unificada - un solo punto de mantenimiento (DATA-001)."""
    ruta_str = str(ruta_caso)
    state_key = f"gestion.qe.{key_suffix}.case_ref"
    resp_key = f"gestion.qe.{key_suffix}.responsable"
    tarea_key = f"gestion.qe.{key_suffix}.tarea"
    fecha_key = f"gestion.qe.{key_suffix}.fecha"
    obs_key = f"gestion.qe.{key_suffix}.observaciones"
    saved_snapshot_key = f"gestion.qe.{key_suffix}.last_saved"

    # Reset widgets cuando cambia el caso seleccionado
    if st.session_state.get(state_key) != ruta_str:
        st.session_state[state_key] = ruta_str
        try:
            ficha = gestor._leer_ficha(ruta_caso)
        except ValueError as e:
            st.error(str(e))
            return
        st.session_state[resp_key] = ficha.get('RESPONSABLE', '')
        st.session_state[tarea_key] = ficha.get('TAREA_PENDIENTE', '')
        st.session_state[fecha_key] = ficha.get('FECHA_TAREA', '')
        st.session_state[obs_key] = ficha.get('OBSERVACIONES', '')
        st.session_state[saved_snapshot_key] = {
            "RESPONSABLE": _normalize_text_value(ficha.get('RESPONSABLE', '')),
            "TAREA_PENDIENTE": _normalize_text_value(ficha.get('TAREA_PENDIENTE', '')),
            "FECHA_TAREA": _normalize_date_value(ficha.get('FECHA_TAREA', '')),
            "OBSERVACIONES": _normalize_text_value(ficha.get('OBSERVACIONES', '')),
        }

    st.markdown("#### Edicion rapida")
    qe_resp = st.text_input("Responsable", key=resp_key)
    qe_tarea = st.text_input("Tarea Pendiente", key=tarea_key)
    qe_fecha = st.text_input("Fecha Tarea (DD/MM/YYYY)", key=fecha_key)
    qe_obs = st.text_area("Observaciones", key=obs_key)

    auto_save_mode = _auto_save_changes_enabled()
    current_changes = {
        "RESPONSABLE": _normalize_text_value(qe_resp),
        "TAREA_PENDIENTE": _normalize_text_value(qe_tarea),
        "FECHA_TAREA": _normalize_date_value(qe_fecha),
        "OBSERVACIONES": _normalize_text_value(qe_obs),
    }

    if auto_save_mode:
        st.caption("Guardado automatico activado (VG_AUTO_SAVE_CHANGES=1).")
        if not _is_valid_supported_date(qe_fecha):
            st.warning("Fecha tarea invalida. Use DD/MM/YYYY, YYYY-MM-DD, DD-MM-YYYY o DD.MM.YYYY.")
        else:
            baseline = st.session_state.get(saved_snapshot_key, {})
            if not isinstance(baseline, dict):
                baseline = {}
            if current_changes != baseline:
                if _enforce_permission("cases:write", "No tiene permiso para modificar casos."):
                    try:
                        ok = gestor.actualizar_campos_ficha(
                            ruta_caso,
                            current_changes,
                            actor_ctx=_actor_ctx(),
                        )
                    except ValueError as e:
                        st.error(str(e))
                        ok = False
                    if ok:
                        st.session_state[saved_snapshot_key] = dict(current_changes)
                        st.cache_data.clear()
                        st.session_state.pop("df_full", None)
                        if hasattr(gestor, "_cache_casos"):
                            gestor._cache_casos = []
                        _ui_toast("Auto-guardado")
                        st.caption(f"Auto-guardado: {datetime.now().strftime('%H:%M:%S')}")
                    else:
                        st.error("No se pudo auto-guardar la actualizacion.")

    b1, b2 = st.columns(2)
    with b1:
        if auto_save_mode:
            st.button(
                "Guardar",
                key=f"gestion.qe.{key_suffix}.guardar.disabled",
                width="stretch",
                disabled=True,
                help="Guardado automatico activo.",
            )
        else:
            if st.button("Guardar", key=f"gestion.qe.{key_suffix}.guardar", width="stretch"):
                cambios = {
                    'RESPONSABLE': qe_resp,
                    'TAREA_PENDIENTE': qe_tarea,
                    'FECHA_TAREA': qe_fecha,
                    'OBSERVACIONES': qe_obs,
                }
                st.session_state[saved_snapshot_key] = {
                    "RESPONSABLE": _normalize_text_value(qe_resp),
                    "TAREA_PENDIENTE": _normalize_text_value(qe_tarea),
                    "FECHA_TAREA": _normalize_date_value(qe_fecha),
                    "OBSERVACIONES": _normalize_text_value(qe_obs),
                }
                accion_guardar_campos(gestor, ruta_caso, cambios, f"Edicion rapida ({key_suffix})")
    with b2:
        if st.button("Tarea completada", key=f"gestion.qe.{key_suffix}.done", width="stretch", type="secondary"):
            accion_completar_tarea(gestor, ruta_caso)


# Ã¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢Â
# MODULO CASOS (Sprint 3: maestro-detalle)
# Ã¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢Â

def render_modulo_casos(df: pd.DataFrame, gestor: GestorCasos, mode: str = "listado"):
    """MÃ³dulo Casos: cuerpo exclusivo por modo."""
    if mode == "listado":
        df_filtrado = mostrar_filtros(df)
        if bool(_gget(_gestion_filter_key("priorizar_urgentes"), True)):
            df_filtrado = ordenar_por_urgencia(df_filtrado)
    else:
        df_filtrado = df

    if mode == "listado":
        _render_casos_listado_v3(df_filtrado, gestor)
    elif mode == "detalle":
        if not _require_selected("case"):
            return
        _render_casos_detalle_v3(df_filtrado, gestor)
    elif mode == "editar":
        if not _require_selected("case"):
            return
        _render_casos_editar_v3(df_filtrado, gestor)


def _build_batch_incomplete_candidates(df: pd.DataFrame) -> List[Dict[str, object]]:
    if df is None or df.empty or "_RUTA" not in df.columns:
        return []

    field_col_map = {
        "RESPONSABLE": "RESPONSABLE",
        "EXPEDIENTE": "EXPEDIENTE",
        "EVENTO": "EVENTO",
        "FECHA_EVENTO": "FECHA EVENTO",
        "TAREA_PENDIENTE": "TAREA PENDIENTE",
        "FECHA_TAREA": "FECHA TAREA",
    }
    resolved_cols = {f: _resolve_col(df, col_name) for f, col_name in field_col_map.items()}

    rows: List[Dict[str, object]] = []
    for _, row in df.iterrows():
        case_ref = _canonical_case_ref(row.get("_RUTA", ""))
        if not case_ref:
            continue

        missing_fields: List[str] = []
        for field, col_name in resolved_cols.items():
            value = row.get(col_name, "")
            if is_blank(value):
                missing_fields.append(field)

        if not missing_fields:
            continue

        score = sum(DEFAULT_INCOMPLETE_WEIGHTS.get(field, 1) for field in missing_fields)
        rows.append({
            "case_ref": case_ref,
            "cliente": str(row.get(_resolve_col(df, "CLIENTE"), "") or ""),
            "causa": str(row.get(_resolve_col(df, "CAUSA"), "") or ""),
            "missing_fields": missing_fields,
            "missing_count": len(missing_fields),
            "score": score,
        })

    rows.sort(
        key=lambda item: (
            -int(item.get("score", 0)),
            -int(item.get("missing_count", 0)),
            str(item.get("cliente", "")).upper(),
            str(item.get("causa", "")).upper(),
        )
    )
    return rows


def _render_batch_apply_panel(df: pd.DataFrame, gestor: GestorCasos):
    """
    Aplicacion rapida (batch controlado):
    - seleccion 5/10/20
    - previsualizacion
    - aplicacion con log de actualizados/omitidos
    """
    with st.expander("AplicaciÃ³n rÃ¡pida (batch controlado)", expanded=False):
        candidates = _build_batch_incomplete_candidates(df)
        if not candidates:
            st.success("No hay casos candidatos para aplicaciÃ³n rÃ¡pida.")
            return

        prefix = "gestion.casos.batch"
        size = st.selectbox("Seleccionar lote", [5, 10, 20], key=f"{prefix}.size")
        top = candidates[: int(size)]
        top_df = pd.DataFrame([
            {
                "Cliente": item["cliente"],
                "Causa": item["causa"],
                "Faltantes": ", ".join(item["missing_fields"]),
                "Score": item["score"],
                "Caso": item["case_ref"],
            }
            for item in top
        ])
        st.caption("Top candidatos por criticidad (segÃºn faltantes objetivo).")
        st.dataframe(top_df, width="stretch", hide_index=True)

        labels = {
            f"{idx+1}. {item['cliente']} - {item['causa']} (score {item['score']})": item
            for idx, item in enumerate(top)
        }
        default_labels = list(labels.keys())[: min(3, len(labels))]
        selected_labels = st.multiselect(
            "Casos a incluir en el lote",
            options=list(labels.keys()),
            default=default_labels,
            key=f"{prefix}.selected",
        )
        selected_cases = [labels[label] for label in selected_labels]

        st.markdown("**Campos a aplicar en lote**")
        c1, c2 = st.columns(2)
        with c1:
            responsable = st.text_input("Responsable", key=f"{prefix}.field.responsable")
            evento = st.text_input("Ãšltimo evento", key=f"{prefix}.field.evento")
            fecha_evento = st.text_input("Fecha evento (DD/MM/YYYY)", key=f"{prefix}.field.fecha_evento")
        with c2:
            tarea = st.text_input("Tarea pendiente", key=f"{prefix}.field.tarea")
            fecha_tarea = st.text_input("Fecha tarea (DD/MM/YYYY)", key=f"{prefix}.field.fecha_tarea")
            overwrite = st.checkbox("Sobrescribir valores existentes", value=False, key=f"{prefix}.overwrite")

        payload = {
            "RESPONSABLE": responsable,
            "EVENTO": evento,
            "FECHA_EVENTO": fecha_evento,
            "TAREA_PENDIENTE": tarea,
            "FECHA_TAREA": fecha_tarea,
        }
        date_fields = {"FECHA_EVENTO", "FECHA_TAREA"}

        if st.button("Previsualizar lote", key=f"{prefix}.preview", width="stretch", type="secondary"):
            if not selected_cases:
                st.warning("Seleccione al menos un caso para previsualizar.")
            else:
                invalid_dates = []
                for field in date_fields:
                    if payload.get(field) and not _is_valid_supported_date(payload.get(field)):
                        invalid_dates.append(field)

                if invalid_dates:
                    st.error(f"Formato de fecha invÃ¡lido en: {', '.join(invalid_dates)}.")
                else:
                    apply_rows = []
                    skip_rows = []
                    for item in selected_cases:
                        case_ref = item["case_ref"]
                        ruta_repo = _to_repo_path(case_ref)
                        try:
                            ficha = gestor._leer_ficha(ruta_repo)
                        except ValueError as e:
                            skip_rows.append({
                                "case_ref": case_ref,
                                "cliente": item["cliente"],
                                "causa": item["causa"],
                                "motivo": str(e),
                            })
                            continue

                        cambios = {}
                        for field, new_raw in payload.items():
                            new_norm = _normalize_date_value(new_raw) if field in date_fields else _normalize_text_value(new_raw)
                            if not new_norm:
                                continue

                            current_raw = ficha.get(field, "")
                            current_norm = _normalize_date_value(current_raw) if field in date_fields else _normalize_text_value(current_raw)
                            if not overwrite and not is_blank(current_norm):
                                continue
                            if new_norm != current_norm:
                                cambios[field] = new_norm

                        if cambios:
                            apply_rows.append({
                                "case_ref": case_ref,
                                "cliente": item["cliente"],
                                "causa": item["causa"],
                                "cambios": cambios,
                            })
                        else:
                            skip_rows.append({
                                "case_ref": case_ref,
                                "cliente": item["cliente"],
                                "causa": item["causa"],
                                "motivo": "Sin cambios aplicables",
                            })

                    st.session_state[f"{prefix}.plan"] = {
                        "apply_rows": apply_rows,
                        "skip_rows": skip_rows,
                    }

        plan = st.session_state.get(f"{prefix}.plan", {})
        apply_rows = plan.get("apply_rows", []) if isinstance(plan, dict) else []
        skip_rows = plan.get("skip_rows", []) if isinstance(plan, dict) else []

        if apply_rows or skip_rows:
            st.markdown("**PrevisualizaciÃ³n**")
            if apply_rows:
                prev_apply_df = pd.DataFrame([
                    {
                        "Cliente": row["cliente"],
                        "Causa": row["causa"],
                        "Cambios": ", ".join(f"{k}={v}" for k, v in row["cambios"].items()),
                        "Caso": row["case_ref"],
                    }
                    for row in apply_rows
                ])
                st.dataframe(prev_apply_df, width="stretch", hide_index=True)
            if skip_rows:
                prev_skip_df = pd.DataFrame([
                    {
                        "Cliente": row["cliente"],
                        "Causa": row["causa"],
                        "Motivo": row["motivo"],
                        "Caso": row["case_ref"],
                    }
                    for row in skip_rows
                ])
                st.caption("Omitidos en previsualizaciÃ³n")
                st.dataframe(prev_skip_df, width="stretch", hide_index=True)

            if st.button("Aplicar lote", key=f"{prefix}.apply", width="stretch", disabled=not apply_rows):
                if not _enforce_permission("cases:write", "No tiene permiso para aplicar cambios en lote."):
                    return
                updated = 0
                omitted = len(skip_rows)
                errors = 0
                result_rows = []

                for row in apply_rows:
                    case_ref = row["case_ref"]
                    ruta_repo = _to_repo_path(case_ref)
                    try:
                        ok = gestor.actualizar_campos_ficha(
                            ruta_repo,
                            row["cambios"],
                            actor_ctx=_actor_ctx(),
                        )
                    except ValueError as e:
                        errors += 1
                        result_rows.append({
                            "Cliente": row["cliente"],
                            "Causa": row["causa"],
                            "Estado": "ERROR",
                            "Detalle": str(e),
                            "Caso": case_ref,
                        })
                        continue

                    if ok:
                        updated += 1
                        result_rows.append({
                            "Cliente": row["cliente"],
                            "Causa": row["causa"],
                            "Estado": "ACTUALIZADO",
                            "Detalle": ", ".join(row["cambios"].keys()),
                            "Caso": case_ref,
                        })
                    else:
                        omitted += 1
                        result_rows.append({
                            "Cliente": row["cliente"],
                            "Causa": row["causa"],
                            "Estado": "OMITIDO",
                            "Detalle": "No se pudo guardar",
                            "Caso": case_ref,
                        })

                st.session_state[f"{prefix}.result"] = {
                    "updated": updated,
                    "omitted": omitted,
                    "errors": errors,
                    "rows": result_rows,
                }
                st.cache_data.clear()
                st.session_state.pop("df_full", None)
                if hasattr(gestor, "_cache_casos"):
                    gestor._cache_casos = []
                st.rerun()

        result = st.session_state.get(f"{prefix}.result", {})
        if isinstance(result, dict) and result.get("rows"):
            st.markdown("**Resultado Ãºltimo lote**")
            st.caption(
                f"Actualizados: {result.get('updated', 0)} | "
                f"Omitidos: {result.get('omitted', 0)} | "
                f"Errores: {result.get('errors', 0)}"
            )
            st.dataframe(pd.DataFrame(result["rows"]), width="stretch", hide_index=True)


def _render_casos_listado_v3(df: pd.DataFrame, gestor: GestorCasos):
    """Modo Listado: filtros arriba, acciones/exportes debajo, tabla al final."""
    modo = _gget(_gestion_filter_key("modo"), "Tabla")
    densidad = _gget(_gestion_filter_key("densidad"), "Compacta")
    if densidad not in ("Compacta", "Confort"):
        densidad = "Compacta"
        _gset(_gestion_filter_key("densidad"), densidad)
    wrap = bool(_gget(_gestion_filter_key("wrap"), False))
    _gset(_gestion_filter_key("wrap"), wrap)

    df_full = st.session_state.get("df_full", df)
    sem_col = _semaforo_col(df)
    anio_col = _anio_col(df)

    card_begin("Acciones y exportes", subtitle="Descargas y vista de planilla", variant="tight")
    col_csv, col_xlsx, col_regen, col_extra = st.columns([1.4, 1.4, 1.4, 3.2])
    export_allowed = can_export()

    with col_regen:
        if st.button("Regenerar exportes", key="gestion.casos.export.regenerar", width="stretch", type="secondary"):
            _regen_export_ts(["casos_csv", "casos_xlsx"])
            st.cache_data.clear()
            _ui_toast("Exportes regenerados")

    ts_csv = _get_export_ts("casos_csv")
    ts_xlsx = _get_export_ts("casos_xlsx")

    with col_csv:
        csv = _csv_bytes(df_full)
        csv_meta = build_export_metadata("casos_csv", csv)
        st.download_button(
            label="Exportar CSV",
            data=csv,
            file_name=f"reporte_legal_{ts_csv}.csv",
            mime="text/csv",
            width="stretch",
            key="gestion.casos.export.csv",
            disabled=not export_allowed,
            help="" if export_allowed else "Exportes restringidos por rol/política.",
        )
    with col_xlsx:
        planilla_cols = st.session_state.get("gestion.casos.listado.cols")
        if isinstance(planilla_cols, list) and planilla_cols:
            cols_export = [c for c in planilla_cols if c in df_full.columns and not str(c).startswith("_")]
        else:
            cols_export = [c for c in df_full.columns if not str(c).startswith("_")]
        df_export = df_full[cols_export].replace("S/D", "")
        xlsx_bytes = _xlsx_bytes(df_export)
        xlsx_meta = build_export_metadata("casos_xlsx", xlsx_bytes)
        st.download_button(
            label="Exportar Excel",
            data=xlsx_bytes,
            file_name=f"reporte_legal_{ts_xlsx}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            width="stretch",
            key="gestion.casos.export.xlsx",
            disabled=not export_allowed,
            help="" if export_allowed else "Exportes restringidos por rol/política.",
        )
    with col_extra:
        st.checkbox("Ajustar texto", key=_gestion_filter_key("wrap"))
        st.caption(f"{len(df)} casos Â· {modo} Â· Densidad {densidad}")
        st.caption(f"CSV sha256: {csv_meta['sha256'][:12]}...")
        st.caption(f"XLSX sha256: {xlsx_meta['sha256'][:12]}...")
    card_end()

    wrap = bool(_gget(_gestion_filter_key("wrap"), False))
    if wrap:
        st.markdown(
            """
        <style>
        div[data-testid="stDataFrame"] * { font-size: 13px !important; }
        div[data-testid="stDataFrame"] [role="grid"] div,
        div[data-testid="stDataFrame"] [role="grid"] span,
        div[data-testid="stDataFrame"] [role="grid"] p {
            white-space: normal !important;
            word-break: break-word !important;
            line-height: 1.15 !important;
        }
        </style>
        """,
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            """
        <style>
        div[data-testid="stDataFrame"] * { font-size: 13px !important; }
        div[data-testid="stDataFrame"] [role="grid"] div,
        div[data-testid="stDataFrame"] [role="grid"] span,
        div[data-testid="stDataFrame"] [role="grid"] p {
            white-space: nowrap !important;
            overflow: hidden !important;
            text-overflow: ellipsis !important;
        }
        </style>
        """,
            unsafe_allow_html=True,
        )

    presets = {
        "GestiÃ³n": [sem_col, "LEGACY", "FECHA TAREA", "TAREA PENDIENTE", "CLIENTE", "FUERO", "CAUSA", "EXPEDIENTE", "RESPONSABLE", "ESTADO", anio_col],
        "Cliente/Causa": ["CLIENTE", "FUERO", "CAUSA", "CARATULA", "EXPEDIENTE", "RESPONSABLE", sem_col, "FECHA TAREA", "TAREA PENDIENTE", "LEGACY"],
        "Procesal": ["CLIENTE", "FUERO", "TIPO PROCESO", "JURISDICCION", "ORGANISMO", "EXPEDIENTE", "CARATULA", "CONTROL", "EVENTO", "FECHA EVENTO", "LEGACY"],
        "Completo": [c for c in df.columns if not str(c).startswith("_")],
    }

    preset_key = "gestion.casos.listado.preset"
    cols_key = "gestion.casos.listado.cols"
    visible_key = "gestion.casos.listado.cols_visible"
    order_key = "gestion.casos.listado.col_sel"

    st.session_state.setdefault(preset_key, "GestiÃ³n")
    if st.session_state[preset_key] not in presets:
        st.session_state[preset_key] = "GestiÃ³n"
    if cols_key not in st.session_state or not isinstance(st.session_state[cols_key], list):
        base = presets.get(st.session_state[preset_key], presets["GestiÃ³n"])
        st.session_state[cols_key] = [c for c in base if c in df.columns]
    if visible_key not in st.session_state or not isinstance(st.session_state[visible_key], list):
        st.session_state[visible_key] = list(st.session_state[cols_key])
    if order_key not in st.session_state and st.session_state[cols_key]:
        st.session_state[order_key] = st.session_state[cols_key][0]

    st.caption("Seleccione columnas visibles y ordene con las flechas.")
    with st.expander("Columnas (orden y visibilidad)", expanded=False):
        all_cols = [c for c in presets["Completo"] if not str(c).startswith("_")]
        pcol1, pcol2 = st.columns([2, 3])
        with pcol1:
            preset = st.selectbox("Vista estÃ¡ndar", list(presets.keys()), key=preset_key)
            if st.button("Restaurar vista", key="gestion.casos.listado.restaurar", width="stretch", type="secondary"):
                base = presets.get(preset, presets["GestiÃ³n"])
                st.session_state[cols_key] = [c for c in base if c in df.columns]
                st.session_state[visible_key] = list(st.session_state[cols_key])
                st.session_state[order_key] = st.session_state[cols_key][0] if st.session_state[cols_key] else ""
                st.rerun()
        with pcol2:
            selected = st.multiselect("Visibilidad", options=all_cols, key=visible_key)
            current = st.session_state.get(cols_key, [])
            new_order = [c for c in current if c in selected] + [c for c in selected if c not in current]
            if new_order != current:
                st.session_state[cols_key] = new_order
                if new_order and st.session_state.get(order_key) not in new_order:
                    st.session_state[order_key] = new_order[0]
                st.rerun()

        cols = st.session_state.get(cols_key, [])
        if not cols:
            st.session_state[cols_key] = [c for c in presets["GestiÃ³n"] if c in df.columns]
            cols = st.session_state[cols_key]
            if cols:
                st.session_state[order_key] = cols[0]

        if cols:
            col_sel = st.selectbox("Orden", cols, key=order_key)
            idx = cols.index(col_sel) if col_sel in cols else 0
            b1, b2 = st.columns(2)
            with b1:
                if st.button("Subir", key="gestion.casos.listado.col_up", width="stretch", type="secondary") and idx > 0:
                    st.session_state[cols_key] = _swap(cols, idx, idx - 1)
                    st.rerun()
            with b2:
                if st.button("Bajar", key="gestion.casos.listado.col_down", width="stretch", type="secondary") and idx < len(cols) - 1:
                    st.session_state[cols_key] = _swap(cols, idx, idx + 1)
                    st.rerun()

    if modo == "Tarjetas":
        _render_tarjetas(df, gestor)
        return

    cols = [c for c in st.session_state.get(cols_key, []) if c in df.columns and not str(c).startswith("_")]
    if not cols:
        cols = [c for c in presets["GestiÃ³n"] if c in df.columns]

    df_grid = df[cols + (["_RUTA"] if "_RUTA" in df.columns else [])].copy()
    df_grid = df_grid.replace("S/D", "")

    column_config = {
        sem_col: st.column_config.TextColumn("", width="small"),
        "LEGACY": st.column_config.TextColumn("Legacy", width="small"),
        "FECHA TAREA": st.column_config.TextColumn("Fecha", width="small"),
        "TAREA PENDIENTE": st.column_config.TextColumn("Tarea", width="medium"),
        "CLIENTE": st.column_config.TextColumn("Cliente", width="medium"),
        "FUERO": st.column_config.TextColumn("Fuero", width="small"),
        "CAUSA": st.column_config.TextColumn("Causa", width="large"),
        "CARATULA": st.column_config.TextColumn("CarÃ¡tula", width="large"),
        "EXPEDIENTE": st.column_config.TextColumn("Expte.", width="small"),
        "RESPONSABLE": st.column_config.TextColumn("Resp.", width="small"),
        "ESTADO": st.column_config.TextColumn("Estado", width="small"),
        anio_col: st.column_config.TextColumn("AÃ±o", width="small"),
    }

    height = 520 if densidad == "Compacta" else 640
    st.caption(f"{len(df_grid)} casos filtrados Â· clic en una fila para ver detalle")
    selected_ruta = render_aggrid(df_grid, key="gestion.casos.listado.grid", height=height, column_config=column_config)
    _persist_casos_filter_state()
    _render_batch_apply_panel(df, gestor)

    if selected_ruta:
        _debug_selected_case_id("casos_listado:selected_raw", selected_ruta)
        selected_case = _set_selected_case_id(selected_ruta, stage="casos_listado")
        if selected_case:
            _go(section="casos", mode="detalle", selected_id=selected_case)


def _render_tarjetas(df: pd.DataFrame, gestor: GestorCasos):
    """Vista tarjetas para Listado (mÃ³vil)."""
    df_cards = df.copy()
    sem_col = _semaforo_col(df_cards)
    try:
        orden = {
            SEMAFORO_ICONS["Vencidos"]: 0,
            SEMAFORO_ICONS["PrÃ³ximos"]: 1,
            SEMAFORO_ICONS["En tiempo"]: 2,
            SEMAFORO_ICONS["Sin tarea"]: 3,
        }
        df_cards["_ORD_SEM"] = df_cards[sem_col].map(orden).fillna(99)
        df_cards["_FECHA_TAREA_DT"] = pd.to_datetime(df_cards.get("FECHA TAREA", ""), errors="coerce", dayfirst=True)
        df_cards = df_cards.sort_values(by=["_ORD_SEM", "_FECHA_TAREA_DT"], ascending=[True, True], kind="mergesort")
    except Exception as exc:
        logger.warning("orden de tarjetas fallo: %s", exc)

    for i, row in df_cards.reset_index(drop=True).iterrows():
        cliente = str(row.get("CLIENTE", ""))
        causa = str(row.get("CAUSA", ""))
        sem = str(row.get(sem_col, ""))
        legacy_badge = str(row.get("LEGACY", ""))
        vence = str(row.get("FECHA TAREA", ""))
        tarea = str(row.get("TAREA PENDIENTE", ""))
        fuero = str(row.get("FUERO", ""))
        expte = str(row.get("EXPEDIENTE", ""))
        caratula = str(row.get("CARATULA", ""))
        responsable = str(row.get("RESPONSABLE", ""))
        ruta = str(row.get("_RUTA", ""))

        titulo = f"{sem} {cliente} Â· {causa}"
        with st.expander(titulo, expanded=False):
            if legacy_badge:
                st.markdown(_legacy_badge_html(legacy_badge), unsafe_allow_html=True)
            cA, cB = st.columns([3, 2])
            with cA:
                st.write(f"**Fuero:** {fuero}")
                if expte and expte != "S/D":
                    st.write(f"**Expediente:** {expte}")
                if caratula and caratula != "S/D":
                    st.write(f"**CarÃ¡tula:** {caratula}")
            with cB:
                st.write(f"**SemÃ¡foro:** {sem}")
                if vence:
                    st.write(f"**Vence:** {vence}")
                if responsable and responsable != "S/D":
                    st.write(f"**Responsable:** {responsable}")

            if tarea and tarea != "S/D":
                st.write(f"**Tarea:** {tarea}")

            if ruta:
                act1, act2, act3 = st.columns(3)
                with act1:
                    if st.button("Abrir carpeta", key=f"gestion.casos.tarjeta.open.{i}", width="stretch", type="secondary"):
                        open_path(ruta)
                with act2:
                    if tarea and tarea != "S/D":
                        if st.button("Tarea completada", key=f"gestion.casos.tarjeta.done.{i}", width="stretch", type="secondary"):
                            accion_completar_tarea(gestor, Path(ruta))
                with act3:
                    if st.button("Ver detalle", key=f"gestion.casos.tarjeta.det.{i}", width="stretch"):
                        _go(section="casos", mode="detalle", selected_id=ruta)

    st.caption(f"Mostrando {len(df_cards)} casos")


def _render_casos_detalle_v3(df: pd.DataFrame, gestor: GestorCasos):
    """Modo Detalle: ficha legible con acciones contextuales."""
    ruta = _require_selected("case")
    if not ruta:
        return
    ruta_repo = _to_repo_path(ruta)

    caso_row = None
    if "_RUTA" in df.columns:
        match = df[df["_RUTA"].astype(str).map(lambda x: _canonical_case_ref(x)) == ruta]
        if not match.empty:
            caso_row = match.iloc[0].to_dict()

    if caso_row is None:
        vg_empty_state(
            "El caso seleccionado ya no existe en los datos actuales.",
            "Ir a listado",
            lambda: _go(section="casos", mode="listado"),
            key="gestion.casos.detalle.no_case",
        )
        return

    if st.session_state.get("auto_normalize", False) and isinstance(ruta_repo, Path):
        gestor.ensure_case_structure(ruta_repo)

    sem_col = _semaforo_col(df)
    sem = caso_row.get(sem_col, "")
    badges = []
    if sem == SEMAFORO_ICONS["Vencidos"]:
        badges.append('<span class="vg-badge-danger">Vencido</span>')
    elif sem == SEMAFORO_ICONS["PrÃ³ximos"]:
        badges.append('<span class="vg-badge-warn">PrÃ³ximo</span>')
    elif sem == SEMAFORO_ICONS["En tiempo"]:
        badges.append('<span class="vg-badge-ok">En tiempo</span>')

    detail_shell(f"{sem} {caso_row.get('CLIENTE', '')} Â· {caso_row.get('CAUSA', '')}", badges=badges)

    cA, cB, cC = st.columns(3)
    with cA:
        st.write(f"**Cliente:** {caso_row.get('CLIENTE','')}")
        st.write(f"**Causa:** {caso_row.get('CAUSA','')}")
        st.write(f"**Fuero:** {caso_row.get('FUERO','')}")
        st.write(f"**Estado:** {caso_row.get('ESTADO','')}")
        st.write(f"**AÃ±o:** {caso_row.get(_anio_col(df), '')}")
    with cB:
        st.write(f"**Expediente:** {caso_row.get('EXPEDIENTE','')}")
        st.write(f"**CarÃ¡tula:** {caso_row.get('CARATULA','')}")
        st.write(f"**Tipo de Proceso:** {caso_row.get('TIPO PROCESO','')}")
        st.write(f"**JurisdicciÃ³n:** {caso_row.get('JURISDICCION','')}")
        st.write(f"**Organismo:** {caso_row.get('ORGANISMO','')}")
    with cC:
        st.write(f"**Responsable:** {caso_row.get('RESPONSABLE','')}")
        st.write(f"**Tarea:** {caso_row.get('TAREA PENDIENTE','')}")
        st.write(f"**Vence:** {caso_row.get('FECHA TAREA','')}")
        st.write(f"**Control:** {caso_row.get('CONTROL','')}")
        st.write(f"**Evento:** {caso_row.get('EVENTO','')}")

    st.markdown("---")

    ac1, ac2, ac3, ac4 = st.columns(4)
    with ac1:
        if st.button("Editar", key="gestion.casos.detalle.editar", width="stretch"):
            _go(section="casos", mode="editar", selected_id=ruta)
    with ac2:
        if st.button("Abrir carpeta", key="gestion.casos.detalle.abrir", width="stretch", type="secondary"):
            open_path(ruta)
    with ac3:
        if st.button("Volver", key="gestion.casos.detalle.volver", width="stretch", type="secondary"):
            _go(section="casos", mode="listado")
    with ac4:
        tarea = caso_row.get("TAREA PENDIENTE", "")
        if tarea and tarea != "S/D":
            if st.button("Completar tarea", key="gestion.casos.detalle.tarea_ok", width="stretch", type="secondary"):
                accion_completar_tarea(gestor, ruta_repo)

    can_agenda, reason_agenda = _route_enabled("Agenda")
    can_finanzas, reason_finanzas = _route_enabled("Finanzas")

    dl1, dl2 = st.columns(2)
    with dl1:
        if st.button(
            "Abrir en Agenda",
            key="gestion.casos.detalle.deep.agenda",
            width="stretch",
            type="secondary",
            disabled=not can_agenda,
            help=reason_agenda or None,
        ):
            _go_route("Agenda", mode="detalle", item_id=ruta)
    with dl2:
        if st.button(
            "Abrir en Finanzas",
            key="gestion.casos.detalle.deep.finanzas",
            width="stretch",
            type="secondary",
            disabled=not can_finanzas,
            help=reason_finanzas or None,
        ):
            _go_route("Finanzas", mode="detalle", item_id=ruta)

    st.markdown("---")

    render_minimum_completion_wizard(gestor, ruta_repo, ruta, caso_row=caso_row)

    st.markdown("---")

    render_quick_edit(gestor, ruta_repo, "detalle")

    mostrar_documentos_recientes(gestor, ruta_repo, key_suffix="detalle_v3")


def _render_casos_editar_v3(df: pd.DataFrame, gestor: GestorCasos):
    """Modo Editar: formulario completo del caso seleccionado."""
    ruta = _require_selected("case")
    if not ruta:
        return

    ruta_repo = _to_repo_path(ruta)

    try:
        ficha = gestor._leer_ficha(ruta_repo)
    except ValueError as e:
        st.error(str(e))
        vg_empty_state(
            "No se pudo cargar la ficha del caso para ediciÃ³n.",
            "Volver a detalle",
            lambda: _go(section="casos", mode="detalle", selected_id=ruta),
            key="gestion.casos.editar.no_ficha",
        )
        return

    caso_row = None
    if "_RUTA" in df.columns:
        match = df[df["_RUTA"].astype(str).map(lambda x: _canonical_case_ref(x)) == ruta]
        if not match.empty:
            caso_row = match.iloc[0].to_dict()

    if caso_row is None:
        vg_empty_state(
            "El caso seleccionado ya no existe en la vista actual.",
            "Ir a listado",
            lambda: _go(section="casos", mode="listado"),
            key="gestion.casos.editar.no_case",
        )
        return

    page_header("Editar caso", subtitle=f"{caso_row.get('CLIENTE','')} Â· {caso_row.get('CAUSA','')}")

    fields = {
        "TIPO_PROCESO": "gestion.casos.editar.field.tipo_proceso",
        "JURISDICCION": "gestion.casos.editar.field.jurisdiccion",
        "ORGANISMO": "gestion.casos.editar.field.organismo",
        "EXPEDIENTE": "gestion.casos.editar.field.expediente",
        "CARATULA": "gestion.casos.editar.field.caratula",
        "RESPONSABLE": "gestion.casos.editar.field.responsable",
        "CONTROL": "gestion.casos.editar.field.control",
        "EVENTO": "gestion.casos.editar.field.evento",
        "FECHA_EVENTO": "gestion.casos.editar.field.fecha_evento",
        "TAREA_PENDIENTE": "gestion.casos.editar.field.tarea",
        "FECHA_TAREA": "gestion.casos.editar.field.fecha_tarea",
        "OBSERVACIONES": "gestion.casos.editar.field.observaciones",
    }
    date_fields = {"FECHA_EVENTO", "FECHA_TAREA"}
    form_case_key = "gestion.casos.editar.case_ref"
    saved_snapshot_key = "gestion.casos.editar.last_saved"
    auto_save_mode = _auto_save_changes_enabled()

    if st.session_state.get(form_case_key) != ruta:
        st.session_state[form_case_key] = ruta
        for field, state_key in fields.items():
            raw = ficha.get(field, "")
            st.session_state[state_key] = _normalize_date_value(raw) if field in date_fields else _normalize_text_value(raw)
        st.session_state[saved_snapshot_key] = {
            field: (
                _normalize_date_value(ficha.get(field, ""))
                if field in date_fields
                else _normalize_text_value(ficha.get(field, ""))
            )
            for field in fields.keys()
        }

    if auto_save_mode:
        st.caption("Guardado automatico activado (VG_AUTO_SAVE_CHANGES=1).")
        st.markdown("#### Identificacion")
        ident_a, ident_b = st.columns(2)
        with ident_a:
            st.write(f"**Año:** {caso_row.get(_anio_col(df), '')}")
            st.write(f"**Estado:** {caso_row.get('ESTADO', '')}")
            st.write(f"**Cliente:** {caso_row.get('CLIENTE', '')}")
        with ident_b:
            st.write(f"**Fuero:** {caso_row.get('FUERO', '')}")
            st.write(f"**Causa:** {caso_row.get('CAUSA', '')}")
            st.write(f"**Expediente actual:** {caso_row.get('EXPEDIENTE', '')}")
        st.caption("Para cambiar jerarquía o nombre de carpeta, use Configuración > Editar caso.")

        st.markdown("#### Expediente y proceso")
        p1, p2, p3 = st.columns(3)
        with p1:
            st.text_input("Tipo de Proceso", key=fields["TIPO_PROCESO"])
        with p2:
            st.text_input("Jurisdicción", key=fields["JURISDICCION"])
        with p3:
            st.text_input("Organismo", key=fields["ORGANISMO"])
        p4, p5 = st.columns(2)
        with p4:
            st.text_input("Expediente", key=fields["EXPEDIENTE"])
        with p5:
            st.text_input("Carátula", key=fields["CARATULA"])

        st.markdown("#### Gestión y control")
        g1, g2 = st.columns(2)
        with g1:
            st.text_input("Responsable", key=fields["RESPONSABLE"])
            st.text_input("Control", key=fields["CONTROL"])
        with g2:
            st.text_input("Último evento", key=fields["EVENTO"])
            st.text_input("Fecha evento (DD/MM/YYYY)", key=fields["FECHA_EVENTO"])

        st.markdown("#### Agenda y observaciones")
        a1, a2 = st.columns(2)
        with a1:
            st.text_input("Tarea pendiente", key=fields["TAREA_PENDIENTE"])
            st.text_input("Fecha tarea (DD/MM/YYYY)", key=fields["FECHA_TAREA"])
        with a2:
            st.text_area("Observaciones", key=fields["OBSERVACIONES"], height=150)

        if st.button("Volver", key="gestion.casos.editar.volver.auto", width="stretch", type="secondary"):
            _go(section="casos", mode="detalle", selected_id=ruta)

        cambios = {}
        invalid_dates: List[str] = []
        for field, state_key in fields.items():
            raw_new = st.session_state.get(state_key, "")
            if field in date_fields:
                if not _is_valid_supported_date(raw_new):
                    invalid_dates.append(field)
                cambios[field] = _normalize_date_value(raw_new)
            else:
                cambios[field] = _normalize_text_value(raw_new)

        if invalid_dates:
            bad = ", ".join(sorted(invalid_dates))
            st.warning(f"Fechas inválidas ({bad}). Corrija formato para auto-guardar.")
            return

        baseline = st.session_state.get(saved_snapshot_key, {})
        if not isinstance(baseline, dict):
            baseline = {}

        if cambios != baseline:
            if not _enforce_permission("cases:write", "No tiene permiso para editar casos."):
                return
            try:
                ok = gestor.actualizar_campos_ficha(ruta_repo, cambios, actor_ctx=_actor_ctx())
            except ValueError as e:
                st.error(str(e))
                return

            if not ok:
                st.error("No se pudo auto-guardar la actualización.")
                return

            st.session_state[saved_snapshot_key] = dict(cambios)
            st.cache_data.clear()
            st.session_state.pop("df_full", None)
            for key in list(st.session_state.keys()):
                if key.startswith("gestion.qe."):
                    st.session_state.pop(key, None)
            if hasattr(gestor, "_cache_casos"):
                gestor._cache_casos = []
            st.session_state["_edit_last_snapshot"] = dict(cambios)
            _save_tab_snapshot("casos")
            _ui_toast("Auto-guardado caso")
            st.caption(f"Auto-guardado: {datetime.now().strftime('%H:%M:%S')}")
        return

    submitted = False
    cancel_clicked = False
    with st.form("gestion.casos.editar.form", clear_on_submit=False):
        st.markdown("#### IdentificaciÃ³n")
        ident_a, ident_b = st.columns(2)
        with ident_a:
            st.write(f"**AÃ±o:** {caso_row.get(_anio_col(df), '')}")
            st.write(f"**Estado:** {caso_row.get('ESTADO', '')}")
            st.write(f"**Cliente:** {caso_row.get('CLIENTE', '')}")
        with ident_b:
            st.write(f"**Fuero:** {caso_row.get('FUERO', '')}")
            st.write(f"**Causa:** {caso_row.get('CAUSA', '')}")
            st.write(f"**Expediente actual:** {caso_row.get('EXPEDIENTE', '')}")
        st.caption("Para cambiar jerarquÃ­a o nombre de carpeta, use ConfiguraciÃ³n > Editar caso.")

        st.markdown("#### Expediente y proceso")
        p1, p2, p3 = st.columns(3)
        with p1:
            st.text_input("Tipo de Proceso", key=fields["TIPO_PROCESO"])
        with p2:
            st.text_input("JurisdicciÃ³n", key=fields["JURISDICCION"])
        with p3:
            st.text_input("Organismo", key=fields["ORGANISMO"])
        p4, p5 = st.columns(2)
        with p4:
            st.text_input("Expediente", key=fields["EXPEDIENTE"])
        with p5:
            st.text_input("CarÃ¡tula", key=fields["CARATULA"])

        st.markdown("#### GestiÃ³n y control")
        g1, g2 = st.columns(2)
        with g1:
            st.text_input("Responsable", key=fields["RESPONSABLE"])
            st.text_input("Control", key=fields["CONTROL"])
        with g2:
            st.text_input("Ãšltimo evento", key=fields["EVENTO"])
            st.text_input("Fecha evento (DD/MM/YYYY)", key=fields["FECHA_EVENTO"])

        st.markdown("#### Agenda y observaciones")
        a1, a2 = st.columns(2)
        with a1:
            st.text_input("Tarea pendiente", key=fields["TAREA_PENDIENTE"])
            st.text_input("Fecha tarea (DD/MM/YYYY)", key=fields["FECHA_TAREA"])
        with a2:
            st.text_area("Observaciones", key=fields["OBSERVACIONES"], height=150)

        act1, act2 = st.columns(2)
        with act1:
            submitted = st.form_submit_button("Guardar", key="gestion.casos.editar.guardar", width="stretch")
        with act2:
            cancel_clicked = st.form_submit_button(
                "Cancelar",
                key="gestion.casos.editar.cancelar",
                width="stretch",
                type="secondary",
            )

    if cancel_clicked:
        _go(section="casos", mode="detalle", selected_id=ruta)

    if submitted:
        cambios = {}
        baseline = {}
        for field, state_key in fields.items():
            raw_new = st.session_state.get(state_key, "")
            raw_old = ficha.get(field, "")
            if field in date_fields:
                cambios[field] = _normalize_date_value(raw_new)
                baseline[field] = _normalize_date_value(raw_old)
            else:
                cambios[field] = _normalize_text_value(raw_new)
                baseline[field] = _normalize_text_value(raw_old)

        if cambios == baseline:
            st.info("Sin cambios para guardar.")
            return

        try:
            ok = gestor.actualizar_campos_ficha(ruta_repo, cambios, actor_ctx=_actor_ctx())
        except ValueError as e:
            st.error(str(e))
            return

        if not ok:
            st.error("No se pudo guardar la actualizaciÃ³n.")
            return

        st.cache_data.clear()
        st.session_state.pop("df_full", None)
        for key in list(st.session_state.keys()):
            if key.startswith("gestion.qe."):
                st.session_state.pop(key, None)
        if hasattr(gestor, "_cache_casos"):
            gestor._cache_casos = []

        try:
            refreshed = gestor._leer_ficha(ruta_repo)
        except ValueError:
            refreshed = {}
        st.session_state["_edit_last_snapshot"] = refreshed or dict(cambios)
        _save_tab_snapshot("casos")
        _ui_toast("Caso guardado")
        st.success("Caso actualizado correctamente.")
        _go(section="casos", mode="detalle", selected_id=ruta)

def render_modulo_cliente(gestor: GestorCasos, casos: List[Caso], mode: str = "listado"):
    """MÃ³dulo Cliente: cuerpo exclusivo por modo."""
    clientes = gestor.obtener_clientes_existentes()
    if not clientes:
        vg_empty_state(
            "No hay clientes registrados en el sistema.",
            "Ir a Casos",
            lambda: _go(section="casos", mode="listado"),
            key="gestion.cliente.empty",
        )
        return

    selected_client = _normalize_text_value(_gget(_selected_state_key("clientes"), ""))
    has_valid_selected = selected_client in clientes
    if mode == "listado" and not has_valid_selected:
        selected_client = clientes[0]
        _set_selected_for_section("clientes", selected_client, stage="clientes.listado.default")
    elif mode in {"detalle", "editar"} and not has_valid_selected:
        vg_empty_state(
            "No hay un cliente seleccionado para continuar.",
            "Ir a listado",
            lambda: _go(section="clientes", mode="listado"),
            key=f"gestion.empty.guard.clientes.{mode}",
        )
        return

    st.session_state["gestion.cliente.selector"] = selected_client
    cliente_sel = st.selectbox("Seleccione cliente", clientes, key="gestion.cliente.selector")
    _set_selected_for_section("clientes", cliente_sel, stage="clientes.selector")
    casos_cliente = [c for c in casos if c.cliente == cliente_sel]

    if mode == "listado":
        _render_cliente_listado(casos_cliente, cliente_sel, gestor)
    elif mode == "detalle":
        if not _require_selected("client"):
            return
        _render_cliente_detalle(casos_cliente, cliente_sel, gestor)
    elif mode == "editar":
        if not _require_selected("client"):
            return
        _render_cliente_editar(casos_cliente, cliente_sel, gestor)


def _render_cliente_listado(casos_cliente: list, cliente_sel: str, gestor: GestorCasos):
    """Cliente - Listado: grilla de casos del cliente."""
    grid_shell("Clientes", subtitle=f"{cliente_sel} - {len(casos_cliente)} causas", fluid=True)

    if not casos_cliente:
        st.info("Este cliente no tiene causas registradas.")
        return

    sem_col = _semaforo_col(pd.DataFrame([c.to_dict() for c in casos_cliente]))
    cols_cli = [sem_col, "FUERO", "CAUSA", "EXPEDIENTE", "RESPONSABLE", "FECHA TAREA", "TAREA PENDIENTE", "ESTADO"]
    df_cli = pd.DataFrame([c.to_dict() for c in casos_cliente])
    df_cli_grid = df_cli[[c for c in cols_cli if c in df_cli.columns] + (["_RUTA"] if "_RUTA" in df_cli.columns else [])].copy()
    df_cli_grid = df_cli_grid.replace("S/D", "")

    selected_ruta = render_aggrid(df_cli_grid, key="gestion.cliente.listado.grid", height=480)

    if selected_ruta:
        selected_case = _canonical_case_ref(selected_ruta)
        if selected_case:
            selected_case = _set_selected_case_id(selected_ruta, stage="cliente_listado")
        if selected_case:
            _go(section="clientes", mode="detalle")

    c1, c2 = st.columns(2)
    with c1:
        if st.button("Detalle cliente", key="gestion.cliente.listado.detalle", width="stretch"):
            _go(section="clientes", mode="detalle")
    with c2:
        has_case = bool(_gget(_selected_state_key("casos"), ""))
        if st.button(
            "Abrir caso seleccionado",
            key="gestion.cliente.listado.abrir_caso",
            width="stretch",
            type="secondary",
            disabled=not has_case,
        ):
            _go(section="casos", mode="detalle", selected_id=_gget(_selected_state_key("casos"), ""))


def _render_cliente_detalle(casos_cliente: list, cliente_sel: str, gestor: GestorCasos):
    """Cliente - Detalle: ficha del caso y estadÃ­sticas del cliente."""
    if not casos_cliente:
        st.info("Este cliente no tiene causas registradas.")
        return

    ruta = _validate_selected_for_section("casos", _gget(_selected_state_key("casos"), ""))
    caso_sel = None
    if ruta:
        for c in casos_cliente:
            if _same_case_ref(c.ruta, ruta):
                caso_sel = c
                break
    if caso_sel is None and casos_cliente:
        caso_sel = casos_cliente[0]
        _set_selected_case_id(str(caso_sel.ruta), stage="cliente.detalle.fallback")

    detail_shell(f"{caso_sel.semaforo} {caso_sel.cliente} Â· {caso_sel.causa}")

    cA, cB = st.columns(2)
    with cA:
        st.write(f"**Causa:** {caso_sel.causa}")
        st.write(f"**Fuero:** {caso_sel.fuero}")
        st.write(f"**Expediente:** {caso_sel.expediente}")
        st.write(f"**Estado:** {caso_sel.estado}")
    with cB:
        st.write(f"**Responsable:** {caso_sel.responsable}")
        if caso_sel.tarea_pendiente and caso_sel.tarea_pendiente != "S/D":
            st.write(f"**Tarea:** {caso_sel.tarea_pendiente}")
            st.write(f"**Vence:** {caso_sel.fecha_tarea}")

    st.markdown("---")

    ac1, ac2, ac3 = st.columns(3)
    with ac1:
        if st.button("Abrir carpeta", key="gestion.cliente.detalle.abrir", width="stretch", type="secondary"):
            open_path(caso_sel.ruta)
    with ac2:
        if caso_sel.tarea_pendiente and caso_sel.tarea_pendiente != "S/D":
            if st.button("Tarea completada", key="gestion.cliente.detalle.done", width="stretch", type="secondary"):
                accion_completar_tarea(gestor, caso_sel.ruta)
    with ac3:
        if st.button("Editar caso", key="gestion.cliente.detalle.editar", width="stretch"):
            _go(section="casos", mode="editar", selected_id=str(caso_sel.ruta))

    can_agenda, reason_agenda = _route_enabled("Agenda")
    can_finanzas, reason_finanzas = _route_enabled("Finanzas")

    dl1, dl2 = st.columns(2)
    with dl1:
        if st.button(
            "Abrir en Agenda",
            key="gestion.cliente.detalle.deep.agenda",
            width="stretch",
            type="secondary",
            disabled=not can_agenda,
            help=reason_agenda or None,
        ):
            _go_route("Agenda", mode="detalle", item_id=str(caso_sel.ruta))
    with dl2:
        if st.button(
            "Abrir en Finanzas",
            key="gestion.cliente.detalle.deep.finanzas",
            width="stretch",
            type="secondary",
            disabled=not can_finanzas,
            help=reason_finanzas or None,
        ):
            _go_route("Finanzas", mode="detalle", item_id=str(caso_sel.ruta))

    st.markdown("---")
    render_quick_edit(gestor, caso_sel.ruta, "cli_det")
    mostrar_documentos_recientes(gestor, caso_sel.ruta, key_suffix="cli_det_v3")

    # EstadÃ­sticas del cliente
    st.markdown("---")
    st.markdown("#### EstadÃ­sticas del cliente")

    estados = {}
    semaforos = {
        SEMAFORO_ICONS["Vencidos"]: 0,
        SEMAFORO_ICONS["PrÃ³ximos"]: 0,
        SEMAFORO_ICONS["En tiempo"]: 0,
        SEMAFORO_ICONS["Sin tarea"]: 0,
    }

    for c in casos_cliente:
        estados[c.estado] = estados.get(c.estado, 0) + 1
        semaforos[c.semaforo] = semaforos.get(c.semaforo, 0) + 1

    m1, m2, m3, m4 = st.columns(4)
    with m1:
        st.metric("Vencidos", semaforos[SEMAFORO_ICONS["Vencidos"]])
    with m2:
        st.metric("PrÃ³ximos", semaforos[SEMAFORO_ICONS["PrÃ³ximos"]])
    with m3:
        st.metric("En tiempo", semaforos[SEMAFORO_ICONS["En tiempo"]])
    with m4:
        st.metric("Sin tarea", semaforos[SEMAFORO_ICONS["Sin tarea"]])

    st.markdown("**Por Estado:**")
    df_est = pd.DataFrame(
        [{"Estado": k, "Cantidad": v} for k, v in sorted(estados.items(), key=lambda x: x[0])]
    )
    st.dataframe(df_est, width="stretch", hide_index=True)


def _render_cliente_editar(casos_cliente: list, cliente_sel: str, gestor: GestorCasos):
    """Cliente - Editar: seleccion de caso asociado para edicion en Casos."""
    if not casos_cliente:
        st.info("Este cliente no tiene causas para editar.")
        return

    page_header("Editar cliente", subtitle=cliente_sel)
    st.caption("Seleccione una causa del cliente para abrir su edicion completa en Casos.")

    options = {f"{c.fuero} Â· {c.causa}": str(c.ruta) for c in casos_cliente}
    labels = list(options.keys())
    selected_label = st.selectbox("Causa asociada", labels, key="gestion.cliente.editar.case_selector")
    ruta = options.get(selected_label, "")
    if ruta:
        _set_selected_case_id(ruta, stage="cliente.editar.selector")

    c1, c2 = st.columns(2)
    with c1:
        if st.button("Abrir edicion de caso", key="gestion.cliente.editar.open_case", width="stretch"):
            _go(section="casos", mode="editar", selected_id=ruta)
    with c2:
        if st.button("Volver a detalle cliente", key="gestion.cliente.editar.volver", width="stretch", type="secondary"):
            _go(section="clientes", mode="detalle")


# Ã¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢Â
# MODULO AGENDA
# Ã¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢Â

def render_modulo_agenda(gestor: GestorCasos, casos: List[Caso], mode: str = "listado"):
    """MÃ³dulo Agenda: cuerpo exclusivo por modo."""
    tareas = [c for c in casos if c.fecha_tarea and c.fecha_tarea != "S/D"]

    if not tareas:
        vg_empty_state(
            "No hay tareas programadas en ningÃºn caso.",
            "Ir a Casos",
            lambda: _go(section="casos", mode="listado"),
            key="gestion.agenda.empty",
        )
        return

    tareas_con_fecha = []
    for t in tareas:
        fecha_obj = t._parsear_fecha(t.fecha_tarea)
        if fecha_obj:
            tareas_con_fecha.append((fecha_obj, t))
    tareas_con_fecha.sort(key=lambda x: x[0])

    if mode == "listado":
        agenda_filters = _gget(_section_filter_state_key("agenda"), _section_filter_defaults("agenda"))
        if not isinstance(agenda_filters, dict):
            agenda_filters = _section_filter_defaults("agenda")
        _gset("gestion.agenda.filtro.ver", agenda_filters.get("ver", "Todas"))
        _gset("gestion.agenda.filtro.activos", bool(agenda_filters.get("solo_activos", True)))
        fc1, fc2 = st.columns(2)
        with fc1:
            agenda_ver = st.selectbox(
                "Ver",
                ["Todas", "Solo vencidas", "PrÃ³ximos 7 dÃ­as", "PrÃ³ximos 30 dÃ­as"],
                key="gestion.agenda.filtro.ver",
            )
        with fc2:
            _ensure_bool_state("gestion.agenda.filtro.activos", True)
            solo_activos = st.checkbox("Solo casos activos", key="gestion.agenda.filtro.activos")
    else:
        agenda_filters = _gget(_section_filter_state_key("agenda"), _section_filter_defaults("agenda"))
        if not isinstance(agenda_filters, dict):
            agenda_filters = _section_filter_defaults("agenda")
        agenda_ver = agenda_filters.get("ver", "Todas")
        solo_activos = bool(agenda_filters.get("solo_activos", True))

    _gset(_section_filter_state_key("agenda"), {"ver": agenda_ver, "solo_activos": bool(solo_activos)})

    hoy = datetime.now().date()
    tareas_filtradas = []
    for fecha_obj, t in tareas_con_fecha:
        if solo_activos and "Activo" not in t.estado:
            continue
        if agenda_ver == "Solo vencidas" and fecha_obj >= hoy:
            continue
        if agenda_ver == "PrÃ³ximos 7 dÃ­as" and not (hoy <= fecha_obj <= hoy + timedelta(days=7)):
            continue
        if agenda_ver == "PrÃ³ximos 30 dÃ­as" and not (hoy <= fecha_obj <= hoy + timedelta(days=30)):
            continue
        tareas_filtradas.append((fecha_obj, t))

    # Priorizacion operativa: vencidas > proximas (<=7d) > resto; luego responsable.
    def _agenda_priority(item):
        fecha_obj, tarea = item
        delta = (fecha_obj - hoy).days
        if delta < 0:
            bucket = 0
        elif delta <= 7:
            bucket = 1
        else:
            bucket = 2
        responsable = _normalize_text_value(getattr(tarea, "responsable", "")) or "ZZZ"
        return (
            bucket,
            fecha_obj,
            responsable.upper(),
            str(getattr(tarea, "cliente", "")).upper(),
            str(getattr(tarea, "causa", "")).upper(),
        )

    tareas_filtradas.sort(key=_agenda_priority)

    if mode == "listado":
        _render_agenda_listado(tareas_filtradas, tareas_con_fecha, gestor, agenda_ver=agenda_ver, solo_activos=solo_activos)
    elif mode == "detalle":
        if not _require_selected("agenda"):
            return
        _render_agenda_detalle(tareas_filtradas, gestor)
    elif mode == "editar":
        if not _require_selected("agenda"):
            return
        _render_agenda_editar(tareas_filtradas, gestor)


def _render_agenda_listado(
    tareas_filtradas: list,
    tareas_total: list,
    gestor: GestorCasos,
    agenda_ver: str = "Todas",
    solo_activos: bool = True,
):
    """Agenda - Listado: grilla de vencimientos."""
    card_begin("Listado de agenda", subtitle=f"{len(tareas_filtradas)} de {len(tareas_total)} tareas", variant="tight")

    if not tareas_filtradas:
        st.info(f"0 de {len(tareas_total)} tareas para los filtros actuales.")
        st.caption(
            f"Vista: {agenda_ver} | Solo activos: {'SÃ­' if solo_activos else 'No'}."
        )
        if st.button("Limpiar filtros", key="gestion.agenda.empty.clear_filters", width="stretch", type="secondary"):
            _reset_filtros_agenda()
            st.rerun()
        card_end()
        return

    df_agenda = pd.DataFrame([{
        "SEMÃFORO": t.semaforo,
        "FECHA TAREA": t.fecha_tarea,
        "CLIENTE": t.cliente,
        "CAUSA": t.causa,
        "FUERO": t.fuero,
        "EXPEDIENTE": t.expediente,
        "TAREA PENDIENTE": t.tarea_pendiente,
        "ESTADO": t.estado,
        "RESPONSABLE": t.responsable,
        "_RUTA": str(t.ruta),
    } for _, t in tareas_filtradas])

    agenda_bytes = _xlsx_bytes(
        df_agenda[[c for c in df_agenda.columns if c != "_RUTA"]],
        sheet_name="Agenda"
    )
    agenda_meta = build_export_metadata("agenda_xlsx", agenda_bytes)
    export_allowed = can_export()
    ts_agenda = _get_export_ts("agenda_xlsx")
    col_dl, col_regen = st.columns([3, 1])
    with col_dl:
        st.download_button(
            label="Exportar Agenda (Excel)",
            data=agenda_bytes,
            file_name=f"agenda_{ts_agenda}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            width="stretch",
            key="gestion.agenda.export.xlsx",
            disabled=not export_allowed,
            help="" if export_allowed else "Exportes restringidos por rol/política.",
        )
    with col_regen:
        if st.button("Regenerar export", key="gestion.agenda.export.regenerar", width="stretch", type="secondary"):
            _regen_export_ts(["agenda_xlsx"])
            st.cache_data.clear()
            _ui_toast("Export agenda regenerada")
            st.rerun()

    st.caption(f"Agenda XLSX sha256: {agenda_meta['sha256'][:12]}...")

    selected_ruta = render_aggrid(df_agenda, key="gestion.agenda.listado.grid", height=520)

    if selected_ruta:
        selected_item = _canonical_case_ref(selected_ruta)
        if selected_item:
            _go(section="agenda", mode="detalle", selected_id=selected_item)
    card_end()


def _render_agenda_detalle(tareas_filtradas: list, gestor: GestorCasos):
    """Agenda - Detalle: ficha de la tarea seleccionada + quick-edit."""
    ruta = _require_selected("agenda")
    if not ruta or not tareas_filtradas:
        return

    t = None
    for _, tarea in tareas_filtradas:
        if _same_case_ref(tarea.ruta, ruta):
            t = tarea
            break

    if not t:
        vg_empty_state(
            "La tarea seleccionada ya no coincide con el filtro actual.",
            "Ir a listado",
            lambda: _go(section="agenda", mode="listado"),
            key="gestion.agenda.detalle.no_task",
        )
        return

    card_begin("Detalle de agenda", subtitle=f"{t.semaforo} {t.cliente} - {t.causa}", variant="tight")

    cA, cB = st.columns(2)
    with cA:
        st.write(f"**Fecha:** {t.fecha_tarea}")
        st.write(f"**Tarea:** {t.tarea_pendiente}")
        st.write(f"**Responsable:** {t.responsable}")
    with cB:
        st.write(f"**Fuero:** {t.fuero}")
        st.write(f"**Expediente:** {t.expediente}")
        st.write(f"**Estado:** {t.estado}")

    st.markdown("---")

    ab1, ab2, ab3 = st.columns(3)
    with ab1:
        if st.button("Abrir carpeta", key="gestion.agenda.detalle.abrir", width="stretch", type="secondary"):
            open_path(t.ruta)
    with ab2:
        if st.button("Marcar completada", key="gestion.agenda.detalle.done", width="stretch", type="secondary"):
            accion_completar_tarea(gestor, t.ruta)
    with ab3:
        if st.button("Volver", key="gestion.agenda.detalle.volver", width="stretch", type="secondary"):
            _go(section="agenda", mode="listado")

    st.markdown("---")
    render_quick_edit(gestor, t.ruta, "agenda_det")
    card_end()


def _render_agenda_editar(tareas_filtradas: list, gestor: GestorCasos):
    """Agenda - Editar: formulario de edicion completa de la tarea."""
    ruta = _require_selected("agenda")
    if not ruta:
        return

    _go(section="casos", mode="editar", selected_id=ruta)


# Ã¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢Â
# MODULO FINANZAS
# Ã¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢Â

def render_modulo_finanzas(gestor: GestorCasos, casos: List[Caso], mode: str = "listado"):
    """MÃ³dulo Finanzas: cuerpo exclusivo por modo."""
    if not casos:
        vg_empty_state(
            "No hay casos cargados para visualizar finanzas.",
            "Ir a Casos",
            lambda: _go(section="casos", mode="listado"),
            key="gestion.finanzas.empty",
        )
        return

    fin_by_case: Dict[str, Dict[str, str]] = {}
    if hasattr(gestor, "leer_datos_financieros_batch"):
        try:
            rutas = [c.ruta for c in casos]
            fin_by_case = gestor.leer_datos_financieros_batch(rutas)
        except Exception as exc:
            logger.warning("finanzas batch read failed, fallback single-case mode: %s", exc)
            fin_by_case = {}

    resumen = []
    for c in casos:
        fin = fin_by_case.get(str(c.ruta), {}) if isinstance(fin_by_case, dict) else {}
        if not isinstance(fin, dict) or not fin:
            fin = gestor.leer_datos_financieros(c.ruta)
        resumen.append({
            "Cliente": c.cliente,
            "Causa": c.causa,
            "Estado": c.estado,
            "Monto Demandado": fin.get("MONTO_DEMANDADO", ""),
            "Honorarios Pactados": fin.get("HONORARIOS_PACTADOS", ""),
            "Estado Pago": fin.get("ESTADO_PAGO", ""),
            "_RUTA": str(c.ruta),
        })

    df_fin = pd.DataFrame(resumen)

    if mode == "listado":
        _render_finanzas_listado(df_fin, gestor)
    elif mode == "detalle":
        if not _require_selected("fin"):
            return
        _render_finanzas_detalle(df_fin, casos, gestor)
    elif mode == "editar":
        if not _require_selected("fin"):
            return
        _render_finanzas_editar(df_fin, casos, gestor)


def _render_finanzas_listado(df_fin: pd.DataFrame, gestor: GestorCasos):
    """Finanzas - Listado: grilla resumen y totales."""
    card_begin("Listado financiero", subtitle="Resumen economico", variant="tight")

    filtros = _gget(_section_filter_state_key("finanzas"), _section_filter_defaults("finanzas"))
    if not isinstance(filtros, dict):
        filtros = _section_filter_defaults("finanzas")
    _gset("gestion.finanzas.filtro_pago", filtros.get("estado_pago", "Todos"))
    filtro_pago = st.selectbox("Filtrar por estado de pago", ["Todos"] + ESTADOS_PAGO, key="gestion.finanzas.filtro_pago")
    _gset(_section_filter_state_key("finanzas"), {"estado_pago": filtro_pago})
    if filtro_pago and filtro_pago != "Todos":
        df_fin_f = df_fin[df_fin["Estado Pago"] == filtro_pago].copy()
    else:
        df_fin_f = df_fin.copy()

    _render_finanzas_csv_import_panel(df_fin, gestor)

    selected_ruta = render_aggrid(df_fin_f, key="gestion.finanzas.listado.grid", height=480)

    # Totales
    def parse_monto(val):
        try:
            return float(str(val).replace("$", "").replace(".", "").replace(",", ".").strip())
        except (ValueError, TypeError):
            return 0.0

    total_demandado = sum(parse_monto(v) for v in df_fin_f["Monto Demandado"])
    total_honorarios = sum(parse_monto(v) for v in df_fin_f["Honorarios Pactados"])

    m1, m2, m3 = st.columns(3)
    m1.metric("Total Demandado", f"${total_demandado:,.0f}")
    m2.metric("Total Honorarios", f"${total_honorarios:,.0f}")
    m3.metric("Casos mostrados", len(df_fin_f))

    if selected_ruta:
        selected_item = _canonical_case_ref(selected_ruta)
        if selected_item:
            _go(section="finanzas", mode="detalle", selected_id=selected_item)
    card_end()


def _render_finanzas_detalle(df_fin: pd.DataFrame, casos: List[Caso], gestor: GestorCasos):
    """Finanzas - Detalle: ficha financiera del caso."""
    ruta = _require_selected("fin")
    if not ruta:
        return

    caso_sel = None
    for c in casos:
        if _same_case_ref(c.ruta, ruta):
            caso_sel = c
            break

    if not caso_sel:
        vg_empty_state(
            "El caso seleccionado ya no existe.",
            "Ir a listado",
            lambda: _go(section="finanzas", mode="listado"),
            key="gestion.finanzas.detalle.no_case",
        )
        return

    fin = gestor.leer_datos_financieros(caso_sel.ruta)

    card_begin("Detalle financiero", subtitle=f"{caso_sel.cliente} - {caso_sel.causa}", variant="tight")

    cA, cB = st.columns(2)
    with cA:
        st.write(f"**Cliente:** {caso_sel.cliente}")
        st.write(f"**Causa:** {caso_sel.causa}")
        st.write(f"**Estado:** {caso_sel.estado}")
    with cB:
        st.write(f"**Monto Demandado:** {fin.get('MONTO_DEMANDADO', '-')}")
        st.write(f"**Honorarios Pactados:** {fin.get('HONORARIOS_PACTADOS', '-')}")
        st.write(f"**Estado Pago:** {fin.get('ESTADO_PAGO', '-')}")

    st.markdown("---")

    ac1, ac2 = st.columns(2)
    with ac1:
        if st.button("Editar finanzas", key="gestion.finanzas.detalle.editar", width="stretch"):
            _go(section="finanzas", mode="editar", selected_id=ruta)
    with ac2:
        if st.button("Volver", key="gestion.finanzas.detalle.volver", width="stretch", type="secondary"):
            _go(section="finanzas", mode="listado")
    card_end()


def _render_finanzas_editar(df_fin: pd.DataFrame, casos: List[Caso], gestor: GestorCasos):
    """Finanzas - Editar: formulario de datos financieros."""
    ruta = _require_selected("fin")
    if not ruta:
        return

    caso_sel = None
    for c in casos:
        if _same_case_ref(c.ruta, ruta):
            caso_sel = c
            break

    if not caso_sel:
        vg_empty_state(
            "El caso seleccionado no estÃ¡ disponible para editar finanzas.",
            "Ir a listado",
            lambda: _go(section="finanzas", mode="listado"),
            key="gestion.finanzas.editar.no_case",
        )
        return

    card_begin("Editar finanzas", subtitle=f"{caso_sel.cliente} - {caso_sel.causa}", variant="tight")

    fin_actual = gestor.leer_datos_financieros(caso_sel.ruta)
    fin_case_key = _canonical_case_ref(str(caso_sel.ruta))
    fin_state_case_key = "gestion.finanzas.editar.case_ref"
    fin_saved_key = "gestion.finanzas.editar.last_saved"
    auto_save_mode = _auto_save_changes_enabled()
    fin_state = {
        "gestion.finanzas.editar.monto": fin_actual.get("MONTO_DEMANDADO", ""),
        "gestion.finanzas.editar.honorarios": fin_actual.get("HONORARIOS_PACTADOS", ""),
        "gestion.finanzas.editar.estado_pago": fin_actual.get("ESTADO_PAGO", ESTADOS_PAGO[-1]),
    }
    if fin_state["gestion.finanzas.editar.estado_pago"] not in ESTADOS_PAGO:
        fin_state["gestion.finanzas.editar.estado_pago"] = ESTADOS_PAGO[-1]

    if st.session_state.get(fin_state_case_key) != fin_case_key:
        st.session_state[fin_state_case_key] = fin_case_key
        for k, v in fin_state.items():
            st.session_state[k] = v
        st.session_state[fin_saved_key] = {
            "MONTO_DEMANDADO": str(fin_state["gestion.finanzas.editar.monto"] or ""),
            "HONORARIOS_PACTADOS": str(fin_state["gestion.finanzas.editar.honorarios"] or ""),
            "ESTADO_PAGO": str(fin_state["gestion.finanzas.editar.estado_pago"] or ""),
        }
    else:
        for k, v in fin_state.items():
            st.session_state.setdefault(k, v)

    if auto_save_mode:
        st.caption("Guardado automatico activado (VG_AUTO_SAVE_CHANGES=1).")
        fc1, fc2, fc3 = st.columns(3)
        with fc1:
            st.text_input("Monto demandado", key="gestion.finanzas.editar.monto")
        with fc2:
            st.text_input("Honorarios pactados", key="gestion.finanzas.editar.honorarios")
        with fc3:
            st.selectbox("Estado de pago", ESTADOS_PAGO, key="gestion.finanzas.editar.estado_pago")

        if st.button("Volver", key="gestion.finanzas.editar.volver.auto", width="stretch", type="secondary"):
            _go(section="finanzas", mode="detalle", selected_id=ruta)

        datos_fin = {
            "MONTO_DEMANDADO": str(st.session_state.get("gestion.finanzas.editar.monto", "") or ""),
            "HONORARIOS_PACTADOS": str(st.session_state.get("gestion.finanzas.editar.honorarios", "") or ""),
            "ESTADO_PAGO": str(st.session_state.get("gestion.finanzas.editar.estado_pago", "") or ""),
        }
        baseline = st.session_state.get(fin_saved_key, {})
        if not isinstance(baseline, dict):
            baseline = {}

        if datos_fin != baseline:
            if not _enforce_permission("finance:write", "No tiene permiso para modificar finanzas."):
                card_end()
                return
            try:
                ok_fin = gestor.guardar_datos_financieros(
                    caso_sel.ruta,
                    datos_fin,
                    actor_ctx=_actor_ctx(),
                )
            except ValueError as e:
                st.error(str(e))
                card_end()
                return
            if ok_fin:
                st.session_state[fin_saved_key] = dict(datos_fin)
                st.cache_data.clear()
                st.session_state.pop("df_full", None)
                _ui_toast("Auto-guardado finanzas")
                st.caption(f"Auto-guardado: {datetime.now().strftime('%H:%M:%S')}")
            else:
                st.error("No se pudo auto-guardar finanzas.")
        card_end()
        return

    submitted = False
    cancel_clicked = False
    with st.form("gestion.finanzas.editar.form"):
        fc1, fc2, fc3 = st.columns(3)
        with fc1:
            monto = st.text_input("Monto demandado", key="gestion.finanzas.editar.monto")
        with fc2:
            honorarios = st.text_input("Honorarios pactados", key="gestion.finanzas.editar.honorarios")
        with fc3:
            estado_pago = st.selectbox("Estado de pago", ESTADOS_PAGO, key="gestion.finanzas.editar.estado_pago")

        b1, b2 = st.columns(2)
        with b1:
            submitted = st.form_submit_button("Guardar", key="gestion.finanzas.editar.guardar", width="stretch")
        with b2:
            cancel_clicked = st.form_submit_button(
                "Cancelar",
                key="gestion.finanzas.editar.cancelar",
                width="stretch",
                type="secondary",
            )

    if cancel_clicked:
        _go(section="finanzas", mode="detalle", selected_id=ruta)

    if submitted:
        if not _enforce_permission("finance:write", "No tiene permiso para modificar finanzas."):
            card_end()
            return
        datos_fin = {
            "MONTO_DEMANDADO": monto,
            "HONORARIOS_PACTADOS": honorarios,
            "ESTADO_PAGO": estado_pago,
        }
        try:
            ok_fin = gestor.guardar_datos_financieros(
                caso_sel.ruta,
                datos_fin,
                actor_ctx=_actor_ctx(),
            )
        except ValueError as e:
            st.error(str(e))
            card_end()
            return
        if ok_fin:
            st.cache_data.clear()
            st.success("Datos financieros guardados.")
            _ui_toast("Finanzas guardadas")
            _go(section="finanzas", mode="detalle", selected_id=ruta)
    card_end()


# Ã¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢Â
# FORMULARIOS
# Ã¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢Â

def formulario_nuevo_caso(ui, gestor: GestorCasos):
    """Formulario optimizado para crear un nuevo caso."""
    with ui.form("nuevo_caso_form"):
        anio = st.selectbox("AÃ±o", gestor.obtener_años_existentes())
        estado = st.selectbox("Estado", ESTADOS_DISPONIBLES)

        opcion_cliente = st.radio("Cliente", ["Existente", "Nuevo"], horizontal=True)

        clientes_existentes = gestor.obtener_clientes_existentes()

        if opcion_cliente == "Existente" and clientes_existentes:
            cliente_final = st.selectbox("Seleccionar Cliente", clientes_existentes)
        else:
            cliente_final = st.text_input("Nombre del Nuevo Cliente", placeholder="Apellido Nombre")

        fuero = st.selectbox("Fuero", FUEROS_DISPONIBLES)
        nombre_caso = st.text_input("Nombre del Caso (Causa)", placeholder="Ej: Perez vs. Lopez")

        submitted = st.form_submit_button("CREAR CASO", width="stretch")

        if submitted:
            if not _enforce_permission("cases:create", "No tiene permiso para crear casos."):
                return
            if not cliente_final or not nombre_caso or cliente_final.strip() == "":
                st.error("El nombre del cliente y del caso son obligatorios.")
            else:
                exito, mensaje = gestor.crear_caso(
                    anio,
                    estado,
                    cliente_final,
                    fuero,
                    nombre_caso,
                    actor_ctx=_actor_ctx(),
                )
                if exito:
                    st.cache_data.clear()
                    st.success(mensaje)
                    st.rerun()
                else:
                    st.error(mensaje)


def formulario_editar_caso(ui, gestor: GestorCasos, casos: List[Caso]):
    """Formulario para editar un caso existente con sincronizacion de carpetas."""
    if not casos:
        ui.warning("No hay casos para editar")
        return

    opciones_casos = [f"{c.cliente} | {c.causa}" for c in casos]
    caso_seleccionado_idx = ui.selectbox(
        "Seleccionar caso:",
        options=range(len(opciones_casos)),
        format_func=lambda x: opciones_casos[x]
    )

    caso = casos[caso_seleccionado_idx]

    st.markdown(f"**{caso.causa}**")
    st.caption(f"{caso.cliente} | {caso.fuero}")

    if ui.button("Abrir carpeta del caso", width="stretch"):
        open_path(caso.ruta, ui)

    with ui.form("editar_caso_form"):
        st.markdown("#### Ubicacion del Caso")

        anio_actual = getattr(caso, "aÃ±o", getattr(caso, "a\u00c3\u00b1o", ""))
        idx_anio = gestor.obtener_años_existentes().index(anio_actual) if anio_actual in gestor.obtener_años_existentes() else 0
        nuevo_anio = st.selectbox("AÃ±o", gestor.obtener_años_existentes(), index=idx_anio)

        idx_estado = ESTADOS_DISPONIBLES.index(caso.estado) if caso.estado in ESTADOS_DISPONIBLES else 0
        nuevo_estado = st.selectbox("Estado", ESTADOS_DISPONIBLES, index=idx_estado)

        clientes_existentes = ["[Mantener actual]"] + gestor.obtener_clientes_existentes()
        idx_cliente = clientes_existentes.index(caso.cliente) if caso.cliente in clientes_existentes else 0
        cliente_sel = st.selectbox("Cliente", clientes_existentes, index=idx_cliente)

        if cliente_sel == "[Mantener actual]":
            nuevo_cliente = caso.cliente
        else:
            nuevo_cliente = cliente_sel

        idx_fuero = FUEROS_DISPONIBLES.index(caso.fuero) if caso.fuero in FUEROS_DISPONIBLES else 0
        nuevo_fuero = st.selectbox("Fuero", FUEROS_DISPONIBLES, index=idx_fuero)

        nueva_causa = st.text_input("Nombre del Caso (Causa)", caso.causa,
                                    help="Cambiar esto renombrara la carpeta fisica")

        st.markdown("---")
        st.markdown("#### Datos del Expediente")

        tipo_proceso = st.text_input("Tipo Proceso", caso.tipo_proceso)
        jurisdiccion = st.text_input("Jurisdiccion", caso.jurisdiccion)
        organismo = st.text_input("Organismo", caso.organismo)
        expediente = st.text_input("Expediente", caso.expediente)
        caratula = st.text_input("Caratula", caso.caratula)
        responsable = st.text_input("Responsable", caso.responsable)
        control = st.text_input("Control", caso.control)
        evento = st.text_input("Ultimo Evento", caso.evento)
        fecha_evento = st.text_input("Fecha Evento (DD/MM/YYYY)", caso.fecha_evento)
        tarea_pendiente = st.text_input("Tarea Pendiente", caso.tarea_pendiente)
        fecha_tarea = st.text_input("Fecha Tarea (DD/MM/YYYY)", caso.fecha_tarea)
        observaciones = st.text_area("Observaciones", caso.observaciones)

        nueva_ruta = caso.ruta

        submitted = st.form_submit_button("GUARDAR CAMBIOS", width="stretch")

        if submitted:
            if not _enforce_permission("cases:write", "No tiene permiso para editar casos."):
                return
            # En modo DB, mover_carpeta_fisica actualiza clasificacion sin mover carpetas
            exito_mov, nueva_ruta = gestor.mover_carpeta_fisica(
                caso,
                nuevo_anio,
                nuevo_estado,
                nuevo_cliente,
                nuevo_fuero,
                nueva_causa,
                actor_ctx=_actor_ctx(),
            )

            if not exito_mov:
                st.error("No se pudo actualizar la clasificacion. Cambios cancelados.")
                return

            datos = {
                'TIPO_PROCESO': tipo_proceso,
                'JURISDICCION': jurisdiccion,
                'ORGANISMO': organismo,
                'EXPEDIENTE': expediente,
                'CARATULA': caratula,
                'RESPONSABLE': responsable,
                'CONTROL': control,
                'EVENTO': evento,
                'FECHA_EVENTO': fecha_evento,
                'TAREA_PENDIENTE': tarea_pendiente,
                'FECHA_TAREA': fecha_tarea,
                'OBSERVACIONES': observaciones
            }

            if gestor.actualizar_caso(nueva_ruta, datos, actor_ctx=_actor_ctx()):
                st.cache_data.clear()
                st.success("Caso actualizado y sincronizado correctamente")
                st.rerun()
            else:
                st.error("Error al guardar cambios en la ficha")


# Ã¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢Â
# SPRINT 4: AUDITORIA (sin CSV crudo)
# Ã¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢Â

def _render_trend_degradation_alert(alert: Dict[str, Any]) -> None:
    if not isinstance(alert, dict):
        return
    if not bool(alert.get("show_alert", False)):
        return

    severity = str(alert.get("severity", "leve")).lower()
    message = str(alert.get("message", "")).strip()

    if severity == "critica":
        st.error(message or "Degradacion critica detectada en tendencia.")
    elif severity == "moderada":
        st.warning(message or "Degradacion moderada detectada en tendencia.")
    else:
        st.info(message or "Degradacion leve detectada en tendencia.")

    delta = alert.get("delta", {}) if isinstance(alert.get("delta"), dict) else {}
    ratio = alert.get("ratio", {}) if isinstance(alert.get("ratio"), dict) else {}
    st.caption(
        "Delta: "
        f"Errores {float(delta.get('errores', 0.0)):+.1f} | "
        f"Warnings {float(delta.get('warnings', 0.0)):+.1f} | "
        f"Ratio E={float(ratio.get('errores', 1.0)):.2f} "
        f"W={float(ratio.get('warnings', 1.0)):.2f}"
    )

    suggestions = alert.get("suggested_actions", [])
    if isinstance(suggestions, list) and suggestions:
        st.caption("Sugerencias:")
        for action in suggestions:
            text = str(action).strip()
            if text:
                st.write(f"- {text}")


def render_auditoria(gestor: GestorCasos, casos: List[Caso]):
    """Auditoria: pantalla tecnica limpia con estado + detalles colapsados."""
    start_ui_block_order("Auditoria")
    mark_ui_block("Auditoria", "summary")
    section_header(
        "Auditoria",
        subtitle="Mando de seguridad y calidad de datos",
        meta=[f"Casos {len(casos)}", f"Backend {'DB' if is_db_mode() else 'FS'}", f"Auto-guardado {'ON' if _auto_save_changes_enabled() else 'OFF'}"],
    )
    auto_daily_result = _ensure_daily_audit_snapshot_ui(gestor, casos)

    can_dashboard, reason_dashboard = _route_enabled("Dashboard")
    can_gestion, reason_gestion = _route_enabled("Gestion")
    can_agenda, reason_agenda = _route_enabled("Agenda")
    can_config, reason_config = _route_enabled("Configuracion")
    mark_ui_block("Auditoria", "actions")
    with st.expander("Mas acciones", expanded=False):
        card_begin("Navegacion rapida", subtitle="Volver a operacion diaria", variant="tight")
        n1, n2, n3, n4 = st.columns(4)
        with n1:
            if st.button(
                "Ir a Dashboard",
                key="audit.nav.dashboard",
                width="stretch",
                type="secondary",
                disabled=not can_dashboard,
                help=reason_dashboard or None,
            ):
                _go_route("Dashboard")
        with n2:
            if st.button(
                "Ir a Gestion",
                key="audit.nav.gestion",
                width="stretch",
                type="secondary",
                disabled=not can_gestion,
                help=reason_gestion or None,
            ):
                _go_route("Gestion", mode="listado")
        with n3:
            if st.button(
                "Ir a Agenda",
                key="audit.nav.agenda",
                width="stretch",
                type="secondary",
                disabled=not can_agenda,
                help=reason_agenda or None,
            ):
                _go_route("Agenda", mode="listado")
        with n4:
            if st.button(
                "Ir a Configuracion",
                key="audit.nav.configuracion",
                width="stretch",
                type="secondary",
                disabled=not can_config,
                help=reason_config or None,
            ):
                _go_route("Configuracion", mode="listado")
        st.caption(f"Snapshot diario: {auto_daily_result.get('date', datetime.now().strftime('%Y-%m-%d'))}")
        card_end()

    # Toolbar de acciones
    card_begin("Acciones", subtitle="Ejecutar, reparar, exportar", variant="tight")
    a1, a2, a3 = st.columns(3)
    with a1:
        run_audit = st.button("Ejecutar auditoria", width="stretch", key="audit_run")
    with a2:
        confirmar_fix = st.checkbox("Confirmo reparar", key="audit_fix_confirm")
        if st.button("Reparar subcarpetas", width="stretch", disabled=not confirmar_fix, key="audit_fix"):
            total_creadas = 0
            pb = st.progress(0)
            for i, c in enumerate(casos, start=1):
                total_creadas += gestor.ensure_case_structure(c.ruta)
                pb.progress(int((i / max(1, len(casos))) * 100))
            st.success(f"Reparacion finalizada. Subcarpetas creadas: {total_creadas}.")
            st.cache_data.clear()
            _ui_toast("Reparacion masiva aplicada")
    with a3:
        if auto_daily_result.get("error"):
            st.caption("Snapshot diario auto: error")
            st.caption(str(auto_daily_result.get("error")))
        elif auto_daily_result.get("created"):
            st.caption("Snapshot diario auto: generado")
            st.caption(str(auto_daily_result.get("snapshot_path", "")))
        else:
            st.caption("Snapshot diario auto: ya existente hoy")
            st.caption("Exportes en la secciÃ³n inferior.")
    card_end()

    # Ejecutar auditoria si se presiono el boton
    mark_ui_block("Auditoria", "work")
    if run_audit:
        with st.spinner("Ejecutando auditoria..."):
            reporte = auditar_app(gestor, casos)
            kpi_snapshot = build_operational_kpi_snapshot(gestor, casos)
            st.session_state["ultimo_resultado_auditoria"] = reporte
            st.session_state["ultimo_kpi_snapshot"] = kpi_snapshot
            try:
                manual_snapshot = _persist_daily_audit_snapshot(
                    gestor,
                    casos,
                    reporte=reporte,
                    kpi_snapshot=kpi_snapshot,
                    source="ui_manual",
                )
                st.session_state["audit.daily.auto_result"] = manual_snapshot
            except Exception as exc:
                st.session_state["audit.daily.auto_result"] = {
                    "created": False,
                    "date": datetime.now().strftime("%Y-%m-%d"),
                    "snapshot_path": "",
                    "history_path": "",
                    "error": str(exc),
                }

    reporte = st.session_state.get("ultimo_resultado_auditoria")
    auto_daily_result = st.session_state.get("audit.daily.auto_result", auto_daily_result) or {}

    # Mostrar resultado si existe
    if reporte:
        r = reporte.get("resumen", {})
        errores = int(r.get("errores", 0))
        warnings = int(r.get("warnings", 0))
        infos = int(r.get("info", 0))
        casos_total = int(r.get("casos", 0))

        card_begin("Resumen", subtitle="Estado del sistema", variant="tight")
        audit_status_badge(errores, warnings)
        c1, c2, c3 = st.columns(3)
        with c1:
            kpi_card("Errores", errores, status="error", tone="bad")
        with c2:
            kpi_card("Advertencias", warnings, status="warn", tone="warn")
        with c3:
            kpi_card("Info", infos, status="ok", tone="good")
        st.caption(f"Casos auditados: {casos_total}")
        card_end()

        hall = reporte.get("hallazgos", [])
        if hall:
            card_begin("Hallazgos")
            with st.expander("Ver detalles tecnicos", expanded=False):
                df_h = pd.DataFrame(hall)
                orden = {"ERROR": 0, "WARN": 1, "INFO": 2}
                df_h["_ORD"] = df_h["nivel"].map(orden).fillna(9)
                df_h = df_h.sort_values(
                    ["_ORD", "codigo"], ascending=[True, True]
                ).drop(columns=["_ORD"])

                st.dataframe(df_h, width="stretch", hide_index=True)

                csv_h = _csv_bytes(df_h)
                ts_aud_csv = _get_export_ts("auditoria_csv")
                st.download_button(
                    "Descargar hallazgos (CSV)",
                    data=csv_h,
                    file_name=f"auditoria_hallazgos_{ts_aud_csv}.csv",
                    mime="text/csv",
                    width="stretch",
                    key="download_audit_csv",
                )
            card_end()

    else:
        st.info("Presione 'Ejecutar auditoria' para analizar el sistema.")

    metricas = _cargar_metricas_auditoria(gestor, casos)
    completitud = metricas.get("completitud", {})

    card_begin("Salud de datos", subtitle="Completitud por campo (Ãºltima auditorÃ­a o cÃ¡lculo rÃ¡pido)", variant="tight")
    campos_salud = ["JURISDICCION", "ORGANISMO", "EXPEDIENTE", "CARATULA", "RESPONSABLE", "CONTROL"]
    st.caption("Porcentaje de completitud por campo clave.")
    if completitud:
        for campo in campos_salud:
            pct = completitud.get(campo, {}).get("pct_completos", 0)
            progress_row(campo.capitalize(), pct)

        with st.expander("Tabla completa de completitud (por campo)", expanded=False):
            df_m = pd.DataFrame([
                {"Campo": k, **v} for k, v in completitud.items()
            ]).sort_values("pct_completos", ascending=True)
            st.dataframe(df_m, width="stretch", hide_index=True)
    else:
        st.info("No hay datos para calcular completitud.")
    card_end()

    kpi_snapshot = st.session_state.get("ultimo_kpi_snapshot")
    if not isinstance(kpi_snapshot, dict):
        kpi_snapshot = build_operational_kpi_snapshot(gestor, casos)
    kpi_data = kpi_snapshot.get("kpis", {}) if isinstance(kpi_snapshot, dict) else {}
    card_begin("KPI operativo", subtitle="Snapshot de metas Fase 1", variant="tight")
    if kpi_data:
        metric_labels = [
            ("FECHA_TAREA", "FECHA_TAREA > 60%"),
            ("EXPEDIENTE", "EXPEDIENTE > 70%"),
            ("EVENTO_FECHA_EVENTO", "EVENTO/FECHA_EVENTO > 40%"),
            ("COBERTURA_FINANCIERA", "Cobertura financiera >= 70%"),
        ]
        rows = []
        for metric_key, metric_label in metric_labels:
            metric = kpi_data.get(metric_key, {}) or {}
            pct = float(metric.get("pct", 0.0))
            target_pct = float(metric.get("target_pct", 0.0))
            progress_row(metric_label, pct)
            st.caption(
                f"Actual: {pct:.1f}% ({int(metric.get('completed', 0))}/{int(metric.get('total', 0))}) "
                f"| Objetivo: {target_pct:.1f}% | Gap: {float(metric.get('gap_pct', 0.0)):.1f}"
            )
            rows.append({
                "KPI": metric_label,
                "Actual %": pct,
                "Objetivo %": target_pct,
                "Gap %": float(metric.get("gap_pct", 0.0)),
                "Cumple": "SÃ­" if metric.get("goal_met") else "No",
                "Completos": int(metric.get("completed", 0)),
                "Total": int(metric.get("total", 0)),
            })

        with st.expander("Ver tabla KPI", expanded=False):
            df_kpi = pd.DataFrame(rows)
            st.dataframe(df_kpi, width="stretch", hide_index=True)

            json_kpi = json.dumps(kpi_snapshot, ensure_ascii=False, indent=2).encode("utf-8")
            csv_kpi = _csv_bytes(df_kpi)
            ts_kpi_json = _get_export_ts("kpi_snapshot_json")
            ts_kpi_csv = _get_export_ts("kpi_snapshot_csv")
            b1, b2 = st.columns(2)
            with b1:
                st.download_button(
                    "Exportar KPI (JSON)",
                    data=json_kpi,
                    file_name=f"kpi_snapshot_{ts_kpi_json}.json",
                    mime="application/json",
                    width="stretch",
                    key="download_kpi_snapshot_json",
                )
            with b2:
                st.download_button(
                    "Exportar KPI (CSV)",
                    data=csv_kpi,
                    file_name=f"kpi_snapshot_{ts_kpi_csv}.csv",
                    mime="text/csv",
                    width="stretch",
                    key="download_kpi_snapshot_csv",
                )
        st.caption(f"Generado: {kpi_snapshot.get('generated_at', '')}")
    else:
        st.info("No hay datos para calcular KPI operativo.")
    card_end()

    trend_rows = _load_daily_audit_trend_rows(limit=21)
    card_begin("Tendencia diaria", subtitle="Errores y advertencias (historial persistido)", variant="tight")
    if trend_rows:
        df_trend = pd.DataFrame(trend_rows).sort_values("date")
        degradation_alert = build_trend_degradation_alert(df_trend.to_dict("records"), baseline_days=7)
        _render_trend_degradation_alert(degradation_alert)
        chart_df = df_trend[["date", "errores", "warnings"]].set_index("date")
        st.line_chart(chart_df, width="stretch")
        st.caption("Serie diaria agregada por fecha (se conserva la ultima corrida del dia).")

        with st.expander("Ver detalle de tendencia", expanded=False):
            cols = [
                "date",
                "errores",
                "warnings",
                "info",
                "casos",
                "kpi_fecha_tarea_pct",
                "kpi_expediente_pct",
                "kpi_evento_fecha_evento_pct",
                "kpi_cobertura_financiera_pct",
                "source",
            ]
            df_detail = df_trend[cols]
            st.dataframe(df_detail, width="stretch", hide_index=True)

            csv_trend = _csv_bytes(df_detail)
            ts_trend_csv = _get_export_ts("audit_trend_csv")
            st.download_button(
                "Descargar tendencia (CSV)",
                data=csv_trend,
                file_name=f"auditoria_tendencia_{ts_trend_csv}.csv",
                mime="text/csv",
                width="stretch",
                key="download_audit_trend_csv",
            )
    else:
        st.info("Sin historial diario aun. Se genera automaticamente una vez por dia en esta vista.")
    card_end()

    snapshots = load_daily_audit_snapshots(limit=120)
    hallazgo_rows = build_operational_hallazgos_rows(snapshots)
    card_begin("Export operativo de hallazgos", subtitle="Filtro por nivel/codigo/fecha + metadata de snapshot/backend", variant="tight")
    if hallazgo_rows:
        niveles = sorted({
            str(row.get("nivel", "")).strip().upper()
            for row in hallazgo_rows
            if str(row.get("nivel", "")).strip()
        })
        level_options = ["Todos"] + niveles

        def _to_date_yyyy_mm_dd(raw: str) -> date | None:
            text = str(raw or "").strip()
            if not text:
                return None
            try:
                return datetime.strptime(text[:10], "%Y-%m-%d").date()
            except Exception:
                return None

        available_dates = sorted({
            str(row.get("date", "")).strip()
            for row in hallazgo_rows
            if str(row.get("date", "")).strip()
        })
        date_min = _to_date_yyyy_mm_dd(available_dates[0]) if available_dates else None
        date_max = _to_date_yyyy_mm_dd(available_dates[-1]) if available_dates else None

        default_from = date_min or date.today()
        default_to = date_max or date.today()

        f1, f2, f3, f4 = st.columns([1.2, 1.2, 1, 1])
        with f1:
            filter_level = st.selectbox(
                "Nivel",
                options=level_options,
                index=0,
                key="audit.ops_export.filter.level",
            )
        with f2:
            filter_code = st.text_input(
                "Codigo contiene",
                value="",
                key="audit.ops_export.filter.code",
                placeholder="Ej: DATA-050",
            )
        with f3:
            filter_date_from = st.date_input(
                "Desde",
                value=default_from,
                key="audit.ops_export.filter.date_from",
            )
        with f4:
            filter_date_to = st.date_input(
                "Hasta",
                value=default_to,
                key="audit.ops_export.filter.date_to",
            )

        if filter_date_from and filter_date_to and filter_date_from > filter_date_to:
            filter_date_from, filter_date_to = filter_date_to, filter_date_from

        date_from_iso = filter_date_from.isoformat() if isinstance(filter_date_from, date) else ""
        date_to_iso = filter_date_to.isoformat() if isinstance(filter_date_to, date) else ""

        filtered_rows = filter_operational_hallazgos(
            hallazgo_rows,
            level=filter_level,
            code_query=filter_code,
            date_from=date_from_iso,
            date_to=date_to_iso,
        )

        st.caption(
            f"Hallazgos filtrados: {len(filtered_rows)} de {len(hallazgo_rows)} "
            f"| Snapshots analizados: {len(snapshots)}"
        )

        df_ops = pd.DataFrame(filtered_rows)
        show_columns = [
            "date",
            "nivel",
            "codigo",
            "mensaje",
            "source",
            "backend_mode",
            "generated_at",
        ]
        if not df_ops.empty:
            with st.expander("Ver detalle filtrado", expanded=False):
                cols = [col for col in show_columns if col in df_ops.columns]
                st.dataframe(df_ops[cols], width="stretch", hide_index=True)
        else:
            st.info("No hay hallazgos para los filtros seleccionados.")

        filters_payload = {
            "level": filter_level,
            "code_query": str(filter_code or "").strip(),
            "date_from": date_from_iso,
            "date_to": date_to_iso,
        }
        export_payload = build_operational_hallazgos_export_payload(
            filtered_rows,
            filters=filters_payload,
            snapshots_count=len(snapshots),
        )

        csv_ops = _csv_bytes(df_ops) if not df_ops.empty else _csv_bytes(pd.DataFrame(columns=show_columns))
        json_ops = payload_to_json_bytes(export_payload)
        ts_ops_csv = _get_export_ts("audit_ops_hallazgos_csv")
        ts_ops_json = _get_export_ts("audit_ops_hallazgos_json")
        b1, b2 = st.columns(2)
        with b1:
            st.download_button(
                "Descargar hallazgos operativos (CSV)",
                data=csv_ops,
                file_name=f"auditoria_hallazgos_operativos_{ts_ops_csv}.csv",
                mime="text/csv",
                width="stretch",
                key="download_audit_ops_hallazgos_csv",
            )
        with b2:
            st.download_button(
                "Descargar hallazgos operativos (JSON)",
                data=json_ops,
                file_name=f"auditoria_hallazgos_operativos_{ts_ops_json}.json",
                mime="application/json",
                width="stretch",
                key="download_audit_ops_hallazgos_json",
            )
    else:
        st.info("No hay snapshots diarios para export operativo de hallazgos.")
    card_end()

    # Exportes
    card_begin("Exportes", variant="tight")
    if reporte:
        json_bytes = json.dumps(reporte, ensure_ascii=False, indent=2).encode("utf-8")
        ts_aud_json = _get_export_ts("auditoria_json")
        st.download_button(
            "Exportar reporte (JSON)",
            data=json_bytes,
            file_name=f"auditoria_vg_{ts_aud_json}.json",
            mime="application/json",
            width="stretch",
            key="download_audit_json",
        )
        if st.button("Regenerar exportes auditoria", key="regen_audit_exports", width="stretch"):
            _regen_export_ts(["auditoria_json", "auditoria_csv"])
            st.cache_data.clear()
            _ui_toast("Exportes de auditoria regenerados")
            st.rerun()
    else:
        st.caption("Ejecute auditoria para habilitar exportes.")
    if auto_daily_result.get("snapshot_path"):
        st.caption(f"Snapshot diario actual: {auto_daily_result.get('snapshot_path')}")
    if auto_daily_result.get("history_path"):
        st.caption(f"Historial de tendencia: {auto_daily_result.get('history_path')}")
    if auto_daily_result.get("error"):
        st.warning(f"No se pudo persistir snapshot diario: {auto_daily_result.get('error')}")
    card_end()

    # Diagnostico basico (siempre visible)
    st.markdown("---")
    st.markdown("#### Diagnostico basico")

    conteo_diag = st.session_state.get("conteo_casos_diag")
    if conteo_diag:
        delta = conteo_diag.get("delta", 0)
        st.write(f"**Conteo DB vs listado:** {conteo_diag.get('db_total', 0)} / {conteo_diag.get('listado_total', 0)} (delta {delta})")
        if delta:
            st.warning("Diferencia detectada entre count(*) y casos cargados. Revisar filtros/joins.")

    st.write("**Backend:** Base de datos PostgreSQL")
    st.write("**Casos cargados:** " + str(len(casos)))


# Ã¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢Â
# CONFIGURACION
# Ã¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢Â

def render_configuracion(gestor: GestorCasos, casos: List[Caso]):
    """Vista de configuracion: estado operativo, edicion y ayuda."""
    start_ui_block_order("Configuracion")
    db_ready = bool(st.session_state.get("db_ready", True))
    db_health = st.session_state.get("db_health", {}) or {}
    auth_required = _env_bool("VG_AUTH_REQUIRED", default=True)
    rbac_strict = _env_bool("VG_RBAC_STRICT", default=True)
    export_strict = _env_bool("VG_EXPORT_STRICT", default=True)
    audit_strict = _env_bool("VG_AUDIT_WRITE_STRICT", default=False)

    mark_ui_block("Configuracion", "summary")
    section_header(
        "Configuracion",
        subtitle="Ajustes operativos y soporte",
        meta=[
            f"Backend {'DB' if is_db_mode() else 'FS'}",
            f"DB {'OK' if db_ready else 'DEGRADADA'}",
            f"Auto-guardado {'ON' if _auto_save_changes_enabled() else 'OFF'}",
        ],
    )

    card_begin("Estado operativo", subtitle="Control de acceso, persistencia y entorno", variant="tight")
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        kpi_card("Auth requerida", "ON" if auth_required else "OFF")
    with c2:
        kpi_card("RBAC estricto", "ON" if rbac_strict else "OFF")
    with c3:
        kpi_card("Export estricto", "ON" if export_strict else "OFF")
    with c4:
        kpi_card("Audit strict", "ON" if audit_strict else "OFF")
    if not db_ready:
        st.warning(f"DB no operativa: {db_health.get('last_error', 'sin detalle')}")
    card_end()

    mark_ui_block("Configuracion", "actions")
    _render_route_quick_nav(
        "config.quick",
        [
            ("Dashboard", "Dashboard", "listado"),
            ("Gestion", "Gestion", "listado"),
            ("Agenda", "Agenda", "listado"),
            ("Finanzas", "Finanzas", "listado"),
            ("Auditoria", "Auditoria", "listado"),
        ],
        title="Navegacion rapida",
        subtitle="Saltos directos para trabajo diario",
        group_in_more_actions=True,
    )

    mark_ui_block("Configuracion", "work")
    tab1, tab2, tab3 = st.tabs(["Operativo", "Editar caso", "Ayuda"])

    with tab1:
        if AUTO_SAVE_OVERRIDE_KEY not in st.session_state:
            st.session_state[AUTO_SAVE_OVERRIDE_KEY] = _env_bool(AUTO_SAVE_CHANGES_ENV, default=True)

        st.toggle(
            "Auto-guardado de cambios",
            key=AUTO_SAVE_OVERRIDE_KEY,
            help="Aplica en ediciones rapidas y formularios compatibles. Recomendado para operacion diaria.",
        )
        st.caption(
            f"Valor efectivo: {'ON' if _auto_save_changes_enabled() else 'OFF'} | "
            f"Default entorno ({AUTO_SAVE_CHANGES_ENV}): {'ON' if _env_bool(AUTO_SAVE_CHANGES_ENV, default=True) else 'OFF'}"
        )

        o1, o2, o3 = st.columns(3)
        with o1:
            if st.button("Recargar cache", key="config.ops.reload_cache", width="stretch", type="secondary"):
                st.cache_data.clear()
                st.session_state.pop("df_full", None)
                _ui_toast("Cache recargada")
                st.rerun()
        with o2:
            if st.button("Ir a Dashboard", key="config.ops.go_dashboard", width="stretch", type="secondary"):
                _go_route("Dashboard")
        with o3:
            if st.button("Reintentar conexion DB", key="config.ops.retry_db", width="stretch", type="secondary"):
                st.session_state["db_ready"] = None
                st.session_state["db_health"] = {}
                st.rerun()

        p1, p2, p3 = st.columns(3)
        with p1:
            if st.button(
                "Crear acceso directo en Escritorio",
                key="config.ops.shortcut.desktop",
                width="stretch",
                type="secondary",
            ):
                ok_shortcut, detail_shortcut = _create_desktop_shortcut()
                if ok_shortcut:
                    st.success(detail_shortcut)
                    _ui_toast("Acceso directo listo")
                else:
                    st.error(detail_shortcut)
        with p2:
            if st.button(
                "Preparar DB de pruebas",
                key="config.ops.setup_test_db",
                width="stretch",
                type="secondary",
            ):
                ok_setup, detail_setup = _setup_test_database_from_ui()
                if ok_setup:
                    st.success("DB de pruebas lista para suites completas.")
                    st.code(detail_setup, language="text")
                    _ui_toast("DB de pruebas preparada")
                else:
                    st.error("No se pudo preparar DB de pruebas.")
                    st.code(detail_setup, language="text")
        with p3:
            st.caption("Ingreso recomendado: icono 'SistemaLegal ERP' en el Escritorio.")

        flags_df = pd.DataFrame(
            [
                {"Flag": "VG_AUTH_REQUIRED", "Valor": "1" if auth_required else "0", "Descripcion": "Requiere autenticacion"},
                {"Flag": "VG_RBAC_STRICT", "Valor": "1" if rbac_strict else "0", "Descripcion": "Permisos por rol estrictos"},
                {"Flag": "VG_EXPORT_STRICT", "Valor": "1" if export_strict else "0", "Descripcion": "Control de exportes por rol"},
                {"Flag": "VG_AUDIT_WRITE_STRICT", "Valor": "1" if audit_strict else "0", "Descripcion": "Bloquea mutaciones sin auditoria"},
                {"Flag": AUTO_SAVE_CHANGES_ENV, "Valor": "1" if _env_bool(AUTO_SAVE_CHANGES_ENV, default=True) else "0", "Descripcion": "Default de auto-guardado"},
            ]
        )
        st.dataframe(flags_df, width="stretch", hide_index=True)

    with tab2:
        if casos:
            formulario_editar_caso(st, gestor, casos)
        else:
            st.info("No hay casos para editar.")

    with tab3:
        ui_centro_ayuda_content()


# Ã¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢Â
# LEGACY: render_panel, render_ajustes (para compatibilidad)
# Ã¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢Â

def render_panel(gestor: GestorCasos, casos: List[Caso], df=None):
    """Legacy: redirige a Dashboard."""
    render_dashboard(gestor, casos)


def render_ajustes(gestor: GestorCasos, casos: List[Caso]):
    """Legacy: redirige a Configuracion."""
    render_configuracion(gestor, casos)

