import hashlib
import html
import inspect
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Literal

import streamlit as st

# --- DESIGN SYSTEM: STITCH / DEEP NAVY ---

logger = logging.getLogger(__name__)

TOKENS = {
    "colors": {
        "dark": {
            "bg_app": "#090F1C",
            "bg_sidebar": "#111A2E",
            "bg_card": "#141F36",
            "bg_card_hover": "#1A2845",
            "border": "rgba(160, 178, 212, 0.30)",
            "text_main": "#F5F7FF",
            "text_muted": "#B2BED8",
            "primary": "#5B8CFF",
            "primary_hover": "#3F73F0",
            "success": "#2BCB94",
            "warning": "#FFB347",
            "danger": "#FF6B6B",
            "badge_bg": "rgba(255,255,255,0.09)",
            "bg_glow_1": "rgba(91, 140, 255, 0.26)",
            "bg_glow_2": "rgba(43, 203, 148, 0.14)",
        },
        "light": {
            "bg_app": "#F2F5FB",
            "bg_sidebar": "#EAF0FB",
            "bg_card": "#FFFFFF",
            "bg_card_hover": "#EEF3FB",
            "border": "rgba(20, 33, 61, 0.24)",
            "text_main": "#0D1B34",
            "text_muted": "#3F4F6F",
            "primary": "#305FD8",
            "primary_hover": "#234CB9",
            "success": "#0E9F6E",
            "warning": "#B7791F",
            "danger": "#C0392B",
            "badge_bg": "rgba(13,27,52,0.06)",
            "bg_glow_1": "rgba(48, 95, 216, 0.18)",
            "bg_glow_2": "rgba(14, 159, 110, 0.10)",
        },
    },
    "typography": {
        "font_family": '"Plus Jakarta Sans", "IBM Plex Sans", "Segoe UI", sans-serif',
        "h1": "2rem",
        "h2": "1.5rem",
        "body": "0.98rem",
        "small": "0.88rem",
    },
    "spacing": {"xs": "4px", "sm": "8px", "md": "12px", "lg": "18px", "xl": "26px"},
    "radius": {"sm": "0.45rem", "md": "0.75rem", "lg": "1rem", "full": "9999px"},
    "shadows": {
        "card": "0 10px 28px rgba(15, 25, 50, 0.15)",
        "glow": "0 0 0 3px rgba(91, 140, 255, 0.28)",
    },
}

# --- ESTADO GLOBAL DE UI ---

UI_REVAMP_FLAG_ENV = "VG_UI_REVAMP_V2"
UI_THEME_DEFAULT_ENV = "VG_UI_THEME_DEFAULT"
UI_DENSITY_DEFAULT_ENV = "VG_UI_DENSITY_DEFAULT"

THEME_OPTIONS = {"dark": "Oscuro", "light": "Claro"}
DENSITY_OPTIONS = {"compact": "Compacta", "balanced": "Balanceada", "wide": "Amplia"}

SESSION_THEME_KEY = "theme_mode"
SESSION_DENSITY_KEY = "ui_density_mode"
SESSION_PREFS_USER_KEY = "ui.prefs.user_id"
SESSION_PREFS_LOADED_KEY = "ui.prefs.loaded"
SESSION_BLOCK_ORDER_PREFIX = "ui.block_order."


@dataclass(frozen=True)
class UIPreferences:
    theme_mode: str = "dark"
    density_mode: str = "compact"


def _env_bool(name: str, default: bool = False) -> bool:
    raw = str(os.environ.get(name, "")).strip().lower()
    if not raw:
        return bool(default)
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off"}:
        return False
    return bool(default)


def is_ui_revamp_enabled() -> bool:
    return _env_bool(UI_REVAMP_FLAG_ENV, default=True)


def _default_theme_mode() -> str:
    raw = str(os.environ.get(UI_THEME_DEFAULT_ENV, "dark")).strip().lower()
    return raw if raw in THEME_OPTIONS else "dark"


def _default_density_mode() -> str:
    raw = str(os.environ.get(UI_DENSITY_DEFAULT_ENV, "compact")).strip().lower()
    return raw if raw in DENSITY_OPTIONS else "compact"


def _current_user_id() -> str:
    try:
        from security import current_user

        user = current_user()
        return str(user.user_id or "").strip()
    except Exception:
        return ""


def _load_ui_preferences_for_user(user_id: str) -> UIPreferences:
    theme = _default_theme_mode()
    density = _default_density_mode()
    if not user_id:
        return UIPreferences(theme_mode=theme, density_mode=density)
    try:
        from security import load_user_ui_preferences

        raw = load_user_ui_preferences(user_id)
        if isinstance(raw, dict):
            theme_raw = str(raw.get("theme_mode", "")).strip().lower()
            density_raw = str(raw.get("density_mode", "")).strip().lower()
            if theme_raw in THEME_OPTIONS:
                theme = theme_raw
            if density_raw in DENSITY_OPTIONS:
                density = density_raw
    except Exception as exc:
        logger.debug("load user ui preferences unavailable: %s", exc)
    return UIPreferences(theme_mode=theme, density_mode=density)


def _ensure_ui_preferences_loaded() -> None:
    user_id = _current_user_id()
    loaded_user = str(st.session_state.get(SESSION_PREFS_USER_KEY, "")).strip()
    loaded = bool(st.session_state.get(SESSION_PREFS_LOADED_KEY, False))
    if loaded and loaded_user == user_id and SESSION_THEME_KEY in st.session_state and SESSION_DENSITY_KEY in st.session_state:
        return
    prefs = _load_ui_preferences_for_user(user_id)
    st.session_state[SESSION_THEME_KEY] = prefs.theme_mode
    st.session_state[SESSION_DENSITY_KEY] = prefs.density_mode
    st.session_state[SESSION_PREFS_USER_KEY] = user_id
    st.session_state[SESSION_PREFS_LOADED_KEY] = True


def _persist_ui_preferences_if_possible(theme_mode: str, density_mode: str) -> None:
    user_id = _current_user_id()
    if not user_id:
        return
    payload = {"theme_mode": theme_mode, "density_mode": density_mode}
    last_saved = st.session_state.get("ui.prefs.last_saved")
    if isinstance(last_saved, dict) and last_saved == payload:
        return
    try:
        from security import save_user_ui_preferences

        if save_user_ui_preferences(user_id, payload):
            st.session_state["ui.prefs.last_saved"] = dict(payload)
    except Exception as exc:
        logger.debug("save user ui preferences unavailable: %s", exc)


# --- GESTION DE ESTADO Y TEMA ---


def inicializar_ui():
    """Configura variables de sesión iniciales para la UI."""
    _ensure_ui_preferences_loaded()


def get_current_theme():
    """Retorna el diccionario de colores para el tema actual."""
    mode = st.session_state.get(SESSION_THEME_KEY, _default_theme_mode())
    return TOKENS["colors"].get(mode, TOKENS["colors"]["dark"])


def toggle_theme():
    """Alterna entre modo claro y oscuro."""
    current = st.session_state.get(SESSION_THEME_KEY, _default_theme_mode())
    st.session_state[SESSION_THEME_KEY] = "light" if current == "dark" else "dark"


# --- COMPATIBILIDAD (helpers heredados usados por views.py) ---


def _df_select_kwargs():
    """Devuelve kwargs opcionales para habilitar selecciÃ³n en st.dataframe si la versiÃ³n lo soporta."""
    try:
        params = inspect.signature(st.dataframe).parameters
        kw = {}
        if "on_select" in params:
            kw["on_select"] = "rerun"
        if "selection_mode" in params:
            kw["selection_mode"] = "single-row"
        return kw
    except Exception:
        return {}


def _ensure_bool_state(key: str, default: bool = False) -> bool:
    """Compat: garantiza que session_state[key] exista como booleano y lo retorna."""
    if key not in st.session_state:
        st.session_state[key] = default
    st.session_state[key] = bool(st.session_state[key])
    return bool(st.session_state[key])


def _ensure_int_step_state(key: str, min_v: int, max_v: int, step: int, default: int) -> int:
    """Normaliza un entero en session_state con lÃ­mites y step."""
    v = st.session_state.get(key, default)
    try:
        if isinstance(v, (list, tuple)):
            v = v[0]
        v = int(v)
    except Exception:
        v = default
    v = max(min_v, min(max_v, v))
    v = min_v + round((v - min_v) / step) * step
    v = max(min_v, min(max_v, v))
    st.session_state[key] = v
    return v


def _swap(lst, i, j):
    """Intercambia dos posiciones de una lista (sin mutar el original)."""
    items = list(lst)
    if 0 <= i < len(items) and 0 <= j < len(items):
        items[i], items[j] = items[j], items[i]
    return items


def _ui_toast(msg: str, icon: str | None = None):
    """Toast seguro si la versiÃ³n de Streamlit lo soporta."""
    if hasattr(st, "toast"):
        try:
            st.toast(msg, icon=icon)
        except Exception as exc:
            logger.debug("toast no disponible: %s", exc)


# --- COMPONENTES BASE ---


def help_section(key: str, title: str, body_md: str):
    """Ayuda contextual reusable en expander."""
    with st.expander(f"Ayuda: {title}", expanded=False):
        st.markdown(body_md)


def page_header(
    title: str,
    subtitle: str | None = None,
    right_actions: list | None = None,
    context_badges: list | None = None,
):
    """Header de pÃ¡gina con acciones y badges opcionales."""
    right_actions = right_actions or []
    context_badges = context_badges or []
    st.markdown('<div class="vg-card vg-page-header">', unsafe_allow_html=True)
    left, right = st.columns([0.72, 0.28])
    with left:
        st.markdown(f"<div class='vg-page-title'>{html.escape(title)}</div>", unsafe_allow_html=True)
        if subtitle:
            st.markdown(f"<p class='vg-page-subtitle'>{html.escape(subtitle)}</p>", unsafe_allow_html=True)
        if context_badges:
            st.markdown("<div class='vg-badges'>", unsafe_allow_html=True)
            for badge in context_badges:
                if isinstance(badge, str):
                    st.markdown(badge, unsafe_allow_html=True)
                else:
                    st.write(badge)
            st.markdown("</div>", unsafe_allow_html=True)
    with right:
        for action in right_actions:
            if isinstance(action, str):
                st.markdown(action, unsafe_allow_html=True)
            else:
                st.write(action)
    st.markdown("</div>", unsafe_allow_html=True)


def _vh_to_px(vh: int) -> int:
    """ConversiÃ³n aproximada de vh a px (Streamlit no expone viewport real)."""
    return int(vh * 7.2)


def render_grid(
    df,
    *,
    key: str,
    height_vh: int = 65,
    editable: bool = False,
    selection_mode: str | None = None,
    column_config: dict | None = None,
    hide_index: bool = True,
):
    """Grilla simple con altura controlada y soporte opcional de selecciÃ³n."""
    kw = {"width": "stretch", "hide_index": hide_index, "height": _vh_to_px(height_vh)}
    if column_config:
        kw["column_config"] = column_config
    if selection_mode:
        kw.update(_df_select_kwargs())
    if editable:
        return st.data_editor(df, key=f"{key}_ed", **kw)
    return st.dataframe(df, key=f"{key}_df", **kw)


def section(title: str, help_text: str | None = None):
    """SecciÃ³n con encabezado; devuelve el contenedor para contexto."""
    st.markdown(f"<div class='vg-section-title'>{html.escape(title)}</div>", unsafe_allow_html=True)
    if help_text:
        help_section(f"sec_{title.lower().replace(' ', '_')}", title, help_text)
    return st.container()


def section_header(title: str, subtitle: str | None = None, meta: list[str] | None = None):
    """Header compacto de sección."""
    st.markdown(
        f"""
<div class="vg-section-head">
  <div class="vg-section-title">{html.escape(title)}</div>
  {f'<div class="vg-section-subtitle">{html.escape(subtitle)}</div>' if subtitle else ''}
  {f'<div class="vg-badges">{" · ".join(html.escape(m) for m in meta)}</div>' if meta else ''}
</div>
""",
        unsafe_allow_html=True,
    )


def start_ui_block_order(route: str) -> None:
    route_key = str(route or "").strip().lower() or "unknown"
    st.session_state[f"{SESSION_BLOCK_ORDER_PREFIX}{route_key}"] = []


def mark_ui_block(route: str, block_id: Literal["summary", "actions", "work"]) -> None:
    route_key = str(route or "").strip().lower() or "unknown"
    key = f"{SESSION_BLOCK_ORDER_PREFIX}{route_key}"
    seq = st.session_state.get(key)
    if not isinstance(seq, list):
        seq = []
    seq.append(str(block_id))
    st.session_state[key] = seq


def render_module_frame(
    route: str,
    summary: Callable[[], None],
    actions: Callable[[], None],
    work: Callable[[], None],
) -> None:
    """
    Contrato estructural estable de módulo:
    Resumen -> Acciones -> Trabajo.
    """
    safe_route = html.escape(str(route or "modulo").strip().lower())
    start_ui_block_order(route)
    st.markdown(f"<div class='vg-module-frame vg-module-{safe_route}'>", unsafe_allow_html=True)

    mark_ui_block(route, "summary")
    st.markdown("<div class='vg-module-block vg-block-summary'>", unsafe_allow_html=True)
    summary()
    st.markdown("</div>", unsafe_allow_html=True)

    mark_ui_block(route, "actions")
    st.markdown("<div class='vg-module-block vg-block-actions'>", unsafe_allow_html=True)
    actions()
    st.markdown("</div>", unsafe_allow_html=True)

    mark_ui_block(route, "work")
    st.markdown("<div class='vg-module-block vg-block-work'>", unsafe_allow_html=True)
    work()
    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("</div>", unsafe_allow_html=True)


MODE_LABELS = {"listado": "Listado", "detalle": "Detalle", "editar": "Editar"}


def mode_tabs(current_mode: str, enabled_modes: list | None = None, key: str = "mode_tabs") -> str:
    """Pills de modo: Listado / Detalle / Editar. Retorna el modo seleccionado."""
    enabled_modes = enabled_modes or ["listado", "detalle", "editar"]
    if current_mode not in enabled_modes:
        current_mode = enabled_modes[0]
    labels = [MODE_LABELS.get(m, m) for m in enabled_modes]
    idx = enabled_modes.index(current_mode) if current_mode in enabled_modes else 0
    selected_label = st.radio(
        "Modo",
        labels,
        index=idx,
        horizontal=True,
        key=key,
        label_visibility="collapsed",
    )
    selected_mode = enabled_modes[labels.index(selected_label)]
    if selected_mode != st.session_state.get("route_mode"):
        st.session_state["route_mode"] = selected_mode
    return selected_mode


def vg_section(title: str, subtitle: str | None = None):
    """Header visual de modulo con jerarquia estable."""
    section_header(title, subtitle=subtitle)


def vg_toolbar(
    options: list[tuple[str, str]],
    current: str,
    *,
    key: str,
    label: str = "Seccion",
) -> str:
    """Barra primaria de navegacion para modulo Gestion."""
    if not options:
        return ""
    valid_values = [value for value, _ in options]
    label_map = {value: text for value, text in options}
    reverse_map = {text: value for value, text in options}
    selected_value = current if current in label_map else valid_values[0]
    label_key = f"{key}.label"
    default_label = label_map[selected_value]
    if st.session_state.get(label_key) not in reverse_map:
        st.session_state[label_key] = default_label

    st.markdown('<div class="vg-toolbar">', unsafe_allow_html=True)
    selected_label = st.radio(
        label,
        [label_map[value] for value in valid_values],
        key=label_key,
        horizontal=True,
        label_visibility="collapsed",
    )
    st.markdown("</div>", unsafe_allow_html=True)
    return reverse_map.get(selected_label, selected_value)


def vg_modebar(
    options: list[tuple[str, str]],
    current: str,
    *,
    key: str,
    label: str = "Modo",
) -> str:
    """Barra secundaria de modos (Listado/Detalle/Editar)."""
    if not options:
        return ""
    valid_values = [value for value, _ in options]
    label_map = {value: text for value, text in options}
    reverse_map = {text: value for value, text in options}
    selected_value = current if current in label_map else valid_values[0]
    label_key = f"{key}.label"
    default_label = label_map[selected_value]
    if st.session_state.get(label_key) not in reverse_map:
        st.session_state[label_key] = default_label

    st.markdown('<div class="vg-modebar">', unsafe_allow_html=True)
    selected_label = st.radio(
        label,
        [label_map[value] for value in valid_values],
        key=label_key,
        horizontal=True,
        label_visibility="collapsed",
    )
    st.markdown("</div>", unsafe_allow_html=True)
    return reverse_map.get(selected_label, selected_value)


def vg_empty_state(
    message: str,
    action_label: str,
    action_cb,
    *,
    key: str | None = None,
):
    """Empty state explicito con CTA trazable."""
    safe_msg = message.strip() or "Sin datos disponibles."
    digest = hashlib.md5(safe_msg.encode("utf-8")).hexdigest()[:10]
    btn_key = key or f"vg.empty.{digest}"
    st.markdown('<div class="vg-empty-state">', unsafe_allow_html=True)
    st.info(safe_msg)
    if st.button(action_label, key=btn_key, width="stretch", type="secondary"):
        action_cb()
    st.markdown("</div>", unsafe_allow_html=True)


def empty_state_nav(
    title: str,
    body: str,
    cta_label: str | None = None,
    cta_module: str | None = None,
    cta_mode: str = "listado",
):
    """Estado vacÃ­o con CTA opcional que navega usando nav.navigate_to."""
    st.info(f"**{title}**\n\n{body}")
    if cta_label and cta_module:
        if st.button(cta_label, width="stretch", key=f"es_cta_{cta_module}"):
            from nav import navigate_to

            route_map = {
                "panel": "Dashboard",
                "casos": "Gestion",
                "cliente": "Gestion",
                "agenda": "Agenda",
                "finanzas": "Finanzas",
            }
            navigate_to(route_map.get(cta_module, "Dashboard"), cta_mode)


def grid_shell(title: str, subtitle: str | None = None, fluid: bool = True):
    """Wrapper para vistas de listado."""
    if fluid:
        st.markdown("<style>.main .block-container { max-width: 100% !important; }</style>", unsafe_allow_html=True)
    page_header(title, subtitle=subtitle)


def detail_shell(title: str, badges: list | None = None):
    """Wrapper para vistas de detalle."""
    page_header(title, context_badges=badges or [])


def edit_shell(title: str, steps: list[str], current_step: int, key: str = "edit_wizard") -> int:
    """Wizard por pasos; retorna el Ã­ndice seleccionado."""
    page_header(title, subtitle=f"Paso {current_step + 1} de {len(steps)}")
    selected = st.radio(
        "Paso",
        steps,
        index=current_step,
        horizontal=True,
        key=key,
        label_visibility="collapsed",
    )
    return steps.index(selected) if selected in steps else current_step


def kpi_card(label: str, value, status: str | None = None, tone: str = "neutral", delta: str | None = None):
    """KPI compacto; usa st.metric con estilo global."""
    st.metric(label, value, delta if delta is not None else status)


def progress_row(label: str, pct: float):
    """Barra de progreso simple con etiqueta."""
    pct = max(0, min(100, pct))
    st.write(f"{label}: {pct:.0f}%")
    st.progress(pct / 100)


def audit_status_badge(errores: int, warnings: int):
    """Badge de estado para auditorÃ­a."""
    if errores == 0 and warnings == 0:
        txt = "Ã“ptimo Â· Sin problemas detectados"
        variant = "ok"
    elif errores > 0:
        txt = f"Errores: {errores} Â· Advertencias: {warnings}"
        variant = "danger"
    else:
        txt = f"Advertencias: {warnings}"
        variant = "warn"
    st.markdown(
        f"<span class='vg-badge vg-badge-{variant}'>{html.escape(txt)}</span>",
        unsafe_allow_html=True,
    )


def card_begin(title: str | None = None, subtitle: str | None = None, variant: str = "default"):
    """Abre un contenedor tipo tarjeta; debe cerrarse con card_end()."""
    classes = ["vg-card"]
    if variant == "tight":
        classes.append("tight")
    st.markdown(f"<div class=\"{' '.join(classes)}\">", unsafe_allow_html=True)
    if title:
        st.markdown(f"<div class='vg-card-title'>{html.escape(str(title))}</div>", unsafe_allow_html=True)
    if subtitle:
        st.markdown(f"<p class='vg-card-subtitle'>{html.escape(str(subtitle))}</p>", unsafe_allow_html=True)


def card_end():
    """Cierra un contenedor abierto con card_begin()."""
    st.markdown("</div>", unsafe_allow_html=True)


def pill(text: str, kind: str = "default"):
    """Renderiza una pill bÃ¡sica."""
    safe_kind = "".join(ch for ch in (kind or "").lower() if ch.isalnum() or ch in ("-", "_"))
    classes = ["vg-pill"]
    if safe_kind in {"danger", "warn", "ok"}:
        classes.append(f"variant-{safe_kind}")
    st.markdown(
        f"<span class=\"{' '.join(classes)}\">{html.escape(str(text))}</span>",
        unsafe_allow_html=True,
    )


def ui_centro_ayuda_content():
    """Contenido del centro de ayuda (versiÃ³n breve)."""
    tab1, tab2, tab3, tab4 = st.tabs(["Uso bÃ¡sico", "Planilla", "Carpetas", "Problemas tÃ­picos"])
    with tab1:
        st.markdown("**Flujo recomendado:**\n1) Gestion > Casos > seleccionar un caso.\n2) Completar Responsable / Tarea / Fecha.\n3) Usar Agenda para priorizar.")
    with tab2:
        st.markdown("Atajos: priorizar urgentes, prÃ³ximos 7/30 dÃ­as, vista tarjetas.")
    with tab3:
        st.markdown("Estructura estÃ¡ndar por caso: 01.PRUEBA / 02.ESCRITOS / 03.RECIBOS / 04.OTROS.")
    with tab4:
        st.markdown("Tips OneDrive/Windows: evitar rutas largas, carpetas fantasma, normalizar UTF-8.")


def open_path(path: Path | str | None, container: "st.container | None" = None) -> bool:
    """Abre archivo/carpeta de forma segura; muestra mensajes si no es posible."""
    target = container or st
    if path is None:
        target.info("No hay carpeta fÃ­sica asociada.")
        return False
    path = Path(path)
    if str(path).startswith("db://"):
        target.info(f"Este caso estÃ¡ en base de datos.\n\nID: `{str(path).replace('db://cases/', '')}`")
        return False
    if not path.exists():
        target.error(f"Ruta no encontrada: `{path}`")
        return False
    if os.name == "nt":
        try:
            os.startfile(str(path))
            return True
        except Exception as exc:
            target.error(f"No se pudo abrir: {exc}")
            return False
    target.info(f"Ruta: `{path}`")
    return False


# --- CONFIGURACION BASE ---


def configurar_pagina():
    """Configura Streamlit y prepara el tema Stitch."""
    try:
        st.set_page_config(
            page_title="VACA & GENTILE ERP v1.0",
            page_icon="⚖️",
            layout="wide",
            initial_sidebar_state="expanded",
        )
    except Exception:
        # Streamlit lanza excepciÃ³n si set_page_config ya fue invocado; mantener idempotencia.
        logger.debug("set_page_config ya estaba inicializado")
    inicializar_ui()


# --- INYECCIÃ“N DE CSS (CORE) ---


def aplicar_estilos_stitch():
    """Inyecta CSS global y unifica la experiencia claro/oscuro de toda la app."""
    inicializar_ui()
    theme_by_label = {label: key for key, label in THEME_OPTIONS.items()}
    density_by_label = {label: key for key, label in DENSITY_OPTIONS.items()}

    theme_mode = st.session_state.get(SESSION_THEME_KEY, _default_theme_mode())
    density_mode = st.session_state.get(SESSION_DENSITY_KEY, _default_density_mode())
    if theme_mode not in THEME_OPTIONS:
        theme_mode = _default_theme_mode()
    if density_mode not in DENSITY_OPTIONS:
        density_mode = _default_density_mode()

    theme_opts = list(theme_by_label.keys())
    density_opts = list(density_by_label.keys())
    theme_default_idx = theme_opts.index(THEME_OPTIONS.get(theme_mode, "Oscuro"))
    density_default_idx = density_opts.index(DENSITY_OPTIONS.get(density_mode, "Compacta"))

    with st.sidebar:
        st.markdown('<div class="vg-theme-toggle">', unsafe_allow_html=True)
        theme_label = st.radio(
            "Tema",
            theme_opts,
            index=theme_default_idx,
            key="stitch_theme_selector",
            label_visibility="collapsed",
        )
        st.session_state[SESSION_THEME_KEY] = theme_by_label.get(theme_label, _default_theme_mode())
        st.markdown("</div>", unsafe_allow_html=True)
        st.markdown('<div class="vg-density-toggle">', unsafe_allow_html=True)
        density_label = st.radio(
            "Densidad",
            density_opts,
            index=density_default_idx,
            key="stitch_density_selector",
            label_visibility="collapsed",
            horizontal=True,
        )
        st.session_state[SESSION_DENSITY_KEY] = density_by_label.get(density_label, _default_density_mode())
        st.markdown("</div>", unsafe_allow_html=True)

    _persist_ui_preferences_if_possible(
        st.session_state.get(SESSION_THEME_KEY, _default_theme_mode()),
        st.session_state.get(SESSION_DENSITY_KEY, _default_density_mode()),
    )

    t = get_current_theme()
    ty = TOKENS["typography"]
    density_cfg = {
        "compact": {"container_max": "1680px", "pad_top": "0.9rem", "pad_bottom": "1.8rem", "input_h": "36px"},
        "balanced": {"container_max": "1540px", "pad_top": "1.1rem", "pad_bottom": "2.0rem", "input_h": "40px"},
        "wide": {"container_max": "1460px", "pad_top": "1.3rem", "pad_bottom": "2.2rem", "input_h": "44px"},
    }.get(st.session_state.get(SESSION_DENSITY_KEY, _default_density_mode()), {
        "container_max": "1680px",
        "pad_top": "0.9rem",
        "pad_bottom": "1.8rem",
        "input_h": "36px",
    })

    st.markdown(
        """
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&family=IBM+Plex+Sans:wght@400;500;600&display=swap');
        @import url('https://fonts.googleapis.com/icon?family=Material+Symbols+Rounded');
        </style>
    """,
        unsafe_allow_html=True,
    )

    css = """
    <style>
        :root {{
            --vg-bg: {bg_app};
            --vg-sidebar: {bg_sidebar};
            --vg-surface: {bg_card};
            --vg-surface-2: {bg_card_hover};
            --vg-bg-glow-1: {bg_glow_1};
            --vg-bg-glow-2: {bg_glow_2};
            --vg-border: {border};
            --vg-text: {text_main};
            --vg-muted: {text_muted};
            --vg-primary: {primary};
            --vg-primary-strong: {primary_hover};
            --vg-success: {success};
            --vg-warning: {warning};
            --vg-danger: {danger};
            --vg-badge: {badge_bg};
            --vg-font: {font_family};
            --vg-h1: {h1};
            --vg-h2: {h2};
            --vg-body: {body};
            --vg-small: {small};
            --vg-radius-sm: {radius_sm};
            --vg-radius-md: {radius_md};
            --vg-radius-lg: {radius_lg};
            --vg-radius-full: {radius_full};
            --vg-shadow-card: {shadow_card};
            --vg-shadow-glow: {shadow_glow};
            --muted: var(--vg-muted);
        }}

        body, .stApp {{
            background:
                radial-gradient(920px 520px at 6% -6%, var(--vg-bg-glow-1), transparent 60%),
                radial-gradient(860px 460px at 94% -2%, var(--vg-bg-glow-2), transparent 58%),
                linear-gradient(180deg, var(--vg-bg), var(--vg-bg));
            color: var(--vg-text);
            font-family: var(--vg-font);
        }}
        .stMarkdown {{
            color: var(--vg-text);
        }}

        .main .block-container {{
            padding-top: {container_pad_top};
            padding-bottom: {container_pad_bottom};
            max-width: {container_max_width};
        }}

        section[data-testid="stSidebar"] {{
            background: var(--vg-sidebar);
            border-right: 1px solid var(--vg-border);
            color: var(--vg-text);
        }}
        section[data-testid="stSidebar"] .block-container {{
            padding-top: 1.5rem;
        }}
        section[data-testid="stSidebar"] p {{
            color: var(--vg-text);
        }}
        section[data-testid="stSidebar"] span,
        section[data-testid="stSidebar"] label,
        section[data-testid="stSidebar"] [data-testid="stWidgetLabel"] {{
            color: var(--vg-text) !important;
        }}
        section[data-testid="stSidebar"] small,
        section[data-testid="stSidebar"] .stCaption,
        section[data-testid="stSidebar"] [data-testid="stCaptionContainer"] {{
            color: var(--vg-muted) !important;
        }}

        h1, h2, h3, h4, h5, h6 {{
            color: var(--vg-text) !important;
            font-weight: 700 !important;
            margin-bottom: 0.35rem;
        }}
        .stMarkdown p,
        [data-testid="stCaptionContainer"],
        .stCaption,
        .stHelp,
        small {{
            color: var(--vg-muted) !important;
        }}
        [data-testid="stWidgetLabel"] {{
            color: var(--vg-muted) !important;
            font-weight: 600 !important;
        }}

        /* Botones */
        .stButton > button,
        .stDownloadButton > button {{
            background: linear-gradient(135deg, var(--vg-primary), var(--vg-primary-strong));
            color: #fff !important;
            border: 1px solid transparent;
            border-radius: var(--vg-radius-md);
            padding: 0.55rem 1rem;
            font-weight: 600;
            box-shadow: none;
            transition: all 0.2s ease;
        }}
        .stButton > button:hover,
        .stDownloadButton > button:hover {{
            box-shadow: var(--vg-shadow-glow);
            transform: translateY(-1px);
        }}
        .stButton > button *,
        .stDownloadButton > button * {{
            color: #fff !important;
            fill: #fff !important;
        }}
        section[data-testid="stSidebar"] .stButton > button,
        section[data-testid="stSidebar"] .stDownloadButton > button {{
            color: #fff !important;
        }}
        section[data-testid="stSidebar"] .stButton > button *,
        section[data-testid="stSidebar"] .stDownloadButton > button * {{
            color: #fff !important;
            fill: #fff !important;
        }}
        button[data-testid="baseButton-secondary"] {{
            background: transparent !important;
            color: var(--vg-text) !important;
            border: 1px solid var(--vg-border) !important;
        }}
        button[data-testid="baseButton-secondary"]:hover {{
            color: var(--vg-primary) !important;
            border-color: var(--vg-primary) !important;
            box-shadow: var(--vg-shadow-glow);
        }}
        button[data-testid="baseButton-secondary"] *, button[data-testid="baseButton-secondary"] svg {{
            color: var(--vg-text) !important;
            fill: var(--vg-text) !important;
        }}
        section[data-testid="stSidebar"] .stButton > button p,
        section[data-testid="stSidebar"] .stButton > button span {{
            color: #fff !important;
        }}

        /* Inputs */
        .stTextInput input, .stSelectbox div[data-baseweb="select"] > div, .stDateInput input, textarea, .stNumberInput input {{
            background: var(--vg-surface-2) !important;
            color: var(--vg-text) !important;
            border: 1px solid var(--vg-border) !important;
            border-radius: var(--vg-radius-md) !important;
            box-shadow: none !important;
        }}
        .stTextInput input:focus, .stSelectbox div[data-baseweb="select"] > div:focus, .stDateInput input:focus, textarea:focus, .stNumberInput input:focus {{
            border-color: var(--vg-primary) !important;
            box-shadow: 0 0 0 2px rgba(59,130,246,0.25) !important;
            outline: none !important;
        }}
        .stButton > button:focus-visible, .stDownloadButton > button:focus-visible {{
            outline: none !important;
            box-shadow: var(--vg-shadow-glow);
        }}
        .stTextInput input::placeholder, textarea::placeholder, .stDateInput input::placeholder {{
            color: var(--vg-muted) !important;
            opacity: 0.6;
        }}
        .stSelectbox div[data-baseweb="select"] svg {{
            color: var(--vg-muted);
        }}
        label {{
            color: var(--vg-muted) !important;
            font-weight: 600 !important;
            margin-bottom: 4px !important;
        }}

        /* Metrics */
        [data-testid="stMetricValue"] {{
            color: var(--vg-text);
            font-weight: 700;
        }}
        [data-testid="stMetricLabel"] {{
            color: var(--vg-muted);
        }}

        /* Tabs / radios */
        .stTabs [role="tablist"] button, div[role="radiogroup"] > label {{
            background: var(--vg-surface-2);
            color: var(--vg-muted);
            border: 1px solid var(--vg-border);
            border-radius: var(--vg-radius-full);
            padding: 0.35rem 0.9rem;
            margin-right: 0.35rem;
            transition: all 0.2s ease;
        }}
        .stTabs [aria-selected="true"] {{
            background: var(--vg-primary);
            color: var(--vg-text);
            border-color: var(--vg-primary-strong);
            box-shadow: var(--vg-shadow-glow);
        }}
        div[role="radiogroup"] > label[data-checked="true"] {{
            background: var(--vg-primary);
            color: #fff;
            border-color: var(--vg-primary-strong);
            box-shadow: var(--vg-shadow-glow);
        }}
        /* Theme toggle segmented */
        .vg-theme-toggle div[role="radiogroup"] > label {{
            background: var(--vg-surface-2);
            color: var(--vg-text) !important;
            border: 1px solid var(--vg-border);
            border-radius: var(--vg-radius-full);
            padding: 0.4rem 1rem;
            margin-right: 0.35rem;
            font-weight: 600;
        }}
        .vg-theme-toggle div[role="radiogroup"] > label:hover {{
            background: var(--vg-surface);
        }}
        .vg-theme-toggle div[role="radiogroup"] > label[data-checked="true"] {{
            background: var(--vg-primary);
            color: #fff !important;
            border-color: var(--vg-primary-strong);
            box-shadow: var(--vg-shadow-glow);
        }}
        .vg-theme-toggle div[role="radiogroup"] label > div:first-child {{
            display: none !important;
        }}
        .vg-density-toggle {{
            margin: 4px 0 10px;
        }}
        .vg-density-toggle div[role="radiogroup"] > label {{
            background: var(--vg-surface-2);
            color: var(--vg-text) !important;
            border: 1px solid var(--vg-border);
            border-radius: var(--vg-radius-full);
            padding: 0.35rem 0.9rem;
            margin-right: 0.3rem;
            font-weight: 600;
        }}
        .vg-density-toggle div[role="radiogroup"] > label[data-checked="true"] {{
            background: var(--vg-primary);
            color: #fff !important;
            border-color: var(--vg-primary-strong);
            box-shadow: var(--vg-shadow-glow);
        }}
        .vg-density-toggle div[role="radiogroup"] label > div:first-child {{
            display: none !important;
        }}
        /* Radios/checkbox as pills */
        div[data-baseweb="checkbox"] {{
            background: var(--vg-surface-2);
            border: 1px solid var(--vg-border);
            border-radius: var(--vg-radius-md);
            padding: 6px 10px;
        }}
        div[data-baseweb="checkbox"][aria-checked="true"] {{
            border-color: var(--vg-primary);
            box-shadow: var(--vg-shadow-glow);
        }}
        div[data-baseweb="checkbox"] label {{
            color: var(--vg-text);
            font-weight: 600;
        }}

        /* Expander */
        [data-testid="stExpander"] {{
            background: var(--vg-surface);
            border: 1px solid var(--vg-border);
            border-radius: var(--vg-radius-md);
            color: var(--vg-text);
            padding: 8px 10px;
        }}
        [data-testid="stExpander"] summary {{
            color: var(--vg-text);
            font-weight: 700;
        }}

        /* Dataframes */
        div[data-testid="stDataFrame"], div[data-testid="stDataEditor"] {{
            background: var(--vg-surface);
            border: 1px solid var(--vg-border);
            border-radius: var(--vg-radius-lg);
            padding: 0.5rem;
            box-shadow: var(--vg-shadow-card);
        }}
        div[data-testid="stDataFrame"] thead, div[data-testid="stDataEditor"] thead {{
            background: var(--vg-surface-2);
        }}
        div[data-testid="stDataFrame"] table, div[data-testid="stDataEditor"] table {{
            color: var(--vg-text);
        }}

        /* Progress */
        div[data-testid="stProgress"] > div {{
            background: var(--vg-surface-2) !important;
            border-radius: var(--vg-radius-full) !important;
        }}
        div[data-testid="stProgress"] > div > div {{
            background: var(--vg-primary) !important;
            border-radius: var(--vg-radius-full) !important;
        }}

        /* Alertas */
        .stAlert {{
            border-radius: var(--vg-radius-md);
            border: 1px solid var(--vg-border);
            box-shadow: var(--vg-shadow-card);
        }}

        /* Componentes Stitch */
        .vg-card {{
            background: var(--vg-surface);
            border: 1px solid var(--vg-border);
            border-radius: var(--vg-radius-lg);
            padding: 16px;
            margin-bottom: 16px;
            box-shadow: var(--vg-shadow-card);
        }}
        .vg-card.tight {{
            padding: 12px 14px;
        }}
        .vg-card-title {{ font-size: 1rem; color: var(--vg-text); font-weight: 700; }}
        .vg-card-subtitle {{ color: var(--vg-muted); margin-top: 2px; }}

        .vg-page-header {{
            display: flex;
            align-items: flex-start;
            justify-content: space-between;
            gap: 12px;
        }}
        .vg-page-title {{ font-size: var(--vg-h2); font-weight: 700; color: var(--vg-text); line-height: 1.1; }}
        .vg-page-subtitle {{ color: var(--vg-muted); margin: 2px 0 8px; }}
        .vg-badges {{ display: flex; flex-wrap: wrap; gap: 6px; }}
        .vg-page-header > div:last-child {{ display:flex; flex-direction:column; gap:8px; align-items:flex-end; }}

        .vg-section-head {{ margin: 6px 0 10px; }}
        .vg-section-title {{ font-size: 1.05rem; font-weight: 700; color: var(--vg-text); }}
        .vg-section-subtitle {{ color: var(--vg-muted); font-size: 0.95rem; }}

        .vg-pill {{
            display: inline-flex;
            align-items: center;
            gap: 6px;
            padding: 4px 10px;
            border-radius: var(--vg-radius-full);
            border: 1px solid var(--vg-border);
            background: var(--vg-badge);
            color: var(--vg-text);
            font-weight: 600;
            font-size: 12px;
        }}
        .vg-pill.variant-warn {{ border-color: rgba(245,158,11,0.35); color: var(--vg-warning); }}
        .vg-pill.variant-danger {{ border-color: rgba(239,68,68,0.35); color: var(--vg-danger); }}
        .vg-pill.variant-ok {{ border-color: rgba(16,185,129,0.35); color: var(--vg-success); }}

        .vg-badge {{
            display: inline-flex;
            align-items: center;
            padding: 6px 10px;
            border-radius: var(--vg-radius-full);
            font-size: 12px;
            font-weight: 700;
            background: var(--vg-badge);
            border: 1px solid var(--vg-border);
            color: var(--vg-text);
        }}
        .vg-badge-ok {{ color: var(--vg-success); border-color: rgba(16,185,129,0.35); background: rgba(16,185,129,0.12); }}
        .vg-badge-warn {{ color: var(--vg-warning); border-color: rgba(245,158,11,0.35); background: rgba(245,158,11,0.12); }}
        .vg-badge-danger {{ color: var(--vg-danger); border-color: rgba(239,68,68,0.35); background: rgba(239,68,68,0.12); }}

        .vg-toolbar {{
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 10px;
            padding: 10px 14px;
            border: 1px solid var(--vg-border);
            border-radius: var(--vg-radius-lg);
            background: linear-gradient(135deg, rgba(255,255,255,0.02), rgba(59,130,246,0.05));
            margin-bottom: 10px;
        }}
        .vg-toolbar .title {{ color: var(--vg-text); font-weight: 700; }}
        .vg-modebar {{
            margin: 2px 0 12px;
        }}
        .vg-empty-state {{
            margin: 10px 0 14px;
        }}

        /* Separadores / hr */
        hr, .stDivider {{
            border-color: var(--vg-border) !important;
            opacity: 0.35;
        }}
        hr:empty, .stDivider:empty {{
            display: none !important;
        }}

        /* Tabla estrecha en mobile */
        @media (max-width: 780px) {{
            .main .block-container {{ padding: 0.75rem; }}
            .vg-page-header {{ flex-direction: column; }}
        }}
    </style>
    """.format(
        bg_app=t["bg_app"],
        bg_sidebar=t["bg_sidebar"],
        bg_card=t["bg_card"],
        bg_card_hover=t["bg_card_hover"],
        border=t["border"],
        text_main=t["text_main"],
        text_muted=t["text_muted"],
        primary=t["primary"],
        primary_hover=t["primary_hover"],
        success=t["success"],
        warning=t["warning"],
        danger=t["danger"],
        badge_bg=t["badge_bg"],
        bg_glow_1=t["bg_glow_1"],
        bg_glow_2=t["bg_glow_2"],
        font_family=ty["font_family"],
        h1=ty["h1"],
        h2=ty["h2"],
        body=ty["body"],
        small=ty["small"],
        radius_sm=TOKENS["radius"]["sm"],
        radius_md=TOKENS["radius"]["md"],
        radius_lg=TOKENS["radius"]["lg"],
        radius_full=TOKENS["radius"]["full"],
        shadow_card=TOKENS["shadows"]["card"],
        shadow_glow=TOKENS["shadows"]["glow"],
        container_max_width=density_cfg["container_max"],
        container_pad_top=density_cfg["pad_top"],
        container_pad_bottom=density_cfg["pad_bottom"],
    )
    st.markdown(css, unsafe_allow_html=True)

    # Capa de refinamiento visual para ordenar todos los modulos con el mismo shell.
    st.markdown(
        f"""
        <style>
        .stApp {
            background-attachment: fixed;
        }

        .main .block-container {
            max-width: {density_cfg['container_max']};
            padding-top: {density_cfg['pad_top']};
            padding-bottom: {density_cfg['pad_bottom']};
        }
        .vg-workspace-shell {
            display: flex;
            flex-direction: column;
            gap: 0.8rem;
            margin-bottom: 0.4rem;
        }
        .vg-module-frame {
            display: flex;
            flex-direction: column;
            gap: 0.7rem;
        }
        .vg-module-block {
            display: block;
        }
        .vg-block-summary {
            order: 1;
        }
        .vg-block-actions {
            order: 2;
        }
        .vg-block-work {
            order: 3;
        }
        .vg-workspace-shell .stMarkdown p {
            line-height: 1.38;
        }
        [data-testid="stCaptionContainer"],
        .stCaption {
            font-size: 0.86rem;
            line-height: 1.35;
        }

        section[data-testid="stSidebar"] {
            background: linear-gradient(
                180deg,
                color-mix(in srgb, var(--vg-sidebar), #ffffff 0%),
                color-mix(in srgb, var(--vg-sidebar), #000000 8%)
            );
            box-shadow: inset -1px 0 0 rgba(255, 255, 255, 0.06);
        }
        section[data-testid="stSidebar"] .block-container {
            padding-top: 0.75rem;
        }

        .stButton > button,
        .stDownloadButton > button {
            border-radius: var(--vg-radius-md);
            font-weight: 650;
            letter-spacing: 0.01em;
            transition: transform .18s ease, box-shadow .18s ease, border-color .18s ease;
        }
        button[data-testid="baseButton-primary"] {
            background: linear-gradient(135deg, var(--vg-primary), var(--vg-primary-strong)) !important;
            color: #ffffff !important;
            box-shadow: 0 8px 18px color-mix(in srgb, var(--vg-primary), transparent 72%);
        }
        button[data-testid="baseButton-primary"]:hover {
            transform: translateY(-1px);
            box-shadow: var(--vg-shadow-glow);
        }
        button[data-testid="baseButton-secondary"] {
            background: color-mix(in srgb, var(--vg-surface-2), transparent 10%) !important;
            border: 1px solid var(--vg-border) !important;
            color: var(--vg-text) !important;
        }
        button[data-testid="baseButton-secondary"]:hover {
            border-color: color-mix(in srgb, var(--vg-primary), #fff 20%) !important;
            color: var(--vg-primary) !important;
        }
        .stButton > button:disabled,
        .stDownloadButton > button:disabled {
            opacity: 0.52 !important;
            filter: saturate(0.8);
            cursor: not-allowed !important;
        }

        .stTextInput input,
        .stDateInput input,
        .stNumberInput input,
        .stTextArea textarea,
        .stSelectbox div[data-baseweb="select"] > div {
            min-height: {density_cfg['input_h']};
            background: color-mix(in srgb, var(--vg-surface-2), transparent 14%) !important;
        }
        .stTextInput input:focus,
        .stDateInput input:focus,
        .stNumberInput input:focus,
        .stTextArea textarea:focus,
        .stSelectbox div[data-baseweb="select"] > div:focus {
            border-color: color-mix(in srgb, var(--vg-primary), #fff 14%) !important;
            box-shadow: 0 0 0 3px color-mix(in srgb, var(--vg-primary), transparent 75%) !important;
        }

        .vg-theme-toggle {
            margin: 4px 0 10px;
        }
        .vg-theme-toggle div[role="radiogroup"] > label {
            min-height: 34px;
            padding: 0.42rem 1rem;
        }

        .vg-sidebar-brand {
            padding: 12px 10px 8px;
            border-bottom: 1px solid var(--vg-border);
            margin-bottom: 4px;
        }
        .vg-sidebar-title {
            margin: 0;
            font-size: 15px;
            font-weight: 800;
            letter-spacing: .02em;
            color: var(--vg-text);
        }
        .vg-sidebar-subtitle {
            margin: 4px 0 0;
            font-size: 11px;
            color: var(--vg-muted);
        }

        .vg-shell-header {
            border: 1px solid var(--vg-border);
            border-radius: var(--vg-radius-lg);
            background: linear-gradient(
                180deg,
                color-mix(in srgb, var(--vg-surface), transparent 0%),
                color-mix(in srgb, var(--vg-surface-2), transparent 28%)
            );
            box-shadow: var(--vg-shadow-card);
            padding: 14px 16px;
            margin-bottom: 8px;
        }
        .vg-shell-top {
            display: flex;
            justify-content: space-between;
            align-items: center;
            gap: 12px;
            flex-wrap: wrap;
        }
        .vg-shell-brand {
            color: var(--vg-primary);
            font-size: 1.16rem;
            font-weight: 800;
            letter-spacing: .01em;
        }
        .vg-shell-version {
            font-size: 11px;
            color: var(--vg-muted);
        }
        .vg-shell-meta {
            display: flex;
            gap: 6px;
            flex-wrap: wrap;
            margin-top: 8px;
        }
        .vg-shell-meta-item {
            display: inline-flex;
            align-items: center;
            border: 1px solid var(--vg-border);
            border-radius: var(--vg-radius-full);
            background: var(--vg-badge);
            color: var(--vg-text);
            font-size: 12px;
            font-weight: 650;
            padding: 5px 10px;
            letter-spacing: .01em;
        }
        .vg-shell-meta-item.ok {
            color: var(--vg-success);
            border-color: color-mix(in srgb, var(--vg-success), #fff 42%);
        }
        .vg-shell-meta-item.warn {
            color: var(--vg-warning);
            border-color: color-mix(in srgb, var(--vg-warning), #fff 42%);
        }

        .vg-workspace-nav {
            border: 1px solid var(--vg-border);
            border-radius: var(--vg-radius-lg);
            background: linear-gradient(
                180deg,
                color-mix(in srgb, var(--vg-surface), transparent 0%),
                color-mix(in srgb, var(--vg-surface-2), transparent 30%)
            );
            padding: 10px;
            margin: 8px 0 12px;
            position: sticky;
            top: 0.4rem;
            z-index: 4;
            backdrop-filter: blur(8px);
        }
        .vg-workspace-nav .stButton > button {
            min-height: 38px;
            width: 100%;
            border-radius: var(--vg-radius-md);
        }
        .vg-workspace-title {
            font-size: 11px;
            color: var(--vg-muted);
            letter-spacing: .08em;
            text-transform: uppercase;
            margin: 0 0 8px 4px;
        }

        .vg-card {
            margin-bottom: 14px;
        }
        .vg-card.tight .stButton > button,
        .vg-card.tight .stDownloadButton > button {
            min-height: 36px;
        }
        .vg-section-head {
            border: 1px solid var(--vg-border);
            border-radius: var(--vg-radius-md);
            background: color-mix(in srgb, var(--vg-surface), transparent 8%);
            padding: 10px 12px;
            margin-bottom: 12px;
        }
        .vg-section-title {
            letter-spacing: -0.01em;
        }
        .vg-section-head .vg-badges {
            margin-top: 8px;
        }
        .vg-section-head .vg-badges,
        .vg-section-head .vg-section-subtitle {
            color: var(--vg-muted);
        }

        @media (max-width: 960px) {
            .main .block-container {
                padding-top: .8rem;
                padding-bottom: 1.6rem;
            }
            .vg-workspace-nav {
                position: static;
                top: auto;
            }
            .vg-shell-version {
                width: 100%;
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


# --- WRAPPERS LEGACY DE TEMA (compat) ---


def aplicar_tema(*args, **kwargs):
    """Compatibilidad: alias legacy que delega al tema Stitch."""
    return aplicar_estilos_stitch()


def inject_theme(*args, **kwargs):
    """Compatibilidad: alias legacy que delega al tema Stitch."""
    return aplicar_estilos_stitch()


# --- COMPONENTES LEGADOS (placeholders Fase 1) ---


def stitch_header(titulo, subtitulo=None):
    """Renderiza el header principal de la pÃ¡gina."""
    html_block = f"""
    <div style="margin-bottom: 2rem;">
        <h1 style="font-size: 1.875rem; margin-bottom: 0.5rem;">{html.escape(titulo)}</h1>
        {f'<p style="font-size: 1rem; opacity: 0.8;">{html.escape(subtitulo)}</p>' if subtitulo else ''}
    </div>
    """
    st.markdown(html_block, unsafe_allow_html=True)


def container_card_start():
    st.markdown('<div class="vg-card">', unsafe_allow_html=True)


def container_card_end():
    st.markdown("</div>", unsafe_allow_html=True)


# --- SIDEBAR / CONTROLES GLOBALES ---


def barra_lateral_config(gestor: Any = None):
    """Sidebar con branding, acciones rápidas y selector de tema."""
    mode = st.session_state.get(SESSION_THEME_KEY, _default_theme_mode())
    density_mode = st.session_state.get(SESSION_DENSITY_KEY, _default_density_mode())
    mode_label = "Oscuro" if mode == "dark" else "Claro"
    density_label = DENSITY_OPTIONS.get(str(density_mode), "Compacta")

    st.sidebar.markdown(
        """
        <div class="vg-sidebar-brand">
            <p class="vg-sidebar-title">VACA &amp; GENTILE</p>
            <p class="vg-sidebar-subtitle">Gestion juridica profesional · v1.0</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.sidebar.caption(f"Tema activo: {mode_label} · Densidad: {density_label}")
    st.sidebar.caption("Acciones rapidas")
    if st.sidebar.button("Abrir carpeta base", key="sidebar.open_base", width="stretch"):
        try:
            from config import RUTA_BASE

            os.startfile(str(RUTA_BASE))
        except Exception as exc:  # pragma: no cover - UI feedback
            st.sidebar.error(f"No se pudo abrir la ruta base: {exc}")

    if st.sidebar.button("Recargar datos", key="sidebar.reload", width="stretch"):
        st.cache_data.clear()
        st.rerun()

    st.sidebar.markdown("---")
    st.sidebar.caption("Navegacion principal")
    st.sidebar.caption("Use el selector lateral y el switcher superior para moverse.")
    st.sidebar.markdown("---")
    st.sidebar.caption("Operativo")
    st.sidebar.caption("Dashboard · Gestion · Agenda · Finanzas · Auditoria · Configuracion")
