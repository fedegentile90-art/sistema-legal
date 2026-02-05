"""
Navegacion primaria: sidebar unico con 4 secciones.
Compatible con Streamlit viejo (st.sidebar.radio).
"""

import streamlit as st

ROUTES = ["Dashboard", "Gestion", "Auditoria", "Configuracion"]

# Sub-tabs dentro de Gestion
GESTION_TABS = ["Casos", "Cliente", "Agenda", "Finanzas"]


def get_route() -> str:
    """Devuelve la ruta seleccionada (una de ROUTES).
    Usa st.sidebar.radio como unica navegacion primaria."""
    st.session_state.setdefault("nav_route", "Dashboard")

    # Procesar navegacion programatica
    if st.session_state.get("_nav_target"):
        target = st.session_state["_nav_target"]
        st.session_state["nav_route"] = target
        st.session_state["_nav_target"] = ""
        st.rerun()

    current = st.session_state.get("nav_route", "Dashboard")
    idx = ROUTES.index(current) if current in ROUTES else 0

    route = st.sidebar.radio(
        "Navegacion",
        ROUTES,
        index=idx,
        key="_sidebar_nav",
        label_visibility="collapsed",
    )
    if route != current:
        st.session_state["nav_route"] = route
        st.session_state["route_mode"] = "listado"

    return route


def navigate_to(route: str, mode: str = "listado", item_id: str | None = None):
    """Navegar programaticamente a una ruta."""
    st.session_state["nav_route"] = route
    st.session_state["route_mode"] = mode
    if item_id is not None:
        if route == "Gestion":
            st.session_state["selected_case_id"] = item_id
        else:
            st.session_state["selected_item_id"] = item_id
    st.rerun()
