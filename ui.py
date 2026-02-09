import streamlit as st
import os
import inspect
import html
import hashlib
from pathlib import Path
from typing import Any

# --- DESIGN SYSTEM: STITCH / DEEP NAVY ---

TOKENS = {
    "colors": {
        "dark": {
            "bg_app": "#0B1220",
            "bg_sidebar": "#0F172A",
            "bg_card": "#111827",
            "bg_card_hover": "#1F2937",
            "border": "rgba(148, 163, 184, 0.28)",
            "text_main": "#F3F4F6",
            "text_muted": "#A7B0C3",
            "primary": "#3B82F6",
            "primary_hover": "#2563EB",
            "success": "#10B981",
            "warning": "#F59E0B",
            "danger": "#EF4444",
            "badge_bg": "rgba(255,255,255,0.06)",
        },
        "light": {
            "bg_app": "#EEF2F7",
            "bg_sidebar": "#F7F8FC",
            "bg_card": "#FFFFFF",
            "bg_card_hover": "#F3F5FA",
            "border": "rgba(15, 23, 42, 0.18)",
            "text_main": "#0B1220",
            "text_muted": "#445065",
            "primary": "#2563EB",
            "primary_hover": "#1D4ED8",
            "success": "#059669",
            "warning": "#D97706",
            "danger": "#DC2626",
            "badge_bg": "rgba(0,0,0,0.05)",
        },
    },
    "typography": {
        "font_family": '"Inter", -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
        "h1": "1.9rem",
        "h2": "1.45rem",
        "body": "1rem",
        "small": "0.9rem",
    },
    "spacing": {"xs": "4px", "sm": "8px", "md": "12px", "lg": "16px", "xl": "24px"},
    "radius": {"sm": "0.35rem", "md": "0.55rem", "lg": "0.9rem", "full": "9999px"},
    "shadows": {
        "card": "0 12px 30px rgba(0, 0, 0, 0.22)",
        "glow": "0 0 0 3px rgba(59, 130, 246, 0.35)",
    },
}

# --- GESTIÓN DE ESTADO Y TEMA ---


def inicializar_ui():
    """Configura variables de sesión iniciales para la UI."""
    if "theme_mode" not in st.session_state:
        st.session_state.theme_mode = "dark"  # modo Stitch por defecto


def get_current_theme():
    """Retorna el diccionario de colores para el tema actual."""
    mode = st.session_state.get("theme_mode", "dark")
    return TOKENS["colors"].get(mode, TOKENS["colors"]["dark"])


def toggle_theme():
    """Alterna entre modo claro y oscuro."""
    current = st.session_state.get("theme_mode", "dark")
    st.session_state.theme_mode = "light" if current == "dark" else "dark"


# --- COMPATIBILIDAD (helpers heredados usados por views.py) ---


def _df_select_kwargs():
    """Devuelve kwargs opcionales para habilitar selección en st.dataframe si la versión lo soporta."""
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
    """Normaliza un entero en session_state con límites y step."""
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
    """Toast seguro si la versión de Streamlit lo soporta."""
    if hasattr(st, "toast"):
        try:
            st.toast(msg, icon=icon)
        except Exception:
            pass


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
    """Header de página con acciones y badges opcionales."""
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
    """Conversión aproximada de vh a px (Streamlit no expone viewport real)."""
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
    """Grilla simple con altura controlada y soporte opcional de selección."""
    kw = {"width": "stretch", "hide_index": hide_index, "height": _vh_to_px(height_vh)}
    if column_config:
        kw["column_config"] = column_config
    if selection_mode:
        kw.update(_df_select_kwargs())
    if editable:
        return st.data_editor(df, key=f"{key}_ed", **kw)
    return st.dataframe(df, key=f"{key}_df", **kw)


def section(title: str, help_text: str | None = None):
    """Sección con encabezado; devuelve el contenedor para contexto."""
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
  {f'<div class="vg-badges">{" • ".join(html.escape(m) for m in meta)}</div>' if meta else ''}
</div>
""",
        unsafe_allow_html=True,
    )


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
    """Estado vacío con CTA opcional que navega usando nav.navigate_to."""
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
    """Wizard por pasos; retorna el índice seleccionado."""
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
    """Badge de estado para auditoría."""
    if errores == 0 and warnings == 0:
        txt = "Óptimo · Sin problemas detectados"
        variant = "ok"
    elif errores > 0:
        txt = f"Errores: {errores} · Advertencias: {warnings}"
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
    """Renderiza una pill básica."""
    safe_kind = "".join(ch for ch in (kind or "").lower() if ch.isalnum() or ch in ("-", "_"))
    classes = ["vg-pill"]
    if safe_kind in {"danger", "warn", "ok"}:
        classes.append(f"variant-{safe_kind}")
    st.markdown(
        f"<span class=\"{' '.join(classes)}\">{html.escape(str(text))}</span>",
        unsafe_allow_html=True,
    )


def ui_centro_ayuda_content():
    """Contenido del centro de ayuda (versión breve)."""
    tab1, tab2, tab3, tab4 = st.tabs(["Uso básico", "Planilla", "Carpetas", "Problemas típicos"])
    with tab1:
        st.markdown("**Flujo recomendado:**\n1) Gestion > Casos > seleccionar un caso.\n2) Completar Responsable / Tarea / Fecha.\n3) Usar Agenda para priorizar.")
    with tab2:
        st.markdown("Atajos: priorizar urgentes, próximos 7/30 días, vista tarjetas.")
    with tab3:
        st.markdown("Estructura estándar por caso: 01.PRUEBA / 02.ESCRITOS / 03.RECIBOS / 04.OTROS.")
    with tab4:
        st.markdown("Tips OneDrive/Windows: evitar rutas largas, carpetas fantasma, normalizar UTF-8.")


def open_path(path: Path | str | None, container: "st.container | None" = None) -> bool:
    """Abre archivo/carpeta de forma segura; muestra mensajes si no es posible."""
    target = container or st
    if path is None:
        target.info("No hay carpeta física asociada.")
        return False
    path = Path(path)
    if str(path).startswith("db://"):
        target.info(f"Este caso está en base de datos.\n\nID: `{str(path).replace('db://cases/', '')}`")
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
        # Streamlit lanza excepción si set_page_config ya fue invocado; lo ignoramos para idempotencia.
        pass
    inicializar_ui()


# --- INYECCIÓN DE CSS (CORE) ---


def aplicar_estilos_stitch():
    """Inyecta el CSS global para transformar Streamlit en el diseño Stitch."""
    # Toggle de tema: fuente única de verdad en session_state["theme_mode"]
    theme_opts = ["Oscuro (Deep Navy)", "Claro"]
    current_mode = st.session_state.get("theme_mode", "dark")
    default_idx = 0 if current_mode == "dark" else 1
    with st.sidebar:
        st.markdown('<div class="vg-theme-toggle">', unsafe_allow_html=True)
        option = st.radio(
            "Tema",
            theme_opts,
            index=default_idx,
            key="stitch_theme_selector",
            label_visibility="collapsed",
        )
        st.session_state["theme_mode"] = "dark" if option.startswith("Oscuro") else "light"
        st.markdown("</div>", unsafe_allow_html=True)

    t = get_current_theme()
    ty = TOKENS["typography"]

    st.markdown(
        """
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
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
        }}

        body, .stApp {{
            background: var(--vg-bg);
            color: var(--vg-text);
            font-family: var(--vg-font);
        }}
        .stMarkdown {{
            color: var(--vg-text);
        }}

        .main .block-container {{
            padding-top: 1.25rem;
            padding-bottom: 2rem;
            max-width: 1600px;
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
    )
    st.markdown(css, unsafe_allow_html=True)


# --- WRAPPERS LEGACY DE TEMA (compat) ---


def aplicar_tema(*args, **kwargs):
    """Compatibilidad: alias legacy que delega al tema Stitch."""
    return aplicar_estilos_stitch()


def inject_theme(*args, **kwargs):
    """Compatibilidad: alias legacy que delega al tema Stitch."""
    return aplicar_estilos_stitch()


# --- COMPONENTES LEGADOS (placeholders Fase 1) ---


def stitch_header(titulo, subtitulo=None):
    """Renderiza el header principal de la página."""
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
    st.sidebar.markdown(
        """
        <div style="padding:12px 10px 6px 10px;border-bottom:1px solid var(--vg-border);">
            <p style="font-weight:800;letter-spacing:.3px;color:var(--vg-text);font-size:16px;margin:0;">VACA &amp; GENTILE</p>
            <p style="color:var(--vg-muted);font-size:12px;margin:4px 0 0 0;">Gestión jurídica · v1.0</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if st.sidebar.button("Abrir carpeta base", width="stretch"):
        try:
            from config import RUTA_BASE

            os.startfile(str(RUTA_BASE))
        except Exception as exc:  # pragma: no cover - UI feedback
            st.sidebar.error(f"No se pudo abrir la ruta base: {exc}")

    if st.sidebar.button("Recargar datos", width="stretch"):
        st.cache_data.clear()
        st.rerun()

    st.sidebar.markdown("---")

    st.sidebar.caption("UI · Stitch Design System")
