"""
Repositorio PostgreSQL - Implementacion alternativa a fs_repo.py.
Se activa automaticamente cuando DATABASE_URL esta configurada.
"""

import ipaddress
import json
import logging
import os
import re
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, TypedDict
from urllib.parse import urlparse

import config as _config
from config import CAMPOS_FICHA, CAMPOS_FINANCIEROS
from db.health import parse_database_url
from domain import Caso

ANOS_ACTIVOS = getattr(_config, "AÑOS_ACTIVOS", getattr(_config, "AÃ‘OS_ACTIVOS", []))

# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# CONEXION A BASE DE DATOS
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

_DB_URL = os.environ.get("DATABASE_URL", "")
_CASE_URI_RE = re.compile(r"db[:/\\\\]+cases[:/\\\\]+([0-9a-fA-F-]{36})")
AUDIT_WRITE_STRICT_ENV = "VG_AUDIT_WRITE_STRICT"
CASE_DUPLICATE_POLICY_ENV = "VG_CASE_DUPLICATE_POLICY"

logger = logging.getLogger(__name__)


class ActorContext(TypedDict, total=False):
    user_id: str
    user_name: str
    role: str
    ip: str
    ip_address: str
    user_agent: str
    request_id: str


def _env_bool(name: str, default: bool = False) -> bool:
    raw = str(os.environ.get(name, "")).strip().lower()
    if not raw:
        return bool(default)
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off"}:
        return False
    return bool(default)


def _normalize_db_text(value: str) -> str:
    return str(value or "").strip().lower()


def _sanitize_ip(ip_raw: str) -> Optional[str]:
    candidate = str(ip_raw or "").strip()
    if not candidate:
        return None
    try:
        return str(ipaddress.ip_address(candidate))
    except ValueError:
        return None


def _mask_db_url(u: str) -> str:
    if not u:
        return ""
    try:
        p = urlparse(u)
        # Oculta password si estÃ¡ presente
        netloc = p.netloc
        if "@" in netloc and ":" in netloc.split("@")[0]:
            userpass, host = netloc.split("@", 1)
            user = userpass.split(":", 1)[0]
            netloc = f"{user}:***@{host}"
        return p._replace(netloc=netloc).geturl()
    except Exception:
        return "<unparseable>"


def _get_connection():
    """Obtiene conexion a PostgreSQL usando DATABASE_URL."""
    import psycopg2

    url = parse_database_url(os.environ.get("DATABASE_URL", ""))
    if os.environ.get("VG_DEBUG") == "1":
        print("[repo_db] DATABASE_URL =", _mask_db_url(url))

    return psycopg2.connect(url, connect_timeout=3)


@contextmanager
def get_conn():
    """Context manager para conexiones con auto-commit y cleanup."""
    conn = _get_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# CLASE PRINCIPAL: GestorCasosDB
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

class GestorCasosDB:
    """Motor de gestion usando PostgreSQL - API compatible con GestorCasos (fs_repo)."""

    def __init__(self, ruta_base: Optional[Path] = None):
        """
        Inicializa el gestor DB.
        ruta_base se ignora en modo DB pero se acepta para compatibilidad de API.
        """
        self.ruta_base = ruta_base  # No usado, solo compatibilidad
        self._cache_casos: List[Caso] = []

    def _resolve_actor_ctx(self, actor_ctx: Optional[ActorContext]) -> ActorContext:
        actor = dict(actor_ctx or {})
        actor.setdefault("user_id", str(os.environ.get("VG_ACTOR_USER_ID", "system")))
        actor.setdefault("user_name", str(os.environ.get("VG_ACTOR_USER_NAME", "system")))
        actor.setdefault("role", str(os.environ.get("VG_ACTOR_ROLE", "system")))
        actor.setdefault("request_id", str(os.environ.get("VG_RUN_ID", "")))
        actor_ip = str(actor.get("ip", "")).strip() or str(actor.get("ip_address", "")).strip()
        if not actor_ip:
            actor_ip = str(os.environ.get("VG_ACTOR_IP", "")).strip()
        actor["ip"] = actor_ip
        actor["ip_address"] = actor_ip
        actor.setdefault("user_agent", str(actor.get("user_agent", "")))
        return actor  # type: ignore[return-value]

    def _write_audit_log(
        self,
        cur: Any,
        *,
        entity_type: str,
        entity_id: str,
        action: str,
        changes: Dict[str, Any],
        actor_ctx: Optional[ActorContext],
    ) -> None:
        actor = self._resolve_actor_ctx(actor_ctx)
        payload = {
            "changes": changes,
            "meta": {
                "role": actor.get("role", ""),
                "request_id": actor.get("request_id", ""),
            },
        }
        safe_ip = _sanitize_ip(str(actor.get("ip", "")) or str(actor.get("ip_address", "")))
        cur.execute(
            """
            INSERT INTO audit_log (
                entity_type,
                entity_id,
                action,
                changes,
                user_id,
                user_name,
                ip_address,
                user_agent
            ) VALUES (%s, %s, %s, %s::jsonb, %s, %s, %s, %s)
            """,
            (
                str(entity_type).strip() or "case",
                entity_id,
                str(action).strip() or "update",
                json.dumps(payload, ensure_ascii=False, default=str),
                str(actor.get("user_id", ""))[:100],
                str(actor.get("user_name", ""))[:255],
                safe_ip,
                str(actor.get("user_agent", "")),
            ),
        )

    def _try_write_audit_log(
        self,
        cur: Any,
        *,
        entity_type: str,
        entity_id: str,
        action: str,
        changes: Dict[str, Any],
        actor_ctx: Optional[ActorContext],
    ) -> None:
        strict = _env_bool(AUDIT_WRITE_STRICT_ENV, default=False)
        try:
            self._write_audit_log(
                cur,
                entity_type=entity_type,
                entity_id=entity_id,
                action=action,
                changes=changes,
                actor_ctx=actor_ctx,
            )
        except Exception as exc:
            logger.warning(
                "audit_log write failed entity_type=%s action=%s entity_id=%s strict=%s err=%s",
                entity_type,
                action,
                entity_id,
                strict,
                exc,
            )
            if strict:
                raise

    def _db_path(self, case_id: str) -> Path:
        """Genera pseudo-path para casos en DB (para compatibilidad con UI)."""
        return Path(f"db://cases/{case_id}")

    def _row_to_caso(self, row: dict) -> Caso:
        """Convierte una fila de la DB a objeto Caso."""
        extra = row.get("extra") or {}
        if isinstance(extra, str):
            try:
                extra = json.loads(extra)
            except Exception:
                extra = {}

        # Pseudo-path usando ID del caso
        case_id = str(row.get("id", ""))
        pseudo_ruta = self._db_path(case_id)
        fs_path = row.get("fs_path") or ""
        is_legacy = bool(fs_path)

        return Caso(
            ruta=pseudo_ruta,
            año=row.get("year", ""),
            estado=row.get("status", ""),
            cliente=row.get("client_name", ""),  # JOIN con clients
            fuero=row.get("fuero", ""),
            causa=row.get("causa", ""),
            tipo_proceso=extra.get("TIPO_PROCESO", row.get("tipo_proceso", "") or ""),
            jurisdiccion=extra.get("JURISDICCION", row.get("jurisdiccion", "") or ""),
            organismo=extra.get("ORGANISMO", row.get("organismo", "") or ""),
            expediente=extra.get("EXPEDIENTE", row.get("expediente", "") or ""),
            caratula=extra.get("CARATULA", row.get("caratula", "") or ""),
            responsable=extra.get("RESPONSABLE", row.get("responsable", "") or ""),
            control=extra.get("CONTROL", row.get("control", "") or ""),
            evento=extra.get("EVENTO", row.get("evento", "") or ""),
            fecha_evento=extra.get("FECHA_EVENTO", "") or (str(row.get("fecha_evento", "")) if row.get("fecha_evento") else ""),
            tarea_pendiente=extra.get("TAREA_PENDIENTE", row.get("tarea_pendiente", "") or ""),
            fecha_tarea=extra.get("FECHA_TAREA", "") or (str(row.get("fecha_tarea", "")) if row.get("fecha_tarea") else ""),
            observaciones=extra.get("OBSERVACIONES", row.get("observaciones", "") or ""),
            fs_path=fs_path,
            is_legacy=is_legacy,
        )

    def escanear_casos(self) -> List[Caso]:
        """Lee todos los casos de la base de datos."""
        casos = []

        query = """
            SELECT
                c.id, c.year, c.status, c.fuero, c.causa,
                c.tipo_proceso, c.jurisdiccion, c.organismo, c.expediente,
                c.caratula, c.responsable, c.control, c.evento,
                c.fecha_evento, c.tarea_pendiente, c.fecha_tarea,
                c.observaciones, c.fs_path, c.extra,
                COALESCE(cl.name, 'S/D') AS client_name
            FROM cases c
            LEFT JOIN clients cl ON c.client_id = cl.id
            ORDER BY c.year DESC, c.status, client_name, c.causa
        """

        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(query)
                columns = [desc[0] for desc in cur.description]
                for row in cur.fetchall():
                    row_dict = dict(zip(columns, row))
                    caso = self._row_to_caso(row_dict)
                    casos.append(caso)

        self._cache_casos = casos
        return casos

    def listar_casos(self) -> List[Caso]:
        """Alias para compatibilidad con API anterior."""
        return self.escanear_casos()

    def verificar_conteo_casos(self, casos: Optional[List[Caso]] = None) -> Dict[str, int]:
        """
        Verifica rapidamente la cantidad de casos reales en DB vs los listados en memoria.
        Loguea discrepancias (para detectar filtrados involuntarios o joins excluyentes).
        """
        listado = casos if casos is not None else self._cache_casos
        listado_total = len(listado)

        db_total = listado_total
        try:
            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT count(*) FROM cases")
                    row = cur.fetchone()
                    if row and row[0] is not None:
                        db_total = int(row[0])
        except Exception as exc:
            logger.warning("verificar_conteo_casos failed: %s", exc)

        delta = db_total - listado_total
        if delta != 0 or os.environ.get("VG_DEBUG") == "1":
            print(f"[repo_db] Conteo casos: db={db_total} listado={listado_total} delta={delta}")

        return {"db_total": db_total, "listado_total": listado_total, "delta": delta}

    def _get_case_id_from_path(self, ruta: Path) -> Optional[str]:
        """Extrae el UUID del caso desde el pseudo-path db://cases/<uuid>."""
        if ruta is None:
            return None
        path_str = str(ruta).strip()
        match = _CASE_URI_RE.search(path_str)
        if match:
            return match.group(1)
        return None

    def _require_case_id(self, ruta_caso: Path) -> str:
        """Valida y retorna el UUID del caso; falla con mensaje claro si es invalido."""
        case_id = self._get_case_id_from_path(ruta_caso)
        if not case_id:
            raise ValueError(f"Ruta DB de caso invalida: {ruta_caso!r}")
        return case_id

    def _leer_ficha(self, ruta_caso: Path) -> Dict[str, str]:
        """Lee datos de ficha desde la DB."""
        case_id = self._require_case_id(ruta_caso)

        query = """
            SELECT tipo_proceso, jurisdiccion, organismo, expediente,
                   caratula, responsable, control, evento,
                   fecha_evento, tarea_pendiente, fecha_tarea,
                   observaciones, extra
            FROM cases WHERE id = %s
        """

        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (case_id,))
                row = cur.fetchone()
                if not row:
                    return {campo: "" for campo in CAMPOS_FICHA}

                columns = ["tipo_proceso", "jurisdiccion", "organismo", "expediente",
                          "caratula", "responsable", "control", "evento",
                          "fecha_evento", "tarea_pendiente", "fecha_tarea",
                          "observaciones", "extra"]
                row_dict = dict(zip(columns, row))

        extra = row_dict.get("extra") or {}
        if isinstance(extra, str):
            try:
                extra = json.loads(extra)
            except Exception:
                extra = {}

        # Construir diccionario normalizado
        datos = {campo: "" for campo in CAMPOS_FICHA}

        # Mapeo columnas DB -> campos ficha
        col_map = {
            "TIPO_PROCESO": "tipo_proceso",
            "JURISDICCION": "jurisdiccion",
            "ORGANISMO": "organismo",
            "EXPEDIENTE": "expediente",
            "CARATULA": "caratula",
            "RESPONSABLE": "responsable",
            "CONTROL": "control",
            "EVENTO": "evento",
            "FECHA_EVENTO": "fecha_evento",
            "TAREA_PENDIENTE": "tarea_pendiente",
            "FECHA_TAREA": "fecha_tarea",
            "OBSERVACIONES": "observaciones",
        }

        for ficha_key, db_col in col_map.items():
            # Prioridad: extra JSONB > columna directa
            val = extra.get(ficha_key) or row_dict.get(db_col)
            if val is not None:
                if isinstance(val, str):
                    datos[ficha_key] = val
                else:
                    datos[ficha_key] = str(val) if val else ""

        return datos

    def _leer_contenido_ficha(self, ficha_path: Path) -> str:
        """En modo DB, genera un string legible desde los datos del caso."""
        datos = self._leer_ficha(ficha_path)
        lineas = []
        for campo in CAMPOS_FICHA:
            valor = datos.get(campo, "")
            lineas.append(f"{campo}: {valor}")
        return "\n".join(lineas)

    def actualizar_campos_ficha(
        self,
        ruta_caso: Path,
        cambios: Dict[str, str],
        actor_ctx: Optional[ActorContext] = None,
    ) -> bool:
        """Actualiza solo los campos indicados (merge JSONB)."""
        case_id = self._require_case_id(ruta_caso)

        # Leer extra actual
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT extra FROM cases WHERE id = %s", (case_id,))
                row = cur.fetchone()
                if not row:
                    return False

                extra = row[0] or {}
                if isinstance(extra, str):
                    try:
                        extra = json.loads(extra)
                    except Exception:
                        extra = {}

                # Merge cambios
                for k, v in cambios.items():
                    extra[k] = v

                # Actualizar columnas directas si aplica
                col_updates = []
                params: List[Any] = []

                col_map = {
                    "TIPO_PROCESO": "tipo_proceso",
                    "JURISDICCION": "jurisdiccion",
                    "ORGANISMO": "organismo",
                    "EXPEDIENTE": "expediente",
                    "CARATULA": "caratula",
                    "RESPONSABLE": "responsable",
                    "CONTROL": "control",
                    "EVENTO": "evento",
                    "TAREA_PENDIENTE": "tarea_pendiente",
                    "OBSERVACIONES": "observaciones",
                }

                for ficha_key, db_col in col_map.items():
                    if ficha_key in cambios:
                        col_updates.append(f"{db_col} = %s")
                        params.append(cambios[ficha_key])

                # Manejar fechas
                if "FECHA_EVENTO" in cambios:
                    col_updates.append("fecha_evento = %s")
                    fecha_val = cambios["FECHA_EVENTO"]
                    params.append(self._parse_date_for_db(fecha_val))

                if "FECHA_TAREA" in cambios:
                    col_updates.append("fecha_tarea = %s")
                    fecha_val = cambios["FECHA_TAREA"]
                    params.append(self._parse_date_for_db(fecha_val))

                # Siempre actualizar extra
                col_updates.append("extra = %s")
                params.append(json.dumps(extra, ensure_ascii=False))

                params.append(case_id)

                query = f"UPDATE cases SET {', '.join(col_updates)} WHERE id = %s"
                cur.execute(query, params)
                self._try_write_audit_log(
                    cur,
                    entity_type="case",
                    entity_id=case_id,
                    action="update_fields",
                    changes={"fields": list(cambios.keys()), "values": dict(cambios)},
                    actor_ctx=actor_ctx,
                )

        return True

    def _parse_date_for_db(self, fecha_str: str) -> Optional[str]:
        """Convierte fecha string a formato DB (YYYY-MM-DD) o None."""
        if not fecha_str or fecha_str == "S/D":
            return None

        from datetime import datetime
        formatos = ["%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y", "%d.%m.%Y"]
        for fmt in formatos:
            try:
                dt = datetime.strptime(fecha_str.strip(), fmt)
                return dt.strftime("%Y-%m-%d")
            except ValueError:
                continue
        return None

    def actualizar_caso(
        self,
        ruta_caso: Path,
        datos: Dict[str, str],
        actor_ctx: Optional[ActorContext] = None,
    ) -> bool:
        """Reemplaza datos completos del caso (sobrescribe extra JSONB)."""
        case_id = self._get_case_id_from_path(ruta_caso)
        if not case_id:
            return False

        # Construir extra completo
        extra = {}
        for campo in CAMPOS_FICHA:
            if campo in datos:
                extra[campo] = datos[campo]

        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE cases SET
                        tipo_proceso = %s,
                        jurisdiccion = %s,
                        organismo = %s,
                        expediente = %s,
                        caratula = %s,
                        responsable = %s,
                        control = %s,
                        evento = %s,
                        fecha_evento = %s,
                        tarea_pendiente = %s,
                        fecha_tarea = %s,
                        observaciones = %s,
                        extra = %s
                    WHERE id = %s
                """, (
                    datos.get("TIPO_PROCESO", ""),
                    datos.get("JURISDICCION", ""),
                    datos.get("ORGANISMO", ""),
                    datos.get("EXPEDIENTE", ""),
                    datos.get("CARATULA", ""),
                    datos.get("RESPONSABLE", ""),
                    datos.get("CONTROL", ""),
                    datos.get("EVENTO", ""),
                    self._parse_date_for_db(datos.get("FECHA_EVENTO", "")),
                    datos.get("TAREA_PENDIENTE", ""),
                    self._parse_date_for_db(datos.get("FECHA_TAREA", "")),
                    datos.get("OBSERVACIONES", ""),
                    json.dumps(extra, ensure_ascii=False),
                    case_id,
                ))
                self._try_write_audit_log(
                    cur,
                    entity_type="case",
                    entity_id=case_id,
                    action="replace_case",
                    changes={"fields": sorted(list(datos.keys()))},
                    actor_ctx=actor_ctx,
                )

        return True

    def leer_datos_financieros(self, ruta_caso: Path) -> Dict[str, str]:
        """Lee campos financieros desde extra JSONB."""
        case_id = self._get_case_id_from_path(ruta_caso)
        out = {campo: "" for campo in CAMPOS_FINANCIEROS}

        if not case_id:
            return out

        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT monto_demandado, honorarios_pactados, estado_pago, extra
                    FROM cases WHERE id = %s
                """, (case_id,))
                row = cur.fetchone()
                if not row:
                    return out

                monto, honorarios, estado_pago, extra = row

                # Prioridad: columnas directas > extra JSONB
                if monto is not None:
                    out["MONTO_DEMANDADO"] = str(monto)
                if honorarios is not None:
                    out["HONORARIOS_PACTADOS"] = str(honorarios)
                if estado_pago:
                    out["ESTADO_PAGO"] = estado_pago

                # Fallback a extra
                if isinstance(extra, str):
                    try:
                        extra = json.loads(extra)
                    except Exception:
                        extra = {}
                extra = extra or {}

                for campo in CAMPOS_FINANCIEROS:
                    if not out[campo] and campo in extra:
                        out[campo] = str(extra[campo]) if extra[campo] else ""

        return out

    def guardar_datos_financieros(
        self,
        ruta_caso: Path,
        datos_fin: Dict[str, str],
        actor_ctx: Optional[ActorContext] = None,
    ) -> bool:
        """Guarda campos financieros en columnas directas + extra JSONB."""
        case_id = self._require_case_id(ruta_caso)

        with get_conn() as conn:
            with conn.cursor() as cur:
                # Leer extra actual
                cur.execute("SELECT extra FROM cases WHERE id = %s", (case_id,))
                row = cur.fetchone()
                if not row:
                    return False

                extra = row[0] or {}
                if isinstance(extra, str):
                    try:
                        extra = json.loads(extra)
                    except Exception:
                        extra = {}

                # Merge financieros en extra
                for campo in CAMPOS_FINANCIEROS:
                    if campo in datos_fin:
                        extra[campo] = datos_fin[campo]

                # Parsear valores numericos
                monto = None
                honorarios = None
                try:
                    val = datos_fin.get("MONTO_DEMANDADO", "").replace(",", ".")
                    if val:
                        monto = float(val)
                except ValueError:
                    pass

                try:
                    val = datos_fin.get("HONORARIOS_PACTADOS", "").replace(",", ".")
                    if val:
                        honorarios = float(val)
                except ValueError:
                    pass

                cur.execute("""
                    UPDATE cases SET
                        monto_demandado = %s,
                        honorarios_pactados = %s,
                        estado_pago = %s,
                        extra = %s
                    WHERE id = %s
                """, (
                    monto,
                    honorarios,
                    datos_fin.get("ESTADO_PAGO", ""),
                    json.dumps(extra, ensure_ascii=False),
                    case_id,
                ))
                self._try_write_audit_log(
                    cur,
                    entity_type="case",
                    entity_id=case_id,
                    action="update_financials",
                    changes={"financials": dict(datos_fin)},
                    actor_ctx=actor_ctx,
                )

        return True

    def obtener_clientes_existentes(self) -> List[str]:
        """Lista clientes unicos que tienen al menos un caso (igual que FS)."""
        clientes = set()

        with get_conn() as conn:
            with conn.cursor() as cur:
                # Solo clientes con al menos un caso - misma semantica que FS
                cur.execute("""
                    SELECT DISTINCT cl.name
                    FROM clients cl
                    INNER JOIN cases c ON cl.id = c.client_id
                    WHERE cl.name IS NOT NULL
                    ORDER BY cl.name
                """)
                for row in cur.fetchall():
                    if row[0]:
                        clientes.add(row[0])

        return sorted(list(clientes))

    def obtener_años_existentes(self) -> List[str]:
        """Devuelve años activos (igual que FS - desde config)."""
        return sorted(ANOS_ACTIVOS, reverse=True)

    def crear_caso(
        self,
        año: str,
        estado: str,
        cliente: str,
        fuero: str,
        nombre_caso: str,
        actor_ctx: Optional[ActorContext] = None,
    ) -> Tuple[bool, str]:
        """Crea un nuevo caso en la base de datos."""
        try:
            with get_conn() as conn:
                with conn.cursor() as cur:
                    duplicate_policy = str(
                        os.environ.get(CASE_DUPLICATE_POLICY_ENV, "block")
                    ).strip().lower()
                    if duplicate_policy not in {"block", "allow"}:
                        duplicate_policy = "block"

                    cur.execute(
                        """
                        SELECT c.id
                        FROM cases c
                        JOIN clients cl ON cl.id = c.client_id
                        WHERE lower(trim(cl.name)) = lower(trim(%s))
                          AND lower(trim(c.causa)) = lower(trim(%s))
                          AND c.year = %s
                          AND c.status = %s
                          AND c.fuero = %s
                        LIMIT 1
                        """,
                        (cliente, nombre_caso, año, estado, fuero),
                    )
                    dup_row = cur.fetchone()
                    if dup_row and duplicate_policy == "block":
                        dup_id = str(dup_row[0] or "")
                        return (
                            False,
                            f"Caso duplicado detectado (ID: {dup_id[:8]}...). "
                            f"Puede permitir duplicados con {CASE_DUPLICATE_POLICY_ENV}=allow.",
                        )

                    # Buscar o crear cliente
                    cur.execute("SELECT id FROM clients WHERE name = %s", (cliente,))
                    row = cur.fetchone()
                    if row:
                        client_id = row[0]
                    else:
                        client_id = str(uuid.uuid4())
                        cur.execute("""
                            INSERT INTO clients (id, name, status)
                            VALUES (%s, %s, 'activo')
                        """, (client_id, cliente))

                    # Crear caso
                    case_id = str(uuid.uuid4())
                    cur.execute("""
                        INSERT INTO cases (
                            id, client_id, year, status, fuero, causa,
                            caratula, responsable, extra
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """, (
                        case_id,
                        client_id,
                        año,
                        estado,
                        fuero,
                        nombre_caso,
                        nombre_caso,  # caratula = nombre por defecto
                        "A asignar",
                        json.dumps({"CASE_ID": case_id}, ensure_ascii=False),
                    ))
                    self._try_write_audit_log(
                        cur,
                        entity_type="case",
                        entity_id=case_id,
                        action="create_case",
                        changes={
                            "year": año,
                            "status": estado,
                            "fuero": fuero,
                            "causa": nombre_caso,
                            "cliente": cliente,
                        },
                        actor_ctx=actor_ctx,
                    )

            return True, f"Caso creado exitosamente: {nombre_caso} (ID: {case_id[:8]}...)"
        except Exception as e:
            logger.warning("crear_caso failed cliente=%s causa=%s err=%s", cliente, nombre_caso, e)
            return False, f"Error al crear caso: {str(e)}"

    def mover_carpeta_fisica(
        self,
        caso_actual: Caso,
        nuevo_año: str,
        nuevo_estado: str,
        nuevo_cliente: str,
        nuevo_fuero: str,
        nueva_causa: str,
        actor_ctx: Optional[ActorContext] = None,
    ) -> Tuple[bool, Path]:
        """
        En modo DB: actualiza atributos de clasificacion (no hay carpeta fisica).
        Retorna pseudo-path actualizado.
        """
        case_id = self._get_case_id_from_path(caso_actual.ruta)
        if not case_id:
            return False, caso_actual.ruta

        try:
            with get_conn() as conn:
                with conn.cursor() as cur:
                    # Buscar o crear cliente destino
                    cur.execute("SELECT id FROM clients WHERE name = %s", (nuevo_cliente,))
                    row = cur.fetchone()
                    if row:
                        client_id = row[0]
                    else:
                        client_id = str(uuid.uuid4())
                        cur.execute("""
                            INSERT INTO clients (id, name, status)
                            VALUES (%s, %s, 'activo')
                        """, (client_id, nuevo_cliente))

                    # Actualizar caso
                    cur.execute("""
                        UPDATE cases SET
                            client_id = %s,
                            year = %s,
                            status = %s,
                            fuero = %s,
                            causa = %s
                        WHERE id = %s
                    """, (client_id, nuevo_año, nuevo_estado, nuevo_fuero, nueva_causa, case_id))
                    self._try_write_audit_log(
                        cur,
                        entity_type="case",
                        entity_id=case_id,
                        action="reclassify_case",
                        changes={
                            "year": nuevo_año,
                            "status": nuevo_estado,
                            "fuero": nuevo_fuero,
                            "causa": nueva_causa,
                            "cliente": nuevo_cliente,
                        },
                        actor_ctx=actor_ctx,
                    )

            # Retornar mismo pseudo-path (el ID no cambia)
            return True, caso_actual.ruta
        except Exception as e:
            logger.warning(
                "mover_carpeta_fisica failed case_id=%s err=%s",
                case_id,
                e,
            )
            return False, caso_actual.ruta

    def ensure_case_structure(self, ruta_caso: Path) -> int:
        """En modo DB no hay subcarpetas. Retorna 0 (no aplica)."""
        return 0

    def sincronizar_ruta_fisica(
        self,
        caso_actual: Caso,
        nuevos_datos: Dict,
        actor_ctx: Optional[ActorContext] = None,
    ) -> Tuple[bool, str, Optional[Path]]:
        """En modo DB, actualiza clasificacion sin mover carpetas."""
        def g(k, default):
            return nuevos_datos.get(k, nuevos_datos.get(k.upper(), default))

        año_n = g("año", caso_actual.año)
        estado_n = g("estado", caso_actual.estado)
        cliente_n = g("cliente", caso_actual.cliente)
        fuero_n = g("fuero", caso_actual.fuero)

        ok, new_path = self.mover_carpeta_fisica(
            caso_actual,
            año_n,
            estado_n,
            cliente_n,
            fuero_n,
            caso_actual.causa,
            actor_ctx=actor_ctx,
        )

        if ok:
            return True, "Clasificacion actualizada en DB.", new_path
        else:
            return False, "Error actualizando clasificacion.", None

    def leer_datos_financieros_batch(self, rutas: List[Path]) -> Dict[str, Dict[str, str]]:
        """Lee datos financieros de varios casos en una sola consulta."""
        out: Dict[str, Dict[str, str]] = {}
        case_ids: List[str] = []
        case_to_ref: Dict[str, str] = {}
        for ruta in rutas:
            ref = str(ruta)
            out[ref] = {campo: "" for campo in CAMPOS_FINANCIEROS}
            case_id = self._get_case_id_from_path(ruta)
            if not case_id:
                continue
            case_ids.append(case_id)
            case_to_ref[case_id] = ref

        if not case_ids:
            return out

        placeholders = ", ".join(["%s"] * len(case_ids))
        query = f"""
            SELECT id, monto_demandado, honorarios_pactados, estado_pago, extra
            FROM cases
            WHERE id IN ({placeholders})
        """
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(query, tuple(case_ids))
                for row in cur.fetchall():
                    case_id, monto, honorarios, estado_pago, extra = row
                    ref = case_to_ref.get(str(case_id), "")
                    if not ref:
                        continue
                    vals = out.get(ref, {campo: "" for campo in CAMPOS_FINANCIEROS})
                    if monto is not None:
                        vals["MONTO_DEMANDADO"] = str(monto)
                    if honorarios is not None:
                        vals["HONORARIOS_PACTADOS"] = str(honorarios)
                    if estado_pago:
                        vals["ESTADO_PAGO"] = str(estado_pago)
                    if isinstance(extra, str):
                        try:
                            extra = json.loads(extra)
                        except Exception:
                            extra = {}
                    extra = extra or {}
                    for campo in CAMPOS_FINANCIEROS:
                        if not vals.get(campo) and campo in extra:
                            vals[campo] = str(extra.get(campo) or "")
                    out[ref] = vals
        return out

    def listar_documentos_recientes(self, ruta_caso: Path, n: int = 5) -> List[Dict]:
        """Retorna los Ãºltimos n documentos del caso desde la tabla documents.

        Returns:
            Lista de dicts con claves:
            - filename: str - nombre del archivo
            - updated_at: str - fecha de modificaciÃ³n (dd/mm HH:MM)
            - open_target: str | None - storage_path si existe, None si no
        """
        case_id = self._get_case_id_from_path(ruta_caso)
        if not case_id:
            return []

        query = """
            SELECT filename, storage_path, updated_at, created_at
            FROM documents
            WHERE case_id = %s
            ORDER BY COALESCE(updated_at, created_at) DESC NULLS LAST
            LIMIT %s
        """

        result = []
        try:
            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(query, (case_id, n))
                    for row in cur.fetchall():
                        filename, storage_path, updated_at, created_at = row
                        # Usar updated_at o fallback a created_at
                        ts = updated_at or created_at
                        if ts:
                            fecha_str = ts.strftime("%d/%m %H:%M")
                        else:
                            fecha_str = ""
                        result.append({
                            "filename": filename or "",
                            "updated_at": fecha_str,
                            "open_target": storage_path if storage_path else None,
                        })
        except Exception as exc:
            logger.warning("listar_documentos_recientes failed case_id=%s err=%s", case_id, exc)

        return result
