"""
Navegacion primaria: sidebar unico con secciones operativas.
Compatible con Streamlit viejo (st.sidebar.radio).
"""

import streamlit as st
import re

ROUTES = ["Dashboard", "Gestion", "Agenda", "Finanzas", "Auditoria", "Configuracion"]

# Sub-tabs dentro de Gestion
GESTION_TABS = ["Casos", "Clientes"]
_DB_CASE_RE = re.compile(r"db[:/\\\\]+cases[:/\\\\]+([0-9a-fA-F-]{36})", re.IGNORECASE)
_UUID_RE = re.compile(r"^[0-9a-fA-F-]{36}$")


def available_routes(can_access_fn=None) -> list[str]:
    """
    Devuelve rutas visibles segun permisos.
    Si ninguna ruta queda habilitada, mantiene Dashboard como fallback seguro.
    """
    checker = can_access_fn or (lambda _route: True)
    visible = [route for route in ROUTES if checker(route)]
    return visible or ["Dashboard"]


def _canonical_case_id(value: str) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    m = _DB_CASE_RE.search(raw)
    if m:
        return f"db://cases/{m.group(1).lower()}"
    if _UUID_RE.fullmatch(raw):
        return f"db://cases/{raw.lower()}"
    return raw


def get_route() -> str:
    """Devuelve la ruta seleccionada (una de ROUTES).
    Usa st.sidebar.radio como unica navegacion primaria."""
    st.session_state.setdefault("nav_route", "Dashboard")

    # Procesar navegacion programatica
    if st.session_state.get("_nav_target"):
        target = st.session_state["_nav_target"]
        st.session_state["nav_route"] = target
        st.session_state["_sidebar_nav"] = target
        st.session_state["_nav_target"] = ""
        st.rerun()

    # Resolver rutas visibles segun RBAC.
    from security import can_access_route

    visible_routes = available_routes(can_access_route)

    current = st.session_state.get("nav_route", "Dashboard")
    if current not in visible_routes:
        current = visible_routes[0]
        st.session_state["nav_route"] = current
    if st.session_state.get("_sidebar_nav") not in visible_routes:
        st.session_state["_sidebar_nav"] = current

    idx = visible_routes.index(current) if current in visible_routes else 0

    with st.sidebar.expander("Modulos de trabajo", expanded=True):
        route = st.radio(
            "Navegacion principal",
            visible_routes,
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
        if route in {"Gestion", "Agenda", "Finanzas"}:
            st.session_state["selected_case_id"] = _canonical_case_id(item_id)
        else:
            st.session_state["selected_item_id"] = item_id
    st.rerun()
