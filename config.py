"""
Configuracion y constantes del sistema VACA & GENTILE ERP v1.0.
"""

import re
import os
from pathlib import Path

# ══════════════════════════════════════════════════════════════════════════════
# CONFIGURACION RAIZ
# ══════════════════════════════════════════════════════════════════════════════

_RUTA_BASE_DEFAULT = r"C:\Users\Pc\Desktop\Derecho y Comunidad Ética\01. Clientes y Casos"
RUTA_BASE = Path(os.environ.get("VG_RUTA_BASE", _RUTA_BASE_DEFAULT))

# Años a escanear (explícitos para control)
AÑOS_ACTIVOS = ["2024", "2025", "2026"]

# Carpetas internas del caso a IGNORAR (no son casos, son subcarpetas)
IGNORAR_CARPETAS_INTERNAS = [
    "1. Prueba", "2. Escritos", "3. Recibos", "4. Otros", "ficha.txt",
    "01. Prueba", "02. Escritos", "03. Recibos", "04. Otros",
    "01. PRUEBA", "02. ESCRITOS", "03. RECIBOS", "04. OTROS",
    "Prueba", "Escritos", "Recibos", "Otros", "PRUEBA", "ESCRITOS"
]

# Fueros a ignorar completamente
FUEROS_IGNORAR = ["100. DOCUMENTOS GENERALES"]

# Patrones para ignorar archivos/carpetas basura del sistema
IGNORAR_SISTEMA = {'.git', '__pycache__', '.idea', 'desktop.ini', 'Thumbs.db'}
IGNORAR_PATRONES = {'~$', '.tmp', '.temp'}

# Archivos de ficha (JSON canónico, TXT legacy)
FICHA_JSON = "ficha.json"
FICHA_TXT = "ficha.txt"
CASE_ID_FILE = ".vg_case_id"

# Campos financieros (solo en JSON, no contaminan CAMPOS_FICHA ni la planilla principal)
CAMPOS_FINANCIEROS = ['MONTO_DEMANDADO', 'HONORARIOS_PACTADOS', 'ESTADO_PAGO']
ESTADOS_PAGO = ['Pendiente', 'Parcial', 'Cobrado', 'Pro bono', '']

# Campos del archivo ficha.txt
CAMPOS_FICHA = [
    'TIPO_PROCESO', 'JURISDICCION', 'ORGANISMO', 'EXPEDIENTE',
    'CARATULA', 'RESPONSABLE', 'CONTROL', 'EVENTO', 'FECHA_EVENTO',
    'TAREA_PENDIENTE', 'FECHA_TAREA', 'OBSERVACIONES'
]

# Mapeo de todas las variaciones posibles de nombres de campos a nombres estándar
MAPEO_CAMPOS_FICHA = {
    # Tipo de Proceso
    'TIPO_DE_PROCESO': 'TIPO_PROCESO',
    'TIPO_PROCESO': 'TIPO_PROCESO',
    'TIPOPROCESO': 'TIPO_PROCESO',

    # Jurisdicción
    'JURISDICCION': 'JURISDICCION',
    'JURISDICCIÓN': 'JURISDICCION',

    # Organismo
    'ORGANISMO': 'ORGANISMO',
    'ORGANISMO/JUZGADO': 'ORGANISMO',
    'ORGANISMO_JUZGADO': 'ORGANISMO',

    # Expediente
    'EXPEDIENTE': 'EXPEDIENTE',
    'N°_EXPEDIENTE': 'EXPEDIENTE',
    'Nº_EXPEDIENTE': 'EXPEDIENTE',
    'N_EXPEDIENTE': 'EXPEDIENTE',
    'NUM_EXPEDIENTE': 'EXPEDIENTE',
    'NUMERO_EXPEDIENTE': 'EXPEDIENTE',

    # Carátula
    'CARATULA': 'CARATULA',
    'CARÁTULA': 'CARATULA',
    'CARATULA_OFICIAL': 'CARATULA',
    'CARÁTULA_OFICIAL': 'CARATULA',

    # Responsable
    'RESPONSABLE': 'RESPONSABLE',

    # Control
    'CONTROL': 'CONTROL',

    # Evento
    'EVENTO': 'EVENTO',

    # Fecha Evento
    'FECHA_EVENTO': 'FECHA_EVENTO',
    'FECHAEVENTO': 'FECHA_EVENTO',

    # Tarea
    'TAREA': 'TAREA_PENDIENTE',
    'TAREA_PENDIENTE': 'TAREA_PENDIENTE',
    'TAREAPENDIENTE': 'TAREA_PENDIENTE',

    # Fecha Tarea
    'FECHA_TAREA': 'FECHA_TAREA',
    'FECHATAREA': 'FECHA_TAREA',
    'FECHA_CONTROL_TAREA': 'FECHA_TAREA',
    'FECHACONTROLTAREA': 'FECHA_TAREA',

    # Observaciones
    'OBSERVACIONES': 'OBSERVACIONES',
    'OBS': 'OBSERVACIONES',
    'OBSERVACION': 'OBSERVACIONES'
}

# Fueros disponibles (basado en estructura real del sistema)
FUEROS_DISPONIBLES = [
    "01. ADMINISTRATIVO",
    "02. CIVIL",
    "03. SOCIEDADES Y ASOCIACIONES",
    "04. LABORAL",
    "05. PENAL",
    "06. FAMILIA",
    "99. OTROS"
]

# Estados disponibles (basado en estructura real del sistema)
ESTADOS_DISPONIBLES = [
    "01. Abonados",
    "02. Activos",
    "03. Pendientes",
    "04. Renunciado",
    "05. Derivado",
    "06. Finalizado",
    "07. Archivado"
]

SUBCARPETAS_ESTANDAR = ["01. PRUEBA", "02. ESCRITOS", "03. RECIBOS", "04. OTROS"]

# Caracteres inválidos para nombres de carpetas en Windows
RE_INVALID_WIN = re.compile(r'[<>:"/\\|?*\x00-\x1F]')

# Caracteres no permitidos en nombres de carpeta de Windows
INVALID_WIN_CHARS = r'<>:"/\\|?*'


def limpiar_nombre_carpeta(nombre: str) -> str:
    """Sanitiza un nombre para usarlo como carpeta en Windows."""
    n = (nombre or "").strip()
    n = re.sub(rf'[{re.escape(INVALID_WIN_CHARS)}]', ' ', n)
    n = re.sub(r'\s+', ' ', n).strip()
    n = n.rstrip(". ")
    if not n or n in {".", ".."}:
        raise ValueError("Nombre inválido.")
    return n


# =============================================================================
# Compatibilidad con UI (app.py) en modo DB-first
# =============================================================================
RUTA_BASE_AUTO_CREATE = False


def get_ruta_base_info() -> dict:
    """
    Compatibilidad: la UI antigua esperaba información de carpeta base.
    En DB-first devolvemos un shape estable.
    """
    return {
        "mode": "database",
        "ruta_base": "N/A (DB mode)",
        "auto_create": "no",
        "exists": "N/A",
    }


def _is_container_env() -> bool:
    """
    Compatibilidad legacy para UI.
    En DB-first local/desktop asumimos NO container por defecto.
    """
    return False
