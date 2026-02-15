"""
Modelo de datos principal del dominio legal.
"""

from dataclasses import dataclass, field
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, List

from config import CAMPOS_FICHA


@dataclass
class Caso:
    """Representación de un caso jurídico - Unidad atómica del sistema."""
    # Datos estructurales (inferidos de carpetas)
    ruta: Path
    año: str
    estado: str
    cliente: str
    fuero: str
    causa: str

    # Datos de ficha.txt
    tipo_proceso: str = "S/D"
    jurisdiccion: str = "S/D"
    organismo: str = "S/D"
    expediente: str = "S/D"
    caratula: str = "S/D"
    responsable: str = "S/D"
    control: str = "S/D"
    evento: str = "S/D"
    fecha_evento: str = ""
    tarea_pendiente: str = "S/D"
    fecha_tarea: str = ""
    observaciones: str = ""
    # Ruta original en filesystem cuando el caso fue importado (DB: cases.fs_path)
    fs_path: str = ""
    # Flag explícito de caso legacy importado
    is_legacy: bool = False

    @property
    def semaforo(self) -> str:
        """Calcula el semáforo según la fecha de tarea pendiente."""
        if not self.fecha_tarea or self.fecha_tarea == "S/D":
            return "⚪"  # Sin tarea programada

        try:
            fecha = self._parsear_fecha(self.fecha_tarea)
            if fecha is None:
                return "⚪"

            hoy = datetime.now().date()
            delta = (fecha - hoy).days

            if delta < 0:
                return "🔴"  # Vencido
            elif delta <= 7:
                return "🟡"  # Próximo a vencer (7 días)
            else:
                return "🟢"  # En tiempo
        except Exception:
            return "⚪"

    def _parsear_fecha(self, fecha_str: str) -> Optional[datetime]:
        """Intenta parsear una fecha en múltiples formatos."""
        formatos = [
            "%d/%m/%Y %H:%M", "%Y-%m-%d %H:%M",  # con hora
            "%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y", "%d.%m.%Y",  # solo fecha
        ]
        for fmt in formatos:
            try:
                return datetime.strptime(fecha_str.strip(), fmt).date()
            except ValueError:
                continue
        return None

    def to_dict(self) -> Dict:
        """Convierte el caso a diccionario para DataFrame."""
        status_info = case_status(self)

        estado_calidad_map = {
            "error": "ERROR",
            "legacy_incomplete": "LEGACY",
            "ok": "OK",
        }
        estado_calidad = estado_calidad_map.get(status_info["status"], "OK")

        def _norm(v):
            return "" if v is None else v

        return {
            "AÑO": self.año,
            "ESTADO": self.estado,
            "CLIENTE": self.cliente,
            "FUERO": self.fuero,
            "CAUSA": self.causa,
            "TIPO PROCESO": _norm(self.tipo_proceso),
            "JURISDICCION": _norm(self.jurisdiccion),
            "ORGANISMO": _norm(self.organismo),
            "EXPEDIENTE": _norm(self.expediente),
            "CARATULA": _norm(self.caratula),
            "RESPONSABLE": _norm(self.responsable),
            "CONTROL": _norm(self.control),
            "EVENTO": _norm(self.evento),
            "FECHA EVENTO": _norm(self.fecha_evento),
            "TAREA PENDIENTE": _norm(self.tarea_pendiente),
            "FECHA TAREA": _norm(self.fecha_tarea),
            "OBSERVACIONES": _norm(self.observaciones),
            "SEMÁFORO": self.semaforo,
            "LEGACY": "LEGACY - incompleto" if status_info["is_legacy"] else "",
            "is_legacy": status_info["is_legacy"],
            "ESTADO DATOS": estado_calidad,
            "estado_calidad": estado_calidad,
            "_LEGACY": status_info["is_legacy"],
            "_STATUS": status_info["status"],
            "_MISSING_MIN": "; ".join(status_info["missing_minimum"]),
            "_MISSING_QUALITY": "; ".join(status_info["missing_quality"]),
            "_RUTA": str(self.ruta)  # Columna oculta para referencia
        }


@dataclass
class TaskRecord:
    """Representa una tarea operativa de agenda (tabla tasks)."""
    id: str
    case_id: str
    case_ref: str
    title: str
    description: str = ""
    due_date: str = ""
    priority: str = "normal"
    status: str = "pendiente"
    assigned_to: str = ""
    completed_at: str = ""
    created_at: str = ""
    updated_at: str = ""
    client_name: str = ""
    case_causa: str = ""
    case_estado: str = ""
    extra: Dict[str, object] = field(default_factory=dict)


@dataclass
class GoogleCalendarConnection:
    """Conexion OAuth de un usuario a Google Calendar."""
    id: str
    user_id: str
    google_email: str = ""
    calendar_id: str = "primary"
    refresh_token_enc: str = ""
    scope: str = ""
    sync_token: str = ""
    status: str = "active"
    created_at: str = ""
    updated_at: str = ""
    last_sync_at: str = ""
    extra: Dict[str, object] = field(default_factory=dict)


@dataclass
class GoogleEventMap:
    """Mapeo entre task interna y evento Google Calendar."""
    id: str
    task_id: str
    connection_id: str
    google_event_id: str
    google_etag: str = ""
    google_updated_at: str = ""
    last_local_updated_at: str = ""
    is_deleted: bool = False
    created_at: str = ""
    updated_at: str = ""


def is_blank(value) -> bool:
    """
    Considera vacío/nulo cualquier valor None, string vacía o "S/D".
    Se usa para validar completitud de campos de manera consistente.
    """
    if value is None:
        return True
    s = str(value).strip()
    return s == "" or s.upper() == "S/D"


def _get_campo(caso, campo: str):
    """
    Obtiene un campo desde objeto Caso o diccionario usando los nombres de CAMPOS_FICHA.
    """
    attr = campo.lower()
    if hasattr(caso, attr):
        return getattr(caso, attr)
    if isinstance(caso, dict):
        return caso.get(campo) or caso.get(attr) or caso.get(campo.lower())
    return None


def case_status(caso) -> Dict[str, object]:
    """
    Fuente de verdad única para el estado de un caso.

    Returns:
        dict con:
            - is_legacy: bool
            - missing_minimum: list[str]
            - missing_quality: list[str]
            - has_minimum: bool
            - status: "ok" | "legacy_incomplete" | "error"
    """
    # Indicador robusto de legacy: flag explícito o fs_path poblado
    try:
        is_legacy = bool(getattr(caso, "is_legacy", False))
    except Exception:
        is_legacy = False
    try:
        fs_path_val = getattr(caso, "fs_path", None) if not isinstance(caso, dict) else caso.get("fs_path")
        is_legacy = is_legacy or bool(fs_path_val)
    except Exception:
        pass

    min_fields = {"RESPONSABLE"}
    quality_fields = [c for c in CAMPOS_FICHA if c not in min_fields]

    missing_minimum: List[str] = []
    missing_quality: List[str] = []

    for campo in CAMPOS_FICHA:
        val = _get_campo(caso, campo)
        if is_blank(val):
            if campo in min_fields:
                missing_minimum.append(campo)
            elif campo in quality_fields:
                missing_quality.append(campo)

    has_minimum = len(missing_minimum) == 0

    if missing_minimum:
        status = "error"
    elif is_legacy and missing_quality:
        status = "legacy_incomplete"
    else:
        status = "ok"

    return {
        "is_legacy": is_legacy,
        "missing_minimum": missing_minimum,
        "missing_quality": missing_quality,
        "has_minimum": has_minimum,
        "status": status,
    }
