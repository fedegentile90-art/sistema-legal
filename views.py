"""
Vistas principales: Dashboard, Gestion (Casos/Cliente/Agenda/Finanzas), Auditoria, Config.
Sprint 2: Dashboard con KPIs reales
Sprint 3: Gestion maestro-detalle
Sprint 4: Auditoria sin CSV crudo
"""

import streamlit as st
import pandas as pd
from pathlib import Path
from datetime import datetime, timedelta
from typing import List
import os
import shutil
import json

from config import (
    RUTA_BASE, ESTADOS_DISPONIBLES, FUEROS_DISPONIBLES,
    CAMPOS_FINANCIEROS, ESTADOS_PAGO, SUBCARPETAS_ESTANDAR,
    limpiar_nombre_carpeta,
)
from domain import Caso
from fs_repo import GestorCasos
from exports import df_to_xlsx_bytes
from ui import (
    _ensure_bool_state, _ensure_int_step_state, _swap,
    _df_select_kwargs, _ui_toast, help_section,
    page_header, render_grid, section,
    mode_tabs, empty_state_nav, grid_shell, detail_shell, edit_shell,
    kpi_card, progress_row, audit_status_badge,
    ui_centro_ayuda_content,
)
from grids import render_aggrid
from audit import auditar_app


# ══════════════════════════════════════════════════════════════════════════════
# SPRINT 2: DASHBOARD (Centro de mando con KPIs)
# ══════════════════════════════════════════════════════════════════════════════

def render_dashboard(gestor: GestorCasos, casos: List[Caso]):
    """Dashboard real: KPIs + salud de datos + acciones rapidas. Sin tablas."""
    page_header("Dashboard", subtitle="Centro de mando")

    if not casos:
        st.info("No hay casos cargados. Use Gestion para crear el primer caso.")
        if st.button("Ir a Gestion", use_container_width=True):
            from nav import navigate_to
            navigate_to("Gestion")
        return

    # Cargar metricas de auditoria (si hay cache o JSON reciente)
    metricas = _cargar_metricas_auditoria(gestor, casos)

    # ── Fila 1: KPIs principales ──
    st.markdown("#### Resumen")
    k1, k2, k3, k4 = st.columns(4)

    total = metricas.get("casos_total", len(casos))
    completitud = metricas.get("completitud", {})

    pct_responsable = completitud.get("RESPONSABLE", {}).get("pct_completos", 0)
    pct_caratula = completitud.get("CARATULA", {}).get("pct_completos", 0)
    pct_expediente = completitud.get("EXPEDIENTE", {}).get("pct_completos", 0)

    with k1:
        kpi_card("Casos Total", total, tone="neutral")
    with k2:
        tone = "good" if pct_responsable >= 90 else ("warn" if pct_responsable >= 70 else "bad")
        kpi_card("Responsable", f"{pct_responsable:.1f}%", tone=tone)
    with k3:
        tone = "good" if pct_caratula >= 50 else ("warn" if pct_caratula >= 25 else "bad")
        kpi_card("Caratula", f"{pct_caratula:.1f}%", delta="Critico" if pct_caratula < 30 else None, tone=tone)
    with k4:
        tone = "good" if pct_expediente >= 70 else ("warn" if pct_expediente >= 40 else "bad")
        kpi_card("Expediente", f"{pct_expediente:.1f}%", tone=tone)

    st.markdown("---")

    # ── Fila 2: Salud de Datos ──
    st.markdown("#### Salud de Datos")
    st.caption("Porcentaje de completitud por campo clave")

    campos_salud = ["JURISDICCION", "ORGANISMO", "EXPEDIENTE", "CARATULA", "RESPONSABLE", "CONTROL"]
    for campo in campos_salud:
        pct = completitud.get(campo, {}).get("pct_completos", 0)
        progress_row(campo.capitalize(), pct)

    st.markdown("---")

    # ── Fila 3: Acciones rapidas ──
    st.markdown("#### Acciones rapidas")
    a1, a2, a3 = st.columns(3)

    with a1:
        if st.button("Ir a Gestion (Casos)", use_container_width=True, key="dash_go_gestion"):
            from nav import navigate_to
            navigate_to("Gestion")

    with a2:
        if st.button("Ejecutar Auditoria", use_container_width=True, key="dash_go_audit"):
            from nav import navigate_to
            navigate_to("Auditoria")

    with a3:
        if st.button("Reparar subcarpetas", use_container_width=True, key="dash_repair"):
            total_creadas = 0
            pb = st.progress(0)
            for i, c in enumerate(casos, start=1):
                total_creadas += gestor.ensure_case_structure(c.ruta)
                pb.progress(int((i / max(1, len(casos))) * 100))
            st.success(f"Reparacion finalizada. Subcarpetas creadas: {total_creadas}.")
            st.cache_data.clear()

    # ── Proximos vencimientos (compacto, max 5) ──
    st.markdown("---")
    st.markdown("#### Proximos vencimientos (7 dias)")

    hoy = datetime.now().date()
    tareas_prox = []
    for c in casos:
        fecha = c._parsear_fecha(c.fecha_tarea)
        if fecha and (fecha - hoy).days <= 7:
            tareas_prox.append(c)
    tareas_prox.sort(key=lambda c: c._parsear_fecha(c.fecha_tarea) or hoy)

    if tareas_prox:
        for c in tareas_prox[:5]:
            st.markdown(f"""
            <div class="vg-card-tight" style="margin-bottom:6px;">
              <div style="display:flex;justify-content:space-between;align-items:center;">
                <span>{c.semaforo} <b>{c.cliente}</b> -- {c.causa}</span>
                <span class="vg-pill">{c.fecha_tarea}</span>
              </div>
              <div style="font-size:12px;color:var(--muted);margin-top:2px;">{c.tarea_pendiente}</div>
            </div>
            """, unsafe_allow_html=True)
        if len(tareas_prox) > 5:
            st.caption(f"... y {len(tareas_prox) - 5} mas. Ver en Gestion > Agenda.")
    else:
        st.success("Sin vencimientos en los proximos 7 dias.")


def _cargar_metricas_auditoria(gestor: GestorCasos, casos: List[Caso]) -> dict:
    """Carga metricas de auditoria desde session_state o calcula basicas."""
    # Si hay resultado reciente en session_state, usarlo
    if "ultimo_resultado_auditoria" in st.session_state:
        return st.session_state["ultimo_resultado_auditoria"].get("metricas", {})

    # Calcular metricas basicas inline (sin auditoria completa)
    total = len(casos)
    if total == 0:
        return {"casos_total": 0, "completitud": {}}

    campos = ["TIPO_PROCESO", "JURISDICCION", "ORGANISMO", "EXPEDIENTE",
              "CARATULA", "RESPONSABLE", "CONTROL", "EVENTO", "FECHA_EVENTO",
              "TAREA_PENDIENTE", "FECHA_TAREA", "OBSERVACIONES"]

    completitud = {}
    for campo in campos:
        attr = campo.lower()
        completos = sum(1 for c in casos
                        if hasattr(c, attr) and getattr(c, attr)
                        and str(getattr(c, attr)).strip().upper() not in ("", "S/D"))
        completitud[campo] = {
            "vacios_o_sd": total - completos,
            "completos": completos,
            "pct_completos": round((completos / total) * 100, 1)
        }

    return {"casos_total": total, "completitud": completitud}


# ══════════════════════════════════════════════════════════════════════════════
# SPRINT 3: GESTION (Maestro-detalle)
# ══════════════════════════════════════════════════════════════════════════════

def render_gestion(gestor: GestorCasos, casos: List[Caso], df: pd.DataFrame | None):
    """Gestion: tabs secundarios Casos/Cliente/Agenda/Finanzas."""
    gestion_tabs = ["Casos", "Cliente", "Agenda", "Finanzas"]
    st.session_state.setdefault("gestion_tab", "Casos")

    current_tab = st.session_state.get("gestion_tab", "Casos")
    idx = gestion_tabs.index(current_tab) if current_tab in gestion_tabs else 0

    selected_tab = st.radio(
        "Seccion",
        gestion_tabs,
        index=idx,
        horizontal=True,
        key="_gestion_tabs",
        label_visibility="collapsed",
    )

    if selected_tab != current_tab:
        st.session_state["gestion_tab"] = selected_tab
        st.session_state["route_mode"] = "listado"
        st.rerun()

    mode = st.session_state.get("route_mode", "listado")

    if selected_tab == "Casos":
        if df is not None and not df.empty:
            render_modulo_casos(df, gestor, mode)
        else:
            st.info("No hay casos cargados.")
            _render_crear_caso(gestor)

    elif selected_tab == "Cliente":
        if casos:
            render_modulo_cliente(gestor, casos, mode)
        else:
            empty_state_nav("Sin clientes", "No hay casos cargados.",
                           cta_label="Crear caso", cta_module="casos")

    elif selected_tab == "Agenda":
        if casos:
            render_modulo_agenda(gestor, casos, mode)
        else:
            empty_state_nav("Sin tareas", "No hay casos cargados.",
                           cta_label="Crear caso", cta_module="casos")

    elif selected_tab == "Finanzas":
        if casos:
            render_modulo_finanzas(gestor, casos, mode)
        else:
            empty_state_nav("Sin datos financieros", "No hay casos cargados.",
                           cta_label="Crear caso", cta_module="casos")


def _render_crear_caso(gestor: GestorCasos):
    """Formulario para crear caso cuando no hay ninguno."""
    with st.expander("Crear nuevo caso", expanded=True):
        formulario_nuevo_caso(st, gestor)


# ══════════════════════════════════════════════════════════════════════════════
# ORDENAMIENTO Y FILTROS
# ══════════════════════════════════════════════════════════════════════════════

def ordenar_por_urgencia(df: pd.DataFrame) -> pd.DataFrame:
    """Ordena casos priorizando urgentes y fecha de tarea."""
    df2 = df.copy()
    orden = {"🔴": 0, "🟡": 1, "🟢": 2, "⚪": 3}
    df2["_ORD_SEM"] = df2["SEMÁFORO"].map(orden).fillna(99)
    df2["_FECHA_TAREA_DT"] = pd.to_datetime(df2["FECHA TAREA"], errors="coerce", dayfirst=True)
    df2 = df2.sort_values(
        by=["_ORD_SEM", "_FECHA_TAREA_DT", "AÑO", "CLIENTE", "FUERO", "CAUSA"],
        ascending=[True, True, False, True, True, True],
        kind="mergesort"
    )
    return df2.drop(columns=["_ORD_SEM", "_FECHA_TAREA_DT"])


def mostrar_metricas(casos: List[Caso]):
    """Muestra metricas resumidas en la parte superior."""
    total = len(casos)
    activos = sum(1 for c in casos if "Activo" in c.estado or "Activos" in c.estado)
    vencidos = sum(1 for c in casos if c.semaforo == "🔴")
    proximos = sum(1 for c in casos if c.semaforo == "🟡")

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric("Total Casos", total)
    with col2:
        st.metric("Activos", activos)
    with col3:
        st.metric("Vencidos", vencidos)
    with col4:
        st.metric("Proximos", proximos)


def mostrar_filtros(df: pd.DataFrame) -> pd.DataFrame:
    """Barra de filtros horizontal."""
    help_section("filtros", "Filtros y busqueda", """
- **Busqueda global**: filtra en todos los campos visibles de la tabla.
- **Atajos**: acceso directo a casos vencidos o proximos N dias.
- **Priorizar urgentes**: ordena poniendo vencidos (rojo) y proximos (amarillo) primero.
- **Limpiar filtros**: resetea todos los filtros a "Todos".
""")
    col_titulo, col_boton = st.columns([8, 2])
    with col_titulo:
        st.markdown("### Filtros")
    with col_boton:
        if st.button("Limpiar filtros", use_container_width=True):
            st.session_state["busqueda_global"] = ""
            st.session_state["filtro_año"] = "Todos"
            st.session_state["filtro_estado"] = "Todos"
            st.session_state["filtro_cliente"] = "Todos"
            st.session_state["filtro_fuero"] = "Todos"
            st.session_state["filtro_semaforo"] = "Todos"
            st.rerun()

    busqueda = st.text_input("Busqueda Global", placeholder="Buscar por cliente, causa, expediente, caratula...", help="Filtra en todos los campos de la tabla", key="busqueda_global")

    st.checkbox("Priorizar urgentes (vencidos/proximos arriba)", value=True, key="priorizar_urgentes")

    atajo = st.selectbox("Atajos", ["Ninguno", "Solo vencidos", "Proximos 7 dias", "Proximos 30 dias"], key="filtro_atajo")

    if busqueda:
        mask = df["_SEARCH"].str.contains(busqueda.strip().lower(), na=False)
        df = df[mask]

    col1, col2, col3, col4, col5 = st.columns(5)

    with col1:
        años = ["Todos"] + sorted(df["AÑO"].unique().tolist(), reverse=True)
        año_sel = st.selectbox("Año", años, key="filtro_año")

    with col2:
        estados = ["Todos"] + ESTADOS_DISPONIBLES
        estado_sel = st.selectbox("Estado", estados, key="filtro_estado")

    with col3:
        clientes = ["Todos"] + sorted(df["CLIENTE"].unique().tolist())
        cliente_sel = st.selectbox("Cliente", clientes, key="filtro_cliente")

    with col4:
        fueros = ["Todos"] + FUEROS_DISPONIBLES
        fuero_sel = st.selectbox("Fuero", fueros, key="filtro_fuero")

    with col5:
        semaforos = ["Todos", "Vencidos", "Proximos", "En tiempo", "Sin tarea"]
        semaforo_sel = st.selectbox("Semaforo", semaforos, key="filtro_semaforo")

    df_filtrado = df.copy()

    if año_sel != "Todos":
        df_filtrado = df_filtrado[df_filtrado["AÑO"] == año_sel]
    if estado_sel != "Todos":
        df_filtrado = df_filtrado[df_filtrado["ESTADO"] == estado_sel]
    if cliente_sel != "Todos":
        df_filtrado = df_filtrado[df_filtrado["CLIENTE"] == cliente_sel]
    if fuero_sel != "Todos":
        df_filtrado = df_filtrado[df_filtrado["FUERO"] == fuero_sel]
    if semaforo_sel != "Todos":
        emoji_map = {"Vencidos": "🔴", "Proximos": "🟡", "En tiempo": "🟢", "Sin tarea": "⚪"}
        emoji = emoji_map.get(semaforo_sel, "")
        if emoji:
            df_filtrado = df_filtrado[df_filtrado["SEMÁFORO"] == emoji]

    if atajo == "Solo vencidos":
        df_filtrado = df_filtrado[df_filtrado["SEMÁFORO"] == "🔴"]
    elif atajo in ("Proximos 7 dias", "Proximos 30 dias"):
        try:
            dias = 7 if atajo == "Proximos 7 dias" else 30
            ft = pd.to_datetime(df_filtrado["FECHA TAREA"], errors="coerce", dayfirst=True)
            hoy = pd.Timestamp.now().normalize()
            limite = hoy + pd.Timedelta(days=dias)
            df_filtrado = df_filtrado[(ft >= hoy) & (ft <= limite)]
        except Exception:
            pass

    return df_filtrado


# ══════════════════════════════════════════════════════════════════════════════
# DOCUMENTOS RECIENTES
# ══════════════════════════════════════════════════════════════════════════════

def listar_documentos_recientes(ruta_caso: Path, subcarpeta: str = "02. ESCRITOS", n: int = 5) -> List[Path]:
    """Retorna los ultimos n archivos modificados en la subcarpeta del caso."""
    carpeta = ruta_caso / subcarpeta
    if not carpeta.exists():
        return []
    files = []
    for f in carpeta.rglob("*"):
        if f.is_file():
            try:
                files.append((f.stat().st_mtime, f))
            except Exception:
                pass
    files.sort(key=lambda x: x[0], reverse=True)
    return [f for _, f in files[:n]]


def mostrar_documentos_recientes(ruta_caso: Path, key_suffix: str = ""):
    """Muestra los ultimos documentos modificados del caso."""
    docs = listar_documentos_recientes(ruta_caso)
    with st.expander(f"Documentos recientes ({len(docs)})", expanded=False):
        if not docs:
            st.caption("Sin documentos en 02. ESCRITOS")
            return
        for idx, doc in enumerate(docs):
            c1, c2 = st.columns([6, 2])
            with c1:
                try:
                    fecha_mod = datetime.fromtimestamp(doc.stat().st_mtime).strftime("%d/%m %H:%M")
                except Exception:
                    fecha_mod = ""
                st.caption(f"{doc.name}  •  {fecha_mod}")
            with c2:
                if st.button("Abrir", key=f"doc_{key_suffix}_{idx}", use_container_width=True):
                    try:
                        os.startfile(str(doc))
                    except Exception:
                        st.error("No se pudo abrir el archivo.")


# ══════════════════════════════════════════════════════════════════════════════
# ACCIONES
# ══════════════════════════════════════════════════════════════════════════════

def accion_guardar_campos(gestor: GestorCasos, ruta_caso: Path, cambios: dict, accion: str):
    """Accion unificada: guardar cambios en ficha, loguear, limpiar cache y rerun."""
    ok = gestor.actualizar_campos_ficha(ruta_caso, cambios)
    if ok:
        st.cache_data.clear()
        # DATA-001: forzar recarga de valores desde disco en proximo render
        for suf in ("lat", "cls", "panel", "detalle"):
            st.session_state.pop(f"_qe_caso_{suf}", None)
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


def render_quick_edit(gestor: GestorCasos, ruta_caso: Path, key_suffix: str):
    """Edicion rapida unificada — un solo punto de mantenimiento (DATA-001)."""
    ruta_str = str(ruta_caso)
    state_key = f"_qe_caso_{key_suffix}"

    # Reset widgets cuando cambia el caso seleccionado
    if st.session_state.get(state_key) != ruta_str:
        st.session_state[state_key] = ruta_str
        ficha = gestor._leer_ficha(ruta_caso)
        st.session_state[f"qe_resp_{key_suffix}"] = ficha.get('RESPONSABLE', '')
        st.session_state[f"qe_tarea_{key_suffix}"] = ficha.get('TAREA_PENDIENTE', '')
        st.session_state[f"qe_fecha_{key_suffix}"] = ficha.get('FECHA_TAREA', '')
        st.session_state[f"qe_obs_{key_suffix}"] = ficha.get('OBSERVACIONES', '')

    st.markdown("#### Edicion rapida")
    qe_resp = st.text_input("Responsable", key=f"qe_resp_{key_suffix}")
    qe_tarea = st.text_input("Tarea Pendiente", key=f"qe_tarea_{key_suffix}")
    qe_fecha = st.text_input("Fecha Tarea (DD/MM/YYYY)", key=f"qe_fecha_{key_suffix}")
    qe_obs = st.text_area("Observaciones", key=f"qe_obs_{key_suffix}")

    b1, b2 = st.columns(2)
    with b1:
        if st.button("Guardar", key=f"qe_save_{key_suffix}", use_container_width=True):
            cambios = {
                'RESPONSABLE': qe_resp,
                'TAREA_PENDIENTE': qe_tarea,
                'FECHA_TAREA': qe_fecha,
                'OBSERVACIONES': qe_obs,
            }
            accion_guardar_campos(gestor, ruta_caso, cambios, f"Edicion rapida ({key_suffix})")
    with b2:
        if st.button("Tarea completada", key=f"qe_done_{key_suffix}", use_container_width=True):
            accion_completar_tarea(gestor, ruta_caso)


# ══════════════════════════════════════════════════════════════════════════════
# MODULO CASOS (Sprint 3: maestro-detalle)
# ══════════════════════════════════════════════════════════════════════════════

def render_modulo_casos(df: pd.DataFrame, gestor: GestorCasos, mode: str = "listado"):
    """Modulo Casos: 3 modos excluyentes — Listado / Detalle / Editar (UX v3)."""
    # Filtros (se aplican antes de todo, solo visibles en listado)
    if mode == "listado":
        df_filtrado = mostrar_filtros(df)
        if st.session_state.get("priorizar_urgentes", True):
            df_filtrado = ordenar_por_urgencia(df_filtrado)
    else:
        df_filtrado = df

    # Sub-nav de modo
    selected_mode = mode_tabs(mode, ["listado", "detalle", "editar"], key="casos_mode_tabs")
    if selected_mode != mode:
        st.session_state["route_mode"] = selected_mode
        st.rerun()

    # Dispatch exclusivo
    if mode == "listado":
        _render_casos_listado_v3(df_filtrado, gestor)
    elif mode == "detalle":
        _render_casos_detalle_v3(df_filtrado, gestor)
    elif mode == "editar":
        _render_casos_editar_v3(df_filtrado, gestor)


def _render_casos_listado_v3(df: pd.DataFrame, gestor: GestorCasos):
    """Modo Listado: grilla full + filtros + exportacion. Sin detalle ni formulario."""
    grid_shell("Casos", subtitle=f"{len(df)} registros", fluid=True)

    # --- Export buttons
    col_csv, col_xlsx, col_spacer = st.columns([2, 2, 6])
    with col_csv:
        csv = df.to_csv(index=False).encode('utf-8-sig')
        st.download_button(
            label="Exportar CSV",
            data=csv,
            file_name=f"reporte_legal_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
            mime="text/csv",
            use_container_width=True
        )
    with col_xlsx:
        planilla_cols = st.session_state.get("planilla_cols")
        if planilla_cols:
            cols_export = [c for c in planilla_cols if c in df.columns and not str(c).startswith("_")]
        else:
            cols_export = [c for c in df.columns if not str(c).startswith("_")]
        df_export = df[cols_export].replace("S/D", "")
        xlsx_bytes = df_to_xlsx_bytes(df_export)
        st.download_button(
            label="Exportar Excel",
            data=xlsx_bytes,
            file_name=f"reporte_legal_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True
        )

    # --- Toolbar
    _ensure_bool_state("planilla_wrap", False)
    _ensure_int_step_state("planilla_altura", 420, 980, 40, 720)

    c1, c2, c3, c4 = st.columns([2, 2, 2, 4])
    with c1:
        modo = st.selectbox("Modo", ["Tabla", "Tarjetas"], key="planilla_modo")
    with c2:
        st.selectbox("Densidad", ["Compacta", "Normal"], key="planilla_densidad")
    with c3:
        wrap = st.checkbox("Ajustar texto", value=False, key="planilla_wrap")

    # CSS dinamico
    if wrap:
        st.markdown("""
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
        """, unsafe_allow_html=True)
    else:
        st.markdown("""
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
        """, unsafe_allow_html=True)

    # --- Presets de columnas
    presets = {
        "Gestion": ["SEMÁFORO","FECHA TAREA","TAREA PENDIENTE","CLIENTE","FUERO","CAUSA","EXPEDIENTE","RESPONSABLE","ESTADO","AÑO"],
        "Cliente/Causa": ["CLIENTE","FUERO","CAUSA","CARATULA","EXPEDIENTE","RESPONSABLE","SEMÁFORO","FECHA TAREA","TAREA PENDIENTE"],
        "Procesal": ["CLIENTE","FUERO","TIPO PROCESO","JURISDICCION","ORGANISMO","EXPEDIENTE","CARATULA","CONTROL","EVENTO","FECHA EVENTO"],
        "Completo": [c for c in df.columns if not str(c).startswith("_")]
    }

    if "planilla_preset" not in st.session_state:
        st.session_state["planilla_preset"] = "Gestion"
    if "planilla_cols" not in st.session_state:
        base = presets.get(st.session_state["planilla_preset"], presets["Gestion"])
        st.session_state["planilla_cols"] = [c for c in base if c in df.columns]

    st.caption("Seleccione columnas visibles y ordene con las flechas. Use Vista estandar para restaurar.")
    with st.expander("Columnas (orden y visibilidad)", expanded=False):
        all_cols = [c for c in presets["Completo"] if not str(c).startswith("_")]

        pcol1, pcol2 = st.columns([2, 3])
        with pcol1:
            preset = st.selectbox("Vista estandar", list(presets.keys()), key="planilla_preset")
            if st.button("Restaurar vista", use_container_width=True):
                base = presets.get(preset, presets["Gestion"])
                st.session_state["planilla_cols"] = [c for c in base if c in df.columns]
                st.session_state["planilla_cols_visible"] = st.session_state["planilla_cols"]
                st.rerun()

        with pcol2:
            selected = st.multiselect(
                "Visibilidad",
                options=all_cols,
                default=st.session_state["planilla_cols"],
                key="planilla_cols_visible"
            )
            current = st.session_state["planilla_cols"]
            new_order = [c for c in current if c in selected] + [c for c in selected if c not in current]
            if new_order != current:
                st.session_state["planilla_cols"] = new_order
                st.rerun()

        cols = st.session_state["planilla_cols"]
        if not cols:
            st.session_state["planilla_cols"] = [c for c in presets["Gestion"] if c in df.columns]
            cols = st.session_state["planilla_cols"]

        col_sel = st.selectbox("Orden", cols, key="planilla_col_sel")
        idx = cols.index(col_sel) if col_sel in cols else 0
        b1, b2 = st.columns(2)
        with b1:
            if st.button("Subir", use_container_width=True, key="col_up") and idx > 0:
                st.session_state["planilla_cols"] = _swap(cols, idx, idx - 1)
                st.rerun()
        with b2:
            if st.button("Bajar", use_container_width=True, key="col_down") and idx < len(cols) - 1:
                st.session_state["planilla_cols"] = _swap(cols, idx, idx + 1)
                st.rerun()

    # --- Modo tarjetas (movil)
    if modo == "Tarjetas":
        _render_tarjetas(df, gestor)
        return

    # --- Modo tabla (escritorio) con AgGrid/fallback
    cols = [c for c in st.session_state["planilla_cols"] if c in df.columns and not str(c).startswith("_")]
    if not cols:
        cols = [c for c in presets["Gestion"] if c in df.columns]

    # Preparar df con _RUTA para el grid wrapper
    df_grid = df[cols + (["_RUTA"] if "_RUTA" in df.columns else [])].copy()
    df_grid = df_grid.replace("S/D", "")

    column_config = {
        "SEMÁFORO": st.column_config.TextColumn("", width="small"),
        "FECHA TAREA": st.column_config.TextColumn("Fecha", width="small"),
        "TAREA PENDIENTE": st.column_config.TextColumn("Tarea", width="medium"),
        "CLIENTE": st.column_config.TextColumn("Cliente", width="medium"),
        "FUERO": st.column_config.TextColumn("Fuero", width="small"),
        "CAUSA": st.column_config.TextColumn("Causa", width="large"),
        "CARATULA": st.column_config.TextColumn("Caratula", width="large"),
        "EXPEDIENTE": st.column_config.TextColumn("Expte.", width="small"),
        "RESPONSABLE": st.column_config.TextColumn("Resp.", width="small"),
        "ESTADO": st.column_config.TextColumn("Estado", width="small"),
        "AÑO": st.column_config.TextColumn("Ano", width="small"),
    }

    selected_ruta = render_aggrid(
        df_grid, key="planilla_v3", height_px=560,
        column_config=column_config,
    )

    st.caption(f"Mostrando {len(df_grid)} casos")

    # Si se selecciono una fila, navegar a detalle
    if selected_ruta:
        st.session_state["selected_case_id"] = selected_ruta
        st.session_state["route_mode"] = "detalle"
        st.rerun()


def _render_tarjetas(df: pd.DataFrame, gestor: GestorCasos):
    """Vista tarjetas para Listado (movil)."""
    df_cards = df.copy()
    try:
        orden = {"🔴": 0, "🟡": 1, "🟢": 2, "⚪": 3}
        df_cards["_ORD_SEM"] = df_cards["SEMÁFORO"].map(orden).fillna(99)
        df_cards["_FECHA_TAREA_DT"] = pd.to_datetime(df_cards.get("FECHA TAREA", ""), errors="coerce", dayfirst=True)
        df_cards = df_cards.sort_values(by=["_ORD_SEM","_FECHA_TAREA_DT"], ascending=[True, True], kind="mergesort")
    except Exception:
        pass

    for i, row in df_cards.reset_index(drop=True).iterrows():
        cliente = str(row.get("CLIENTE",""))
        causa = str(row.get("CAUSA",""))
        sem = str(row.get("SEMÁFORO",""))
        vence = str(row.get("FECHA TAREA",""))
        tarea = str(row.get("TAREA PENDIENTE",""))
        fuero = str(row.get("FUERO",""))
        expte = str(row.get("EXPEDIENTE",""))
        caratula = str(row.get("CARATULA",""))
        responsable = str(row.get("RESPONSABLE",""))
        ruta = str(row.get("_RUTA",""))

        titulo = f"{sem} {cliente} -- {causa}"
        with st.expander(titulo, expanded=False):
            cA, cB = st.columns([3, 2])
            with cA:
                st.write(f"**Fuero:** {fuero}")
                if expte and expte != "S/D":
                    st.write(f"**Expediente:** {expte}")
                if caratula and caratula != "S/D":
                    st.write(f"**Caratula:** {caratula}")
            with cB:
                st.write(f"**Semaforo:** {sem}")
                if vence:
                    st.write(f"**Vence:** {vence}")
                if responsable and responsable != "S/D":
                    st.write(f"**Responsable:** {responsable}")

            if tarea and tarea != "S/D":
                st.write(f"**Tarea:** {tarea}")

            if ruta:
                act1, act2, act3 = st.columns(3)
                with act1:
                    if st.button("Abrir carpeta", key=f"open_{i}", use_container_width=True):
                        try:
                            os.startfile(ruta)
                        except Exception:
                            st.error("No se pudo abrir la carpeta.")
                with act2:
                    if tarea and tarea != "S/D":
                        if st.button("Tarea completada", key=f"done_{i}", use_container_width=True):
                            accion_completar_tarea(gestor, Path(ruta))
                with act3:
                    if st.button("Ver detalle", key=f"det_{i}", use_container_width=True):
                        st.session_state["selected_case_id"] = ruta
                        st.session_state["route_mode"] = "detalle"
                        st.rerun()

    st.caption(f"Mostrando {len(df_cards)} casos")


def _render_casos_detalle_v3(df: pd.DataFrame, gestor: GestorCasos):
    """Modo Detalle: ficha del caso seleccionado + quick-edit minimo. Sin grilla."""
    ruta = st.session_state.get("selected_case_id")

    if not ruta:
        empty_state_nav(
            "Selecciona un caso",
            "Elegi un caso desde el Listado para ver su detalle.",
            cta_label="Ir a Listado",
            cta_module="casos",
            cta_mode="listado",
        )
        return

    # Buscar caso en df
    caso_row = None
    if "_RUTA" in df.columns:
        match = df[df["_RUTA"] == ruta]
        if not match.empty:
            caso_row = match.iloc[0].to_dict()

    if caso_row is None:
        empty_state_nav(
            "Caso no encontrado",
            "El caso seleccionado ya no existe en los datos actuales.",
            cta_label="Ir a Listado",
            cta_module="casos",
            cta_mode="listado",
        )
        return

    if st.session_state.get("auto_normalize", False):
        gestor.ensure_case_structure(Path(ruta))

    # Header
    sem = caso_row.get("SEMÁFORO", "")
    badges = []
    if sem == "🔴":
        badges.append('<span class="vg-badge-danger">Vencido</span>')
    elif sem == "🟡":
        badges.append('<span class="vg-badge-warn">Proximo</span>')
    elif sem == "🟢":
        badges.append('<span class="vg-badge-ok">En tiempo</span>')

    detail_shell(
        f"{sem} {caso_row.get('CLIENTE', '')} -- {caso_row.get('CAUSA', '')}",
        badges=badges,
    )

    # Datos principales (3 columnas)
    cA, cB, cC = st.columns(3)
    with cA:
        st.write(f"**Cliente:** {caso_row.get('CLIENTE','')}")
        st.write(f"**Causa:** {caso_row.get('CAUSA','')}")
        st.write(f"**Fuero:** {caso_row.get('FUERO','')}")
        st.write(f"**Estado:** {caso_row.get('ESTADO','')}")
        st.write(f"**Ano:** {caso_row.get('AÑO','')}")
    with cB:
        st.write(f"**Expediente:** {caso_row.get('EXPEDIENTE','')}")
        st.write(f"**Caratula:** {caso_row.get('CARATULA','')}")
        st.write(f"**Tipo Proceso:** {caso_row.get('TIPO PROCESO','')}")
        st.write(f"**Jurisdiccion:** {caso_row.get('JURISDICCION','')}")
        st.write(f"**Organismo:** {caso_row.get('ORGANISMO','')}")
    with cC:
        st.write(f"**Responsable:** {caso_row.get('RESPONSABLE','')}")
        st.write(f"**Tarea:** {caso_row.get('TAREA PENDIENTE','')}")
        st.write(f"**Vence:** {caso_row.get('FECHA TAREA','')}")
        st.write(f"**Control:** {caso_row.get('CONTROL','')}")
        st.write(f"**Evento:** {caso_row.get('EVENTO','')}")

    st.markdown("---")

    # Acciones
    ac1, ac2, ac3, ac4 = st.columns(4)
    with ac1:
        if st.button("Editar completo", key="det_edit", use_container_width=True):
            st.session_state["route_mode"] = "editar"
            st.rerun()
    with ac2:
        if st.button("Abrir carpeta", key="det_open_v3", use_container_width=True):
            try:
                os.startfile(ruta)
            except Exception:
                st.error("No se pudo abrir la carpeta.")
    with ac3:
        if st.button("Volver a Listado", key="det_back", use_container_width=True):
            st.session_state["route_mode"] = "listado"
            st.rerun()
    with ac4:
        tarea = caso_row.get("TAREA PENDIENTE", "")
        if tarea and tarea != "S/D":
            if st.button("Completar tarea", key="det_done_v3", use_container_width=True):
                accion_completar_tarea(gestor, Path(ruta))

    st.markdown("---")

    # Quick-edit minimo
    render_quick_edit(gestor, Path(ruta), "detalle")

    # Documentos recientes
    mostrar_documentos_recientes(Path(ruta), key_suffix="detalle_v3")


def _render_casos_editar_v3(df: pd.DataFrame, gestor: GestorCasos):
    """Modo Editar: wizard por pasos o nuevo caso. Sin grilla."""
    ruta = st.session_state.get("selected_case_id")

    # Si no hay caso seleccionado, ofrecer crear nuevo
    if not ruta:
        page_header("Nuevo Caso", subtitle="Crear un caso nuevo")
        formulario_nuevo_caso(st, gestor)
        return

    # Buscar caso en los datos
    ficha = gestor._leer_ficha(Path(ruta))

    # Obtener datos estructurales del df
    caso_row = None
    if "_RUTA" in df.columns:
        match = df[df["_RUTA"] == ruta]
        if not match.empty:
            caso_row = match.iloc[0].to_dict()

    if caso_row is None:
        empty_state_nav(
            "Caso no encontrado",
            "El caso seleccionado ya no existe.",
            cta_label="Ir a Listado",
            cta_module="casos",
            cta_mode="listado",
        )
        return

    page_header("Editar Caso", subtitle=f"{caso_row.get('CLIENTE','')} -- {caso_row.get('CAUSA','')}")

    # Wizard de pasos
    steps = ["Identificacion", "Expediente", "Responsable", "Tarea", "Observaciones"]
    step_key = "edit_caso_step"
    if step_key not in st.session_state:
        st.session_state[step_key] = 0

    current_step = edit_shell("Editar caso", steps, st.session_state[step_key], key="casos_edit_wizard")
    st.session_state[step_key] = current_step

    # Cargar valores actuales de la ficha
    ruta_path = Path(ruta)

    # Inicializar estado del formulario si es primera vez o cambio de caso
    form_init_key = "_edit_form_caso"
    if st.session_state.get(form_init_key) != ruta:
        st.session_state[form_init_key] = ruta
        st.session_state["_ef_tipo_proceso"] = ficha.get("TIPO_PROCESO", "S/D")
        st.session_state["_ef_jurisdiccion"] = ficha.get("JURISDICCION", "S/D")
        st.session_state["_ef_organismo"] = ficha.get("ORGANISMO", "S/D")
        st.session_state["_ef_expediente"] = ficha.get("EXPEDIENTE", "S/D")
        st.session_state["_ef_caratula"] = ficha.get("CARATULA", "S/D")
        st.session_state["_ef_responsable"] = ficha.get("RESPONSABLE", "S/D")
        st.session_state["_ef_control"] = ficha.get("CONTROL", "S/D")
        st.session_state["_ef_evento"] = ficha.get("EVENTO", "S/D")
        st.session_state["_ef_fecha_evento"] = ficha.get("FECHA_EVENTO", "")
        st.session_state["_ef_tarea"] = ficha.get("TAREA_PENDIENTE", "")
        st.session_state["_ef_fecha_tarea"] = ficha.get("FECHA_TAREA", "")
        st.session_state["_ef_observaciones"] = ficha.get("OBSERVACIONES", "")

    # Renderizar paso actual
    if current_step == 0:  # Identificacion
        st.markdown("#### Identificacion del caso")
        st.write(f"**Ano:** {caso_row.get('AÑO', '')}")
        st.write(f"**Estado:** {caso_row.get('ESTADO', '')}")
        st.write(f"**Cliente:** {caso_row.get('CLIENTE', '')}")
        st.write(f"**Fuero:** {caso_row.get('FUERO', '')}")
        st.write(f"**Causa:** {caso_row.get('CAUSA', '')}")
        st.info("Para cambiar ubicacion o nombre del caso, use Configuracion > Editar caso.")

    elif current_step == 1:  # Expediente
        st.markdown("#### Datos del expediente")
        st.text_input("Tipo Proceso", key="_ef_tipo_proceso")
        st.text_input("Jurisdiccion", key="_ef_jurisdiccion")
        st.text_input("Organismo", key="_ef_organismo")
        st.text_input("Expediente", key="_ef_expediente")
        st.text_input("Caratula", key="_ef_caratula")

    elif current_step == 2:  # Responsable y Control
        st.markdown("#### Responsable y Control")
        st.text_input("Responsable", key="_ef_responsable")
        st.text_input("Control", key="_ef_control")
        st.text_input("Ultimo Evento", key="_ef_evento")
        st.text_input("Fecha Evento (DD/MM/YYYY)", key="_ef_fecha_evento")

    elif current_step == 3:  # Tarea
        st.markdown("#### Tarea pendiente")
        st.text_input("Tarea Pendiente", key="_ef_tarea")
        st.text_input("Fecha Tarea (DD/MM/YYYY)", key="_ef_fecha_tarea")

    elif current_step == 4:  # Observaciones
        st.markdown("#### Observaciones")
        st.text_area("Observaciones", key="_ef_observaciones", height=200)

    # Navegacion entre pasos + Guardar/Cancelar
    st.markdown("---")
    nav1, nav2, nav3, nav4 = st.columns(4)
    with nav1:
        if current_step > 0:
            if st.button("Anterior", key="edit_prev", use_container_width=True):
                st.session_state[step_key] = current_step - 1
                st.rerun()
    with nav2:
        if current_step < len(steps) - 1:
            if st.button("Siguiente", key="edit_next", use_container_width=True):
                st.session_state[step_key] = current_step + 1
                st.rerun()
    with nav3:
        if st.button("Guardar todo", key="edit_save_all", use_container_width=True):
            cambios = {
                'TIPO_PROCESO': st.session_state.get("_ef_tipo_proceso", ""),
                'JURISDICCION': st.session_state.get("_ef_jurisdiccion", ""),
                'ORGANISMO': st.session_state.get("_ef_organismo", ""),
                'EXPEDIENTE': st.session_state.get("_ef_expediente", ""),
                'CARATULA': st.session_state.get("_ef_caratula", ""),
                'RESPONSABLE': st.session_state.get("_ef_responsable", ""),
                'CONTROL': st.session_state.get("_ef_control", ""),
                'EVENTO': st.session_state.get("_ef_evento", ""),
                'FECHA_EVENTO': st.session_state.get("_ef_fecha_evento", ""),
                'TAREA_PENDIENTE': st.session_state.get("_ef_tarea", ""),
                'FECHA_TAREA': st.session_state.get("_ef_fecha_tarea", ""),
                'OBSERVACIONES': st.session_state.get("_ef_observaciones", ""),
            }
            ok = gestor.actualizar_campos_ficha(ruta_path, cambios)
            if ok:
                st.cache_data.clear()
                st.session_state[step_key] = 0
                st.session_state.pop(form_init_key, None)
                _ui_toast("Caso guardado")
                st.success("Caso actualizado correctamente.")
                st.session_state["route_mode"] = "detalle"
                st.rerun()
            else:
                st.error("No se pudo guardar la actualizacion.")
    with nav4:
        if st.button("Cancelar", key="edit_cancel", use_container_width=True):
            st.session_state[step_key] = 0
            st.session_state.pop(form_init_key, None)
            st.session_state["route_mode"] = "detalle"
            st.rerun()


# ══════════════════════════════════════════════════════════════════════════════
# MODULO CLIENTE
# ══════════════════════════════════════════════════════════════════════════════

def render_modulo_cliente(gestor: GestorCasos, casos: List[Caso], mode: str = "listado"):
    """Modulo Cliente: 3 modos excluyentes — Listado / Detalle / Editar (UX v3)."""
    clientes = gestor.obtener_clientes_existentes()
    if not clientes:
        empty_state_nav("Sin clientes", "No hay clientes registrados en el sistema.",
                       cta_label="Ir a Casos", cta_module="casos")
        return

    # Sub-nav de modo
    selected_mode = mode_tabs(mode, ["listado", "detalle", "editar"], key="cli_mode_tabs")
    if selected_mode != mode:
        st.session_state["route_mode"] = selected_mode
        st.rerun()

    # Selector de cliente (visible en todos los modos)
    cliente_sel = st.selectbox("Seleccione cliente:", clientes, key="vista_cliente_sel")
    casos_cliente = [c for c in casos if c.cliente == cliente_sel]

    if mode == "listado":
        _render_cliente_listado(casos_cliente, cliente_sel, gestor)
    elif mode == "detalle":
        _render_cliente_detalle(casos_cliente, cliente_sel, gestor)
    elif mode == "editar":
        _render_cliente_editar(casos_cliente, cliente_sel, gestor)


def _render_cliente_listado(casos_cliente: list, cliente_sel: str, gestor: GestorCasos):
    """Cliente - Listado: grilla de casos del cliente."""
    grid_shell("Cliente", subtitle=f"{cliente_sel} - {len(casos_cliente)} causas", fluid=True)

    if not casos_cliente:
        st.info("Este cliente no tiene causas registradas.")
        return

    cols_cli = ["SEMÁFORO", "FUERO", "CAUSA", "EXPEDIENTE", "RESPONSABLE", "FECHA TAREA", "TAREA PENDIENTE", "ESTADO"]
    df_cli = pd.DataFrame([c.to_dict() for c in casos_cliente])
    df_cli_grid = df_cli[[c for c in cols_cli if c in df_cli.columns] + (["_RUTA"] if "_RUTA" in df_cli.columns else [])].copy()
    df_cli_grid = df_cli_grid.replace("S/D", "")

    selected_ruta = render_aggrid(df_cli_grid, key="cli_grid_v3", height_px=480)

    if selected_ruta:
        st.session_state["selected_case_id"] = selected_ruta
        st.session_state["route_mode"] = "detalle"
        st.rerun()


def _render_cliente_detalle(casos_cliente: list, cliente_sel: str, gestor: GestorCasos):
    """Cliente - Detalle: ficha del caso + estadisticas."""
    ruta = st.session_state.get("selected_case_id")

    if not ruta or not casos_cliente:
        empty_state_nav(
            "Selecciona un caso",
            "Elegi un caso del cliente desde el Listado.",
            cta_label="Ir a Listado",
            cta_module="cliente",
            cta_mode="listado",
        )
        return

    # Buscar caso
    caso_sel = None
    for c in casos_cliente:
        if str(c.ruta) == ruta:
            caso_sel = c
            break

    if not caso_sel:
        # Fallback: selector manual
        opciones_cli = [
            f"{i+1:02d} | {casos_cliente[i].causa} ({casos_cliente[i].fuero})"
            for i in range(len(casos_cliente))
        ]
        idx_cli = st.selectbox(
            "Seleccionar caso",
            options=list(range(len(opciones_cli))),
            format_func=lambda i: opciones_cli[i],
            key="cli_caso_sel_v3",
        )
        caso_sel = casos_cliente[idx_cli]

    detail_shell(f"{caso_sel.semaforo} {caso_sel.cliente} -- {caso_sel.causa}")

    # Info del caso
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

    # Acciones
    ac1, ac2, ac3 = st.columns(3)
    with ac1:
        if st.button("Abrir carpeta", key="cli_open_v3", use_container_width=True):
            try:
                os.startfile(str(caso_sel.ruta))
            except Exception:
                st.error("No se pudo abrir la carpeta.")
    with ac2:
        if caso_sel.tarea_pendiente and caso_sel.tarea_pendiente != "S/D":
            if st.button("Tarea completada", key="cli_done_v3", use_container_width=True):
                accion_completar_tarea(gestor, caso_sel.ruta)
    with ac3:
        if st.button("Editar caso", key="cli_edit_btn", use_container_width=True):
            st.session_state["selected_case_id"] = str(caso_sel.ruta)
            st.session_state["route_mode"] = "editar"
            st.session_state["gestion_tab"] = "Casos"
            st.rerun()

    st.markdown("---")
    render_quick_edit(gestor, caso_sel.ruta, "cli_det")
    mostrar_documentos_recientes(caso_sel.ruta, key_suffix="cli_det_v3")

    # Estadisticas del cliente
    st.markdown("---")
    st.markdown("#### Estadisticas del Cliente")

    estados = {}
    semaforos = {"🔴": 0, "🟡": 0, "🟢": 0, "⚪": 0}

    for c in casos_cliente:
        estados[c.estado] = estados.get(c.estado, 0) + 1
        semaforos[c.semaforo] = semaforos.get(c.semaforo, 0) + 1

    m1, m2, m3, m4 = st.columns(4)
    with m1:
        st.metric("Vencidos", semaforos["🔴"])
    with m2:
        st.metric("Proximos", semaforos["🟡"])
    with m3:
        st.metric("En tiempo", semaforos["🟢"])
    with m4:
        st.metric("Sin tarea", semaforos["⚪"])

    st.markdown("**Por Estado:**")
    df_est = pd.DataFrame(
        [{"Estado": k, "Cantidad": v} for k, v in sorted(estados.items(), key=lambda x: x[0])]
    )
    st.dataframe(df_est, use_container_width=True, hide_index=True)


def _render_cliente_editar(casos_cliente: list, cliente_sel: str, gestor: GestorCasos):
    """Cliente - Editar: redirige a edicion de caso completa."""
    ruta = st.session_state.get("selected_case_id")
    if not ruta:
        empty_state_nav(
            "Selecciona un caso para editar",
            "Primero selecciona un caso en el Listado del cliente.",
            cta_label="Ir a Listado",
            cta_module="cliente",
            cta_mode="listado",
        )
        return

    # Redirigir a Casos > Editar
    st.session_state["gestion_tab"] = "Casos"
    st.session_state["route_mode"] = "editar"
    st.rerun()


# ══════════════════════════════════════════════════════════════════════════════
# MODULO AGENDA
# ══════════════════════════════════════════════════════════════════════════════

def render_modulo_agenda(gestor: GestorCasos, casos: List[Caso], mode: str = "listado"):
    """Modulo Agenda: 3 modos excluyentes — Listado / Detalle / Editar (UX v3)."""
    tareas = [c for c in casos if c.fecha_tarea and c.fecha_tarea != "S/D"]

    if not tareas:
        empty_state_nav("Sin tareas", "No hay tareas programadas en ningun caso.",
                       cta_label="Ir a Casos", cta_module="casos")
        return

    # Sub-nav de modo
    selected_mode = mode_tabs(mode, ["listado", "detalle", "editar"], key="agenda_mode_tabs")
    if selected_mode != mode:
        st.session_state["route_mode"] = selected_mode
        st.rerun()

    # Preparar tareas con fecha
    tareas_con_fecha = []
    for t in tareas:
        fecha_obj = t._parsear_fecha(t.fecha_tarea)
        if fecha_obj:
            tareas_con_fecha.append((fecha_obj, t))
    tareas_con_fecha.sort(key=lambda x: x[0])

    # Filtros (visibles en listado)
    if mode == "listado":
        fc1, fc2 = st.columns(2)
        with fc1:
            agenda_ver = st.selectbox("Ver", ["Todas", "Solo vencidas", "Proximos 7 dias", "Proximos 30 dias"], key="agenda_ver")
        with fc2:
            solo_activos = st.checkbox("Solo casos activos", value=True, key="agenda_solo_activos")
    else:
        agenda_ver = st.session_state.get("agenda_ver", "Todas")
        solo_activos = st.session_state.get("agenda_solo_activos", True)

    hoy = datetime.now().date()
    tareas_filtradas = []
    for fecha_obj, t in tareas_con_fecha:
        if solo_activos and "Activo" not in t.estado:
            continue
        if agenda_ver == "Solo vencidas" and fecha_obj >= hoy:
            continue
        if agenda_ver == "Proximos 7 dias" and not (hoy <= fecha_obj <= hoy + timedelta(days=7)):
            continue
        if agenda_ver == "Proximos 30 dias" and not (hoy <= fecha_obj <= hoy + timedelta(days=30)):
            continue
        tareas_filtradas.append((fecha_obj, t))

    if mode == "listado":
        _render_agenda_listado(tareas_filtradas, tareas_con_fecha, gestor)
    elif mode == "detalle":
        _render_agenda_detalle(tareas_filtradas, gestor)
    elif mode == "editar":
        _render_agenda_editar(tareas_filtradas, gestor)


def _render_agenda_listado(tareas_filtradas: list, tareas_total: list, gestor: GestorCasos):
    """Agenda - Listado: grilla de vencimientos."""
    grid_shell("Agenda", subtitle=f"{len(tareas_filtradas)} de {len(tareas_total)} tareas", fluid=True)

    if not tareas_filtradas:
        st.success("No hay tareas para el filtro seleccionado.")
        return

    df_agenda = pd.DataFrame([{
        "SEMÁFORO": t.semaforo,
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

    st.download_button(
        label="Exportar Agenda (Excel)",
        data=df_to_xlsx_bytes(
            df_agenda[[c for c in df_agenda.columns if c != "_RUTA"]],
            sheet_name="Agenda"
        ),
        file_name=f"agenda_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
    )

    selected_ruta = render_aggrid(df_agenda, key="agenda_grid_v3", height_px=520)

    if selected_ruta:
        st.session_state["selected_item_id"] = selected_ruta
        st.session_state["route_mode"] = "detalle"
        st.rerun()


def _render_agenda_detalle(tareas_filtradas: list, gestor: GestorCasos):
    """Agenda - Detalle: ficha de la tarea seleccionada + quick-edit."""
    ruta = st.session_state.get("selected_item_id")

    if not ruta or not tareas_filtradas:
        empty_state_nav(
            "Selecciona una tarea",
            "Elegi una tarea desde el Listado de la Agenda.",
            cta_label="Ir a Listado",
            cta_module="agenda",
            cta_mode="listado",
        )
        return

    # Buscar tarea
    t = None
    for _, tarea in tareas_filtradas:
        if str(tarea.ruta) == ruta:
            t = tarea
            break

    if not t:
        # Fallback: selector manual
        opciones_ag = [
            f"{i+1:02d} | {tareas_filtradas[i][1].fecha_tarea} | {tareas_filtradas[i][1].cliente} -- {tareas_filtradas[i][1].causa}"
            for i in range(len(tareas_filtradas))
        ]
        idx_ag = st.selectbox(
            "Seleccionar tarea",
            options=list(range(len(opciones_ag))),
            format_func=lambda i: opciones_ag[i],
            key="agenda_detalle_sel_v3",
        )
        _, t = tareas_filtradas[idx_ag]

    detail_shell(f"{t.semaforo} {t.cliente} -- {t.causa}")

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
        if st.button("Abrir carpeta", key="agenda_det_open_v3", use_container_width=True):
            try:
                os.startfile(str(t.ruta))
            except Exception:
                st.error("No se pudo abrir la carpeta.")
    with ab2:
        if st.button("Marcar completada", key="agenda_det_done_v3", use_container_width=True):
            accion_completar_tarea(gestor, t.ruta)
    with ab3:
        if st.button("Volver a Listado", key="agenda_det_back", use_container_width=True):
            st.session_state["route_mode"] = "listado"
            st.rerun()

    st.markdown("---")
    render_quick_edit(gestor, t.ruta, "agenda_det")


def _render_agenda_editar(tareas_filtradas: list, gestor: GestorCasos):
    """Agenda - Editar: formulario de edicion completa de la tarea."""
    ruta = st.session_state.get("selected_item_id")

    if not ruta:
        empty_state_nav(
            "Selecciona una tarea para editar",
            "Primero selecciona una tarea en el Listado de la Agenda.",
            cta_label="Ir a Listado",
            cta_module="agenda",
            cta_mode="listado",
        )
        return

    # Redirigir a la edicion completa del caso
    st.session_state["selected_case_id"] = ruta
    st.session_state["gestion_tab"] = "Casos"
    st.session_state["route_mode"] = "editar"
    st.rerun()


# ══════════════════════════════════════════════════════════════════════════════
# MODULO FINANZAS
# ══════════════════════════════════════════════════════════════════════════════

def render_modulo_finanzas(gestor: GestorCasos, casos: List[Caso], mode: str = "listado"):
    """Modulo Finanzas: 3 modos excluyentes — Listado / Detalle / Editar (UX v3)."""
    if not casos:
        empty_state_nav("Sin datos", "No hay casos cargados para ver finanzas.",
                       cta_label="Ir a Casos", cta_module="casos")
        return

    # Sub-nav de modo
    selected_mode = mode_tabs(mode, ["listado", "detalle", "editar"], key="fin_mode_tabs")
    if selected_mode != mode:
        st.session_state["route_mode"] = selected_mode
        st.rerun()

    # Preparar resumen financiero
    resumen = []
    for c in casos:
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
        _render_finanzas_detalle(df_fin, casos, gestor)
    elif mode == "editar":
        _render_finanzas_editar(df_fin, casos, gestor)


def _render_finanzas_listado(df_fin: pd.DataFrame, gestor: GestorCasos):
    """Finanzas - Listado: grilla resumen + totales."""
    grid_shell("Finanzas", subtitle="Resumen economico", fluid=True)

    filtro_pago = st.selectbox("Filtrar por estado de pago", ["Todos"] + ESTADOS_PAGO, key="fin_filtro_pago")
    if filtro_pago and filtro_pago != "Todos":
        df_fin_f = df_fin[df_fin["Estado Pago"] == filtro_pago].copy()
    else:
        df_fin_f = df_fin.copy()

    selected_ruta = render_aggrid(df_fin_f, key="fin_grid_v3", height_px=480)

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
        st.session_state["selected_item_id"] = selected_ruta
        st.session_state["route_mode"] = "detalle"
        st.rerun()


def _render_finanzas_detalle(df_fin: pd.DataFrame, casos: List[Caso], gestor: GestorCasos):
    """Finanzas - Detalle: ficha financiera del caso."""
    ruta = st.session_state.get("selected_item_id")

    if not ruta:
        empty_state_nav(
            "Selecciona un caso",
            "Elegi un caso desde el Listado de Finanzas.",
            cta_label="Ir a Listado",
            cta_module="finanzas",
            cta_mode="listado",
        )
        return

    # Buscar caso
    caso_sel = None
    for c in casos:
        if str(c.ruta) == ruta:
            caso_sel = c
            break

    if not caso_sel:
        empty_state_nav("Caso no encontrado", "El caso seleccionado ya no existe.",
                       cta_label="Ir a Listado", cta_module="finanzas", cta_mode="listado")
        return

    fin = gestor.leer_datos_financieros(caso_sel.ruta)

    detail_shell(f"{caso_sel.cliente} -- {caso_sel.causa}")

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
        if st.button("Editar finanzas", key="fin_det_edit", use_container_width=True):
            st.session_state["route_mode"] = "editar"
            st.rerun()
    with ac2:
        if st.button("Volver a Listado", key="fin_det_back", use_container_width=True):
            st.session_state["route_mode"] = "listado"
            st.rerun()


def _render_finanzas_editar(df_fin: pd.DataFrame, casos: List[Caso], gestor: GestorCasos):
    """Finanzas - Editar: formulario de datos financieros."""
    ruta = st.session_state.get("selected_item_id")

    # Buscar caso o permitir seleccion
    caso_sel = None
    if ruta:
        for c in casos:
            if str(c.ruta) == ruta:
                caso_sel = c
                break

    if not caso_sel:
        page_header("Editar Finanzas")
        opciones = [f"{c.cliente} -- {c.causa}" for c in casos]
        sel_idx = st.selectbox("Seleccionar caso", range(len(opciones)),
                               format_func=lambda i: opciones[i], key="fin_caso_sel_v3")
        caso_sel = casos[sel_idx]
        st.session_state["selected_item_id"] = str(caso_sel.ruta)

    page_header("Editar Finanzas", subtitle=f"{caso_sel.cliente} -- {caso_sel.causa}")

    fin_actual = gestor.leer_datos_financieros(caso_sel.ruta)

    fc1, fc2, fc3 = st.columns(3)
    with fc1:
        monto = st.text_input("Monto Demandado", value=fin_actual.get("MONTO_DEMANDADO", ""), key="fin_monto_v3")
    with fc2:
        honorarios = st.text_input("Honorarios Pactados", value=fin_actual.get("HONORARIOS_PACTADOS", ""), key="fin_honorarios_v3")
    with fc3:
        estado_pago = st.selectbox("Estado Pago", ESTADOS_PAGO,
                                    index=ESTADOS_PAGO.index(fin_actual.get("ESTADO_PAGO", "")) if fin_actual.get("ESTADO_PAGO", "") in ESTADOS_PAGO else len(ESTADOS_PAGO) - 1,
                                    key="fin_estado_pago_v3")

    st.markdown("---")
    b1, b2 = st.columns(2)
    with b1:
        if st.button("Guardar datos financieros", key="fin_guardar_v3", use_container_width=True):
            datos_fin = {
                "MONTO_DEMANDADO": monto,
                "HONORARIOS_PACTADOS": honorarios,
                "ESTADO_PAGO": estado_pago,
            }
            if gestor.guardar_datos_financieros(caso_sel.ruta, datos_fin):
                st.cache_data.clear()
                st.success("Datos financieros guardados.")
                _ui_toast("Finanzas guardadas")
                st.session_state["route_mode"] = "detalle"
                st.rerun()
    with b2:
        if st.button("Cancelar", key="fin_cancel_v3", use_container_width=True):
            st.session_state["route_mode"] = "detalle"
            st.rerun()


# ══════════════════════════════════════════════════════════════════════════════
# FORMULARIOS
# ══════════════════════════════════════════════════════════════════════════════

def formulario_nuevo_caso(ui, gestor: GestorCasos):
    """Formulario optimizado para crear un nuevo caso."""
    with ui.form("nuevo_caso_form"):
        año = st.selectbox("Año", gestor.obtener_años_existentes())
        estado = st.selectbox("Estado", ESTADOS_DISPONIBLES)

        opcion_cliente = st.radio("Cliente", ["Existente", "Nuevo"], horizontal=True)

        clientes_existentes = gestor.obtener_clientes_existentes()

        if opcion_cliente == "Existente" and clientes_existentes:
            cliente_final = st.selectbox("Seleccionar Cliente", clientes_existentes)
        else:
            cliente_final = st.text_input("Nombre del Nuevo Cliente", placeholder="Apellido Nombre")

        fuero = st.selectbox("Fuero", FUEROS_DISPONIBLES)
        nombre_caso = st.text_input("Nombre del Caso (Causa)", placeholder="Ej: Perez vs. Lopez")

        submitted = st.form_submit_button("CREAR CASO", use_container_width=True)

        if submitted:
            if not cliente_final or not nombre_caso or cliente_final.strip() == "":
                st.error("El nombre del cliente y del caso son obligatorios.")
            else:
                exito, mensaje = gestor.crear_caso(año, estado, cliente_final, fuero, nombre_caso)
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

    if ui.button("Abrir carpeta del caso", use_container_width=True):
        try:
            os.startfile(str(caso.ruta))
        except Exception:
            ui.error("No se pudo abrir la carpeta. Verificar permisos/ruta.")

    with ui.form("editar_caso_form"):
        st.markdown("#### Ubicacion del Caso")

        idx_año = gestor.obtener_años_existentes().index(caso.año) if caso.año in gestor.obtener_años_existentes() else 0
        nuevo_año = st.selectbox("Año", gestor.obtener_años_existentes(), index=idx_año)

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

        nueva_ruta_prevista = RUTA_BASE / nuevo_año / nuevo_estado / nuevo_cliente / nuevo_fuero / nueva_causa
        hay_movimiento = str(caso.ruta) != str(nueva_ruta_prevista)

        confirmar_mov = True
        if hay_movimiento and st.session_state.get("modo_seguro", True):
            st.warning(f"**Origen:** {caso.ruta}\n\n**Destino:** {nueva_ruta_prevista}")
            confirmar_mov = st.checkbox("Confirmo mover carpeta fisica", key="confirmar_mover")

        submitted = st.form_submit_button("GUARDAR CAMBIOS", use_container_width=True)

        if submitted:
            if hay_movimiento and st.session_state.get("modo_seguro", True) and not confirmar_mov:
                st.error("Debe confirmar el movimiento de carpeta para guardar cambios.")
                return

            exito_mov, nueva_ruta = gestor.mover_carpeta_fisica(
                caso, nuevo_año, nuevo_estado, nuevo_cliente, nuevo_fuero, nueva_causa
            )

            if not exito_mov:
                st.error("No se pudo mover la carpeta fisica. Cambios cancelados.")
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

            if gestor.actualizar_caso(nueva_ruta, datos):
                st.cache_data.clear()
                st.success("Caso actualizado y sincronizado correctamente")
                st.rerun()
            else:
                if nueva_ruta != caso.ruta:
                    try:
                        os.makedirs(caso.ruta.parent, exist_ok=True)
                        shutil.move(str(nueva_ruta), str(caso.ruta))
                        st.warning("Movimiento revertido porque fallo la escritura de ficha.")
                    except Exception:
                        st.error(f"Error critico: la carpeta quedo en {nueva_ruta} pero la ficha no se actualizo.")
                st.error("Error al guardar cambios en la ficha")


# ══════════════════════════════════════════════════════════════════════════════
# SPRINT 4: AUDITORIA (sin CSV crudo)
# ══════════════════════════════════════════════════════════════════════════════

def render_auditoria(gestor: GestorCasos, casos: List[Caso]):
    """Auditoria: pantalla tecnica limpia con estado + detalles colapsados."""
    page_header("Auditoria y Calidad", subtitle="Estado del sistema")

    # Botones de accion arriba
    a1, a2, a3 = st.columns(3)
    with a1:
        run_audit = st.button("Ejecutar auditoria", use_container_width=True, key="audit_run")
    with a2:
        confirmar_fix = st.checkbox("Confirmo reparar", key="audit_fix_confirm")
        if st.button("Reparar subcarpetas", use_container_width=True, disabled=not confirmar_fix, key="audit_fix"):
            total_creadas = 0
            pb = st.progress(0)
            for i, c in enumerate(casos, start=1):
                total_creadas += gestor.ensure_case_structure(c.ruta)
                pb.progress(int((i / max(1, len(casos))) * 100))
            st.success(f"Reparacion finalizada. Subcarpetas creadas: {total_creadas}.")
            st.cache_data.clear()
            _ui_toast("Reparacion masiva aplicada")
    with a3:
        # Exportar reporte (si hay resultado)
        if "ultimo_resultado_auditoria" in st.session_state:
            reporte = st.session_state["ultimo_resultado_auditoria"]
            json_bytes = json.dumps(reporte, ensure_ascii=False, indent=2).encode("utf-8")
            st.download_button(
                "Exportar reporte (JSON)",
                data=json_bytes,
                file_name=f"auditoria_vg_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
                mime="application/json",
                use_container_width=True,
            )

    st.markdown("---")

    # Ejecutar auditoria si se presiono el boton
    if run_audit:
        with st.spinner("Ejecutando auditoria..."):
            reporte = auditar_app(gestor, casos)
            st.session_state["ultimo_resultado_auditoria"] = reporte

    # Mostrar resultado si existe
    if "ultimo_resultado_auditoria" in st.session_state:
        reporte = st.session_state["ultimo_resultado_auditoria"]
        r = reporte.get("resumen", {})
        errores = int(r.get("errores", 0))
        warnings = int(r.get("warnings", 0))
        infos = int(r.get("info", 0))
        casos_total = int(r.get("casos", 0))

        # Estado del sistema (badge grande)
        st.markdown("#### Estado del sistema")
        audit_status_badge(errores, warnings)

        # Metricas rapidas
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            st.metric("Errores", errores)
        with c2:
            st.metric("Advertencias", warnings)
        with c3:
            st.metric("Info", infos)
        with c4:
            st.metric("Casos auditados", casos_total)

        # Detalles tecnicos (colapsados por defecto)
        hall = reporte.get("hallazgos", [])
        if hall:
            with st.expander("Ver detalles tecnicos", expanded=False):
                df_h = pd.DataFrame(hall)
                orden = {"ERROR": 0, "WARN": 1, "INFO": 2}
                df_h["_ORD"] = df_h["nivel"].map(orden).fillna(9)
                df_h = df_h.sort_values(
                    ["_ORD", "codigo"], ascending=[True, True]
                ).drop(columns=["_ORD"])

                st.dataframe(df_h, use_container_width=True, hide_index=True)

                csv_h = df_h.to_csv(index=False).encode("utf-8-sig")
                st.download_button(
                    "Descargar hallazgos (CSV)",
                    data=csv_h,
                    file_name=f"auditoria_hallazgos_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                    mime="text/csv",
                    use_container_width=True,
                )

        # Completitud (colapsada)
        m = reporte.get("metricas", {}).get("completitud", {})
        if m:
            with st.expander("Completitud de datos (por campo)", expanded=False):
                df_m = pd.DataFrame([
                    {"Campo": k, **v} for k, v in m.items()
                ]).sort_values("pct_completos", ascending=True)
                st.dataframe(df_m, use_container_width=True, hide_index=True)

    else:
        st.info("Presione 'Ejecutar auditoria' para analizar el sistema.")

    # Diagnostico basico (siempre visible)
    st.markdown("---")
    st.markdown("#### Diagnostico basico")
    ruta_ok = RUTA_BASE.exists() and RUTA_BASE.is_dir()
    st.write(f"**Ruta base:** `{RUTA_BASE}` — {'Accesible' if ruta_ok else 'NO ACCESIBLE'}")

    try:
        perms_ok = os.access(str(RUTA_BASE), os.R_OK | os.W_OK)
        st.write(f"**Permisos lectura/escritura:** {'OK' if perms_ok else 'Sin permisos'}")
    except Exception:
        st.write("**Permisos:** No se pudo verificar")

    st.write(f"**Casos cargados:** {len(casos)}")


# ══════════════════════════════════════════════════════════════════════════════
# CONFIGURACION
# ══════════════════════════════════════════════════════════════════════════════

def render_configuracion(gestor: GestorCasos, casos: List[Caso]):
    """Vista de configuracion: editar caso + ayuda."""
    page_header("Configuracion", subtitle="Ajustes avanzados")

    tab1, tab2 = st.tabs(["Editar caso", "Ayuda"])

    with tab1:
        if casos:
            formulario_editar_caso(st, gestor, casos)
        else:
            st.info("No hay casos para editar.")

    with tab2:
        ui_centro_ayuda_content()


# ══════════════════════════════════════════════════════════════════════════════
# LEGACY: render_panel, render_ajustes (para compatibilidad)
# ══════════════════════════════════════════════════════════════════════════════

def render_panel(gestor: GestorCasos, casos: List[Caso], df=None):
    """Legacy: redirige a Dashboard."""
    render_dashboard(gestor, casos)


def render_ajustes(gestor: GestorCasos, casos: List[Caso]):
    """Legacy: redirige a Configuracion."""
    render_configuracion(gestor, casos)
