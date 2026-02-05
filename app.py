"""
VACA & GENTILE ERP v1.0 - Sistema de Gestion Juridica Integral
Sprint 1: Navegacion MPA logica (4 secciones primarias via sidebar)
Jerarquia Sagrada: ANO > ESTADO > CLIENTE > FUERO > CAUSA
"""

import streamlit as st
import pandas as pd
from typing import List

from config import RUTA_BASE, RUTA_BASE_AUTO_CREATE, get_ruta_base_info
from domain import Caso
from repo import GestorCasos, is_db_mode, get_backend_info
from ui import configurar_pagina, barra_lateral_config
from nav import get_route
from views import (
    render_dashboard,
    render_gestion,
    render_auditoria,
    render_configuracion,
)


# ══════════════════════════════════════════════════════════════════════════════
# ESTADO GLOBAL
# ══════════════════════════════════════════════════════════════════════════════

def ensure_state():
    """Inicializa la maquina de estado de la app."""
    # Routing v4: una sola navegacion primaria
    st.session_state.setdefault("nav_route", "Dashboard")
    st.session_state.setdefault("route_mode", "listado")
    st.session_state.setdefault("selected_case_id", None)
    st.session_state.setdefault("selected_item_id", None)
    st.session_state.setdefault("gestion_tab", "Casos")


# ══════════════════════════════════════════════════════════════════════════════
# CARGA DE DATOS (CON CACHE)
# ══════════════════════════════════════════════════════════════════════════════

@st.cache_data(ttl=60)
def cargar_casos(_gestor: GestorCasos) -> List[Caso]:
    """Carga y cachea los casos del sistema de archivos."""
    return _gestor.escanear_casos()


# ══════════════════════════════════════════════════════════════════════════════
# HEADER COMPACTO
# ══════════════════════════════════════════════════════════════════════════════

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


# ══════════════════════════════════════════════════════════════════════════════
# DIAGNOSTICO DE RUTA BASE
# ══════════════════════════════════════════════════════════════════════════════

def _show_ruta_error(mensaje: str):
    """Muestra error de ruta base con información de diagnóstico."""
    info = get_ruta_base_info()
    st.error(f"**Error de configuración:** {mensaje}")
    with st.expander("Diagnóstico técnico", expanded=True):
        st.code(f"""
RUTA_BASE:        {info['ruta_base']}
Existe:           {info['exists']}
Es directorio:    {info['is_dir']}
Auto-creatable:   {info['auto_create']}
En contenedor:    {info['is_container']}
VG_RUTA_BASE:     {info['env_VG_RUTA_BASE']}
CWD:              {info['cwd']}
""".strip())
        st.info("""
**Soluciones posibles:**
- En local: Verificar que la carpeta de datos existe
- En Docker/Render: Setear `VG_RUTA_BASE=/app/data` o montar volumen
- Fallback: Se usará `./data` si ninguna otra ruta está disponible
""")


# ══════════════════════════════════════════════════════════════════════════════
# APP SHELL (FUNCION PRINCIPAL)
# ══════════════════════════════════════════════════════════════════════════════

def main():
    """Punto de entrada principal - App Shell con navegacion MPA logica."""
    configurar_pagina()
    ensure_state()

    # ══════════════════════════════════════════════════════════════════════════
    # INICIALIZACION DE REPOSITORIO (DB o Filesystem)
    # ══════════════════════════════════════════════════════════════════════════

    if is_db_mode():
        # Modo base de datos: no necesita validar filesystem
        gestor = GestorCasos(RUTA_BASE)  # RUTA_BASE se ignora en modo DB
        spinner_msg = "Conectando a base de datos..."
    else:
        # Modo filesystem: validar y crear ruta si es necesario
        if RUTA_BASE_AUTO_CREATE and not RUTA_BASE.exists():
            try:
                RUTA_BASE.mkdir(parents=True, exist_ok=True)
            except Exception as e:
                _show_ruta_error(f"No se pudo crear el directorio: {e}")
                st.stop()

        if not RUTA_BASE.exists() or not RUTA_BASE.is_dir():
            _show_ruta_error("La ruta base no existe o no es un directorio.")
            st.stop()

        gestor = GestorCasos(RUTA_BASE)
        spinner_msg = "Escaneando sistema de archivos..."

    # Cargar casos
    with st.spinner(spinner_msg):
        casos = cargar_casos(gestor)
        gestor._cache_casos = casos

    # Preparar DataFrame global
    df = None
    if casos:
        df = pd.DataFrame([caso.to_dict() for caso in casos])
        cols_search = [c for c in df.columns if not str(c).startswith("_")]
        df["_SEARCH"] = df[cols_search].astype(str).agg(" ".join, axis=1).str.lower()

    # ── SIDEBAR: Navegacion primaria + Config ──
    barra_lateral_config(gestor)
    route = get_route()

    # ── HEADER (minimo) ──
    render_header(len(casos))

    # ── WORKSPACE: Dispatch por ruta ──
    if route == "Dashboard":
        render_dashboard(gestor, casos)

    elif route == "Gestion":
        render_gestion(gestor, casos, df)

    elif route == "Auditoria":
        render_auditoria(gestor, casos)

    elif route == "Configuracion":
        render_configuracion(gestor, casos)


if __name__ == "__main__":
    main()
