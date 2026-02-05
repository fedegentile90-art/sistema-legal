"""
Motor de lectura/escritura del filesystem (GestorCasos).
"""

import streamlit as st
from pathlib import Path
import json
import uuid
import shutil
import os
import platform
from datetime import datetime
from typing import List, Dict, Tuple, Optional

from config import (
    AÑOS_ACTIVOS, IGNORAR_CARPETAS_INTERNAS, FUEROS_IGNORAR,
    IGNORAR_SISTEMA, IGNORAR_PATRONES,
    CAMPOS_FICHA, CAMPOS_FINANCIEROS, MAPEO_CAMPOS_FICHA,
    FICHA_JSON, FICHA_TXT, CASE_ID_FILE,
    SUBCARPETAS_ESTANDAR,
    limpiar_nombre_carpeta,
)
from domain import Caso


class GestorCasos:
    """Motor principal de gestión - Lee y escribe en el sistema de archivos."""

    def __init__(self, ruta_base: Path):
        self.ruta_base = ruta_base
        self._cache_casos: List[Caso] = []

    def _es_carpeta_sistema(self, carpeta: Path) -> bool:
        """Verifica si es una carpeta del sistema a ignorar."""
        if not carpeta.is_dir():
            return True
        nombre = carpeta.name
        if nombre.startswith('.') or nombre in IGNORAR_SISTEMA:
            return True
        for patron in IGNORAR_PATRONES:
            if patron in nombre:
                return True
        return False

    def _es_carpeta_interna_caso(self, nombre_carpeta: str) -> bool:
        """Verifica si es una subcarpeta interna del caso (Prueba, Escritos, etc.)."""
        nombre_limpio = nombre_carpeta.lower().strip()
        for item in IGNORAR_CARPETAS_INTERNAS:
            if item.lower() in nombre_limpio:
                return True
        return False

    def _es_fuero_ignorado(self, nombre_fuero: str) -> bool:
        """Verifica si el fuero debe ser ignorado."""
        for ignorar in FUEROS_IGNORAR:
            if ignorar.lower() in nombre_fuero.lower():
                return True
        return False

    def _asegurar_case_id(self, ruta_caso: Path) -> str:
        """Genera o lee un ID único estable por caso (persiste en .vg_case_id)."""
        id_path = ruta_caso / CASE_ID_FILE
        try:
            if id_path.exists():
                cid = id_path.read_text(encoding="utf-8").strip()
                if cid:
                    return cid
            cid = str(uuid.uuid4())
            id_path.write_text(cid, encoding="utf-8")
            return cid
        except Exception:
            return str(uuid.uuid4())

    def _append_log(self, ruta_caso: Path, accion: str):
        """Registra una acción en historial.log del caso (auditoría local)."""
        try:
            usuario = os.getlogin()
        except Exception:
            usuario = "unknown"
        pc = platform.node()
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        line = f"[{ts}] [{pc}] [{usuario}] {accion}\n"
        try:
            with (ruta_caso / "historial.log").open("a", encoding="utf-8") as f:
                f.write(line)
        except Exception:
            pass

    def _buscar_archivo_ficha_json(self, carpeta_caso: Path) -> Optional[Path]:
        """Busca ficha.json en la carpeta del caso."""
        p = carpeta_caso / FICHA_JSON
        return p if p.exists() and p.is_file() else None

    def _leer_ficha_json(self, ruta_caso: Path) -> Dict[str, str]:
        """Lee ficha.json y retorna diccionario normalizado con los campos estándar."""
        p = ruta_caso / FICHA_JSON
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                return {campo: "" for campo in CAMPOS_FICHA}
            out = {campo: "" for campo in CAMPOS_FICHA}
            for k, v in data.items():
                kk = str(k).strip().upper().replace(" ", "_")
                if kk in out:
                    out[kk] = "" if v is None else str(v)
            return out
        except Exception:
            return {campo: "" for campo in CAMPOS_FICHA}

    def _escribir_ficha_json(self, ruta_caso: Path, datos: Dict[str, str]) -> bool:
        """Escribe ficha.json como fuente canónica de datos del caso.

        Preserva claves extra (e.g. CASE_ID) que no están en CAMPOS_FICHA.
        """
        p = ruta_caso / FICHA_JSON
        try:
            payload = {}
            for campo in CAMPOS_FICHA:
                v = datos.get(campo, "")
                if v == "S/D":
                    v = ""
                payload[campo] = v
            # Preservar claves extra (CASE_ID, etc.)
            for k, v in datos.items():
                if k not in payload:
                    payload[k] = v
            p.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            return True
        except Exception as e:
            st.error(f"Error escribiendo ficha.json en {ruta_caso}: {e}")
            return False

    def _buscar_archivo_ficha(self, carpeta_caso: Path) -> Optional[Path]:
        """Busca ficha: primero ficha.json, luego ficha.txt (case-insensitive)."""
        # Prioridad 1: ficha.json
        json_path = self._buscar_archivo_ficha_json(carpeta_caso)
        if json_path:
            return json_path
        # Prioridad 2: ficha.txt (legacy, case-insensitive)
        try:
            for archivo in carpeta_caso.iterdir():
                if archivo.is_file() and archivo.name.lower() == "ficha.txt":
                    return archivo
        except Exception:
            pass
        return None

    def _leer_contenido_ficha(self, ficha_path: Path) -> str:
        """Lee el contenido de ficha.txt con fallback de encoding."""
        try:
            return ficha_path.read_text(encoding='utf-8')
        except UnicodeDecodeError:
            try:
                return ficha_path.read_text(encoding='latin-1')
            except Exception:
                return ""
        except Exception:
            return ""

    def _leer_ficha(self, ruta_caso: Path) -> Dict[str, str]:
        """Lee la ficha del caso: prioriza ficha.json, fallback a ficha.txt."""
        # Prioridad 1: ficha.json (fuente canónica)
        if self._buscar_archivo_ficha_json(ruta_caso):
            return self._leer_ficha_json(ruta_caso)

        # Prioridad 2: ficha.txt (legacy)
        datos = {campo: "S/D" for campo in CAMPOS_FICHA}
        datos['FECHA_EVENTO'] = ""
        datos['FECHA_TAREA'] = ""
        datos['OBSERVACIONES'] = ""

        ficha_path = self._buscar_archivo_ficha(ruta_caso)
        if not ficha_path:
            return datos

        contenido = self._leer_contenido_ficha(ficha_path)
        if not contenido.strip():
            return datos

        # Acumular observaciones multi-línea
        observaciones_lineas = []
        capturando_obs = False

        for linea in contenido.split('\n'):
            linea_original = linea.strip()

            if not linea_original or linea_original.startswith('---') or linea_original.startswith('==='):
                continue

            if ':' in linea_original:
                clave, valor = linea_original.split(':', 1)
                clave_limpia = clave.strip().upper().replace(' ', '_').replace('/', '_').replace('°', '').replace('º', '')

                clave_normalizada = MAPEO_CAMPOS_FICHA.get(clave_limpia, clave_limpia)

                valor = valor.strip()

                if clave_normalizada == 'OBSERVACIONES':
                    capturando_obs = True
                    if valor:
                        observaciones_lineas.append(valor)
                elif clave_normalizada in datos:
                    capturando_obs = False
                    datos[clave_normalizada] = valor if valor else ("S/D" if clave_normalizada not in ['FECHA_EVENTO', 'FECHA_TAREA', 'OBSERVACIONES'] else "")
            elif capturando_obs and linea_original:
                observaciones_lineas.append(linea_original)

        if observaciones_lineas:
            datos['OBSERVACIONES'] = '\n'.join(observaciones_lineas)

        for campo in datos:
            if datos[campo] == "S/D":
                datos[campo] = ""

        return datos

    def _escribir_ficha(self, ruta_caso: Path, datos: Dict[str, str]) -> bool:
        """Escribe ficha.json (canónico) + ficha.txt (resumen humano)."""
        # 1) Escribir fuente canónica JSON
        if not self._escribir_ficha_json(ruta_caso, datos):
            return False

        # 2) Escribir ficha.txt como resumen seguro (solo lectura humana)
        ficha_path = ruta_caso / FICHA_TXT
        try:
            lineas = []
            campos_ordenados = [
                ('TIPO_PROCESO', 'TIPO PROCESO'),
                ('JURISDICCION', 'JURISDICCION'),
                ('ORGANISMO', 'ORGANISMO'),
                ('EXPEDIENTE', 'EXPEDIENTE'),
                ('CARATULA', 'CARATULA'),
                ('RESPONSABLE', 'RESPONSABLE'),
                ('CONTROL', 'CONTROL'),
                ('EVENTO', 'EVENTO'),
                ('FECHA_EVENTO', 'FECHA EVENTO'),
                ('TAREA_PENDIENTE', 'TAREA PENDIENTE'),
                ('FECHA_TAREA', 'FECHA TAREA'),
                ('OBSERVACIONES', 'OBSERVACIONES')
            ]

            for campo_interno, campo_visible in campos_ordenados:
                valor = datos.get(campo_interno, "")
                if campo_interno == 'OBSERVACIONES' and valor:
                    valor = valor.replace('\n', ' | ').replace('\r', '')
                    if len(valor) > 300:
                        valor = valor[:297] + "..."
                lineas.append(f"{campo_visible}: {valor}")

            with open(ficha_path, 'w', encoding='utf-8') as f:
                f.write('\n'.join(lineas))

            return True
        except Exception as e:
            st.error(f"Error escribiendo ficha.txt en {ruta_caso}: {e}")
            return False

    def escanear_casos(self) -> List[Caso]:
        """Escanea la jerarquía completa de carpetas."""
        casos = []

        if not self.ruta_base.exists():
            st.error(f"⚠️ La ruta base no existe: {self.ruta_base}")
            return casos

        # Nivel 1: AÑO
        for año in AÑOS_ACTIVOS:
            ruta_año = self.ruta_base / año
            if not ruta_año.exists():
                continue

            # Nivel 2: ESTADO
            for carpeta_estado in sorted(ruta_año.iterdir()):
                if not carpeta_estado.is_dir():
                    continue
                if "99" in carpeta_estado.name:
                    continue
                estado = carpeta_estado.name

                # Nivel 3: CLIENTE
                for carpeta_cliente in sorted(carpeta_estado.iterdir()):
                    if not carpeta_cliente.is_dir():
                        continue
                    cliente = carpeta_cliente.name

                    # Nivel 4: FUERO
                    for carpeta_fuero in sorted(carpeta_cliente.iterdir()):
                        if not carpeta_fuero.is_dir():
                            continue
                        if self._es_fuero_ignorado(carpeta_fuero.name):
                            continue
                        fuero = carpeta_fuero.name

                        # Nivel 5: CASO
                        for carpeta_caso in sorted(carpeta_fuero.iterdir()):
                            if not carpeta_caso.is_dir():
                                continue
                            if self._es_carpeta_interna_caso(carpeta_caso.name):
                                continue

                            causa = carpeta_caso.name
                            datos_ficha = self._leer_ficha(carpeta_caso)

                            caso = Caso(
                                ruta=carpeta_caso,
                                año=año,
                                estado=estado,
                                cliente=cliente,
                                fuero=fuero,
                                causa=causa,
                                tipo_proceso=datos_ficha['TIPO_PROCESO'],
                                jurisdiccion=datos_ficha['JURISDICCION'],
                                organismo=datos_ficha['ORGANISMO'],
                                expediente=datos_ficha['EXPEDIENTE'],
                                caratula=datos_ficha['CARATULA'],
                                responsable=datos_ficha['RESPONSABLE'],
                                control=datos_ficha['CONTROL'],
                                evento=datos_ficha['EVENTO'],
                                fecha_evento=datos_ficha['FECHA_EVENTO'],
                                tarea_pendiente=datos_ficha['TAREA_PENDIENTE'],
                                fecha_tarea=datos_ficha['FECHA_TAREA'],
                                observaciones=datos_ficha['OBSERVACIONES']
                            )
                            casos.append(caso)

        # ── Fallback: buscar ficha.json fuera del patrón jerárquico ──
        rutas_ya = {str(c.ruta) for c in casos}
        try:
            for p in self.ruta_base.rglob(FICHA_JSON):
                ruta_caso = p.parent
                if str(ruta_caso) in rutas_ya:
                    continue
                try:
                    partes = ruta_caso.relative_to(self.ruta_base).parts
                except ValueError:
                    continue
                if len(partes) >= 5:
                    año_f, estado_f, cliente_f, fuero_f = partes[0], partes[1], partes[2], partes[3]
                    causa_f = partes[4]
                else:
                    año_f = "SIN_AÑO"
                    estado_f = "SIN_ESTADO"
                    cliente_f = "SIN_CLIENTE"
                    fuero_f = "SIN_FUERO"
                    causa_f = ruta_caso.name

                datos_ficha = self._leer_ficha(ruta_caso)
                caso = Caso(
                    ruta=ruta_caso,
                    año=año_f,
                    estado=estado_f,
                    cliente=cliente_f,
                    fuero=fuero_f,
                    causa=causa_f,
                    tipo_proceso=datos_ficha['TIPO_PROCESO'],
                    jurisdiccion=datos_ficha['JURISDICCION'],
                    organismo=datos_ficha['ORGANISMO'],
                    expediente=datos_ficha['EXPEDIENTE'],
                    caratula=datos_ficha['CARATULA'],
                    responsable=datos_ficha['RESPONSABLE'],
                    control=datos_ficha['CONTROL'],
                    evento=datos_ficha['EVENTO'],
                    fecha_evento=datos_ficha['FECHA_EVENTO'],
                    tarea_pendiente=datos_ficha['TAREA_PENDIENTE'],
                    fecha_tarea=datos_ficha['FECHA_TAREA'],
                    observaciones=datos_ficha['OBSERVACIONES']
                )
                casos.append(caso)
                rutas_ya.add(str(ruta_caso))
        except Exception:
            pass

        casos.sort(key=lambda c: (c.año, c.estado, c.cliente))
        self._cache_casos = casos
        return casos

    def crear_caso(self, año: str, estado: str, cliente: str, fuero: str, nombre_caso: str) -> Tuple[bool, str]:
        """Crea la estructura física exacta."""
        try:
            cliente = limpiar_nombre_carpeta(cliente)
            nombre_caso = limpiar_nombre_carpeta(nombre_caso)
        except ValueError as e:
            return False, f"❌ Nombre inválido: {e}"

        ruta_caso = self.ruta_base / año / estado / cliente / fuero / nombre_caso

        try:
            for sub in SUBCARPETAS_ESTANDAR:
                ruta_sub = ruta_caso / sub
                os.makedirs(ruta_sub, exist_ok=True)

            cid = self._asegurar_case_id(ruta_caso)

            datos_plantilla = {campo: "S/D" for campo in CAMPOS_FICHA}
            datos_plantilla['FECHA_EVENTO'] = ""
            datos_plantilla['FECHA_TAREA'] = ""
            datos_plantilla['OBSERVACIONES'] = ""
            datos_plantilla['CARATULA'] = nombre_caso
            datos_plantilla['RESPONSABLE'] = "A asignar"
            datos_plantilla['CASE_ID'] = cid

            self._escribir_ficha(ruta_caso, datos_plantilla)
            self._append_log(ruta_caso, f"Caso creado: {nombre_caso}")

            return True, f"✅ Caso creado exitosamente: {nombre_caso}\n📂 Ruta: {ruta_caso}"
        except Exception as e:
            return False, f"❌ Error físico al crear carpetas: {str(e)}"

    def actualizar_caso(self, ruta_caso: Path, datos: Dict[str, str]) -> bool:
        """Actualiza la ficha de un caso existente."""
        ok = self._escribir_ficha(ruta_caso, datos)
        if ok:
            self._append_log(ruta_caso, "Actualización de ficha")
        return ok

    def ensure_case_structure(self, ruta_caso: Path) -> int:
        """Crea subcarpetas estandar faltantes. Retorna cantidad creadas."""
        creadas = 0
        for sub in SUBCARPETAS_ESTANDAR:
            p = ruta_caso / sub
            if not p.exists():
                try:
                    os.makedirs(p, exist_ok=True)
                    creadas += 1
                except Exception:
                    pass
        if creadas > 0:
            self._append_log(ruta_caso, f"Estructura normalizada: {creadas} subcarpetas creadas")
        return creadas

    def actualizar_campos_ficha(self, ruta_caso: Path, cambios: Dict[str, str]) -> bool:
        """Actualiza solo los campos indicados sin pisar el resto de la ficha."""
        datos = self._leer_ficha(ruta_caso)
        for k, v in cambios.items():
            if k in datos:
                datos[k] = v
        ok = self._escribir_ficha(ruta_caso, datos)
        if ok:
            campos_mod = ", ".join(cambios.keys())
            self._append_log(ruta_caso, f"Actualización de ficha ({campos_mod})")
        return ok

    def leer_datos_financieros(self, ruta_caso: Path) -> Dict[str, str]:
        """Lee campos financieros desde ficha.json."""
        p = ruta_caso / FICHA_JSON
        out = {campo: "" for campo in CAMPOS_FINANCIEROS}
        try:
            if p.exists():
                data = json.loads(p.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    for campo in CAMPOS_FINANCIEROS:
                        if campo in data:
                            out[campo] = "" if data[campo] is None else str(data[campo])
        except Exception:
            pass
        return out

    def guardar_datos_financieros(self, ruta_caso: Path, datos_fin: Dict[str, str]) -> bool:
        """Guarda campos financieros en ficha.json sin pisar los campos estándar."""
        p = ruta_caso / FICHA_JSON
        try:
            existing = {}
            if p.exists():
                existing = json.loads(p.read_text(encoding="utf-8"))
                if not isinstance(existing, dict):
                    existing = {}
            for campo in CAMPOS_FINANCIEROS:
                if campo in datos_fin:
                    existing[campo] = datos_fin[campo]
            p.write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8")
            self._append_log(ruta_caso, f"Datos financieros actualizados ({', '.join(datos_fin.keys())})")
            return True
        except Exception as e:
            st.error(f"Error guardando datos financieros: {e}")
            return False

    def mover_carpeta_fisica(self, caso_actual: Caso, nuevo_año: str, nuevo_estado: str,
                            nuevo_cliente: str, nuevo_fuero: str, nueva_causa: str) -> Tuple[bool, Path]:
        """Mueve la carpeta física del caso si cambian datos jerárquicos."""
        try:
            nuevo_cliente = limpiar_nombre_carpeta(nuevo_cliente)
            nueva_causa = limpiar_nombre_carpeta(nueva_causa)
        except ValueError as e:
            st.error(f"❌ Nombre inválido: {e}")
            return False, caso_actual.ruta

        nueva_ruta = self.ruta_base / nuevo_año / nuevo_estado / nuevo_cliente / nuevo_fuero / nueva_causa

        if caso_actual.ruta == nueva_ruta:
            return True, caso_actual.ruta

        if nueva_ruta.exists():
            st.error(f"❌ Ya existe una carpeta en: {nueva_ruta}")
            return False, caso_actual.ruta

        ruta_origen = caso_actual.ruta
        try:
            os.makedirs(nueva_ruta.parent, exist_ok=True)
            shutil.move(str(ruta_origen), str(nueva_ruta))

            origen_retenido = False
            if ruta_origen.exists():
                try:
                    remaining = list(ruta_origen.iterdir())
                    if not remaining:
                        os.rmdir(str(ruta_origen))
                    else:
                        origen_retenido = True
                except Exception:
                    pass

            msg = f"📦 Movido: {ruta_origen} → {nueva_ruta}"
            if origen_retenido:
                st.warning(f"{msg} (origen retenido por OneDrive/sincronización)")
            else:
                st.success(msg)

            self._append_log(nueva_ruta, f"Movido desde: {ruta_origen}")
            self._cache_casos = []

            return True, nueva_ruta
        except Exception as e:
            if ruta_origen.exists() and nueva_ruta.exists():
                try:
                    shutil.move(str(nueva_ruta), str(ruta_origen))
                except Exception:
                    pass
            st.error(f"❌ Error al mover carpeta física: {str(e)}")
            return False, caso_actual.ruta

    def sincronizar_ruta_fisica(self, caso_actual: Caso, nuevos_datos: Dict) -> Tuple[bool, str, Optional[Path]]:
        """Mueve físicamente la carpeta del caso si cambian AÑO/ESTADO/CLIENTE/FUERO."""
        def g(k, default):
            return nuevos_datos.get(k, nuevos_datos.get(k.upper(), default))

        año_n = g("año", caso_actual.año)
        estado_n = g("estado", caso_actual.estado)
        cliente_n = g("cliente", caso_actual.cliente)
        fuero_n = g("fuero", caso_actual.fuero)

        nueva_ruta = self.ruta_base / str(año_n) / str(estado_n) / str(cliente_n) / str(fuero_n) / caso_actual.causa

        try:
            if caso_actual.ruta.resolve() == nueva_ruta.resolve():
                return True, "Sin cambios en la ruta física.", caso_actual.ruta
        except Exception:
            if str(caso_actual.ruta) == str(nueva_ruta):
                return True, "Sin cambios en la ruta física.", caso_actual.ruta

        if nueva_ruta.exists():
            return False, f"Ya existe una carpeta destino: {nueva_ruta}", None

        try:
            os.makedirs(nueva_ruta.parent, exist_ok=True)
            shutil.move(str(caso_actual.ruta), str(nueva_ruta))
            return True, f"Carpeta movida a: {nueva_ruta}", nueva_ruta
        except Exception as e:
            return False, f"Error al mover carpeta física: {e}", None

    def obtener_clientes_existentes(self) -> List[str]:
        """Obtiene lista de clientes únicos existentes."""
        clientes = set()
        for caso in self._cache_casos:
            clientes.add(caso.cliente)
        return sorted(list(clientes))

    def obtener_años_existentes(self) -> List[str]:
        """Obtiene lista de años activos (de la configuración)."""
        return sorted(AÑOS_ACTIVOS, reverse=True)

    def listar_documentos_recientes(self, ruta_caso: Path, n: int = 5) -> List[Dict]:
        """Retorna los últimos n documentos del caso (subcarpeta 02. ESCRITOS).

        Returns:
            Lista de dicts con claves:
            - filename: str - nombre del archivo
            - updated_at: str - fecha de modificación (dd/mm HH:MM)
            - open_target: Path | None - Path al archivo para abrir
        """
        carpeta = ruta_caso / "02. ESCRITOS"
        if not carpeta.exists():
            return []

        files = []
        for f in carpeta.rglob("*"):
            if f.is_file():
                try:
                    mtime = f.stat().st_mtime
                    files.append((mtime, f))
                except Exception:
                    pass

        files.sort(key=lambda x: x[0], reverse=True)

        result = []
        for mtime, f in files[:n]:
            try:
                fecha_str = datetime.fromtimestamp(mtime).strftime("%d/%m %H:%M")
            except Exception:
                fecha_str = ""
            result.append({
                "filename": f.name,
                "updated_at": fecha_str,
                "open_target": f,
            })

        return result
