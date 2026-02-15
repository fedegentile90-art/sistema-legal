"""Gestion v2: reemplazo funcional Casos + Clientes."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Callable, Dict, List

import pandas as pd
import streamlit as st

from domain import Caso
from grids import render_aggrid
from security import has_permission
from ui import card_begin, card_end, section_header, vg_empty_state


UUID_RE = re.compile(r"^[0-9a-fA-F-]{36}$")
DB_CASE_RE = re.compile(r"db[:/\\\\]+cases[:/\\\\]+([0-9a-fA-F-]{36})", re.IGNORECASE)


def _canonical_case_ref(value: str) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    m = DB_CASE_RE.search(raw)
    if m:
        return f"db://cases/{m.group(1).lower()}"
    if UUID_RE.fullmatch(raw):
        return f"db://cases/{raw.lower()}"
    return raw


def _extract_grid_value(value: Any, key: str) -> str:
    if value is None:
        return ""
    if isinstance(value, dict):
        rows = value.get("selected_rows")
        if isinstance(rows, list) and rows and isinstance(rows[0], dict):
            return str(rows[0].get(key, "") or "").strip()
    rows_attr = getattr(value, "selected_rows", None)
    if rows_attr is not None:
        rows = rows_attr
        if hasattr(rows, "to_dict"):
            try:
                rows = rows.to_dict("records")
            except Exception:
                rows = []
        if isinstance(rows, list) and rows and isinstance(rows[0], dict):
            return str(rows[0].get(key, "") or "").strip()
    return ""


def _case_by_ref(casos: List[Caso], case_ref: str) -> Caso | None:
    target = _canonical_case_ref(case_ref)
    for c in casos:
        if _canonical_case_ref(str(c.ruta)) == target:
            return c
    return None


def _render_casos_listado(df: pd.DataFrame, casos: List[Caso]) -> None:
    card_begin("Casos", subtitle=f"Listado v2 · {len(df)} filas", variant="tight")
    cols_default = [c for c in ("SEMÁFORO", "FECHA TAREA", "CLIENTE", "FUERO", "CAUSA", "EXPEDIENTE", "RESPONSABLE", "ESTADO", "_RUTA") if c in df.columns]
    if not cols_default:
        cols_default = [c for c in df.columns if c != "_RUTA"] + (["_RUTA"] if "_RUTA" in df.columns else [])
    grid_df = df[cols_default].copy()
    selected = render_aggrid(grid_df, key="gestion.casos.listado.grid", height=520)
    selected_ref = _extract_grid_value(selected, "_RUTA")
    canonical = _canonical_case_ref(selected_ref)
    if canonical:
        st.session_state["gestion.selected.case_id"] = canonical
        st.session_state["selected_case_id"] = canonical
        st.session_state["selected_item_id"] = canonical
        st.session_state["gestion.widgets.modebar.casos.label"] = "Detalle"
        st.rerun()
    card_end()


def _render_casos_detalle(casos: List[Caso]) -> None:
    case_ref = _canonical_case_ref(str(st.session_state.get("gestion.selected.case_id", "") or st.session_state.get("selected_case_id", "") or ""))
    caso = _case_by_ref(casos, case_ref)
    if not caso:
        st.info("Seleccione un caso en Listado para ver Detalle.")
        st.session_state["gestion.widgets.modebar.casos.label"] = "Listado"
        st.rerun()
        return
    card_begin("Detalle caso", subtitle=f"{caso.cliente} · {caso.causa}", variant="tight")
    c1, c2 = st.columns(2)
    with c1:
        st.write(f"**Año:** {caso.año}")
        st.write(f"**Estado:** {caso.estado}")
        st.write(f"**Fuero:** {caso.fuero}")
        st.write(f"**Expediente:** {caso.expediente}")
    with c2:
        st.write(f"**Responsable:** {caso.responsable}")
        st.write(f"**Fecha tarea:** {caso.fecha_tarea}")
        st.write(f"**Tarea pendiente:** {caso.tarea_pendiente}")
        st.write(f"**Evento:** {caso.evento}")
    st.caption(str(caso.ruta))
    card_end()


def _render_casos_editar(gestor: Any, casos: List[Caso], actor_ctx_fn: Callable[[], Dict[str, str]]) -> None:
    case_ref = _canonical_case_ref(str(st.session_state.get("gestion.selected.case_id", "") or st.session_state.get("selected_case_id", "") or ""))
    caso = _case_by_ref(casos, case_ref)
    if not caso:
        st.info("Seleccione un caso en Listado para editar.")
        st.session_state["gestion.widgets.modebar.casos.label"] = "Listado"
        st.rerun()
        return
    if not has_permission("cases:write"):
        st.error("No tiene permisos para editar casos.")
        return

    card_begin("Editar caso", subtitle=f"{caso.cliente} · {caso.causa}", variant="tight")
    with st.form("gestion.v2.casos.editar.form"):
        c1, c2 = st.columns(2)
        with c1:
            responsable = st.text_input("Responsable", value=caso.responsable or "")
            tarea = st.text_input("Tarea pendiente", value=caso.tarea_pendiente or "")
            fecha_tarea = st.text_input("Fecha tarea (YYYY-MM-DD)", value=caso.fecha_tarea or "")
        with c2:
            evento = st.text_input("Evento", value=caso.evento or "")
            fecha_evento = st.text_input("Fecha evento (YYYY-MM-DD)", value=caso.fecha_evento or "")
            expediente = st.text_input("Expediente", value=caso.expediente or "")
        b1, b2 = st.columns(2)
        with b1:
            save = st.form_submit_button("Guardar", width="stretch")
        with b2:
            cancel = st.form_submit_button("Cancelar", width="stretch")
    if cancel:
        st.session_state["gestion.widgets.modebar.casos.label"] = "Detalle"
        st.rerun()
    if save:
        ok = gestor.actualizar_campos_ficha(
            Path(case_ref),
            {
                "RESPONSABLE": responsable,
                "TAREA_PENDIENTE": tarea,
                "FECHA_TAREA": fecha_tarea,
                "EVENTO": evento,
                "FECHA_EVENTO": fecha_evento,
                "EXPEDIENTE": expediente,
            },
            actor_ctx=actor_ctx_fn(),
        )
        if ok:
            st.success("Caso actualizado.")
            st.session_state["gestion.widgets.modebar.casos.label"] = "Detalle"
            st.rerun()
        st.error("No se pudo actualizar el caso.")
    card_end()


def _render_clientes(section_mode: str, casos: List[Caso]) -> None:
    rows = []
    grouped: Dict[str, List[Caso]] = {}
    for c in casos:
        grouped.setdefault(str(c.cliente or "S/D"), []).append(c)
    for cliente, items in grouped.items():
        rows.append(
            {
                "CLIENTE": cliente,
                "CAUSAS": len(items),
                "ACTIVOS": sum(1 for it in items if "activo" in str(it.estado or "").lower()),
                "_CLIENTE": cliente,
            }
        )
    df = pd.DataFrame(rows).sort_values(["CLIENTE"]) if rows else pd.DataFrame(columns=["CLIENTE", "CAUSAS", "ACTIVOS", "_CLIENTE"])
    card_begin("Clientes", subtitle=f"{len(df)} clientes", variant="tight")
    if df.empty:
        st.info("No hay clientes para mostrar.")
        card_end()
        return

    if section_mode == "Listado":
        selected = render_aggrid(df, key="gestion.cliente.listado.grid", height=480)
        selected_client = _extract_grid_value(selected, "_CLIENTE")
        if selected_client:
            st.session_state["gestion.selected.client_id"] = selected_client
            st.session_state["gestion.widgets.modebar.clientes.label"] = "Detalle"
            st.rerun()
    else:
        selected_client = str(st.session_state.get("gestion.selected.client_id", "")).strip()
        if not selected_client:
            st.info("Seleccione un cliente en Listado.")
            st.session_state["gestion.widgets.modebar.clientes.label"] = "Listado"
            st.rerun()
            card_end()
            return
        client_cases = [c for c in casos if str(c.cliente or "") == selected_client]
        st.write(f"**Cliente:** {selected_client}")
        st.caption(f"Casos: {len(client_cases)}")
        details = pd.DataFrame(
            [
                {
                    "FUERO": c.fuero,
                    "CAUSA": c.causa,
                    "EXPEDIENTE": c.expediente,
                    "ESTADO": c.estado,
                    "FECHA TAREA": c.fecha_tarea,
                    "_RUTA": str(c.ruta),
                }
                for c in client_cases
            ]
        )
        if not details.empty:
            render_aggrid(details, key="gestion.v2.clientes.detalle.grid", height=360)
    card_end()


def render_gestion_v2(
    gestor: Any,
    casos: List[Caso],
    df: pd.DataFrame | None,
    *,
    go_route: Callable[[str, str, str | None], None],
    actor_ctx_fn: Callable[[], Dict[str, str]],
) -> None:
    section_header(
        "Gestion",
        subtitle="Gestion v2 (Casos + Clientes)",
        meta=[f"Casos {len(casos)}", "DB-first", "Compatibilidad dual tasks"],
    )

    c1, c2 = st.columns(2)
    with c1:
        if st.button("Ir a Agenda", key="gestion.context.casos.go_agenda", width="stretch", type="secondary"):
            go_route("Agenda", "listado", None)
    with c2:
        if st.button("Ir a Dashboard", key="gestion.context.casos.go_dashboard", width="stretch", type="secondary"):
            go_route("Dashboard", "listado", None)

    section = st.radio(
        "Seccion",
        ["Casos", "Clientes"],
        key="gestion.widgets.tabbar.label",
        horizontal=True,
        label_visibility="collapsed",
    )

    if section == "Casos":
        mode = st.radio(
            "Modo",
            ["Listado", "Detalle", "Editar"],
            key="gestion.widgets.modebar.casos.label",
            horizontal=True,
            label_visibility="collapsed",
        )
        if df is None:
            data = pd.DataFrame([c.to_dict() for c in casos]) if casos else pd.DataFrame()
        else:
            data = df.copy()
        if data.empty:
            vg_empty_state(
                "No hay casos cargados.",
                "Ir a Dashboard",
                lambda: go_route("Dashboard", "listado", None),
                key="gestion.v2.empty.casos",
            )
            return
        if mode == "Listado":
            _render_casos_listado(data, casos)
        elif mode == "Detalle":
            _render_casos_detalle(casos)
        else:
            _render_casos_editar(gestor, casos, actor_ctx_fn)
        return

    mode_cli = st.radio(
        "Modo clientes",
        ["Listado", "Detalle", "Editar"],
        key="gestion.widgets.modebar.clientes.label",
        horizontal=True,
        label_visibility="collapsed",
    )
    _render_clientes(mode_cli, casos)

