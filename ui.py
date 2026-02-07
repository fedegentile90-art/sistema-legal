import streamlit as st
from typing import Any

# --- DESIGN SYSTEM: STITCH ---
# Definición centralizada de variables visuales (Tokens)

TOKENS = {
    "colors": {
        "dark": {
            "bg_app": "#0B1220",       # Deep Navy Background
            "bg_sidebar": "#111827",   # Gray 900
            "bg_card": "#1F2937",      # Gray 800
            "bg_card_hover": "#374151",# Gray 700
            "border": "rgba(55, 65, 81, 0.5)", # Gray 700 con opacidad
            "text_main": "#F9FAFB",    # Gray 50
            "text_muted": "#9CA3AF",   # Gray 400
            "primary": "#2563EB",      # Blue 600
            "primary_hover": "#1D4ED8",# Blue 700
            "success": "#10B981",      # Emerald 500
            "warning": "#F59E0B",      # Amber 500
            "danger": "#EF4444",       # Red 500
            "badge_bg": "rgba(255,255,255,0.05)",
        },
        "light": {
            "bg_app": "#F3F4F6",
            "bg_sidebar": "#FFFFFF",
            "bg_card": "#FFFFFF",
            "bg_card_hover": "#F9FAFB",
            "border": "#E5E7EB",
            "text_main": "#111827",
            "text_muted": "#6B7280",
            "primary": "#2563EB",
            "primary_hover": "#1D4ED8",
            "success": "#059669",
            "warning": "#D97706",
            "danger": "#DC2626",
            "badge_bg": "rgba(0,0,0,0.05)",
        }
    },
    "typography": {
        "font_family": '"Inter", -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
        "h1": "1.875rem",
        "h2": "1.5rem",
        "body": "1rem",
        "small": "0.875rem"
    },
    "radius": {
        "sm": "0.375rem",
        "md": "0.5rem",
        "lg": "0.75rem",
        "full": "9999px"
    },
    "shadows": {
        "card": "0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06)",
        "glow": "0 0 15px rgba(37, 99, 235, 0.2)"
    }
}

# --- GESTIÓN DE ESTADO Y TEMA ---

def inicializar_ui():
    """Configura variables de sesión iniciales para la UI."""
    if 'theme_mode' not in st.session_state:
        st.session_state.theme_mode = 'dark'  # Default a Stitch Dark

def get_current_theme():
    """Retorna el diccionario de colores para el tema actual."""
    mode = st.session_state.get('theme_mode', 'dark')
    return TOKENS["colors"][mode]

def toggle_theme():
    """Alterna entre modo claro y oscuro."""
    current = st.session_state.get('theme_mode', 'dark')
    st.session_state.theme_mode = 'light' if current == 'dark' else 'dark'

# --- CONFIGURACION BASE ---

def configurar_pagina():
    """Configura Streamlit y prepara el tema Stitch."""
    st.set_page_config(
        page_title="VACA & GENTILE ERP v1.0",
        page_icon="⚖️",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    inicializar_ui()

# --- INYECCIÓN DE CSS (CORE) ---

def aplicar_estilos_stitch():
    """Inyecta el CSS global para transformar Streamlit en el diseño Stitch."""
    t = get_current_theme()
    ty = TOKENS["typography"]
    
    # Fuentes e Iconos
    st.markdown("""
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
        @import url('https://fonts.googleapis.com/icon?family=Material+Symbols+Rounded');
        </style>
    """, unsafe_allow_html=True)
    
    # CSS Dinámico
    css = f"""
    <style>
        /* --- GLOBAL RESET --- */
        .stApp {{
            background-color: {t['bg_app']};
            font-family: {ty['font_family']};
        }}
        
        h1, h2, h3, h4, h5, h6 {{
            color: {t['text_main']} !important;
            font-weight: 600 !important;
        }}
        
        p, span, label, div, li {{
            color: {t['text_muted']};
        }}

        /* --- SIDEBAR --- */
        section[data-testid="stSidebar"] {{
            background-color: {t['bg_sidebar']};
            border-right: 1px solid {t['border']};
        }}
        
        /* Ocultar elementos nativos no deseados del sidebar */
        section[data-testid="stSidebar"] .block-container {{
            padding-top: 2rem;
        }}
        
        /* --- WIDGETS ESTILIZADOS --- */
        
        /* Botones Primarios */
        .stButton button {{
            background-color: {t['primary']};
            color: white !important;
            border: none;
            border-radius: {TOKENS['radius']['md']};
            padding: 0.5rem 1rem;
            font-weight: 500;
            transition: all 0.2s ease;
        }}
        .stButton button:hover {{
            background-color: {t['primary_hover']};
            box-shadow: {TOKENS['shadows']['glow']};
        }}
        
        /* Botones Secundarios (Outline) - Usaremos una clase custom o lógica css específica si es necesario */
        
        /* Inputs & Selects */
        .stTextInput input, .stSelectbox div[data-baseweb="select"] > div {{
            background-color: {t['bg_app']};
            color: {t['text_main']};
            border: 1px solid {t['border']};
            border-radius: {TOKENS['radius']['md']};
        }}
        
        /* Dataframes */
        div[data-testid="stDataFrame"] {{
            background-color: {t['bg_card']};
            border: 1px solid {t['border']};
            border-radius: {TOKENS['radius']['lg']};
            padding: 0.5rem;
        }}
        
        /* --- CLASES UTILITARIAS STITCH (Usadas en st.markdown) --- */
        
        /* Tarjeta Estándar */
        .stitch-card {{
            background-color: {t['bg_card']};
            border: 1px solid {t['border']};
            border-radius: {TOKENS['radius']['lg']};
            padding: 1.5rem;
            margin-bottom: 1.5rem;
            box-shadow: {TOKENS['shadows']['card']};
        }}
        
        /* Texto */
        .text-main {{ color: {t['text_main']} !important; }}
        .text-primary {{ color: {t['primary']} !important; }}
        .text-sm {{ font-size: {ty['small']}; }}
        .font-bold {{ font-weight: 600; }}
        
        /* Badges */
        .stitch-badge {{
            display: inline-flex;
            align-items: center;
            padding: 0.25rem 0.75rem;
            border-radius: {TOKENS['radius']['full']};
            font-size: 0.75rem;
            font-weight: 600;
            background-color: {t['badge_bg']};
            border: 1px solid transparent;
        }}
        
    </style>
    """
    st.markdown(css, unsafe_allow_html=True)

# --- COMPONENTES UI REUTILIZABLES (FASE 1) ---

def stitch_header(titulo, subtitulo=None):
    """Renderiza el header principal de la página."""
    html = f"""
    <div style="margin-bottom: 2rem;">
        <h1 style="font-size: 1.875rem; margin-bottom: 0.5rem;">{titulo}</h1>
        {f'<p style="font-size: 1rem; opacity: 0.8;">{subtitulo}</p>' if subtitulo else ''}
    </div>
    """
    st.markdown(html, unsafe_allow_html=True)

# Placeholder para helper de tarjetas - Se expandirá en Fase 2
def container_card_start():
    st.markdown('<div class="stitch-card">', unsafe_allow_html=True)

def container_card_end():
    st.markdown('</div>', unsafe_allow_html=True)


# --- SIDEBAR / CONTROLES GLOBALES ---

def barra_lateral_config(gestor: Any = None):
    """Sidebar con branding, acciones rápidas y selector de tema."""
    st.sidebar.markdown(
        """
        <div style="padding:12px 10px 6px 10px;border-bottom:1px solid rgba(255,255,255,0.08);">
            <p style="font-weight:800;letter-spacing:.3px;color:#F9FAFB;font-size:16px;margin:0;">VACA &amp; GENTILE</p>
            <p style="color:#9CA3AF;font-size:12px;margin:4px 0 0 0;">Gestión jurídica · v1.0</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Acción: abrir carpeta base (solo si existe y sistema soporta)
    if st.sidebar.button("Abrir carpeta base", use_container_width=True):
        try:
            from config import RUTA_BASE
            import os

            os.startfile(str(RUTA_BASE))
        except Exception as exc:  # pragma: no cover - UI feedback
            st.sidebar.error(f"No se pudo abrir la ruta base: {exc}")

    if st.sidebar.button("Recargar datos", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

    st.sidebar.markdown("---")

    # Selector de tema (dark por defecto)
    current = st.session_state.get("theme_mode", "dark")
    option = st.sidebar.radio(
        "Tema",
        ["Oscuro (Deep Navy)", "Claro"],
        index=0 if current == "dark" else 1,
        key="stitch_theme_selector",
        label_visibility="collapsed",
    )
    st.session_state.theme_mode = "dark" if option.startswith("Oscuro") else "light"

    st.sidebar.caption("UI · Stitch Design System")
