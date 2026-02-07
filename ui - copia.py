"""
UI / Design System: tema, CSS, helpers UX, sidebar.
Sprint 0: HTML crudo eliminado (todo via st.markdown + unsafe_allow_html).
Sprint 2: kpi_card, progress_row.
Sprint 5: tokens sobrios, layout controlado.
"""

import streamlit as st
import inspect
import socket
import os
import json
import html
from datetime import datetime
from typing import List

from pathlib import Path

from config import RUTA_BASE, _is_container_env
from domain import Caso
from repo import GestorCasos, is_db_path


# ══════════════════════════════════════════════════════════════════════════════
# APERTURA DE ARCHIVOS/CARPETAS (cross-platform)
# ══════════════════════════════════════════════════════════════════════════════

def open_path(path: Path, container: "st.container | None" = None) -> bool:
    """
    Abre un archivo o carpeta de forma segura (cross-platform).

    - En Windows: usa os.startfile()
    - En Linux/contenedor: muestra mensaje informativo (no hay GUI)
    - En modo DB: muestra info (no hay carpeta física)

    Args:
        path: Ruta al archivo o carpeta a abrir (puede ser None o pseudo-path db://)
        container: Contenedor de Streamlit donde mostrar mensajes (default: st)

    Returns:
        True si se abrió exitosamente, False en caso contrario
    """
    target = container or st

    # Manejar None o path vacío
    if path is None:
        target.info("📂 No hay carpeta física asociada (modo base de datos).")
        return False

    path = Path(path)
    path_str = str(path)

    # Manejar pseudo-paths de base de datos (db://cases/uuid)
    if is_db_path(path):
        target.info(f"📂 Este caso está almacenado en base de datos.\n\n**ID:** `{path_str.replace('db://cases/', '')}`")
        return False

    # En entorno de contenedor (Render/Docker) no hay GUI
    if _is_container_env():
        target.info(f"📂 Apertura local no disponible en este entorno.\n\n**Ruta:** `{path}`")
        return False

    # En Windows, usar os.startfile
    if os.name == "nt":
        try:
            os.startfile(str(path))
            return True
        except FileNotFoundError:
            target.error(f"Ruta no encontrada: `{path}`")
            return False
        except Exception as e:
            target.error(f"No se pudo abrir: {e}")
            return False

    # En otros sistemas (Linux/Mac sin contenedor), mostrar mensaje
    target.warning(f"📂 Apertura automática no soportada en este sistema.\n\n**Ruta:** `{path}`")
    return False


# ══════════════════════════════════════════════════════════════════════════════
# TEMAS
# ══════════════════════════════════════════════════════════════════════════════

THEMES = {
    "Claro": {
        "bg": "#f8f7f6",
        "panel": "#ffffff",
        "panel2": "#f3f0e8",
        "text": "#181511",
        "muted": "#897b61",
        "line": "#e6e2db",
        "brand": "#181511",
        "accent": "#eeab2f",
        "primary": "#eeab2f",
        "danger": "#d32f2f",
        "warn": "#eeab2f",
        "ok": "#0b8a3c",
        "shadow": "0 12px 32px rgba(24, 21, 17, 0.08)",
        "input_bg": "#f5f1e9",
        "input_border": "#e2ddcf",
        "badge_ok_bg": "rgba(11, 138, 60, 0.12)",
        "badge_warn_bg": "rgba(238, 171, 47, 0.18)",
        "badge_danger_bg": "rgba(211, 47, 47, 0.14)",
    },
    "Oscuro": {
        "bg": "#101622",
        "panel": "#1b2334",
        "panel2": "#0f141f",
        "text": "#e8ecf5",
        "muted": "#9da6b9",
        "line": "#1e2430",
        "brand": "#d7e6ff",
        "accent": "#135bec",
        "primary": "#135bec",
        "danger": "#ef4444",
        "warn": "#f59e0b",
        "ok": "#0bda5e",
        "shadow": "0 18px 42px rgba(0, 0, 0, 0.45)",
        "input_bg": "#111827",
        "input_border": "#2a3242",
        "badge_ok_bg": "rgba(11, 218, 94, 0.14)",
        "badge_warn_bg": "rgba(245, 158, 11, 0.18)",
        "badge_danger_bg": "rgba(239, 68, 68, 0.16)",
    },
}


def load_tokens(path: str = "design/stitch_ai/tokens.json") -> dict:
    """Carga tokens JSON desde disco con fallback a estructura vacía."""
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return {"colors": {}, "typography": {}, "radii": {}, "shadows": {}, "spacing": {}, "tailwind_keys": {}}


def _slug(var_name: str) -> str:
    return (
        var_name.lower()
        .replace(" ", "-")
        .replace("_", "-")
        .replace(".", "-")
    )


def _resolve_mode_colors(colors: dict, mode: str) -> dict:
    """Prefiere claves -light/-dark según modo; conserva las otras tal cual."""
    mode = (mode or "light").lower()
    resolved = {}
    for key, val in colors.items():
        if key.endswith("-light") or key.endswith("-dark"):
            base = key.rsplit("-", 1)[0]
            if mode == "light" and key.endswith("-light"):
                resolved[base] = val
            if mode == "dark" and key.endswith("-dark"):
                resolved[base] = val
    for key, val in colors.items():
        if key.endswith("-light") or key.endswith("-dark"):
            continue
        resolved.setdefault(key, val)
    return resolved


def build_css_vars(tokens: dict, mode: str = "light") -> str:
    """Genera bloque CSS con variables en :root a partir de tokens."""
    parts = [":root{"]
    colors = _resolve_mode_colors(tokens.get("colors", {}), mode)
    for k, v in colors.items():
        parts.append(f"--color-{_slug(k)}:{v};")

    radii = tokens.get("radii", {})
    for k, v in radii.items():
        parts.append(f"--radius-{_slug(k)}:{v};")

    shadows = tokens.get("shadows", {})
    for k, v in shadows.items():
        parts.append(f"--shadow-{_slug(k)}:{v};")

    spacing = tokens.get("spacing", {})
    for k, v in spacing.items():
        parts.append(f"--space-{_slug(k)}:{v};")

    fonts = tokens.get("typography", {}).get("font_families", [])
    if fonts:
        parts.append(f"--font-display:{fonts[0]};")

    parts.append("}")
    return "\n".join(parts)


def inject_theme(tokens: dict):
    """
    Inyecta variables CSS basadas en tokens + carga de fuentes.
    Respeta st.session_state['theme_mode'] (light|dark).
    """
    mode = st.session_state.get("theme_mode", "light")
    css_vars = build_css_vars(tokens, mode=mode)
    font_link = "https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap"
    icons_link = "https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:wght,FILL@0,0..1&display=swap"
    css = f"""
    <style>
    @import url('{font_link}');
    @import url('{icons_link}');
    {css_vars}
    body, .stApp {{
        font-family: var(--font-display, 'Inter'), -apple-system, 'Segoe UI', sans-serif;
        background: var(--color-background, var(--color-background-light, #f6f7f8));
        color: var(--color-text, #111418);
    }}
    .vg-card {{
        background: var(--color-surface, var(--color-card, #ffffff));
        border: 1px solid var(--color-border, #E3E6EA);
        border-radius: var(--radius-v2, 12px);
        box-shadow: var(--shadow-v1, 0 1px 2px 0 rgba(0,0,0,0.05));
        padding: var(--space-v2, 16px);
        margin-bottom: var(--space-v2, 16px);
    }}
    .vg-card h4{{margin:0 0 4px 0;font-size:16px;font-weight:700;}}
    .vg-card .subtitle{{color:var(--color-text-sub, #5b677a);font-size:13px;margin-bottom:8px;}}
    .vg-pill {{
        display:inline-flex;align-items:center;gap:6px;
        padding:4px 10px;border-radius:999px;
        font-size:12px;font-weight:600;
        background: var(--color-pill-bg, #f3f4f6);
        color: var(--color-pill-fg, #111418);
        border: 1px solid var(--color-border, #E3E6EA);
    }}
    .vg-kpi {{
        display:flex;flex-direction:column;gap:4px;
        padding:12px 14px;border-radius:var(--radius-v2,12px);
        background: var(--color-surface, #ffffff);
        box-shadow: var(--shadow-v1,0 1px 2px rgba(0,0,0,0.05));
        border: 1px solid var(--color-border,#E3E6EA);
    }}
    .vg-kpi .label{{font-size:12px;color:var(--color-text-sub,#5b677a);text-transform:uppercase;letter-spacing:0.02em;}}
    .vg-kpi .value{{font-size:24px;font-weight:700;color:var(--color-text,#111418);}}
    .vg-kpi .status{{font-size:12px;font-weight:600;color:var(--color-text,#111418);}}
    .vg-section-header{{margin:8px 0 4px 0;}}
    .vg-section-header h3{{margin:0;font-size:16px;font-weight:700;color:var(--color-text,#111418);}}
    .vg-section-header .vg-subtitle{{margin:2px 0 0 0;font-size:13px;color:var(--color-text-sub,#5b677a);}}
    </style>
    """
    st.markdown(css, unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
# ESTADO UI
# ══════════════════════════════════════════════════════════════════════════════

def _ui_init_state():
    if "ui_tema" not in st.session_state:
        st.session_state["ui_tema"] = "Claro"
    if "theme_mode" not in st.session_state:
        st.session_state["theme_mode"] = "light"
    if "ui_help_open" not in st.session_state:
        st.session_state["ui_help_open"] = False
    if "ui_onboarding_ok" not in st.session_state:
        st.session_state["ui_onboarding_ok"] = False


def _ui_toast(msg: str, icon: str | None = None):
    if hasattr(st, "toast"):
        try:
            st.toast(msg, icon=icon)
        except Exception:
            pass


# ══════════════════════════════════════════════════════════════════════════════
# TEMA CSS (Sprint 5: tokens sobrios, jerarquia, espaciado)
# ══════════════════════════════════════════════════════════════════════════════

def aplicar_tema():
    tname = st.session_state.get("ui_tema", "Claro")
    t = THEMES.get(tname, THEMES["Claro"])

    css = f"""
    <style>
    /* ═══════════════════════════════════════════════════════════
       VACA & GENTILE - Design System Tokens (Sprint 5)
       ═══════════════════════════════════════════════════════════ */
    :root{{
      --bg: {t["bg"]};
      --panel: {t["panel"]};
      --panel2: {t["panel2"]};
      --text: {t["text"]};
      --muted: {t["muted"]};
      --line: {t["line"]};
      --brand: {t["brand"]};
      --accent: {t["accent"]};
      --primary: {t.get("primary", t["accent"])};
      --danger: {t["danger"]};
      --warn: {t["warn"]};
      --ok: {t["ok"]};
      --radius: 14px;
      --radius-sm: 10px;
      --shadow: {t["shadow"]};
      --input-bg: {t["input_bg"]};
      --input-border: {t["input_border"]};
      --badge-ok-bg: {t["badge_ok_bg"]};
      --badge-warn-bg: {t["badge_warn_bg"]};
      --badge-danger-bg: {t["badge_danger_bg"]};
      --pill-bg: color-mix(in srgb, var(--muted) 8%, transparent);
      --pill-fg: var(--text);
      --pill-border: color-mix(in srgb, var(--muted) 26%, transparent);
      --text-sub: var(--muted);
      --surface-strong: color-mix(in srgb, var(--panel) 90%, var(--bg) 10%);
      --surface-soft: color-mix(in srgb, var(--panel) 75%, var(--bg) 25%);
      /* Spacing scale (Sprint 5: 8/12/16/24) */
      --sp-xs: 4px;
      --sp-sm: 8px;
      --sp-md: 12px;
      --sp-lg: 18px;
      --sp-xl: 24px;
      --sp-2xl: 32px;
      /* Layout density */
      --card-pad: var(--sp-lg);
      --card-pad-tight: 12px;
      --card-gap: 12px;
      --section-gap: 16px;
      --kpi-pad-x: 18px;
      --kpi-pad-y: 14px;
      --kpi-gap: 6px;
      --kpi-min-height: 118px;
      --shadow-soft: 0 12px 30px -16px rgba(0,0,0,0.28);
    }}

    /* ═══ PLANO 1: Fondo raiz (stApp) ═══ */
    .stApp, .stApp > header {{
      background-color: var(--bg) !important;
    }}

    html, body, [class*="css"] {{
      font-family: 'Inter', 'Inter var', ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, Arial, sans-serif;
      color: var(--text);
      letter-spacing: -0.01em;
      background: var(--bg);
    }}

    .main {{ background: var(--bg) !important; }}
    .block-container {{ padding-top: 1rem; }}

    /* ═══ PLANO 2: Sidebar ═══ */
    section[data-testid="stSidebar"] {{
      background: var(--panel) !important;
      border-right: 1px solid var(--line) !important;
    }}
    section[data-testid="stSidebar"] [data-testid="stSidebarContent"] {{
      background: var(--panel) !important;
    }}
    section[data-testid="stSidebar"] .block-container {{
      background: var(--panel) !important;
    }}
    section[data-testid="stSidebar"] * {{
      color: var(--text);
    }}

    /* ═══ PLANO 3: Tipografia jerarquica (Sprint 5) ═══ */
    h1 {{ color: var(--brand) !important; font-size: 1.6rem !important; font-weight: 900 !important; letter-spacing: -0.01em; margin-bottom: var(--sp-sm) !important; }}
    h2 {{ color: var(--text) !important; font-size: 1.25rem !important; font-weight: 800 !important; margin-bottom: var(--sp-sm) !important; }}
    h3 {{ color: var(--text) !important; font-size: 1.05rem !important; font-weight: 700 !important; margin-bottom: var(--sp-xs) !important; }}
    h4, h5, h6 {{ color: var(--text) !important; font-weight: 700 !important; }}
    p, li, span, label, td, th {{ color: var(--text) !important; }}
    .stCaption, [data-testid="stCaptionContainer"] {{ color: var(--muted) !important; }}

    /* ═══ Tarjetas reutilizables (Sprint 5: borde suave, menos lineas) ═══ */
    .vg-card {{
      background: var(--surface-strong);
      border: 1px solid color-mix(in srgb, var(--line) 70%, transparent);
      border-radius: var(--radius);
      padding: var(--card-pad);
      box-shadow: var(--shadow-soft, var(--shadow));
      margin-bottom: var(--section-gap);
      transition: transform 140ms ease, box-shadow 140ms ease, border-color 140ms ease;
      display: flex;
      flex-direction: column;
      gap: var(--sp-sm);
    }}
    .vg-card:hover {{
      box-shadow: 0 18px 40px -18px rgba(0,0,0,0.35);
      border-color: color-mix(in srgb, var(--primary, var(--accent)) 40%, var(--line));
    }}
    .vg-card.tight,
    .vg-card-tight {{
      padding: var(--card-pad-tight);
      margin-bottom: var(--card-gap);
      gap: var(--sp-xs);
    }}
    .vg-card h4{{margin:0 0 var(--sp-xs) 0;font-size:17px;font-weight:760;letter-spacing:-0.015em;}}
    .vg-card .subtitle{{color:var(--text-sub);font-size:13px;margin:0 0 var(--sp-sm) 0;}}
    .vg-card.tight h4{{margin-bottom:var(--sp-xs);}}
    .vg-card.tight .subtitle{{margin-bottom:var(--sp-xs);}}

    /* KPI card */
    .vg-kpi-card {{
      background: color-mix(in srgb, var(--panel) 92%, var(--bg) 8%);
      border: 1px solid color-mix(in srgb, var(--line) 70%, transparent);
      border-radius: var(--radius);
      padding: var(--kpi-pad-y) var(--kpi-pad-x);
      box-shadow: var(--shadow-soft, var(--shadow));
      display: grid;
      gap: var(--kpi-gap);
      align-content: space-between;
      min-height: var(--kpi-min-height);
    }}
    .vg-kpi-card .kpi-label {{
      font-size: 12px;
      font-weight: 700;
      letter-spacing: 0.05em;
      text-transform: uppercase;
      color: var(--text-sub);
      margin: 0;
    }}
    .vg-kpi-card .kpi-value {{
      font-size: 30px;
      font-weight: 850;
      line-height: 1.05;
      color: var(--text);
      margin: 0;
    }}
    .vg-kpi-card .kpi-status, .vg-kpi-card .kpi-delta {{
      display: inline-flex;
      align-items: center;
      gap: 6px;
      font-size: 12px;
      font-weight: 700;
      color: var(--text-sub);
      line-height: 1;
    }}
    .vg-kpi-card .kpi-dot {{
      width: 9px;
      height: 9px;
      border-radius: 999px;
      background: var(--muted);
      box-shadow: 0 0 0 2px color-mix(in srgb, var(--muted) 22%, transparent);
    }}
    .vg-kpi-card.tone-good {{
      border-color: color-mix(in srgb, var(--ok) 38%, var(--line));
      background: color-mix(in srgb, var(--ok) 8%, var(--panel));
    }}
    .vg-kpi-card.tone-good .kpi-value, .vg-kpi-card.tone-good .kpi-status {{ color: var(--ok); }}
    .vg-kpi-card.tone-good .kpi-dot {{ background: var(--ok); box-shadow: 0 0 0 2px color-mix(in srgb, var(--ok) 25%, transparent); }}
    .vg-kpi-card.tone-warn {{
      border-color: color-mix(in srgb, var(--warn) 40%, var(--line));
      background: color-mix(in srgb, var(--warn) 10%, var(--panel));
    }}
    .vg-kpi-card.tone-warn .kpi-value, .vg-kpi-card.tone-warn .kpi-status {{ color: var(--warn); }}
    .vg-kpi-card.tone-warn .kpi-dot {{ background: var(--warn); box-shadow: 0 0 0 2px color-mix(in srgb, var(--warn) 24%, transparent); }}
    .vg-kpi-card.tone-bad {{
      border-color: color-mix(in srgb, var(--danger) 40%, var(--line));
      background: color-mix(in srgb, var(--danger) 12%, var(--panel));
    }}
    .vg-kpi-card.tone-bad .kpi-value, .vg-kpi-card.tone-bad .kpi-status {{ color: var(--danger); }}
    .vg-kpi-card.tone-bad .kpi-dot {{ background: var(--danger); box-shadow: 0 0 0 2px color-mix(in srgb, var(--danger) 24%, transparent); }}
    .vg-kpi-card.tone-neutral {{
      border-color: color-mix(in srgb, var(--primary, var(--accent)) 30%, var(--line));
      background: color-mix(in srgb, var(--primary, var(--accent)) 6%, var(--panel));
    }}
    .vg-kpi-card.tone-neutral .kpi-value {{ color: var(--text); }}

    /* Progress row (Sprint 2) */
    .vg-progress-row {{
      display: flex;
      align-items: center;
      gap: var(--sp-md);
      padding: var(--sp-sm) 0;
      border-bottom: 1px solid var(--line);
    }}
    .vg-progress-row:last-child {{ border-bottom: none; }}
    .vg-progress-label {{
      font-size: 13px;
      font-weight: 600;
      color: var(--text);
      min-width: 140px;
    }}
    .vg-progress-bar-bg {{
      flex: 1;
      height: 10px;
      background: var(--panel2);
      border-radius: 5px;
      border: 1px solid var(--line);
      overflow: hidden;
    }}
    .vg-progress-bar-fill {{
      height: 100%;
      border-radius: 5px;
      transition: width 0.3s ease;
      background: var(--muted);
    }}
    .vg-progress-pct {{
      font-size: 13px;
      font-weight: 700;
      min-width: 50px;
      text-align: right;
    }}
    .vg-progress-row.good .vg-progress-bar-fill {{ background: var(--ok); }}
    .vg-progress-row.warn .vg-progress-bar-fill {{ background: var(--warn); }}
    .vg-progress-row.bad .vg-progress-bar-fill {{ background: var(--danger); }}
    .vg-progress-row.good .vg-progress-pct {{ color: var(--ok); }}
    .vg-progress-row.warn .vg-progress-pct {{ color: var(--warn); }}
    .vg-progress-row.bad .vg-progress-pct {{ color: var(--danger); }}

    .vg-kpi {{
      display: grid;
      gap: var(--kpi-gap);
      align-content: start;
    }}
    .vg-pill {{
      display: inline-flex;
      align-items: center;
      gap: 6px;
      padding: 4px 11px;
      border-radius: 999px;
      border: 1px solid var(--pill-border);
      background: var(--pill-bg);
      color: var(--pill-fg);
      font-size: 11px;
      font-weight: 700;
      line-height: 1.25;
      text-transform: uppercase;
      letter-spacing: 0.04em;
    }}
    .vg-pill.pill-primary {{ background: color-mix(in srgb, var(--primary) 18%, transparent); color: var(--primary); border-color: color-mix(in srgb, var(--primary) 28%, var(--pill-border)); }}
    .vg-pill.pill-warn {{ background: color-mix(in srgb, var(--warn) 18%, transparent); color: var(--warn); border-color: color-mix(in srgb, var(--warn) 28%, var(--pill-border)); }}
    .vg-pill.pill-danger {{ background: color-mix(in srgb, var(--danger) 18%, transparent); color: var(--danger); border-color: color-mix(in srgb, var(--danger) 28%, var(--pill-border)); }}
    .vg-pill.pill-success {{ background: color-mix(in srgb, var(--ok) 18%, transparent); color: var(--ok); border-color: color-mix(in srgb, var(--ok) 28%, var(--pill-border)); }}
    .vg-pill.pill-info {{ background: color-mix(in srgb, var(--brand) 16%, transparent); color: var(--brand); border-color: color-mix(in srgb, var(--brand) 26%, var(--pill-border)); }}
    .vg-rule {{
      height: 3px;
      background: var(--accent);
      border-radius: 999px;
      margin-top: var(--sp-md);
    }}

    /* Badges */
    .vg-badge-ok {{
      display: inline-block; padding: 2px 10px; border-radius: 999px;
      background: var(--badge-ok-bg); color: var(--ok); font-size: 11px; font-weight: 650;
    }}
    .vg-badge-warn {{
      display: inline-block; padding: 2px 10px; border-radius: 999px;
      background: var(--badge-warn-bg); color: var(--warn); font-size: 11px; font-weight: 650;
    }}
    .vg-badge-danger {{
      display: inline-block; padding: 2px 10px; border-radius: 999px;
      background: var(--badge-danger-bg); color: var(--danger); font-size: 11px; font-weight: 650;
    }}
    /* Audit status badge */
    .vg-badge-status {{
      display: inline-flex; align-items: center; gap: 6px;
      padding: 8px 16px;
      border-radius: var(--radius);
      font-size: 14px;
      font-weight: 700;
    }}
    .vg-badge-status.optimo {{
      background: var(--badge-ok-bg);
      color: var(--ok);
      border: 1px solid var(--ok);
    }}
    .vg-badge-status.atencion {{
      background: var(--badge-warn-bg);
      color: var(--warn);
      border: 1px solid var(--warn);
    }}
    .vg-badge-status.error {{
      background: var(--badge-danger-bg);
      color: var(--danger);
      border: 1px solid var(--danger);
    }}

    /* ═══ Toolbar container ═══ */
    .vg-toolbar {{
      background: var(--panel2);
      border: 1px solid var(--line);
      border-radius: var(--radius);
      padding: var(--sp-sm) var(--sp-md);
      margin-bottom: var(--sp-md);
      display: flex;
      align-items: center;
      gap: var(--sp-sm);
    }}

    /* Section header (Sprint 5: menos lineas, mas espaciado) */
    .vg-section-header {{
      display: flex;
      flex-direction: column;
      gap: var(--sp-xs);
      padding: 0;
      margin-bottom: var(--sp-sm);
    }}
    .vg-section-header h3 {{
      margin: 0 !important;
      padding: 0 !important;
      font-size: 18px;
      font-weight: 750;
      letter-spacing: -0.01em;
    }}
    .vg-section-header h2,
    .vg-section-header h3 {{
      margin: 0;
      display: block !important;
      visibility: visible !important;
    }}
    .vg-section-header .vg-subtitle {{
      color: var(--muted);
      font-size: 13px;
      line-height: 1.3;
    }}
    .vg-section-meta {{
      display: inline-flex;
      flex-wrap: wrap;
      gap: var(--sp-sm);
      margin: 0 0 var(--sp-md) 0;
    }}
    .vg-section-meta .vg-pill {{
      background: color-mix(in srgb, var(--panel) 70%, white 30%);
      color: var(--muted);
    }}

    /* Context bar (caso activo) */
    .vg-context-bar {{
      background: var(--panel);
      border: 1px solid var(--accent);
      border-left: 4px solid var(--accent);
      border-radius: var(--radius-sm);
      padding: var(--sp-sm) var(--sp-md);
      margin-bottom: var(--sp-md);
    }}

    /* Soft block overlay */
    .vg-soft-block {{
      background: var(--panel2);
      border: 1px solid var(--line);
      border-radius: var(--radius);
      padding: var(--sp-xl);
      text-align: center;
      margin: var(--sp-xl) 0;
    }}
    .vg-soft-block p {{
      color: var(--muted) !important;
      font-size: 14px;
    }}

    /* ═══ BOTONES (Sprint 5: acento dorado) ═══ */
    .stButton > button, .stDownloadButton > button {{
      border-radius: var(--radius-sm) !important;
      border: 1px solid var(--line) !important;
      background: var(--panel2) !important;
      color: var(--text) !important;
      font-weight: 600 !important;
      font-size: 13px !important;
      padding: var(--sp-sm) var(--sp-lg) !important;
      transition: all .1s ease;
    }}
    .stButton > button:hover, .stDownloadButton > button:hover {{
      transform: translateY(-1px);
      border-color: var(--primary, var(--accent)) !important;
      box-shadow: 0 2px 8px rgba(0,0,0,0.08);
    }}
    .stButton > button:focus, .stDownloadButton > button:focus {{
      outline: 2px solid color-mix(in srgb, var(--primary, var(--accent)) 28%, transparent) !important;
    }}
    .stButton > button:active {{
      transform: translateY(0);
    }}

    /* Primary button style */
    .vg-btn-primary button {{
      background: var(--primary, var(--brand)) !important;
      color: #fff !important;
      border-color: var(--primary, var(--brand)) !important;
    }}
    .vg-btn-primary button:hover {{
      opacity: 0.9;
    }}

    /* ═══ INPUTS ═══ */
    .stTextInput input, .stTextArea textarea, .stNumberInput input {{
      border-radius: var(--radius-sm) !important;
      border: 1.5px solid var(--input-border) !important;
      background: var(--input-bg) !important;
      color: var(--text) !important;
      font-size: 13px !important;
    }}
    .stTextInput input:focus, .stTextArea textarea:focus, .stNumberInput input:focus {{
      border-color: var(--primary, var(--accent)) !important;
      box-shadow: 0 0 0 2px color-mix(in srgb, var(--primary, var(--accent)) 20%, transparent) !important;
    }}
    .stTextInput input::placeholder, .stTextArea textarea::placeholder {{
      color: var(--muted) !important;
      opacity: 0.7 !important;
    }}

    /* ═══ BASEWEB SELECT / MULTISELECT ═══ */
    div[data-baseweb="select"] > div {{
      border-radius: var(--radius-sm) !important;
      border: 1px solid var(--input-border) !important;
      background-color: var(--input-bg) !important;
      color: var(--text) !important;
    }}
    div[data-baseweb="select"] > div:focus-within {{
      border-color: var(--accent) !important;
      box-shadow: 0 0 0 2px rgba(181,139,0,0.15) !important;
    }}
    div[data-baseweb="select"] span,
    div[data-baseweb="select"] [data-baseweb="tag"] span {{
      color: var(--text) !important;
    }}
    div[data-baseweb="select"] div[aria-selected="false"],
    div[data-baseweb="select"] [data-baseweb="select"] > div > div:first-child {{
      color: var(--muted) !important;
    }}
    div[data-baseweb="select"] svg {{
      fill: var(--muted) !important;
    }}
    div[data-baseweb="popover"] {{
      background-color: var(--panel) !important;
      border: 1px solid var(--line) !important;
      border-radius: var(--radius-sm) !important;
      box-shadow: var(--shadow) !important;
    }}
    div[data-baseweb="popover"] > div {{
      background-color: var(--panel) !important;
    }}
    ul[role="listbox"] {{
      background-color: var(--panel) !important;
      max-height: 330px !important;
      overflow-y: auto !important;
    }}
    ul[role="listbox"] li {{
      background-color: var(--panel) !important;
      color: var(--text) !important;
    }}
    ul[role="listbox"] li:hover,
    ul[role="listbox"] li[aria-selected="true"] {{
      background-color: var(--panel2) !important;
    }}
    ul[role="listbox"] li[aria-selected="true"] {{
      border-left: 3px solid var(--accent);
    }}
    [data-baseweb="tag"] {{
      background-color: var(--panel2) !important;
      border: 1px solid var(--line) !important;
      border-radius: var(--radius-sm) !important;
      color: var(--text) !important;
    }}
    [data-baseweb="tag"] span {{
      color: var(--text) !important;
    }}
    [data-baseweb="tag"] [role="presentation"] {{
      color: var(--muted) !important;
    }}

    /* ═══ METRICAS ═══ */
    div[data-testid="metric-container"] {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: var(--radius);
      padding: var(--sp-md);
      box-shadow: var(--shadow);
    }}
    div[data-testid="metric-container"] label {{
      color: var(--muted) !important;
      font-size: 12px !important;
    }}
    div[data-testid="metric-container"] [data-testid="stMetricValue"] {{
      color: var(--text) !important;
      font-weight: 900 !important;
    }}
    div[data-testid="metric-container"] [data-testid="stMetricDelta"] {{
      color: var(--muted) !important;
    }}

    /* ═══ DATAFRAME ═══ */
    div[data-testid="stDataFrame"] {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: var(--radius);
      padding: var(--sp-xs);
      box-shadow: var(--shadow);
    }}
    div[data-testid="stDataFrame"] thead tr th {{
      background: var(--panel2) !important;
      border-bottom: 1px solid var(--line) !important;
      color: var(--muted) !important;
      font-weight: 800 !important;
      font-size: 12px !important;
    }}
    div[data-testid="stDataFrame"] [role="grid"] {{
      overflow-x: auto !important;
    }}
    div[data-testid="stDataFrame"] {{
      max-width: 100% !important;
    }}

    /* ═══ TABS (Sprint 5: pill style) ═══ */
    .stTabs [data-baseweb="tab-list"] {{
      background: var(--panel) !important;
      border: 1px solid var(--line);
      border-radius: var(--radius);
      padding: var(--sp-xs);
      gap: 2px !important;
    }}
    .stTabs [data-baseweb="tab-list"] button {{
      border-radius: var(--radius-sm) !important;
      color: var(--muted) !important;
      font-weight: 600 !important;
      font-size: 13px !important;
      padding: var(--sp-sm) var(--sp-lg) !important;
      border: none !important;
      background: transparent !important;
    }}
    .stTabs [data-baseweb="tab-list"] button:hover {{
      background: var(--panel2) !important;
      color: var(--text) !important;
    }}
    .stTabs [data-baseweb="tab-list"] button[aria-selected="true"] {{
      background: var(--panel2) !important;
      color: var(--brand) !important;
      font-weight: 700 !important;
      box-shadow: 0 1px 3px rgba(0,0,0,0.06);
    }}
    .stTabs [data-baseweb="tab-highlight"] {{
      display: none !important;
    }}
    .stTabs [data-baseweb="tab-border"] {{
      display: none !important;
    }}

    /* ═══ RADIO (sidebar nav pills) ═══ */
    div[data-testid="stRadio"] > div {{
      gap: 4px !important;
    }}
    div[data-testid="stRadio"] label {{
      background: transparent !important;
      border: 1px solid transparent !important;
      border-radius: var(--radius-sm) !important;
      padding: var(--sp-sm) var(--sp-lg) !important;
      font-weight: 600 !important;
      font-size: 13px !important;
      color: var(--muted) !important;
      cursor: pointer;
      transition: all .1s ease;
    }}
    div[data-testid="stRadio"] label:hover {{
      background: var(--panel2) !important;
      color: var(--text) !important;
    }}
    div[data-testid="stRadio"] label[data-checked="true"],
    div[data-testid="stRadio"] label:has(input:checked) {{
      background: var(--panel) !important;
      border-color: var(--line) !important;
      color: var(--brand) !important;
      font-weight: 700 !important;
      box-shadow: 0 1px 3px rgba(0,0,0,0.06);
    }}

    /* ═══ EXPANDER ═══ */
    .streamlit-expanderHeader {{
      background: var(--panel2) !important;
      border: 1px solid var(--line) !important;
      border-radius: var(--radius-sm) !important;
      color: var(--text) !important;
      font-weight: 600 !important;
      font-size: 13px !important;
    }}
    [data-testid="stExpander"] {{
      border: 1px solid var(--line) !important;
      border-radius: var(--radius) !important;
      background: var(--panel) !important;
    }}
    [data-testid="stExpander"] summary {{
      color: var(--text) !important;
      font-weight: 600 !important;
    }}
    [data-testid="stExpander"] details[open] > div {{
      background: var(--panel) !important;
    }}

    /* ═══ FORM ═══ */
    [data-testid="stForm"] {{
      background: var(--panel) !important;
      border: 1px solid var(--line) !important;
      border-radius: var(--radius) !important;
      padding: var(--sp-lg) !important;
    }}

    /* ═══ CHECKBOX / TOGGLE ═══ */
    .stCheckbox label span,
    .stCheckbox label p {{
      color: var(--text) !important;
    }}

    /* ═══ ALERTS ═══ */
    .stAlert {{
      border-radius: var(--radius-sm) !important;
    }}
    div[data-testid="stNotification"] {{
      background: var(--panel) !important;
      border: 1px solid var(--line) !important;
      color: var(--text) !important;
    }}

    /* ═══ TOAST ═══ */
    [data-testid="stToast"] {{
      background: var(--panel) !important;
      border: 1px solid var(--line) !important;
      color: var(--text) !important;
      border-radius: var(--radius) !important;
      box-shadow: var(--shadow) !important;
    }}

    /* ═══ DIVIDER ═══ */
    hr {{
      border: none;
      border-top: 1px solid var(--line);
      margin: var(--sp-lg) 0;
    }}

    /* ═══ SCROLLBAR ═══ */
    ::-webkit-scrollbar {{
      width: 8px;
      height: 8px;
    }}
    ::-webkit-scrollbar-track {{
      background: var(--bg);
    }}
    ::-webkit-scrollbar-thumb {{
      background: var(--line);
      border-radius: 4px;
    }}
    ::-webkit-scrollbar-thumb:hover {{
      background: var(--muted);
    }}

    /* ═══ SPINNER ═══ */
    .stSpinner > div {{
      border-top-color: var(--accent) !important;
    }}

    /* ═══ SLIDER ═══ */
    .stSlider [data-baseweb="slider"] div {{
      background: var(--line) !important;
    }}
    .stSlider [data-baseweb="slider"] [role="slider"] {{
      background: var(--accent) !important;
      border-color: var(--accent) !important;
    }}

    /* ═══ DROPDOWN HEIGHT LIMIT ═══ */
    div[data-baseweb="select"] > div {{
      max-height: 380px !important;
      overflow-y: auto !important;
    }}
    div[data-baseweb="popover"] {{
      max-height: 380px !important;
    }}

    /* ═══ GRID SHELL (UX v3) ═══ */
    .vg-grid-shell {{
      height: calc(100vh - 220px);
      overflow: auto;
      border-radius: var(--radius);
    }}

    /* Fluid mode */
    .vg-fluid .main .block-container {{
      max-width: 100% !important;
    }}

    /* AgGrid container styling */
    .ag-theme-streamlit,
    .ag-theme-alpine-dark {{
      border: 1px solid var(--line) !important;
      border-radius: var(--radius) !important;
      box-shadow: var(--shadow) !important;
    }}
    .ag-theme-streamlit .ag-header,
    .ag-theme-alpine-dark .ag-header {{
      background: var(--panel2) !important;
      border-bottom: 1px solid var(--line) !important;
    }}
    .ag-theme-streamlit .ag-header-cell-label,
    .ag-theme-alpine-dark .ag-header-cell-label {{
      font-weight: 700 !important;
      font-size: 12px !important;
    }}
    .ag-theme-streamlit .ag-row,
    .ag-theme-alpine-dark .ag-row {{
      border-color: var(--line) !important;
    }}
    .ag-theme-streamlit .ag-row-selected,
    .ag-theme-alpine-dark .ag-row-selected {{
      background: var(--badge-ok-bg) !important;
    }}

    /* Scrollbar refuerzo */
    div[data-testid="stDataFrame"] > div,
    div[data-testid="stDataEditor"] > div {{
      overflow: auto !important;
    }}
    *::-webkit-scrollbar {{ height: 12px; width: 12px; }}
    *::-webkit-scrollbar-thumb {{ background: rgba(255,255,255,0.18); border-radius: 10px; }}
    *::-webkit-scrollbar-thumb:hover {{ background: rgba(255,255,255,0.28); }}

    /* Mode tabs styling */
    .vg-mode-tabs {{
      margin-bottom: var(--sp-md);
    }}

    /* Dialog styling */
    div[data-testid="stDialog"] {{
      background: var(--panel) !important;
      border: 1px solid var(--line) !important;
    }}
    </style>
    """
    st.markdown(css, unsafe_allow_html=True)


def apply_layout(max_width: int = 1400):
    """Controla ancho maximo y densidad del contenedor principal (Sprint 5)."""
    st.markdown(f"""
    <style>
    .main .block-container {{
        max-width: {max_width}px;
        margin-left: auto;
        margin-right: auto;
        padding-left: 2rem;
        padding-right: 2rem;
    }}
    @media (max-width: 768px) {{
        .main .block-container {{
            max-width: 100%;
            padding-left: 1rem;
            padding-right: 1rem;
        }}
    }}
    </style>
    """, unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
# COMPONENTES UI (Sprint 2 + Sprint 5)
# ══════════════════════════════════════════════════════════════════════════════

def card_begin(title: str | None = None, subtitle: str | None = None, variant: str = "default"):
    """Apertura de tarjeta sencilla con estilos basados en tokens."""
    classes = ["vg-card"]
    if variant in {"tight", "compact"}:
        classes.append("tight")
    st.markdown(f"<div class='{' '.join(classes)}'>", unsafe_allow_html=True)
    if title:
        st.markdown(f"<h4>{title}</h4>", unsafe_allow_html=True)
    if subtitle:
        st.markdown(f"<div class='subtitle'>{subtitle}</div>", unsafe_allow_html=True)


def card_end():
    """Cierre de tarjeta abierta con card_begin."""
    st.markdown("</div>", unsafe_allow_html=True)


def pill(text: str, kind: str = "default"):
    safe_kind = "".join(ch for ch in (kind or "").lower() if ch.isalnum() or ch in ("-", "_"))
    cls = f" vg-pill pill-{safe_kind}" if safe_kind and safe_kind != "default" else " vg-pill"
    st.markdown(
        f"<span class='{cls.strip()}'>{html.escape(str(text))}</span>",
        unsafe_allow_html=True,
    )


def kpi_card(label: str, value, status: str | None = None,
             tone: str = "neutral", delta: str | None = None):
    """
    Tarjeta KPI compacta con estado visual. tone: neutral|good|warn|bad.
    """
    tone_alias = {"ok": "good", "error": "bad"}
    tone_key = tone_alias.get(tone or "neutral", tone or "neutral")
    tone_class = f"tone-{tone_key}"
    status_text = status or delta or ""
    status_html = (
        f"<div class='kpi-status'><span class='kpi-dot'></span><span>{html.escape(str(status_text))}</span></div>"
        if status_text else ""
    )
    st.markdown(f"""
    <div class="vg-kpi-card {tone_class}">
      <div class="kpi-label">{html.escape(str(label))}</div>
      <div class="kpi-value">{html.escape(str(value))}</div>
      {status_html}
    </div>
    """, unsafe_allow_html=True)


def section_header(title: str, subtitle: str | None = None, meta: list[str] | None = None):
    """Header de sección compacto con fila meta opcional."""
    sub = f"<div class='vg-subtitle'>{html.escape(subtitle)}</div>" if subtitle else ""
    st.markdown(f"""
    <div class="vg-section-header">
      <div class="vg-section-text">
        <h3>{html.escape(title)}</h3>
        {sub}
      </div>
    </div>
    """, unsafe_allow_html=True)
    if meta:
        chips = "".join(f"<span class='vg-pill'>{html.escape(str(item))}</span>" for item in meta)
        st.markdown(f"<div class='vg-section-meta'>{chips}</div>", unsafe_allow_html=True)


def progress_row(label: str, pct: float):
    """Barra de progreso horizontal con label y porcentaje (Sprint 2)."""
    pct = max(0, min(100, pct))
    tone = "good" if pct >= 80 else "warn" if pct >= 50 else "bad"
    st.markdown(f"""
    <div class="vg-progress-row {tone}">
      <span class="vg-progress-label">{html.escape(str(label))}</span>
      <div class="vg-progress-bar-bg">
        <div class="vg-progress-bar-fill" style="width:{pct:.0f}%"></div>
      </div>
      <span class="vg-progress-pct">{pct:.1f}%</span>
    </div>
    """, unsafe_allow_html=True)


def audit_status_badge(errores: int, warnings: int):
    """Badge de estado del sistema para Auditoria (Sprint 4)."""
    if errores == 0 and warnings == 0:
        cls = "optimo"
        text = "Optimo - Sin problemas detectados"
    elif errores == 0:
        cls = "atencion"
        text = f"Atencion - {warnings} advertencia(s)"
    else:
        cls = "error"
        text = f"Error - {errores} error(es), {warnings} advertencia(s)"
    st.markdown(f"""
    <div class="vg-badge-status {cls}">{text}</div>
    """, unsafe_allow_html=True)


def ui_header_principal(casos_total: int | None = None):
    """Header principal de la app (Sprint 0: sin sandwich pattern)."""
    container = st.container()
    with container:
        left, right = st.columns([0.75, 0.25])
        with left:
            st.markdown("### VACA & GENTILE")
            st.caption("Sistema interno de gestión de causas • ERP v1.0")
        with right:
            if casos_total is not None:
                st.markdown(f"**Casos:** {casos_total}")
        st.divider()


# ══════════════════════════════════════════════════════════════════════════════
# PRIMITIVAS UI v2
# ══════════════════════════════════════════════════════════════════════════════

def page_header(title: str, subtitle: str | None = None,
                right_actions: list | None = None,
                context_badges: list | None = None):
    """Header de pagina reutilizable con titulo, subtitulo, badges y acciones."""
    right_actions = right_actions or []
    context_badges = context_badges or []

    header = st.container()
    with header:
        left, right = st.columns([0.75, 0.25])
        with left:
            st.markdown(f"## {title}")
            if subtitle:
                st.caption(subtitle)
            for badge in context_badges:
                # Permitir badges HTML existentes, pero sin exponer tags sueltos
                st.markdown(badge, unsafe_allow_html=True) if "<" in badge else st.caption(badge)
        with right:
            if right_actions:
                for action in right_actions:
                    st.markdown(action, unsafe_allow_html=True) if isinstance(action, str) else st.write(action)


def section(title: str, help_text: str | None = None):
    """Seccion con header consistente. Retorna un st.container para usar como contexto."""
    st.markdown(f"""
    <div class="vg-section-header" style="margin-top:var(--sp-md);margin-bottom:var(--sp-sm);">
      <h3 style="margin:0;font-size:16px;font-weight:700;color:var(--text);">{title}</h3>
    </div>
    """, unsafe_allow_html=True)
    if help_text:
        help_section(f"sec_{title.lower().replace(' ', '_')}", title, help_text)
    return st.container()


def toolbar(left_cols: int = 8, right_cols: int = 2):
    """Toolbar con columnas izquierda/derecha. Retorna tupla (col_left, col_right)."""
    return st.columns([left_cols, right_cols])


def _vh_to_px(vh: int) -> int:
    """Convierte vh aproximado a px (Streamlit no expone viewport real)."""
    return int(vh * 7.2)


def render_grid(df, *, key: str, height_vh: int = 65, editable: bool = False,
                selection_mode: str | None = None, column_config: dict | None = None,
                hide_index: bool = True):
    """Grilla unificada con altura fija, scroll, y boton de pantalla completa."""
    height_pixels = _vh_to_px(height_vh)

    # Boton ampliar
    col_grid, col_fs = st.columns([11, 1])
    with col_fs:
        if st.button("Ampliar", key=f"{key}_fs_btn"):
            st.session_state[f"{key}_fs_open"] = True

    # Kwargs base
    kw = {
        "use_container_width": True,
        "hide_index": hide_index,
        "height": height_pixels,
    }
    if column_config:
        kw["column_config"] = column_config
    if selection_mode:
        sel_kw = _df_select_kwargs()
        kw.update(sel_kw)

    # Render principal
    with col_grid:
        if editable:
            event = st.data_editor(df, key=f"{key}_ed", **kw)
        else:
            event = st.dataframe(df, key=f"{key}_df", **kw)

    # Pantalla completa via dialog (con fallback)
    if st.session_state.get(f"{key}_fs_open", False):
        _has_dialog = hasattr(st, "dialog")
        if _has_dialog:
            @st.dialog("Vista ampliada", width="large")
            def _fullscreen_dlg():
                kw_fs = {
                    "use_container_width": True,
                    "hide_index": hide_index,
                    "height": _vh_to_px(85),
                }
                if column_config:
                    kw_fs["column_config"] = column_config
                if editable:
                    st.data_editor(df, key=f"{key}_fs_ed", **kw_fs)
                else:
                    st.dataframe(df, key=f"{key}_fs_df", **kw_fs)
                if st.button("Cerrar", key=f"{key}_fs_close"):
                    st.session_state[f"{key}_fs_open"] = False
                    st.rerun()
            _fullscreen_dlg()
        else:
            with st.expander("Vista ampliada", expanded=True):
                kw_fb = {
                    "use_container_width": True,
                    "hide_index": hide_index,
                    "height": _vh_to_px(85),
                }
                if column_config:
                    kw_fb["column_config"] = column_config
                if editable:
                    st.data_editor(df, key=f"{key}_fb_ed", **kw_fb)
                else:
                    st.dataframe(df, key=f"{key}_fb_df", **kw_fb)
                if st.button("Cerrar", key=f"{key}_fb_close"):
                    st.session_state[f"{key}_fs_open"] = False
                    st.rerun()

    return event


# Sprint 0: centro de ayuda sin sandwich div pattern
def ui_centro_ayuda():
    if not st.session_state.get("ui_help_open", False):
        return

    st.markdown("### Centro de ayuda")
    st.caption("Guia operativa breve, criterios de orden y solucion de problemas tipicos (Windows/OneDrive).")
    if st.button("Cerrar ayuda", use_container_width=True, key="help_close_btn"):
        st.session_state["ui_help_open"] = False
        st.rerun()

    st.markdown("---")
    ui_centro_ayuda_content()


def ui_centro_ayuda_content():
    """Contenido del centro de ayuda (para usar en Ajustes o standalone)."""
    tab1, tab2, tab3, tab4 = st.tabs(["Uso basico", "Planilla", "Carpetas", "Problemas tipicos"])

    with tab1:
        st.markdown("""
**Flujo recomendado:**
1) Ir a **Gestion** > buscar o seleccionar un caso > ver ficha.
2) Usar **Edicion rapida** para mantener: responsable, tarea y fecha.
3) Usar la **Agenda** como tablero diario/semana.
4) Cargar **Finanzas** solo cuando el caso esta razonablemente maduro.
""")
        st.info("Criterio de calidad: cada caso deberia tener al menos Responsable + Tarea + Fecha.")

    with tab2:
        st.markdown("""
**Atajos utiles:**
- "Priorizar urgentes": pone los vencidos y proximos primero.
- "Proximos 7/30 dias": arma una cola de ejecucion.
- Vista "Tarjetas": util en movil o para revisar rapido.
""")

    with tab3:
        st.markdown("""
**Estructura estandar por caso:**
- 01. PRUEBA
- 02. ESCRITOS
- 03. RECIBOS
- 04. OTROS

La auditoria marca como WARN cuando falta alguna.
""")

    with tab4:
        st.markdown("""
**OneDrive / Windows:**
- "Origen retenido": OneDrive puede dejar carpetas fantasma durante sincronizacion.
- "Ruta muy larga": cerca de 240+ caracteres aparecen errores reales de I/O.
- Encoding roto: reescribir desde el ERP para normalizar UTF-8.
""")
        st.info("Recomendacion: evitar nombres de causa demasiado largos.")


# Sprint 0: onboarding sin sandwich div pattern
def ui_onboarding():
    if st.session_state.get("ui_onboarding_ok", False):
        return

    st.markdown("### Inicio rapido")
    st.markdown("""
1) Ir a **Gestion > Casos** y filtrar por vencidos o proximos.
2) Entrar al caso > "Abrir carpeta" > trabajar sobre **02. ESCRITOS**.
3) Volver y completar **Responsable / Tarea / Fecha** (edicion rapida).
4) Revisar **Agenda** para priorizacion diaria/semana.
""")
    if st.button("No mostrar", key="onb_hide", use_container_width=True):
        st.session_state["ui_onboarding_ok"] = True
        _ui_toast("Onboarding ocultado")
        st.rerun()


def help_section(key: str, title: str, body_md: str):
    """Ayuda contextual reutilizable como expander colapsable."""
    with st.expander(f"Ayuda: {title}", expanded=False):
        st.markdown(body_md)


def configurar_pagina():
    """Configuracion inicial de Streamlit + inicializacion UI."""
    st.set_page_config(
        page_title="VACA & GENTILE ERP v1.0",
        page_icon="⚖️",
        layout="wide",
        initial_sidebar_state="expanded"
    )
    _ui_init_state()
    aplicar_tema()
    width = st.session_state.get("layout_width", 1400)
    apply_layout(max_width=width)


# ══════════════════════════════════════════════════════════════════════════════
# PRIMITIVAS UX v3 — Modos excluyentes
# ══════════════════════════════════════════════════════════════════════════════

MODE_LABELS = {"listado": "Listado", "detalle": "Detalle", "editar": "Editar"}


def mode_tabs(current_mode: str, enabled_modes: list | None = None, key: str = "mode_tabs") -> str:
    """Pills de modo: Listado / Detalle / Editar. Retorna el modo seleccionado."""
    if enabled_modes is None:
        enabled_modes = ["listado", "detalle", "editar"]
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

    # Si cambio de modo, actualizar session_state
    if selected_mode != st.session_state.get("route_mode"):
        st.session_state["route_mode"] = selected_mode

    return selected_mode


def empty_state(title: str, body: str, cta_label: str | None = None,
                cta_callback=None):
    """Estado vacio centrado con titulo, descripcion y CTA opcional."""
    st.markdown(f"""
    <div class="vg-soft-block" style="padding:40px 20px;">
      <p style="font-size:18px;font-weight:700;color:var(--text);margin-bottom:8px;">{title}</p>
      <p style="font-size:14px;color:var(--muted);">{body}</p>
    </div>
    """, unsafe_allow_html=True)
    if cta_label and cta_callback:
        if st.button(cta_label, use_container_width=True, key=f"es_cta_{id(cta_callback)}"):
            cta_callback()


def empty_state_nav(title: str, body: str, cta_label: str | None = None,
                    cta_module: str | None = None, cta_mode: str = "listado"):
    """Estado vacio con navegacion a modulo (legacy compat)."""
    st.markdown(f"""
    <div class="vg-soft-block" style="padding:40px 20px;">
      <p style="font-size:18px;font-weight:700;color:var(--text);margin-bottom:8px;">{title}</p>
      <p style="font-size:14px;color:var(--muted);">{body}</p>
    </div>
    """, unsafe_allow_html=True)
    if cta_label and cta_module:
        if st.button(cta_label, use_container_width=True, key=f"es_cta_{cta_module}"):
            from nav import navigate_to
            # Map old module names to new routes
            route_map = {
                "panel": "Dashboard", "casos": "Gestion", "cliente": "Gestion",
                "agenda": "Gestion", "finanzas": "Gestion",
            }
            navigate_to(route_map.get(cta_module, "Dashboard"), cta_mode)


def grid_shell(title: str, subtitle: str | None = None, fluid: bool = True):
    """Shell para modo listado: aplica layout fluid si corresponde."""
    if fluid:
        st.markdown("""
        <style>
        .main .block-container { max-width: 100% !important; }
        </style>
        """, unsafe_allow_html=True)

    page_header(title, subtitle=subtitle)


def detail_shell(title: str, badges: list | None = None):
    """Shell para modo detalle: header con badges."""
    badges_html = ""
    if badges:
        badges_html = " ".join(badges)
    page_header(title, context_badges=[badges_html] if badges_html else None)


def edit_shell(title: str, steps: list[str], current_step: int,
               key: str = "edit_wizard") -> int:
    """Shell para modo editar: wizard por pasos. Retorna el step seleccionado."""
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


# ══════════════════════════════════════════════════════════════════════════════
# HELPERS DE ESTADO
# ══════════════════════════════════════════════════════════════════════════════

def _df_select_kwargs():
    """Habilita seleccion de fila si la version de Streamlit lo soporta."""
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


def _ensure_bool_state(key: str, default: bool = False):
    v = st.session_state.get(key, default)
    if not isinstance(v, bool):
        st.session_state[key] = default


def _ensure_int_step_state(key: str, min_v: int, max_v: int, step: int, default: int):
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


def _swap(lst, i, j):
    if 0 <= i < len(lst) and 0 <= j < len(lst):
        lst[i], lst[j] = lst[j], lst[i]
    return lst


# ══════════════════════════════════════════════════════════════════════════════
# BARRA LATERAL (Sprint 1: marca arriba + config colapsada)
# ══════════════════════════════════════════════════════════════════════════════

def barra_lateral_config(gestor: 'GestorCasos'):
    """Sidebar: marca arriba, botones operativos, config en expander."""
    # Marca / branding
    st.sidebar.markdown("""
        <div class="vg-card-tight" style="margin:8px 8px 10px 8px;">
          <p style="font-weight:800;letter-spacing:.3px;color:var(--brand);font-size:16px;margin:0;">VACA & GENTILE</p>
          <p style="color:var(--muted);font-size:12px;margin:4px 0 0 0;">Gestion juridica &bull; v1.0</p>
        </div>
    """, unsafe_allow_html=True)

    # Botones operativos
    if st.sidebar.button("Abrir carpeta base", use_container_width=True):
        open_path(RUTA_BASE, st.sidebar)

    if st.sidebar.button("Recargar datos", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

    st.sidebar.markdown("---")

    # Navegacion primaria va AQUI (se inserta desde app.py via nav.get_route())

    # Configuracion colapsada (Sprint 1)
    with st.sidebar.expander("Configuracion", expanded=False):
        st.radio("Tema", ["Claro", "Oscuro"], horizontal=True, key="ui_tema")
        aplicar_tema()

        st.slider("Ancho contenido", min_value=1000, max_value=1800,
                  value=1400, step=100, key="layout_width")

        st.toggle("Modo seguro", value=True, key="modo_seguro",
                  help="Requiere confirmacion para mover carpetas")

        st.toggle("Auto-crear subcarpetas", value=False, key="auto_normalize",
                  help="Crea subcarpetas estandar al abrir un caso")

    # Footer
    st.sidebar.markdown("---")
    try:
        port = st.get_option("server.port") or 8501
        ip = socket.gethostbyname(socket.gethostname())
        st.sidebar.caption(f"Local: http://localhost:{port}")
        st.sidebar.caption(f"Red: http://{ip}:{port}")
    except Exception:
        pass

    st.sidebar.caption(f"Ruta: {RUTA_BASE}")
    st.sidebar.caption(f"Actualizado: {datetime.now().strftime('%H:%M:%S')}")
