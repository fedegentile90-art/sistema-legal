"""
Modelo de datos: Caso juridico (unidad atomica del sistema).
"""

from dataclasses import dataclass
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict


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
        return {
            "AÑO": self.año,
            "ESTADO": self.estado,
            "CLIENTE": self.cliente,
            "FUERO": self.fuero,
            "CAUSA": self.causa,
            "TIPO PROCESO": self.tipo_proceso,
            "JURISDICCION": self.jurisdiccion,
            "ORGANISMO": self.organismo,
            "EXPEDIENTE": self.expediente,
            "CARATULA": self.caratula,
            "RESPONSABLE": self.responsable,
            "CONTROL": self.control,
            "EVENTO": self.evento,
            "FECHA EVENTO": self.fecha_evento,
            "TAREA PENDIENTE": self.tarea_pendiente,
            "FECHA TAREA": self.fecha_tarea,
            "OBSERVACIONES": self.observaciones,
            "SEMÁFORO": self.semaforo,
            "_RUTA": str(self.ruta)  # Columna oculta para referencia
        }
