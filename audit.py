"""
Auditoria integral del sistema.
"""

import streamlit as st
from dataclasses import dataclass, asdict
from pathlib import Path
from datetime import datetime
import time
import platform
from typing import Dict, List

from config import (
    AÑOS_ACTIVOS, CAMPOS_FICHA, CAMPOS_FINANCIEROS,
    FICHA_JSON, FICHA_TXT, SUBCARPETAS_ESTANDAR, RE_INVALID_WIN,
)
from domain import Caso
from fs_repo import GestorCasos


@dataclass
class Hallazgo:
    nivel: str          # "ERROR" | "WARN" | "INFO"
    codigo: str         # Ej: "FS-001"
    mensaje: str
    ruta: str = ""
    sugerencia: str = ""


def _is_blank(v: str) -> bool:
    if v is None:
        return True
    s = str(v).strip()
    return s == "" or s.upper() == "S/D"


def _safe_len_path(p: Path) -> int:
    try:
        return len(str(p))
    except Exception:
        return 0


def auditar_app(gestor: GestorCasos, casos: List[Caso]) -> Dict:
    """
    Auditoría integral: estructura, datos, coherencia y riesgos típicos en Windows/OneDrive.
    Devuelve dict con resumen + hallazgos + métricas de completitud.
    """
    t0 = time.time()
    hallazgos: List[Hallazgo] = []

    # --- Contexto del entorno (INFO)
    hallazgos.append(Hallazgo(
        nivel="INFO",
        codigo="CTX-001",
        mensaje=f"Entorno: {platform.system()} {platform.release()} | Python: {platform.python_version()}",
        ruta=str(gestor.ruta_base),
        sugerencia="—"
    ))

    # --- Test 1: ruta base accesible
    if not gestor.ruta_base.exists():
        hallazgos.append(Hallazgo(
            nivel="ERROR",
            codigo="FS-001",
            mensaje="La ruta base no existe o no es accesible.",
            ruta=str(gestor.ruta_base),
            sugerencia="Verificar existencia, permisos y que no sea una ruta 'movida' por el sistema."
        ))
        return {
            "ok": False,
            "resumen": {"errores": 1, "warnings": 0, "info": 1, "casos": len(casos)},
            "hallazgos": [asdict(h) for h in hallazgos],
            "metricas": {}
        }

    # --- Test 2: años activos existen
    for año in AÑOS_ACTIVOS:
        ra = gestor.ruta_base / año
        if not ra.exists():
            hallazgos.append(Hallazgo(
                nivel="WARN",
                codigo="FS-010",
                mensaje=f"Año activo configurado pero carpeta inexistente: {año}",
                ruta=str(ra),
                sugerencia="Si el año no se usa, retirarlo de AÑOS_ACTIVOS; si se usa, crear la carpeta."
            ))

    # --- Índices para duplicados lógicos y consistencia
    keys = set()
    rutas_lower = set()

    # --- Métricas de completitud por campo
    campos_metricas = {
        "TIPO_PROCESO": 0, "JURISDICCION": 0, "ORGANISMO": 0, "EXPEDIENTE": 0, "CARATULA": 0,
        "RESPONSABLE": 0, "CONTROL": 0, "EVENTO": 0, "FECHA_EVENTO": 0,
        "TAREA_PENDIENTE": 0, "FECHA_TAREA": 0, "OBSERVACIONES": 0
    }

    # --- Test 3+: por caso
    for c in casos:
        # 3.1 Ruta existe
        if not c.ruta.exists():
            hallazgos.append(Hallazgo(
                nivel="ERROR",
                codigo="FS-020",
                mensaje="Caso indexado pero la carpeta física no existe (caso 'perdido').",
                ruta=str(c.ruta),
                sugerencia="Verificar si se movió/renombró manualmente o si hay sincronización pendiente."
            ))
            continue

        # 3.2 Longitud de ruta (riesgo Windows)
        lp = _safe_len_path(c.ruta)
        if lp >= 240:
            hallazgos.append(Hallazgo(
                nivel="WARN",
                codigo="FS-030",
                mensaje=f"Ruta muy larga ({lp} chars). Riesgo real de errores de lectura/escritura en Windows.",
                ruta=str(c.ruta),
                sugerencia="Acortar nombres de cliente/causa o habilitar rutas largas en Windows (política del sistema)."
            ))

        # 3.3 Nombres inválidos (Windows)
        if RE_INVALID_WIN.search(c.ruta.name):
            hallazgos.append(Hallazgo(
                nivel="ERROR",
                codigo="FS-040",
                mensaje="Nombre de carpeta del caso contiene caracteres inválidos para Windows.",
                ruta=str(c.ruta),
                sugerencia="Renombrar eliminando caracteres: <>:\"/\\|?* o control chars."
            ))

        # 3.4 Subcarpetas estándar
        faltantes = []
        for sub in SUBCARPETAS_ESTANDAR:
            if not (c.ruta / sub).exists():
                faltantes.append(sub)
        if faltantes:
            hallazgos.append(Hallazgo(
                nivel="WARN",
                codigo="FS-050",
                mensaje=f"Faltan subcarpetas estándar: {', '.join(faltantes)}",
                ruta=str(c.ruta),
                sugerencia="Usar 'Reparar subcarpetas' en Auditoría o activar 'Auto-crear subcarpetas' en la barra lateral."
            ))

        # 3.5 Ficha presente
        ficha_txt = c.ruta / "ficha.txt"
        ficha_json = c.ruta / "ficha.json"
        if not ficha_txt.exists() and not ficha_json.exists():
            hallazgos.append(Hallazgo(
                nivel="WARN",
                codigo="DATA-010",
                mensaje="No existe ficha.txt ni ficha.json en el caso.",
                ruta=str(c.ruta),
                sugerencia="Crear ficha para evitar 'casos mudos' (sin metadatos) y mejorar búsqueda."
            ))

        # 3.6 Duplicados lógicos
        k = (c.año.strip(), c.estado.strip(), c.cliente.strip(), c.fuero.strip(), c.causa.strip())
        if k in keys:
            hallazgos.append(Hallazgo(
                nivel="ERROR",
                codigo="DATA-020",
                mensaje="Duplicado lógico: existe más de un caso con la misma clave jerárquica.",
                ruta=str(c.ruta),
                sugerencia="Revisar si hay carpetas duplicadas o diferencias mínimas (espacios/puntos)."
            ))
        else:
            keys.add(k)

        # 3.7 Rutas duplicadas (case-insensitive, Windows)
        rl = str(c.ruta).lower()
        if rl in rutas_lower:
            hallazgos.append(Hallazgo(
                nivel="ERROR",
                codigo="DATA-025",
                mensaje="Ruta duplicada detectada (case-insensitive). Riesgo de colisiones.",
                ruta=str(c.ruta),
                sugerencia="Normalizar nombres evitando variaciones por mayúsculas/minúsculas."
            ))
        else:
            rutas_lower.add(rl)

        # 3.8 Fechas válidas
        if c.fecha_tarea and not _is_blank(c.fecha_tarea):
            if c._parsear_fecha(c.fecha_tarea) is None:
                hallazgos.append(Hallazgo(
                    nivel="WARN",
                    codigo="DATA-030",
                    mensaje=f"FECHA_TAREA inválida (no parseable): {c.fecha_tarea}",
                    ruta=str(c.ruta),
                    sugerencia="Usar DD/MM/YYYY o YYYY-MM-DD; evitar texto libre."
                ))
        if c.fecha_evento and not _is_blank(c.fecha_evento):
            if c._parsear_fecha(c.fecha_evento) is None:
                hallazgos.append(Hallazgo(
                    nivel="WARN",
                    codigo="DATA-031",
                    mensaje=f"FECHA_EVENTO inválida (no parseable): {c.fecha_evento}",
                    ruta=str(c.ruta),
                    sugerencia="Usar DD/MM/YYYY o YYYY-MM-DD; evitar texto libre."
                ))

        # 3.9 Señales típicas de encoding roto
        try:
            if ficha_txt.exists():
                raw = gestor._leer_contenido_ficha(ficha_txt)
                if "�" in raw:
                    hallazgos.append(Hallazgo(
                        nivel="WARN",
                        codigo="DATA-040",
                        mensaje="Posible corrupción de encoding detectada (carácter de reemplazo '�').",
                        ruta=str(ficha_txt),
                        sugerencia="Reguardar contenido y reescribir en UTF-8 desde el formulario del ERP."
                    ))
        except Exception:
            pass

        # 3.10 Completitud
        for key_m in campos_metricas.keys():
            val = getattr(c, key_m.lower(), None) if hasattr(c, key_m.lower()) else None
            if _is_blank(val):
                campos_metricas[key_m] += 1

    # --- Resumen + métricas
    errores = sum(1 for h in hallazgos if h.nivel == "ERROR")
    warns = sum(1 for h in hallazgos if h.nivel == "WARN")
    infos = sum(1 for h in hallazgos if h.nivel == "INFO")

    total = max(1, len(casos))
    metricas = {
        "casos_total": len(casos),
        "tiempo_auditoria_seg": round(time.time() - t0, 3),
        "completitud": {
            k: {
                "vacios_o_sd": v,
                "completos": total - v,
                "pct_completos": round(((total - v) / total) * 100, 1)
            } for k, v in campos_metricas.items()
        }
    }

    ok = errores == 0
    return {
        "ok": ok,
        "resumen": {"errores": errores, "warnings": warns, "info": infos, "casos": len(casos)},
        "hallazgos": [asdict(h) for h in hallazgos],
        "metricas": metricas
    }
