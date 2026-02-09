"""
VACA & GENTILE ERP v1.0 - Sistema de Gestion Juridica Integral
Sprint 1: Navegacion MPA logica (secciones primarias via sidebar)
Jerarquia Sagrada: ANO > ESTADO > CLIENTE > FUERO > CAUSA
"""

import logging
import os
from typing import List

import pandas as pd
import streamlit as st

import views as _views
from db.health import wait_for_db
from domain import Caso
from nav import get_route
from repo import GestorCasos, is_db_mode
from security import can_access_route, render_login_gate, render_sidebar_identity
from ui import aplicar_estilos_stitch, barra_lateral_config, configurar_pagina

render_dashboard = _views.render_dashboard
render_gestion = _views.render_gestion
render_auditoria = _views.render_auditoria
render_configuracion = _views.render_configuracion

logger = logging.getLogger(__name__)


def render_agenda(gestor: GestorCasos, casos: List[Caso]):
    """Compat: usa entrypoint nuevo o fallback al mÃ³dulo legacy."""
    if hasattr(_views, "render_agenda"):
        return _views.render_agenda(gestor, casos)
    return _views.render_modulo_agenda(gestor, casos, "listado")


def render_finanzas(gestor: GestorCasos, casos: List[Caso]):
    """Compat: usa entrypoint nuevo o fallback al mÃ³dulo legacy."""
    if hasattr(_views, "render_finanzas"):
        return _views.render_finanzas(gestor, casos)
    return _views.render_modulo_finanzas(gestor, casos, "listado")


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# ESTADO GLOBAL
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

def ensure_state():
    """Inicializa la maquina de estado de la app."""
    # Routing v4: una sola navegacion primaria
    st.session_state.setdefault("nav_route", "Dashboard")
    st.session_state.setdefault("route_mode", "listado")
    st.session_state.setdefault("selected_case_id", None)
    st.session_state.setdefault("selected_item_id", None)
    st.session_state.setdefault("gestion_tab", "Casos")
    st.session_state.setdefault("gestion_mode_casos", "listado")
    st.session_state.setdefault("gestion_mode_cliente", "listado")
    st.session_state.setdefault("gestion_mode_clientes", "listado")
    st.session_state.setdefault("gestion_mode_agenda", "listado")
    st.session_state.setdefault("gestion_mode_finanzas", "listado")
    # Estado namespaced de Gestion (fuente de verdad).
    st.session_state.setdefault("gestion.section", "casos")
    st.session_state.setdefault("gestion.tab", "casos")  # Legacy.
    st.session_state.setdefault("gestion.mode.casos", "listado")
    st.session_state.setdefault("gestion.mode.clientes", "listado")
    st.session_state.setdefault("gestion.mode.cliente", "listado")  # Legacy.
    st.session_state.setdefault("gestion.mode.agenda", "listado")
    st.session_state.setdefault("gestion.mode.finanzas", "listado")
    st.session_state.setdefault("gestion.selected.case_id", "")
    st.session_state.setdefault("gestion.selected.client_id", "")
    st.session_state.setdefault("gestion.selected.agenda_id", "")
    st.session_state.setdefault("gestion.selected.fin_id", "")
    st.session_state.setdefault("gestion.casos.selected_case_id", "")  # Legacy.
    st.session_state.setdefault("gestion.filters.casos", {})
    st.session_state.setdefault("gestion.filters.clientes", {})
    st.session_state.setdefault("gestion.filters.agenda", {})
    st.session_state.setdefault("gestion.filters.finanzas", {})
    st.session_state.setdefault("gestion.casos.show_new_form", False)
    st.session_state.setdefault("gestion.snapshots.casos", {})
    st.session_state.setdefault("gestion.snapshots.clientes", {})
    st.session_state.setdefault("gestion.snapshots.cliente", {})  # Legacy.
    st.session_state.setdefault("gestion.snapshots.agenda", {})
    st.session_state.setdefault("gestion.snapshots.finanzas", {})
    # Estado de filtros/controles de Gestion > Casos para evitar claves faltantes entre reruns.
    st.session_state.setdefault("busqueda_global", "")
    st.session_state.setdefault("filtro_aÃ±o", "Todos")
    st.session_state.setdefault("filtro_estado", "Todos")
    st.session_state.setdefault("filtro_cliente", "Todos")
    st.session_state.setdefault("filtro_fuero", "Todos")
    st.session_state.setdefault("filtro_semaforo", "Todos")
    st.session_state.setdefault("filtro_atajo", "Ninguno")
    st.session_state.setdefault("priorizar_urgentes", True)
    st.session_state.setdefault("planilla_modo", "Tabla")
    st.session_state.setdefault("planilla_densidad", "Compacta")
    st.session_state.setdefault("planilla_wrap", False)
    st.session_state.setdefault("casos_filters", {})
    st.session_state.setdefault("gestion.casos.filters.busqueda", "")
    st.session_state.setdefault("gestion.casos.filters.anio", "Todos")
    st.session_state.setdefault("gestion.casos.filters.estado", "Todos")
    st.session_state.setdefault("gestion.casos.filters.cliente", "Todos")
    st.session_state.setdefault("gestion.casos.filters.fuero", "Todos")
    st.session_state.setdefault("gestion.casos.filters.semaforo", "Todos")
    st.session_state.setdefault("gestion.casos.filters.atajo", "Ninguno")
    st.session_state.setdefault("gestion.casos.filters.priorizar_urgentes", True)
    st.session_state.setdefault("gestion.casos.filters.modo", "Tabla")
    st.session_state.setdefault("gestion.casos.filters.densidad", "Compacta")
    st.session_state.setdefault("gestion.casos.filters.wrap", False)


def ensure_db_health_state():
    """Inicializa y evalua health DB una sola vez por sesion."""
    st.session_state.setdefault("db_ready", None)
    st.session_state.setdefault("db_health", {})

    if st.session_state["db_ready"] is None:
        health = wait_for_db(os.environ.get("DATABASE_URL", ""), attempts=3)
        st.session_state["db_health"] = health
        st.session_state["db_ready"] = bool(health.get("ok"))


def render_db_health_banner():
    """Banner global de estado DB con reintento manual."""
    if not is_db_mode() or st.session_state.get("db_ready", True):
        return

    health = st.session_state.get("db_health", {}) or {}
    stage = health.get("stage", "init")
    detail = health.get("last_error") or "Sin detalle tecnico."
    st.error(f"Base de datos no disponible (stage={stage}).")
    st.caption(f"Detalle: {detail}")
    if st.button("Reintentar conexion", key="db_health_retry", width="stretch"):
        st.session_state["db_ready"] = None
        st.session_state["db_health"] = {}
        st.rerun()


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# CARGA DE DATOS (CON CACHE)
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

@st.cache_data(ttl=60)
def cargar_casos(_gestor: GestorCasos) -> List[Caso]:
    """Carga y cachea los casos del sistema de archivos."""
    return _gestor.escanear_casos()


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# HEADER COMPACTO
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

def render_header(casos_total: int):
    """Header fijo con branding compacto."""
    st.markdown(f"""
    <div class="vg-card" style="padding: 12px 16px; margin-bottom: 8px;">
      <div style="display:flex;align-items:center;justify-content:space-between;gap:12px;">
        <div style="display:flex;align-items:center;gap:12px;">
          <div style="font-size:20px;font-weight:900;letter-spacing:.2px;color:var(--brand);line-height:1;">
            VACA &amp; GENTILE
          </div>
          <span class="vg-pill">Casos: {casos_total}</span>
        </div>
        <div style="font-size:11px;color:var(--muted);">ERP v1.0</div>
      </div>
    </div>
    """, unsafe_allow_html=True)


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# DIAGNOSTICO DE ARRANQUE
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# APP SHELL (FUNCION PRINCIPAL)
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

def main():
    """Punto de entrada principal - App Shell con navegacion MPA logica."""
    if not logging.getLogger().handlers:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s %(levelname)s %(name)s %(message)s",
        )

    configurar_pagina()
    aplicar_estilos_stitch()
    ensure_state()
    if not render_login_gate():
        return
    ensure_db_health_state()
    render_db_health_banner()

    # â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
    # INICIALIZACION DE REPOSITORIO (DB-first)
    # â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

    gestor = GestorCasos()
    spinner_msg = "Conectando a base de datos..."

    # Cargar casos
    casos = []
    if is_db_mode() and not st.session_state.get("db_ready", False):
        health = st.session_state.get("db_health", {})
        detail = health.get("last_error") or "Sin detalle tecnico."
        st.warning(f"Base de datos no disponible. Modo degradado activo. ({detail})")
    else:
        try:
            with st.spinner(spinner_msg):
                casos = cargar_casos(gestor)
                gestor._cache_casos = casos
        except Exception as e:
            logger.warning("carga de casos fallida: %s", e)
            st.session_state["db_ready"] = False
            st.session_state["db_health"] = {
                "ok": False,
                "error_type": type(e).__name__,
                "last_error": str(e),
                "attempt": 0,
                "attempts": 0,
            }
            st.warning(f"No se pudieron cargar casos desde DB. ({type(e).__name__}: {e})")
            casos = []

    if st.session_state.get("db_ready", False) and hasattr(gestor, "verificar_conteo_casos"):
        st.session_state["conteo_casos_diag"] = gestor.verificar_conteo_casos(casos)

    # Preparar DataFrame global
    df = None
    if casos:
        df = pd.DataFrame([caso.to_dict() for caso in casos])
        st.session_state["df_full"] = df.copy()
        cols_search = [c for c in df.columns if not str(c).startswith("_")]
        df["_SEARCH"] = df[cols_search].astype(str).agg(" ".join, axis=1).str.lower()

    # â”€â”€ SIDEBAR: Navegacion primaria + Config â”€â”€
    barra_lateral_config(gestor)
    render_sidebar_identity()
    route = get_route()
    if is_db_mode() and not st.session_state.get("db_ready", False):
        allowed_routes = {"Dashboard", "Auditoria", "Configuracion"}
        if route not in allowed_routes:
            st.session_state["nav_route"] = "Dashboard"
            route = "Dashboard"
    if not can_access_route(route):
        logger.warning("route blocked by RBAC route=%s", route)
        st.error("Acceso denegado para la ruta seleccionada.")
        st.session_state["nav_route"] = "Dashboard"
        route = "Dashboard"

    # â”€â”€ HEADER (minimo) â”€â”€
    render_header(len(casos))

    # â”€â”€ WORKSPACE: Dispatch por ruta â”€â”€
    if route == "Dashboard":
        render_dashboard(gestor, casos)

    elif route == "Gestion":
        render_gestion(gestor, casos, df)

    elif route == "Agenda":
        render_agenda(gestor, casos)

    elif route == "Finanzas":
        render_finanzas(gestor, casos)

    elif route == "Auditoria":
        render_auditoria(gestor, casos)

    elif route == "Configuracion":
        render_configuracion(gestor, casos)


if __name__ == "__main__":
    main()
