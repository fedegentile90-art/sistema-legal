#!/usr/bin/env python3
"""
Contract Test - Verifica que FS y DB devuelven el mismo shape/tipo.

Este test NO requiere DATABASE_URL ni conexion real.
Valida el contrato de la API publica del repositorio.

Uso:
  python db/contract_test.py
"""

import sys
import io
import json
from pathlib import Path
from typing import List
from unittest.mock import MagicMock

# Forzar UTF-8 en stdout para Windows
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

# Mock streamlit ANTES de importar cualquier modulo del proyecto
sys.modules['streamlit'] = MagicMock()

# Agregar raiz al path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


# ==============================================================================
# COLORES
# ==============================================================================

class C:
    OK = "\033[92m"
    FAIL = "\033[91m"
    WARN = "\033[93m"
    INFO = "\033[94m"
    RESET = "\033[0m"
    BOLD = "\033[1m"


def ok(msg): print(f"{C.OK}[OK] {msg}{C.RESET}")
def fail(msg): print(f"{C.FAIL}[FAIL] {msg}{C.RESET}")
def info(msg): print(f"{C.INFO}[INFO] {msg}{C.RESET}")


# ==============================================================================
# TEST: Contrato de obtener_clientes_existentes
# ==============================================================================

def test_obtener_clientes_existentes_contract():
    """
    Verifica que ambas implementaciones cumplen el contrato:
    - Firma: () -> List[str]
    - Retorno: lista ordenada alfabeticamente
    - Elementos: strings no vacios
    """
    print(f"\n{C.BOLD}{'=' * 60}")
    print("  CONTRACT TEST: obtener_clientes_existentes")
    print(f"{'=' * 60}{C.RESET}\n")

    errors = 0

    # --- Importar ambas clases directamente (sin activar backend)
    try:
        from fs_repo import GestorCasos as GestorFS
        from repo_db import GestorCasosDB as GestorDB
        ok("Imports exitosos: GestorCasos (FS) y GestorCasosDB (DB)")
    except ImportError as e:
        fail(f"Error importando: {e}")
        return False

    # --- Verificar que el metodo existe en ambas clases
    if not hasattr(GestorFS, 'obtener_clientes_existentes'):
        fail("GestorCasos (FS) no tiene metodo obtener_clientes_existentes")
        errors += 1
    else:
        ok("GestorCasos (FS) tiene metodo obtener_clientes_existentes")

    if not hasattr(GestorDB, 'obtener_clientes_existentes'):
        fail("GestorCasosDB (DB) no tiene metodo obtener_clientes_existentes")
        errors += 1
    else:
        ok("GestorCasosDB (DB) tiene metodo obtener_clientes_existentes")

    # --- Verificar firmas con annotations
    import inspect

    sig_fs = inspect.signature(GestorFS.obtener_clientes_existentes)
    sig_db = inspect.signature(GestorDB.obtener_clientes_existentes)

    # Parametros (solo self)
    params_fs = [p for p in sig_fs.parameters.keys() if p != 'self']
    params_db = [p for p in sig_db.parameters.keys() if p != 'self']

    if params_fs == params_db == []:
        ok("Firma: ambos metodos no reciben parametros (solo self)")
    else:
        fail(f"Firma diferente: FS={params_fs}, DB={params_db}")
        errors += 1

    # Return annotation
    ret_fs = sig_fs.return_annotation
    ret_db = sig_db.return_annotation

    # Comparar annotations (pueden ser string o tipo)
    def normalize_annotation(ann):
        if ann == inspect.Parameter.empty:
            return None
        if hasattr(ann, '__origin__'):  # typing.List
            return f"List[{ann.__args__[0].__name__}]"
        return str(ann)

    ann_fs = normalize_annotation(ret_fs)
    ann_db = normalize_annotation(ret_db)

    if ann_fs == ann_db:
        ok(f"Return annotation: ambos -> {ann_fs}")
    else:
        # Pueden ser equivalentes pero escritos diferente
        info(f"Return annotation: FS={ann_fs}, DB={ann_db} (verificar equivalencia)")

    # --- Verificar docstrings mencionan comportamiento clave
    doc_fs = GestorFS.obtener_clientes_existentes.__doc__ or ""
    doc_db = GestorDB.obtener_clientes_existentes.__doc__ or ""

    if "unic" in doc_fs.lower() or "exist" in doc_fs.lower():
        ok("Docstring FS menciona clientes unicos/existentes")
    else:
        info("Docstring FS podria ser mas explicito")

    if "caso" in doc_db.lower() or "unic" in doc_db.lower():
        ok("Docstring DB menciona casos/unicos")
    else:
        info("Docstring DB podria ser mas explicito")

    # --- Resumen
    print()
    if errors == 0:
        print(f"{C.OK}{C.BOLD}CONTRACT TEST PASSED{C.RESET}")
        return True
    else:
        print(f"{C.FAIL}{C.BOLD}CONTRACT TEST FAILED ({errors} errores){C.RESET}")
        return False


# ==============================================================================
# TEST: Contrato de escanear_casos
# ==============================================================================

def test_escanear_casos_contract():
    """
    Verifica contrato de escanear_casos:
    - Firma: () -> List[Caso]
    - Retorno: lista de objetos Caso
    """
    print(f"\n{C.BOLD}{'=' * 60}")
    print("  CONTRACT TEST: escanear_casos")
    print(f"{'=' * 60}{C.RESET}\n")

    errors = 0

    try:
        from fs_repo import GestorCasos as GestorFS
        from repo_db import GestorCasosDB as GestorDB
        from domain import Caso
        ok("Imports exitosos")
    except ImportError as e:
        fail(f"Error importando: {e}")
        return False

    # Verificar metodo existe
    for name, cls in [("FS", GestorFS), ("DB", GestorDB)]:
        if hasattr(cls, 'escanear_casos'):
            ok(f"{name} tiene metodo escanear_casos")
        else:
            fail(f"{name} NO tiene metodo escanear_casos")
            errors += 1

    # Verificar firma
    import inspect
    for name, cls in [("FS", GestorFS), ("DB", GestorDB)]:
        sig = inspect.signature(cls.escanear_casos)
        params = [p for p in sig.parameters.keys() if p != 'self']
        if params == []:
            ok(f"{name}.escanear_casos() no recibe parametros")
        else:
            fail(f"{name}.escanear_casos() tiene parametros inesperados: {params}")
            errors += 1

    print()
    if errors == 0:
        print(f"{C.OK}{C.BOLD}CONTRACT TEST PASSED{C.RESET}")
        return True
    else:
        print(f"{C.FAIL}{C.BOLD}CONTRACT TEST FAILED ({errors} errores){C.RESET}")
        return False


# ==============================================================================
# TEST: Contrato de _leer_ficha
# ==============================================================================

def test_leer_ficha_contract():
    """
    Verifica contrato de _leer_ficha:
    - Firma: (ruta_caso: Path) -> Dict[str, str]
    """
    print(f"\n{C.BOLD}{'=' * 60}")
    print("  CONTRACT TEST: _leer_ficha")
    print(f"{'=' * 60}{C.RESET}\n")

    errors = 0

    try:
        from fs_repo import GestorCasos as GestorFS
        from repo_db import GestorCasosDB as GestorDB
        ok("Imports exitosos")
    except ImportError as e:
        fail(f"Error importando: {e}")
        return False

    import inspect

    for name, cls in [("FS", GestorFS), ("DB", GestorDB)]:
        if not hasattr(cls, '_leer_ficha'):
            fail(f"{name} NO tiene metodo _leer_ficha")
            errors += 1
            continue

        ok(f"{name} tiene metodo _leer_ficha")

        sig = inspect.signature(cls._leer_ficha)
        params = [p for p in sig.parameters.keys() if p != 'self']

        if len(params) == 1 and 'ruta' in params[0].lower():
            ok(f"{name}._leer_ficha recibe 1 parametro de ruta")
        else:
            fail(f"{name}._leer_ficha parametros inesperados: {params}")
            errors += 1

    print()
    if errors == 0:
        print(f"{C.OK}{C.BOLD}CONTRACT TEST PASSED{C.RESET}")
        return True
    else:
        print(f"{C.FAIL}{C.BOLD}CONTRACT TEST FAILED ({errors} errores){C.RESET}")
        return False


# ==============================================================================
# TEST: Contrato de actualizar_campos_ficha
# ==============================================================================

def test_actualizar_campos_ficha_contract():
    """
    Verifica contrato de actualizar_campos_ficha:
    - Firma: (ruta_caso: Path, cambios: Dict[str, str]) -> bool
    """
    print(f"\n{C.BOLD}{'=' * 60}")
    print("  CONTRACT TEST: actualizar_campos_ficha")
    print(f"{'=' * 60}{C.RESET}\n")

    errors = 0

    try:
        from fs_repo import GestorCasos as GestorFS
        from repo_db import GestorCasosDB as GestorDB
        ok("Imports exitosos")
    except ImportError as e:
        fail(f"Error importando: {e}")
        return False

    import inspect

    for name, cls in [("FS", GestorFS), ("DB", GestorDB)]:
        if not hasattr(cls, 'actualizar_campos_ficha'):
            fail(f"{name} NO tiene metodo actualizar_campos_ficha")
            errors += 1
            continue

        ok(f"{name} tiene metodo actualizar_campos_ficha")

        sig = inspect.signature(cls.actualizar_campos_ficha)
        params = [p for p in sig.parameters.keys() if p != 'self']

        # Debe tener 2 parametros: ruta_caso y cambios
        if len(params) == 2:
            ok(f"{name}.actualizar_campos_ficha recibe 2 parametros: {params}")
        else:
            fail(f"{name}.actualizar_campos_ficha parametros inesperados: {params}")
            errors += 1

        # Return type debe ser bool
        ret = sig.return_annotation
        if ret == bool or str(ret) == "<class 'bool'>":
            ok(f"{name}.actualizar_campos_ficha -> bool")
        elif ret == inspect.Parameter.empty:
            info(f"{name}.actualizar_campos_ficha sin annotation de retorno (asumir bool)")
        else:
            info(f"{name}.actualizar_campos_ficha -> {ret}")

    print()
    if errors == 0:
        print(f"{C.OK}{C.BOLD}CONTRACT TEST PASSED{C.RESET}")
        return True
    else:
        print(f"{C.FAIL}{C.BOLD}CONTRACT TEST FAILED ({errors} errores){C.RESET}")
        return False


# ==============================================================================
# TEST: Contrato de objeto Caso (atributos usados por detalle cliente)
# ==============================================================================

def test_caso_attributes_contract():
    """
    Verifica que el objeto Caso tiene todos los atributos usados por
    la vista de detalle de cliente.
    """
    print(f"\n{C.BOLD}{'=' * 60}")
    print("  CONTRACT TEST: Caso attributes (detalle cliente)")
    print(f"{'=' * 60}{C.RESET}\n")

    errors = 0

    try:
        from domain import Caso
        ok("Import Caso exitoso")
    except ImportError as e:
        fail(f"Error importando Caso: {e}")
        return False

    # Atributos requeridos por la vista de detalle de cliente
    required_attrs = [
        # Estructurales
        "ruta", "año", "estado", "cliente", "fuero", "causa",
        # De ficha
        "tipo_proceso", "jurisdiccion", "organismo", "expediente",
        "caratula", "responsable", "control", "evento",
        "fecha_evento", "tarea_pendiente", "fecha_tarea", "observaciones",
    ]

    # Propiedades calculadas
    required_properties = ["semaforo"]

    # Metodos requeridos
    required_methods = ["to_dict", "_parsear_fecha"]

    # Verificar atributos del dataclass
    import dataclasses
    if dataclasses.is_dataclass(Caso):
        ok("Caso es un dataclass")
        fields = {f.name for f in dataclasses.fields(Caso)}

        for attr in required_attrs:
            if attr in fields:
                ok(f"Caso tiene campo '{attr}'")
            else:
                fail(f"Caso NO tiene campo '{attr}'")
                errors += 1
    else:
        fail("Caso NO es un dataclass")
        errors += 1

    # Verificar propiedades
    for prop in required_properties:
        if hasattr(Caso, prop) and isinstance(getattr(Caso, prop), property):
            ok(f"Caso tiene propiedad '{prop}'")
        else:
            fail(f"Caso NO tiene propiedad '{prop}'")
            errors += 1

    # Verificar metodos
    for method in required_methods:
        if hasattr(Caso, method) and callable(getattr(Caso, method)):
            ok(f"Caso tiene metodo '{method}'")
        else:
            fail(f"Caso NO tiene metodo '{method}'")
            errors += 1

    print()
    if errors == 0:
        print(f"{C.OK}{C.BOLD}CONTRACT TEST PASSED{C.RESET}")
        return True
    else:
        print(f"{C.FAIL}{C.BOLD}CONTRACT TEST FAILED ({errors} errores){C.RESET}")
        return False


# ==============================================================================
# TEST: Contrato de to_dict (Case Digital File)
# ==============================================================================

def test_caso_to_dict_contract():
    """
    Verifica que Caso.to_dict() produce el mismo shape en ambos backends.
    Esto es critico para el flujo de Case Digital File (listado + detalle).
    """
    print(f"\n{C.BOLD}{'=' * 60}")
    print("  CONTRACT TEST: Caso.to_dict() (Case Digital File)")
    print(f"{'=' * 60}{C.RESET}\n")

    errors = 0

    try:
        from domain import Caso
        from pathlib import Path
        ok("Import Caso exitoso")
    except ImportError as e:
        fail(f"Error importando: {e}")
        return False

    # Crear caso de prueba
    caso_test = Caso(
        ruta=Path("test/path"),
        año="2026",
        estado="ACTIVOS",
        cliente="CLIENTE_TEST",
        fuero="CIVIL",
        causa="CAUSA_TEST",
        tipo_proceso="Ordinario",
        jurisdiccion="Nacional",
        organismo="Juzgado 1",
        expediente="12345/2026",
        caratula="Test c/ Test",
        responsable="Dr. Test",
        control="Control Test",
        evento="Audiencia",
        fecha_evento="01/02/2026",
        tarea_pendiente="Contestar",
        fecha_tarea="15/02/2026",
        observaciones="Obs test",
    )

    d = caso_test.to_dict()

    # Verificar claves requeridas para grilla
    required_keys = [
        "AÑO", "ESTADO", "CLIENTE", "FUERO", "CAUSA",
        "TIPO PROCESO", "JURISDICCION", "ORGANISMO", "EXPEDIENTE",
        "CARATULA", "RESPONSABLE", "CONTROL", "EVENTO",
        "FECHA EVENTO", "TAREA PENDIENTE", "FECHA TAREA",
        "OBSERVACIONES", "SEMÁFORO", "_RUTA"
    ]

    for key in required_keys:
        if key in d:
            ok(f"to_dict() contiene '{key}'")
        else:
            fail(f"to_dict() NO contiene '{key}'")
            errors += 1

    # Verificar tipos de salida:
    # - flags internos bool
    # - resto de claves en str para grilla/export
    bool_keys = {"is_legacy", "_LEGACY"}
    for key, val in d.items():
        if key in bool_keys:
            if not isinstance(val, bool):
                fail(f"to_dict()['{key}'] no es bool: {type(val)}")
                errors += 1
            continue
        if not isinstance(val, str):
            fail(f"to_dict()['{key}'] no es string: {type(val)}")
            errors += 1

    # Verificar que _RUTA es el str(ruta)
    if d.get("_RUTA") == str(caso_test.ruta):
        ok("_RUTA == str(caso.ruta)")
    else:
        fail(f"_RUTA mismatch: {d.get('_RUTA')} != {str(caso_test.ruta)}")
        errors += 1

    print()
    if errors == 0:
        print(f"{C.OK}{C.BOLD}CONTRACT TEST PASSED{C.RESET}")
        return True
    else:
        print(f"{C.FAIL}{C.BOLD}CONTRACT TEST FAILED ({errors} errores){C.RESET}")
        return False


# ==============================================================================
# TEST: Contrato de pseudo-path DB (Case Digital File - seleccion)
# ==============================================================================

def test_db_pseudo_path_contract():
    """
    Verifica que el pseudo-path de DB es valido para comparacion string.
    Flujo critico: st.session_state["selected_case_id"] == str(c.ruta)
    """
    print(f"\n{C.BOLD}{'=' * 60}")
    print("  CONTRACT TEST: DB pseudo-path (seleccion de caso)")
    print(f"{'=' * 60}{C.RESET}\n")

    errors = 0

    try:
        from repo_db import GestorCasosDB
        from pathlib import Path
        ok("Imports exitosos")
    except ImportError as e:
        fail(f"Error importando: {e}")
        return False

    gestor = GestorCasosDB()

    # Verificar que _db_path genera formato correcto
    test_id = "123e4567-e89b-12d3-a456-426614174000"
    pseudo_path = gestor._db_path(test_id)

    # Debe ser un Path
    if isinstance(pseudo_path, Path):
        ok(f"_db_path retorna Path: {pseudo_path}")
    else:
        fail(f"_db_path no retorna Path: {type(pseudo_path)}")
        errors += 1

    # El string debe empezar con db://cases/ o db:\cases\ (Windows)
    path_str = str(pseudo_path)
    if path_str.startswith("db://cases/") or path_str.startswith("db:\\cases\\"):
        ok(f"Formato correcto (OS-specific): {path_str}")
    else:
        fail(f"Formato incorrecto: {path_str}")
        errors += 1

    # Verificar que str(path) es estable para comparacion
    path_str_1 = str(pseudo_path)
    path_str_2 = str(pseudo_path)
    if path_str_1 == path_str_2:
        ok("str(pseudo_path) es estable para comparacion")
    else:
        fail("str(pseudo_path) NO es estable")
        errors += 1

    # Verificar que _get_case_id_from_path es inversa de _db_path
    recovered_id = gestor._get_case_id_from_path(pseudo_path)
    if recovered_id == test_id:
        ok(f"_get_case_id_from_path inversa correcta: {recovered_id}")
    else:
        fail(f"_get_case_id_from_path fallo: {recovered_id} != {test_id}")
        errors += 1

    print()
    if errors == 0:
        print(f"{C.OK}{C.BOLD}CONTRACT TEST PASSED{C.RESET}")
        return True
    else:
        print(f"{C.FAIL}{C.BOLD}CONTRACT TEST FAILED ({errors} errores){C.RESET}")
        return False


# ==============================================================================
# TEST: Contrato de _row_to_caso (DB) vs construccion directa (FS)
# ==============================================================================

def test_caso_construction_contract():
    """
    Verifica que DB construye objetos Caso con los mismos tipos que FS.
    """
    print(f"\n{C.BOLD}{'=' * 60}")
    print("  CONTRACT TEST: Caso construction (FS vs DB)")
    print(f"{'=' * 60}{C.RESET}\n")

    errors = 0

    try:
        from fs_repo import GestorCasos as GestorFS
        from repo_db import GestorCasosDB as GestorDB
        from domain import Caso
        from pathlib import Path
        ok("Imports exitosos")
    except ImportError as e:
        fail(f"Error importando: {e}")
        return False

    # Verificar que DB tiene _row_to_caso
    if hasattr(GestorDB, '_row_to_caso'):
        ok("GestorDB tiene metodo _row_to_caso")
    else:
        fail("GestorDB NO tiene metodo _row_to_caso")
        errors += 1

    # Verificar que ambos retornan List[Caso] en escanear_casos
    import inspect

    for name, cls in [("FS", GestorFS), ("DB", GestorDB)]:
        sig = inspect.signature(cls.escanear_casos)
        ret = sig.return_annotation

        # Verificar que el return annotation menciona Caso o List
        ret_str = str(ret)
        if "Caso" in ret_str or "List" in ret_str:
            ok(f"{name}.escanear_casos annotation incluye Caso/List")
        else:
            info(f"{name}.escanear_casos annotation: {ret_str}")

    # Verificar tipos de atributos en Caso
    import dataclasses
    fields = dataclasses.fields(Caso)

    expected_types = {
        "ruta": Path,
        "año": str,
        "estado": str,
        "cliente": str,
        "fuero": str,
        "causa": str,
        "tipo_proceso": str,
        "jurisdiccion": str,
        "organismo": str,
        "expediente": str,
        "caratula": str,
        "responsable": str,
        "control": str,
        "evento": str,
        "fecha_evento": str,
        "fecha_tarea": str,
        "tarea_pendiente": str,
        "observaciones": str,
    }

    for field in fields:
        if field.name in expected_types:
            expected = expected_types[field.name]
            if field.type == expected or str(field.type) == str(expected):
                ok(f"Caso.{field.name}: {field.type}")
            else:
                fail(f"Caso.{field.name} tipo inesperado: {field.type} (esperado: {expected})")
                errors += 1

    print()
    if errors == 0:
        print(f"{C.OK}{C.BOLD}CONTRACT TEST PASSED{C.RESET}")
        return True
    else:
        print(f"{C.FAIL}{C.BOLD}CONTRACT TEST FAILED ({errors} errores){C.RESET}")
        return False


# ==============================================================================
# TEST: Contrato de listar_documentos_recientes (shape)
# ==============================================================================

def test_recent_documents_contract_shape():
    """
    Verifica que ambas implementaciones cumplen el contrato:
    - Firma: (ruta_caso: Path, n: int = 5) -> List[Dict]
    - Retorno: lista de dicts con claves: filename, updated_at, open_target
    - API publica (repo.GestorCasos) expone el metodo
    """
    print(f"\n{C.BOLD}{'=' * 60}")
    print("  CONTRACT TEST: listar_documentos_recientes (shape)")
    print(f"{'=' * 60}{C.RESET}\n")

    errors = 0

    try:
        from fs_repo import GestorCasos as GestorFS
        from repo_db import GestorCasosDB as GestorDB
        from repo import GestorCasos as GestorPublic
        ok("Imports exitosos: FS, DB y API publica (repo.GestorCasos)")
    except ImportError as e:
        fail(f"Error importando: {e}")
        return False

    # Verificar que el metodo existe en ambas implementaciones
    for name, cls in [("FS", GestorFS), ("DB", GestorDB)]:
        if hasattr(cls, 'listar_documentos_recientes'):
            ok(f"{name} tiene metodo listar_documentos_recientes")
        else:
            fail(f"{name} NO tiene metodo listar_documentos_recientes")
            errors += 1

    # Verificar que la API publica expone el metodo
    if hasattr(GestorPublic, 'listar_documentos_recientes'):
        ok("API publica (repo.GestorCasos) expone listar_documentos_recientes")
    else:
        fail("API publica (repo.GestorCasos) NO expone listar_documentos_recientes")
        errors += 1

    # Verificar firma
    import inspect
    for name, cls in [("FS", GestorFS), ("DB", GestorDB)]:
        if not hasattr(cls, 'listar_documentos_recientes'):
            continue
        sig = inspect.signature(cls.listar_documentos_recientes)
        params = [p for p in sig.parameters.keys() if p != 'self']
        # Debe tener 2 parametros: ruta_caso y n
        if len(params) == 2 and 'ruta' in params[0].lower() and params[1] == 'n':
            ok(f"{name}.listar_documentos_recientes(ruta_caso, n) - firma correcta")
        else:
            fail(f"{name}.listar_documentos_recientes parametros inesperados: {params}")
            errors += 1

    # Verificar que retorna List[Dict] (via docstring o annotation)
    for name, cls in [("FS", GestorFS), ("DB", GestorDB)]:
        if not hasattr(cls, 'listar_documentos_recientes'):
            continue
        doc = cls.listar_documentos_recientes.__doc__ or ""
        if "filename" in doc and "updated_at" in doc and "open_target" in doc:
            ok(f"{name} docstring menciona claves requeridas")
        else:
            info(f"{name} docstring podria ser mas explicito sobre claves")

    print()
    if errors == 0:
        print(f"{C.OK}{C.BOLD}CONTRACT TEST PASSED{C.RESET}")
        return True
    else:
        print(f"{C.FAIL}{C.BOLD}CONTRACT TEST FAILED ({errors} errores){C.RESET}")
        return False


# ==============================================================================
# TEST: Contrato de listar_documentos_recientes (empty behavior)
# ==============================================================================

def test_recent_documents_empty_behavior():
    """
    Verifica que si no hay documentos, ambos modos devuelven lista vacia.
    """
    print(f"\n{C.BOLD}{'=' * 60}")
    print("  CONTRACT TEST: listar_documentos_recientes (empty)")
    print(f"{'=' * 60}{C.RESET}\n")

    errors = 0

    try:
        from fs_repo import GestorCasos as GestorFS
        from repo_db import GestorCasosDB as GestorDB
        from pathlib import Path
        ok("Imports exitosos")
    except ImportError as e:
        fail(f"Error importando: {e}")
        return False

    # Test FS con ruta inexistente
    gestor_fs = GestorFS(Path("C:/inexistente_test_dir_12345"))
    result_fs = gestor_fs.listar_documentos_recientes(Path("C:/inexistente_test_dir_12345/caso"))
    if isinstance(result_fs, list) and len(result_fs) == 0:
        ok("FS: ruta inexistente -> lista vacia")
    else:
        fail(f"FS: ruta inexistente -> {type(result_fs)} len={len(result_fs) if hasattr(result_fs, '__len__') else 'N/A'}")
        errors += 1

    # Test DB con case_id invalido
    gestor_db = GestorDB()
    result_db = gestor_db.listar_documentos_recientes(Path("db://cases/00000000-0000-0000-0000-000000000000"))
    if isinstance(result_db, list) and len(result_db) == 0:
        ok("DB: case_id invalido -> lista vacia")
    else:
        fail(f"DB: case_id invalido -> {type(result_db)} len={len(result_db) if hasattr(result_db, '__len__') else 'N/A'}")
        errors += 1

    print()
    if errors == 0:
        print(f"{C.OK}{C.BOLD}CONTRACT TEST PASSED{C.RESET}")
        return True
    else:
        print(f"{C.FAIL}{C.BOLD}CONTRACT TEST FAILED ({errors} errores){C.RESET}")
        return False


# ==============================================================================
# TEST: Contrato de campos evento en Caso.to_dict()
# ==============================================================================

def test_evento_fields_contract():
    """
    Verifica campos de evento en Caso.to_dict():
    - Existen claves 'EVENTO' y 'FECHA EVENTO'
    - Ambas son str (nunca None)
    - Caso vacio mantiene strings vacios
    """
    print(f"\n{C.BOLD}{'=' * 60}")
    print("  CONTRACT TEST: evento fields in Caso.to_dict()")
    print(f"{'=' * 60}{C.RESET}\n")

    errors = 0

    try:
        from domain import Caso
        from pathlib import Path
        ok("Import Caso exitoso")
    except ImportError as e:
        fail(f"Error importando: {e}")
        return False

    caso_con_evento = Caso(
        ruta=Path("test/path"),
        año="2026",
        estado="ACTIVOS",
        cliente="TEST",
        fuero="CIVIL",
        causa="TEST",
        evento="Audiencia preliminar",
        fecha_evento="20/03/2026",
    )
    d = caso_con_evento.to_dict()

    if "EVENTO" in d:
        ok("to_dict() contiene clave 'EVENTO'")
    else:
        fail("to_dict() NO contiene clave 'EVENTO'")
        errors += 1

    if "FECHA EVENTO" in d:
        ok("to_dict() contiene clave 'FECHA EVENTO'")
    else:
        fail("to_dict() NO contiene clave 'FECHA EVENTO'")
        errors += 1

    if isinstance(d.get("EVENTO"), str):
        ok(f"EVENTO es str: '{d.get('EVENTO')}'")
    else:
        fail(f"EVENTO no es str: {type(d.get('EVENTO'))}")
        errors += 1

    if isinstance(d.get("FECHA EVENTO"), str):
        ok(f"FECHA EVENTO es str: '{d.get('FECHA EVENTO')}'")
    else:
        fail(f"FECHA EVENTO no es str: {type(d.get('FECHA EVENTO'))}")
        errors += 1

    caso_sin_evento = Caso(
        ruta=Path("test/path2"),
        año="2026",
        estado="ACTIVOS",
        cliente="TEST",
        fuero="CIVIL",
        causa="TEST",
        evento="",
        fecha_evento="",
    )
    d2 = caso_sin_evento.to_dict()

    if d2.get("EVENTO") == "":
        ok("EVENTO vacio -> string vacio")
    else:
        fail(f"EVENTO vacio inesperado: '{d2.get('EVENTO')}'")
        errors += 1

    if d2.get("FECHA EVENTO") == "":
        ok("FECHA EVENTO vacia -> string vacio")
    else:
        fail(f"FECHA EVENTO vacia inesperada: '{d2.get('FECHA EVENTO')}'")
        errors += 1

    print()
    if errors == 0:
        print(f"{C.OK}{C.BOLD}CONTRACT TEST PASSED{C.RESET}")
        return True
    else:
        print(f"{C.FAIL}{C.BOLD}CONTRACT TEST FAILED ({errors} errores){C.RESET}")
        return False


def test_tarea_fields_contract():
    """
    Verifica paridad FS/DB para campos de tarea en Caso.to_dict():
    - Existen claves 'TAREA PENDIENTE' y 'FECHA TAREA'
    - Ambas son str (nunca None) en ambos modos
    - SEMÁFORO existe y es str
    - Sin tarea: strings vacíos y semáforo ⚪
    """
    print(f"\n{C.BOLD}{'=' * 60}")
    print("  CONTRACT TEST: tarea fields in Caso.to_dict()")
    print(f"{'=' * 60}{C.RESET}\n")

    errors = 0

    try:
        from domain import Caso
        from pathlib import Path
        ok("Import Caso exitoso")
    except ImportError as e:
        fail(f"Error importando: {e}")
        return False

    # Caso con tarea
    caso_con_tarea = Caso(
        ruta=Path("test/path"),
        año="2026",
        estado="ACTIVOS",
        cliente="TEST",
        fuero="CIVIL",
        causa="TEST",
        tarea_pendiente="Contestar demanda",
        fecha_tarea="20/03/2026",
    )
    d = caso_con_tarea.to_dict()

    # Claves
    if "TAREA PENDIENTE" in d:
        ok("to_dict() contiene clave 'TAREA PENDIENTE'")
    else:
        fail("to_dict() NO contiene clave 'TAREA PENDIENTE'")
        errors += 1

    if "FECHA TAREA" in d:
        ok("to_dict() contiene clave 'FECHA TAREA'")
    else:
        fail("to_dict() NO contiene clave 'FECHA TAREA'")
        errors += 1

    if "SEMÁFORO" in d:
        ok("to_dict() contiene clave 'SEMÁFORO'")
    else:
        fail("to_dict() NO contiene clave 'SEMÁFORO'")
        errors += 1

    # Tipos
    if isinstance(d.get("TAREA PENDIENTE"), str):
        ok(f"TAREA PENDIENTE es str: '{d.get('TAREA PENDIENTE')}'")
    else:
        fail(f"TAREA PENDIENTE no es str: {type(d.get('TAREA PENDIENTE'))}")
        errors += 1

    if isinstance(d.get("FECHA TAREA"), str):
        ok(f"FECHA TAREA es str: '{d.get('FECHA TAREA')}'")
    else:
        fail(f"FECHA TAREA no es str: {type(d.get('FECHA TAREA'))}")
        errors += 1

    if isinstance(d.get("SEMÁFORO"), str):
        ok(f"SEMÁFORO es str: '{d.get('SEMÁFORO')}'")
    else:
        fail(f"SEMÁFORO no es str: {type(d.get('SEMÁFORO'))}")
        errors += 1

    # Caso sin tarea (vacío)
    caso_sin_tarea = Caso(
        ruta=Path("test/path2"),
        año="2026",
        estado="ACTIVOS",
        cliente="TEST",
        fuero="CIVIL",
        causa="TEST",
        tarea_pendiente="",
        fecha_tarea="",
    )
    d2 = caso_sin_tarea.to_dict()

    if d2.get("TAREA PENDIENTE") == "":
        ok("TAREA PENDIENTE vacio -> string vacio")
    else:
        fail(f"TAREA PENDIENTE vacio inesperado: '{d2.get('TAREA PENDIENTE')}'")
        errors += 1

    if d2.get("FECHA TAREA") == "":
        ok("FECHA TAREA vacio -> string vacio")
    else:
        fail(f"FECHA TAREA vacio inesperado: '{d2.get('FECHA TAREA')}'")
        errors += 1

    if d2.get("SEMÁFORO") == "⚪":
        ok("Sin tarea -> semáforo ⚪")
    else:
        fail(f"Sin tarea -> semáforo inesperado: '{d2.get('SEMÁFORO')}'")
        errors += 1

    print()
    if errors == 0:
        print(f"{C.OK}{C.BOLD}CONTRACT TEST PASSED{C.RESET}")
        return True
    else:
        print(f"{C.FAIL}{C.BOLD}CONTRACT TEST FAILED ({errors} errores){C.RESET}")
        return False


# ==============================================================================
# TEST: Contrato operativo runner DailyOps (P2-02)
# ==============================================================================

def test_dailyops_runner_contract():
    """
    Valida contrato estatico del runner DailyOps:
    - switch -DailyOps
    - secuencia env_contract_daily_ops -> nightly_audit -> release_gate
    - corte explicito ante fallo nightly
    - corte explicito ante fallo de contrato de entorno
    - corte explicito ante timeout por paso
    - timeout configurable por env VG_STEP_TIMEOUT_SEC
    - exit codes estables (0/20/30/99)
    - alias ops en RUN_ERP.cmd
    """
    print(f"\n{C.BOLD}{'=' * 60}")
    print("  CONTRACT TEST: DailyOps runner (P2-02)")
    print(f"{'=' * 60}{C.RESET}\n")

    errors = 0
    ps1_path = ROOT / "RUN_ERP.ps1"
    cmd_path = ROOT / "RUN_ERP.cmd"

    if not ps1_path.exists():
        fail(f"No existe {ps1_path}")
        return False
    if not cmd_path.exists():
        fail(f"No existe {cmd_path}")
        return False

    ps1_text = ps1_path.read_text(encoding="utf-8", errors="replace")
    cmd_text = cmd_path.read_text(encoding="utf-8", errors="replace")

    required_ps1_tokens = [
        "[switch]$DailyOps",
        '$EXIT_OK = 0',
        '$EXIT_NIGHTLY_FAIL = 20',
        '$EXIT_GATE_FAIL = 30',
        '$EXIT_RUNTIME_FAIL = 99',
        'function Get-PositiveIntEnv',
        'VG_STEP_TIMEOUT_SEC',
        'Step timeout: {0}s (env VG_STEP_TIMEOUT_SEC)',
        'function Run-DailyOps',
        'Invoke-PythonStep -StepName "env_contract_daily_ops" -StepArgs @("db/env_contract.py", "--profile", "daily_ops") -TimeoutSec $StepTimeoutSec',
        'Invoke-PythonStep -StepName "nightly_audit" -StepArgs @("db/nightly_audit.py") -TimeoutSec $StepTimeoutSec',
        'Invoke-PythonStep -StepName "release_gate" -StepArgs @("db/release_gate.py") -TimeoutSec $StepTimeoutSec',
        '[TIMEOUT] {0} excedio {1}s. Terminando proceso PID={2}.',
        '[CUT] env_contract_daily_ops timeout. Se corta flujo antes de nightly_audit.',
        '[CUT] env_contract_daily_ops fallido. Se corta flujo antes de nightly_audit.',
        '[CUT] nightly_audit timeout. Se corta flujo antes de release_gate.',
        '[CUT] release_gate timeout.',
        '[CUT] nightly_audit fallido. Se corta flujo antes de release_gate.',
    ]
    for token in required_ps1_tokens:
        if token in ps1_text:
            ok(f"RUN_ERP.ps1 contiene: {token}")
        else:
            fail(f"RUN_ERP.ps1 NO contiene: {token}")
            errors += 1

    env_idx = ps1_text.find('Invoke-PythonStep -StepName "env_contract_daily_ops"')
    nightly_idx = ps1_text.find('Invoke-PythonStep -StepName "nightly_audit"')
    gate_idx = ps1_text.find('Invoke-PythonStep -StepName "release_gate"')
    if env_idx >= 0 and nightly_idx >= 0 and gate_idx >= 0 and env_idx < nightly_idx < gate_idx:
        ok("Secuencia correcta: env_contract_daily_ops -> nightly_audit -> release_gate")
    else:
        fail("Secuencia invalida en DailyOps (env_contract/nightly/release_gate)")
        errors += 1

    required_cmd_tokens = [
        'if /I "%~1"=="ops" goto run_ops',
        'if /I "%~1"=="-DailyOps" goto run_ops',
        'powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0RUN_ERP.ps1" -DailyOps',
    ]
    for token in required_cmd_tokens:
        if token in cmd_text:
            ok(f"RUN_ERP.cmd contiene: {token}")
        else:
            fail(f"RUN_ERP.cmd NO contiene: {token}")
            errors += 1

    print()
    if errors == 0:
        print(f"{C.OK}{C.BOLD}CONTRACT TEST PASSED{C.RESET}")
        return True
    else:
        print(f"{C.FAIL}{C.BOLD}CONTRACT TEST FAILED ({errors} errores){C.RESET}")
        return False


# ==============================================================================
# TEST: Contrato timeout release gate (P3-03)
# ==============================================================================

def test_release_gate_timeout_contract():
    """
    Valida contrato estatico de timeout en release_gate:
    - timeout configurable por env (VG_SUITE_TIMEOUT_SEC)
    - subprocess.run con timeout
    - manejo explicito de TimeoutExpired
    - resumen/fallo final con motivo de timeout
    """
    print(f"\n{C.BOLD}{'=' * 60}")
    print("  CONTRACT TEST: release_gate timeout contract (P3-03)")
    print(f"{'=' * 60}{C.RESET}\n")

    errors = 0
    gate_path = ROOT / "db" / "release_gate.py"
    if not gate_path.exists():
        fail(f"No existe {gate_path}")
        return False

    gate_text = gate_path.read_text(encoding="utf-8", errors="replace")
    required_tokens = [
        '_env_int("VG_SUITE_TIMEOUT_SEC", 900)',
        'Timeout por suite: {suite_timeout_sec}s (env VG_SUITE_TIMEOUT_SEC)',
        'timeout=max(1, int(timeout_sec))',
        'except subprocess.TimeoutExpired:',
        '[TIMEOUT]',
        '"status": "TIMEOUT"',
        'Motivo: al menos una suite excedio el timeout',
    ]

    for token in required_tokens:
        if token in gate_text:
            ok(f"release_gate.py contiene: {token}")
        else:
            fail(f"release_gate.py NO contiene: {token}")
            errors += 1

    print()
    if errors == 0:
        print(f"{C.OK}{C.BOLD}CONTRACT TEST PASSED{C.RESET}")
        return True
    else:
        print(f"{C.FAIL}{C.BOLD}CONTRACT TEST FAILED ({errors} errores){C.RESET}")
        return False


# ==============================================================================
# TEST: Contrato modo release gate (P3-05)
# ==============================================================================

def test_release_gate_mode_contract():
    """
    Valida contrato estatico de modo en release_gate:
    - modo configurable por CLI/env (read_only/full)
    - default en full para preservar contrato P3-04
    - read_only marca suites DB como SKIPPED
    """
    print(f"\n{C.BOLD}{'=' * 60}")
    print("  CONTRACT TEST: release_gate mode contract (P3-05)")
    print(f"{'=' * 60}{C.RESET}\n")

    errors = 0
    gate_path = ROOT / "db" / "release_gate.py"
    if not gate_path.exists():
        fail(f"No existe {gate_path}")
        return False

    gate_text = gate_path.read_text(encoding="utf-8", errors="replace")
    required_tokens = [
        'RELEASE_GATE_MODE_ENV = "VG_RELEASE_GATE_MODE"',
        'RELEASE_MODE_READ_ONLY = "read_only"',
        'RELEASE_MODE_FULL = "full"',
        '"--mode"',
        "default: {RELEASE_MODE_FULL}",
        "Modo read_only: suite DB deshabilitada por seguridad.",
        '"status": "SKIPPED"',
        "Modo de ejecucion: {release_mode} (env {RELEASE_GATE_MODE_ENV})",
    ]

    for token in required_tokens:
        if token in gate_text:
            ok(f"release_gate.py contiene: {token}")
        else:
            fail(f"release_gate.py NO contiene: {token}")
            errors += 1

    print()
    if errors == 0:
        print(f"{C.OK}{C.BOLD}CONTRACT TEST PASSED{C.RESET}")
        return True
    else:
        print(f"{C.FAIL}{C.BOLD}CONTRACT TEST FAILED ({errors} errores){C.RESET}")
        return False


# ==============================================================================
# TEST: Contrato de entorno reproducible + sync documental (P3-06)
# ==============================================================================

def test_env_contract_reproducible_docs_sync_contract():
    """
    Valida contrato estatico P3-06:
    - existe db/env_contract.py con perfiles operativos
    - existe .env.example con variables esperadas
    - docs operativas alineadas con el contrato de entorno
    """
    print(f"\n{C.BOLD}{'=' * 60}")
    print("  CONTRACT TEST: env reproducible + docs sync (P3-06)")
    print(f"{'=' * 60}{C.RESET}\n")

    errors = 0
    env_contract_path = ROOT / "db" / "env_contract.py"
    env_example_path = ROOT / ".env.example"

    if not env_contract_path.exists():
        fail(f"No existe {env_contract_path}")
        return False
    if not env_example_path.exists():
        fail(f"No existe {env_example_path}")
        return False

    env_contract_text = env_contract_path.read_text(encoding="utf-8", errors="replace")
    env_example_text = env_example_path.read_text(encoding="utf-8", errors="replace")

    env_contract_tokens = [
        'PROFILE_APP = "app"',
        'PROFILE_DB_SUITE = "db_suite"',
        'PROFILE_RELEASE_GATE_FULL = "release_gate_full"',
        'PROFILE_RELEASE_GATE_READ_ONLY = "release_gate_read_only"',
        'PROFILE_DAILY_OPS = "daily_ops"',
        'RELEASE_GATE_MODE_ENV = "VG_RELEASE_GATE_MODE"',
        "ENV CONTRACT: PASS",
        '"--profile"',
    ]
    for token in env_contract_tokens:
        if token in env_contract_text:
            ok(f"env_contract.py contiene: {token}")
        else:
            fail(f"env_contract.py NO contiene: {token}")
            errors += 1

    env_example_tokens = [
        "DATABASE_URL=",
        "VG_TEST_DATABASE_URL=",
        "VG_RELEASE_GATE_MODE=",
        "VG_SUITE_TIMEOUT_SEC=",
        "VG_STEP_TIMEOUT_SEC=",
    ]
    for token in env_example_tokens:
        if token in env_example_text:
            ok(f".env.example contiene: {token}")
        else:
            fail(f".env.example NO contiene: {token}")
            errors += 1

    doc_targets = [
        (ROOT / "db" / "README.md", ["python db/env_contract.py --profile daily_ops", ".env.example"]),
        (ROOT / "docs" / "README.md", ["python db/env_contract.py --profile daily_ops", "VG_RELEASE_GATE_MODE"]),
        (ROOT / "docs" / "MANUAL_ADMINISTRACION.md", ["db/env_contract.py --profile daily_ops", "VG_STEP_TIMEOUT_SEC"]),
    ]
    for path, tokens in doc_targets:
        if not path.exists():
            fail(f"No existe {path}")
            errors += 1
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for token in tokens:
            if token in text:
                ok(f"{path.name} contiene: {token}")
            else:
                fail(f"{path.name} NO contiene: {token}")
                errors += 1

    print()
    if errors == 0:
        print(f"{C.OK}{C.BOLD}CONTRACT TEST PASSED{C.RESET}")
        return True
    else:
        print(f"{C.FAIL}{C.BOLD}CONTRACT TEST FAILED ({errors} errores){C.RESET}")
        return False


# ==============================================================================
# TEST: Contrato suite operativa conductual (P4-01)
# ==============================================================================

def test_ops_behavior_suite_contract():
    """
    Valida contrato estatico de suite operativa conductual:
    - existe db/ops_behavior_test.py
    - cubre env_contract y RUN_ERP.ps1 -DailyOps en modo read_only/invalid
    """
    print(f"\n{C.BOLD}{'=' * 60}")
    print("  CONTRACT TEST: ops behavior suite contract (P4-01)")
    print(f"{'=' * 60}{C.RESET}\n")

    errors = 0
    suite_path = ROOT / "db" / "ops_behavior_test.py"
    if not suite_path.exists():
        fail(f"No existe {suite_path}")
        return False

    text = suite_path.read_text(encoding="utf-8", errors="replace")
    required_tokens = [
        "RUN_ERP.ps1",
        "VG_RELEASE_GATE_MODE",
        "daily_ops",
        "read_only",
        "invalid_mode",
        "RELEASE QA GATE: PASS",
        "OPS BEHAVIOR TEST",
    ]
    for token in required_tokens:
        if token in text:
            ok(f"ops_behavior_test.py contiene: {token}")
        else:
            fail(f"ops_behavior_test.py NO contiene: {token}")
            errors += 1

    print()
    if errors == 0:
        print(f"{C.OK}{C.BOLD}CONTRACT TEST PASSED{C.RESET}")
        return True
    print(f"{C.FAIL}{C.BOLD}CONTRACT TEST FAILED ({errors} errores){C.RESET}")
    return False


# ==============================================================================
# TEST: Contrato aislamiento suites DB (P3-04)
# ==============================================================================

def test_db_suite_isolation_contract():
    """
    Valida contrato estatico de aislamiento de suites DB:
    - release_gate usa VG_TEST_DATABASE_URL para suites DB
    - suites DB cargan guardrail require_isolated_test_database_env
    """
    print(f"\n{C.BOLD}{'=' * 60}")
    print("  CONTRACT TEST: DB suite isolation contract (P3-04)")
    print(f"{'=' * 60}{C.RESET}\n")

    errors = 0
    gate_path = ROOT / "db" / "release_gate.py"
    smoke_path = ROOT / "db" / "smoke_test.py"
    ux_phase2_path = ROOT / "db" / "ux_phase2_test.py"
    ux_gestion_path = ROOT / "db" / "ux_gestion_regression_test.py"

    targets = [gate_path, smoke_path, ux_phase2_path, ux_gestion_path]
    for path in targets:
        if not path.exists():
            fail(f"No existe {path}")
            errors += 1

    if errors > 0:
        print()
        print(f"{C.FAIL}{C.BOLD}CONTRACT TEST FAILED ({errors} errores){C.RESET}")
        return False

    gate_text = gate_path.read_text(encoding="utf-8", errors="replace")
    gate_required_tokens = [
        "TEST_DATABASE_URL_ENV",
        "build_isolated_suite_env",
        "requires_test_database=True",
    ]
    for token in gate_required_tokens:
        if token in gate_text:
            ok(f"release_gate.py contiene: {token}")
        else:
            fail(f"release_gate.py NO contiene: {token}")
            errors += 1

    for path in [smoke_path, ux_phase2_path, ux_gestion_path]:
        text = path.read_text(encoding="utf-8", errors="replace")
        if "require_isolated_test_database_env" in text:
            ok(f"{path.name} usa require_isolated_test_database_env")
        else:
            fail(f"{path.name} NO usa require_isolated_test_database_env")
            errors += 1

    print()
    if errors == 0:
        print(f"{C.OK}{C.BOLD}CONTRACT TEST PASSED{C.RESET}")
        return True
    else:
        print(f"{C.FAIL}{C.BOLD}CONTRACT TEST FAILED ({errors} errores){C.RESET}")
        return False


# ==============================================================================
# TEST: Guardrail negativo de entorno de test (P3-04)
# ==============================================================================

def test_test_env_guard_negative_contract():
    """
    Valida comportamiento negativo/positivo del guardrail de DB de test.
    """
    print(f"\n{C.BOLD}{'=' * 60}")
    print("  CONTRACT TEST: test_env negative guard (P3-04)")
    print(f"{'=' * 60}{C.RESET}\n")

    errors = 0
    try:
        from db.test_env import validate_isolated_test_database_url
        ok("Import validate_isolated_test_database_url exitoso")
    except Exception as e:
        fail(f"No se pudo importar validate_isolated_test_database_url: {e}")
        return False

    ok_valid, _, _ = validate_isolated_test_database_url(
        "postgresql://user:pass@localhost:5432/sistemalegal_test",
        runtime_reference_dsn="postgresql://user:pass@localhost:5432/sistemalegal",
        runtime_source_label="DATABASE_URL",
    )
    if ok_valid:
        ok("DB de test dedicada aceptada (caso positivo)")
    else:
        fail("DB de test dedicada rechazada (caso positivo)")
        errors += 1

    ok_missing, _, reason_missing = validate_isolated_test_database_url(
        "",
        runtime_reference_dsn="postgresql://user:pass@localhost:5432/sistemalegal",
        runtime_source_label="DATABASE_URL",
    )
    if not ok_missing and "VG_TEST_DATABASE_URL" in reason_missing:
        ok("Falta VG_TEST_DATABASE_URL => rechazo esperado")
    else:
        fail(f"Caso missing inesperado: ok={ok_missing}, reason={reason_missing!r}")
        errors += 1

    ok_equal, _, reason_equal = validate_isolated_test_database_url(
        "postgresql://user:pass@localhost:5432/sistemalegal_test",
        runtime_reference_dsn="postgresql://user:pass@localhost:5432/sistemalegal_test",
        runtime_source_label="DATABASE_URL",
    )
    if not ok_equal and "coincide con DATABASE_URL" in reason_equal:
        ok("VG_TEST_DATABASE_URL == DATABASE_URL => rechazo esperado")
    else:
        fail(f"Caso equal inesperado: ok={ok_equal}, reason={reason_equal!r}")
        errors += 1

    ok_name, _, reason_name = validate_isolated_test_database_url(
        "postgresql://user:pass@localhost:5432/sistemalegal",
        runtime_reference_dsn="postgresql://user:pass@localhost:5432/erp_prod",
        runtime_source_label="DATABASE_URL",
    )
    if not ok_name and "no aislada" in reason_name:
        ok("Nombre de DB sin marcador de test => rechazo esperado")
    else:
        fail(f"Caso nombre inesperado: ok={ok_name}, reason={reason_name!r}")
        errors += 1

    print()
    if errors == 0:
        print(f"{C.OK}{C.BOLD}CONTRACT TEST PASSED{C.RESET}")
        return True
    else:
        print(f"{C.FAIL}{C.BOLD}CONTRACT TEST FAILED ({errors} errores){C.RESET}")
        return False


# ==============================================================================
# TEST: Contrato CI con PostgreSQL efimero (P4-02)
# ==============================================================================

def test_ci_postgres_ephemeral_contract():
    """
    Valida contrato estatico de CI DB-first:
    - workflow dedicado con PostgreSQL efimero
    - schema aplicado sobre runtime y test DB
    - gate ejecutado en modo full con VG_TEST_DATABASE_URL
    """
    print(f"\n{C.BOLD}{'=' * 60}")
    print("  CONTRACT TEST: CI PostgreSQL efimero (P4-02)")
    print(f"{'=' * 60}{C.RESET}\n")

    errors = 0
    workflow_path = ROOT / ".github" / "workflows" / "ci-db.yml"
    if not workflow_path.exists():
        fail(f"No existe {workflow_path}")
        return False

    workflow_text = workflow_path.read_text(encoding="utf-8", errors="replace")
    required_tokens = [
        "services:",
        "image: postgres:16",
        "VG_TEST_DATABASE_URL: postgresql://postgres:postgres@localhost:5432/sistemalegal_ci_test",
        "VG_RELEASE_GATE_MODE: full",
        "python db/env_contract.py --profile release_gate_full",
        "python db/release_gate.py --mode full",
        "CREATE DATABASE sistemalegal_ci_test;",
        "-f db/schema.sql",
    ]
    for token in required_tokens:
        if token in workflow_text:
            ok(f"ci-db.yml contiene: {token}")
        else:
            fail(f"ci-db.yml NO contiene: {token}")
            errors += 1

    print()
    if errors == 0:
        print(f"{C.OK}{C.BOLD}CONTRACT TEST PASSED{C.RESET}")
        return True
    else:
        print(f"{C.FAIL}{C.BOLD}CONTRACT TEST FAILED ({errors} errores){C.RESET}")
        return False


# ==============================================================================
# TEST: Contrato observabilidad estructurada (P4-03)
# ==============================================================================

def test_structured_observability_contract():
    """
    Valida contrato estatico de observabilidad estructurada:
    - correlacion por run_id
    - etiquetas stage/suite en gate, nightly y DailyOps
    """
    print(f"\n{C.BOLD}{'=' * 60}")
    print("  CONTRACT TEST: structured observability (P4-03)")
    print(f"{'=' * 60}{C.RESET}\n")

    errors = 0
    release_gate_path = ROOT / "db" / "release_gate.py"
    nightly_path = ROOT / "db" / "nightly_audit.py"
    dailyops_path = ROOT / "RUN_ERP.ps1"

    targets = [release_gate_path, nightly_path, dailyops_path]
    for path in targets:
        if not path.exists():
            fail(f"No existe {path}")
            errors += 1

    if errors > 0:
        print()
        print(f"{C.FAIL}{C.BOLD}CONTRACT TEST FAILED ({errors} errores){C.RESET}")
        return False

    release_text = release_gate_path.read_text(encoding="utf-8", errors="replace")
    release_tokens = [
        'RUN_ID_ENV = "VG_RUN_ID"',
        "def _emit_obs(",
        'stage="gate_start"',
        'stage="suite_start"',
        'stage="suite_end"',
        'stage="gate_end"',
    ]
    for token in release_tokens:
        if token in release_text:
            ok(f"release_gate.py contiene: {token}")
        else:
            fail(f"release_gate.py NO contiene: {token}")
            errors += 1

    nightly_text = nightly_path.read_text(encoding="utf-8", errors="replace")
    nightly_tokens = [
        'RUN_ID_ENV = "VG_RUN_ID"',
        "def _emit_obs(",
        'stage="nightly_start"',
        'stage="db_preflight"',
        'stage="nightly_end"',
    ]
    for token in nightly_tokens:
        if token in nightly_text:
            ok(f"nightly_audit.py contiene: {token}")
        else:
            fail(f"nightly_audit.py NO contiene: {token}")
            errors += 1

    dailyops_text = dailyops_path.read_text(encoding="utf-8", errors="replace")
    dailyops_tokens = [
        "function New-RunId",
        "function Write-OpsObs",
        "env VG_RUN_ID",
        "stage=",
        "suite=",
        'Write-OpsObs -RunId $runId -Stage "daily_ops_start"',
    ]
    for token in dailyops_tokens:
        if token in dailyops_text:
            ok(f"RUN_ERP.ps1 contiene: {token}")
        else:
            fail(f"RUN_ERP.ps1 NO contiene: {token}")
            errors += 1

    print()
    if errors == 0:
        print(f"{C.OK}{C.BOLD}CONTRACT TEST PASSED{C.RESET}")
        return True
    else:
        print(f"{C.FAIL}{C.BOLD}CONTRACT TEST FAILED ({errors} errores){C.RESET}")
        return False


# ==============================================================================
# TEST: Contrato quality gate KPI (P4-04)
# ==============================================================================

def test_quality_gate_kpi_contract():
    """
    Valida contrato estatico P4-04:
    - release_gate integra KPI gate configurable (off|warn|enforce)
    - env_contract y .env.example incluyen variables de control KPI
    - docs operativas documentan el uso del KPI gate
    """
    print(f"\n{C.BOLD}{'=' * 60}")
    print("  CONTRACT TEST: quality gate KPI (P4-04)")
    print(f"{'=' * 60}{C.RESET}\n")

    errors = 0
    release_gate_path = ROOT / "db" / "release_gate.py"
    env_contract_path = ROOT / "db" / "env_contract.py"
    env_example_path = ROOT / ".env.example"
    docs_targets = [
        ROOT / "db" / "README.md",
        ROOT / "docs" / "README.md",
        ROOT / "docs" / "MANUAL_ADMINISTRACION.md",
    ]

    targets = [release_gate_path, env_contract_path, env_example_path] + docs_targets
    for path in targets:
        if not path.exists():
            fail(f"No existe {path}")
            errors += 1

    if errors > 0:
        print()
        print(f"{C.FAIL}{C.BOLD}CONTRACT TEST FAILED ({errors} errores){C.RESET}")
        return False

    release_text = release_gate_path.read_text(encoding="utf-8", errors="replace")
    release_tokens = [
        'QUALITY_GATE_KPI_MODE_ENV = "VG_QUALITY_GATE_KPI_MODE"',
        'QUALITY_GATE_KPI_MIN_CASES_ENV = "VG_QUALITY_GATE_KPI_MIN_CASES"',
        'KPI_MODE_ENFORCE = "enforce"',
        '"--kpi-mode"',
        '"--kpi-min-cases"',
        "QUALITY GATE KPI",
        'stage="kpi_gate"',
        "quality_gate_kpi",
    ]
    for token in release_tokens:
        if token in release_text:
            ok(f"release_gate.py contiene: {token}")
        else:
            fail(f"release_gate.py NO contiene: {token}")
            errors += 1

    env_contract_text = env_contract_path.read_text(encoding="utf-8", errors="replace")
    env_contract_tokens = [
        'QUALITY_GATE_KPI_MODE_ENV = "VG_QUALITY_GATE_KPI_MODE"',
        'QUALITY_GATE_KPI_MIN_CASES_ENV = "VG_QUALITY_GATE_KPI_MIN_CASES"',
        'VALID_KPI_GATE_MODES = {"off", "warn", "enforce"}',
    ]
    for token in env_contract_tokens:
        if token in env_contract_text:
            ok(f"env_contract.py contiene: {token}")
        else:
            fail(f"env_contract.py NO contiene: {token}")
            errors += 1

    env_example_text = env_example_path.read_text(encoding="utf-8", errors="replace")
    env_example_tokens = [
        "VG_QUALITY_GATE_KPI_MODE=",
        "VG_QUALITY_GATE_KPI_MIN_CASES=",
    ]
    for token in env_example_tokens:
        if token in env_example_text:
            ok(f".env.example contiene: {token}")
        else:
            fail(f".env.example NO contiene: {token}")
            errors += 1

    doc_tokens = [
        "VG_QUALITY_GATE_KPI_MODE",
        "VG_QUALITY_GATE_KPI_MIN_CASES",
    ]
    for path in docs_targets:
        text = path.read_text(encoding="utf-8", errors="replace")
        for token in doc_tokens:
            if token in text:
                ok(f"{path.name} contiene: {token}")
            else:
                fail(f"{path.name} NO contiene: {token}")
                errors += 1

    print()
    if errors == 0:
        print(f"{C.OK}{C.BOLD}CONTRACT TEST PASSED{C.RESET}")
        return True
    else:
        print(f"{C.FAIL}{C.BOLD}CONTRACT TEST FAILED ({errors} errores){C.RESET}")
        return False


# ==============================================================================
# TEST: Contrato seguridad base auth/roles/least privilege (P5-02)
# ==============================================================================

def test_security_baseline_contract():
    """
    Valida contrato estatico P5-02:
    - release_gate integra security gate configurable (off|warn|enforce)
    - env_contract y .env.example sincronizan variables de seguridad
    - existe modulo reusable db/security_baseline.py
    - docs operativas documentan variables/comandos de seguridad
    """
    print(f"\n{C.BOLD}{'=' * 60}")
    print("  CONTRACT TEST: security baseline (P5-02)")
    print(f"{'=' * 60}{C.RESET}\n")

    errors = 0
    release_gate_path = ROOT / "db" / "release_gate.py"
    env_contract_path = ROOT / "db" / "env_contract.py"
    env_example_path = ROOT / ".env.example"
    security_module_path = ROOT / "db" / "security_baseline.py"
    docs_targets = [
        ROOT / "db" / "README.md",
        ROOT / "docs" / "README.md",
        ROOT / "docs" / "MANUAL_ADMINISTRACION.md",
    ]

    targets = [release_gate_path, env_contract_path, env_example_path, security_module_path] + docs_targets
    for path in targets:
        if not path.exists():
            fail(f"No existe {path}")
            errors += 1

    if errors > 0:
        print()
        print(f"{C.FAIL}{C.BOLD}CONTRACT TEST FAILED ({errors} errores){C.RESET}")
        return False

    release_text = release_gate_path.read_text(encoding="utf-8", errors="replace")
    release_tokens = [
        '"--security-mode"',
        "evaluate_security_baseline(",
        'stage="security_gate"',
        "security_gate",
        "SECURITY_GATE_MODE_ENV",
    ]
    for token in release_tokens:
        if token in release_text:
            ok(f"release_gate.py contiene: {token}")
        else:
            fail(f"release_gate.py NO contiene: {token}")
            errors += 1

    env_contract_text = env_contract_path.read_text(encoding="utf-8", errors="replace")
    env_contract_tokens = [
        "VALID_SECURITY_GATE_MODES",
        "SECURITY_GATE_MODE_ENV",
        "DB_APP_ROLE_ENV",
        "DB_TEST_ROLE_ENV",
        "SECURITY_REQUIRE_TEST_ROLE_SPLIT_ENV",
    ]
    for token in env_contract_tokens:
        if token in env_contract_text:
            ok(f"env_contract.py contiene: {token}")
        else:
            fail(f"env_contract.py NO contiene: {token}")
            errors += 1

    env_example_text = env_example_path.read_text(encoding="utf-8", errors="replace")
    env_example_tokens = [
        "VG_SECURITY_GATE_MODE=",
        "VG_DB_APP_ROLE=",
        "VG_DB_TEST_ROLE=",
        "VG_SECURITY_GATE_REQUIRE_TEST_ROLE_SPLIT=",
    ]
    for token in env_example_tokens:
        if token in env_example_text:
            ok(f".env.example contiene: {token}")
        else:
            fail(f".env.example NO contiene: {token}")
            errors += 1

    security_text = security_module_path.read_text(encoding="utf-8", errors="replace")
    security_tokens = [
        'SECURITY_GATE_MODE_ENV = "VG_SECURITY_GATE_MODE"',
        'DB_APP_ROLE_ENV = "VG_DB_APP_ROLE"',
        'DB_TEST_ROLE_ENV = "VG_DB_TEST_ROLE"',
        'SECURITY_REQUIRE_TEST_ROLE_SPLIT_ENV = "VG_SECURITY_GATE_REQUIRE_TEST_ROLE_SPLIT"',
        "def evaluate_security_baseline(",
    ]
    for token in security_tokens:
        if token in security_text:
            ok(f"security_baseline.py contiene: {token}")
        else:
            fail(f"security_baseline.py NO contiene: {token}")
            errors += 1

    doc_tokens = [
        "VG_SECURITY_GATE_MODE",
        "VG_DB_APP_ROLE",
        "VG_DB_TEST_ROLE",
        "VG_SECURITY_GATE_REQUIRE_TEST_ROLE_SPLIT",
        "security_baseline.py",
    ]
    for path in docs_targets:
        text = path.read_text(encoding="utf-8", errors="replace")
        for token in doc_tokens:
            if token in text:
                ok(f"{path.name} contiene: {token}")
            else:
                fail(f"{path.name} NO contiene: {token}")
                errors += 1

    print()
    if errors == 0:
        print(f"{C.OK}{C.BOLD}CONTRACT TEST PASSED{C.RESET}")
        return True
    else:
        print(f"{C.FAIL}{C.BOLD}CONTRACT TEST FAILED ({errors} errores){C.RESET}")
        return False


# ==============================================================================
# TEST: Contrato performance/capacidad DB (P5-04)
# ==============================================================================

def test_performance_capacity_contract():
    """
    Valida contrato estatico P5-04:
    - release_gate integra performance gate configurable (off|warn|enforce)
    - existe modulo reusable db/performance_capacity.py
    - env_contract y .env.example sincronizan variables de performance
    - docs operativas documentan comandos/variables de performance gate
    """
    print(f"\n{C.BOLD}{'=' * 60}")
    print("  CONTRACT TEST: performance/capacity gate (P5-04)")
    print(f"{'=' * 60}{C.RESET}\n")

    errors = 0
    release_gate_path = ROOT / "db" / "release_gate.py"
    env_contract_path = ROOT / "db" / "env_contract.py"
    env_example_path = ROOT / ".env.example"
    perf_module_path = ROOT / "db" / "performance_capacity.py"
    docs_targets = [
        ROOT / "db" / "README.md",
        ROOT / "docs" / "README.md",
        ROOT / "docs" / "MANUAL_ADMINISTRACION.md",
    ]

    targets = [release_gate_path, env_contract_path, env_example_path, perf_module_path] + docs_targets
    for path in targets:
        if not path.exists():
            fail(f"No existe {path}")
            errors += 1

    if errors > 0:
        print()
        print(f"{C.FAIL}{C.BOLD}CONTRACT TEST FAILED ({errors} errores){C.RESET}")
        return False

    release_text = release_gate_path.read_text(encoding="utf-8", errors="replace")
    release_tokens = [
        '"--performance-mode"',
        "evaluate_performance_capacity(",
        'stage="performance_gate"',
        "performance_gate",
        "PERFORMANCE_GATE_MODE_ENV",
    ]
    for token in release_tokens:
        if token in release_text:
            ok(f"release_gate.py contiene: {token}")
        else:
            fail(f"release_gate.py NO contiene: {token}")
            errors += 1

    env_contract_text = env_contract_path.read_text(encoding="utf-8", errors="replace")
    env_contract_tokens = [
        "VALID_PERFORMANCE_GATE_MODES",
        "PERFORMANCE_GATE_MODE_ENV",
        "PERFORMANCE_MAX_SELECT1_MS_ENV",
        "PERFORMANCE_MAX_CORE_COUNTS_MS_ENV",
        "PERFORMANCE_MAX_RECENT_DOCS_MS_ENV",
        "PERFORMANCE_MAX_RECENT_CASES_MS_ENV",
        "PERFORMANCE_MAX_DOCS_PER_CASE_ENV",
        "PERFORMANCE_MAX_AUDIT_ROWS_ENV",
    ]
    for token in env_contract_tokens:
        if token in env_contract_text:
            ok(f"env_contract.py contiene: {token}")
        else:
            fail(f"env_contract.py NO contiene: {token}")
            errors += 1

    env_example_text = env_example_path.read_text(encoding="utf-8", errors="replace")
    env_example_tokens = [
        "VG_PERFORMANCE_GATE_MODE=",
        "VG_PERFORMANCE_GATE_MAX_SELECT1_MS=",
        "VG_PERFORMANCE_GATE_MAX_CORE_COUNTS_MS=",
        "VG_PERFORMANCE_GATE_MAX_RECENT_DOCS_MS=",
        "VG_PERFORMANCE_GATE_MAX_RECENT_CASES_MS=",
        "VG_PERFORMANCE_GATE_MAX_DOCS_PER_CASE=",
        "VG_PERFORMANCE_GATE_MAX_AUDIT_ROWS=",
    ]
    for token in env_example_tokens:
        if token in env_example_text:
            ok(f".env.example contiene: {token}")
        else:
            fail(f".env.example NO contiene: {token}")
            errors += 1

    perf_text = perf_module_path.read_text(encoding="utf-8", errors="replace")
    perf_tokens = [
        'PERFORMANCE_GATE_MODE_ENV = "VG_PERFORMANCE_GATE_MODE"',
        'PERFORMANCE_MODE_ENFORCE = "enforce"',
        "def load_performance_thresholds(",
        "def evaluate_performance_capacity(",
    ]
    for token in perf_tokens:
        if token in perf_text:
            ok(f"performance_capacity.py contiene: {token}")
        else:
            fail(f"performance_capacity.py NO contiene: {token}")
            errors += 1

    doc_tokens = [
        "VG_PERFORMANCE_GATE_MODE",
        "VG_PERFORMANCE_GATE_MAX_SELECT1_MS",
        "VG_PERFORMANCE_GATE_MAX_CORE_COUNTS_MS",
        "VG_PERFORMANCE_GATE_MAX_RECENT_DOCS_MS",
        "VG_PERFORMANCE_GATE_MAX_RECENT_CASES_MS",
        "VG_PERFORMANCE_GATE_MAX_DOCS_PER_CASE",
        "VG_PERFORMANCE_GATE_MAX_AUDIT_ROWS",
        "performance_capacity.py",
    ]
    for path in docs_targets:
        text = path.read_text(encoding="utf-8", errors="replace")
        for token in doc_tokens:
            if token in text:
                ok(f"{path.name} contiene: {token}")
            else:
                fail(f"{path.name} NO contiene: {token}")
                errors += 1

    print()
    if errors == 0:
        print(f"{C.OK}{C.BOLD}CONTRACT TEST PASSED{C.RESET}")
        return True
    else:
        print(f"{C.FAIL}{C.BOLD}CONTRACT TEST FAILED ({errors} errores){C.RESET}")
        return False


# ==============================================================================
# TEST: Contrato backup + restore drills (P5-03)
# ==============================================================================

def test_backup_restore_drill_contract():
    """
    Valida contrato estatico P5-03:
    - existe script de drill no destructivo DB-first
    - env_contract soporta profile backup_restore_drill
    - .env.example y docs sincronizan variables/comandos de backup drill
    """
    print(f"\n{C.BOLD}{'=' * 60}")
    print("  CONTRACT TEST: backup restore drill (P5-03)")
    print(f"{'=' * 60}{C.RESET}\n")

    errors = 0
    drill_path = ROOT / "db" / "backup_restore_drill.py"
    env_contract_path = ROOT / "db" / "env_contract.py"
    env_example_path = ROOT / ".env.example"
    docs_targets = [
        ROOT / "db" / "README.md",
        ROOT / "docs" / "README.md",
        ROOT / "docs" / "MANUAL_ADMINISTRACION.md",
    ]

    targets = [drill_path, env_contract_path, env_example_path] + docs_targets
    for path in targets:
        if not path.exists():
            fail(f"No existe {path}")
            errors += 1

    if errors > 0:
        print()
        print(f"{C.FAIL}{C.BOLD}CONTRACT TEST FAILED ({errors} errores){C.RESET}")
        return False

    drill_text = drill_path.read_text(encoding="utf-8", errors="replace")
    drill_tokens = [
        "CORE_TABLES = (\"clients\", \"cases\", \"documents\", \"tasks\", \"audit_log\")",
        "validate_isolated_test_database_url(",
        "CREATE SCHEMA",
        "DROP SCHEMA IF EXISTS",
        "json_populate_recordset",
        "BACKUP RESTORE DRILL: PASS",
        "stage=\"restore_table\"",
    ]
    for token in drill_tokens:
        if token in drill_text:
            ok(f"backup_restore_drill.py contiene: {token}")
        else:
            fail(f"backup_restore_drill.py NO contiene: {token}")
            errors += 1

    env_contract_text = env_contract_path.read_text(encoding="utf-8", errors="replace")
    env_contract_tokens = [
        "PROFILE_BACKUP_RESTORE_DRILL = \"backup_restore_drill\"",
        "BACKUP_DIR_ENV = \"VG_BACKUP_DIR\"",
        "BACKUP_DRILL_SCHEMA_PREFIX_ENV = \"VG_BACKUP_DRILL_SCHEMA_PREFIX\"",
        "if profile == PROFILE_BACKUP_RESTORE_DRILL:",
    ]
    for token in env_contract_tokens:
        if token in env_contract_text:
            ok(f"env_contract.py contiene: {token}")
        else:
            fail(f"env_contract.py NO contiene: {token}")
            errors += 1

    env_example_text = env_example_path.read_text(encoding="utf-8", errors="replace")
    env_example_tokens = [
        "VG_BACKUP_DIR=",
        "VG_BACKUP_DRILL_SCHEMA_PREFIX=",
    ]
    for token in env_example_tokens:
        if token in env_example_text:
            ok(f".env.example contiene: {token}")
        else:
            fail(f".env.example NO contiene: {token}")
            errors += 1

    doc_tokens = [
        "backup_restore_drill.py",
        "VG_BACKUP_DIR",
        "VG_BACKUP_DRILL_SCHEMA_PREFIX",
    ]
    for path in docs_targets:
        text = path.read_text(encoding="utf-8", errors="replace")
        for token in doc_tokens:
            if token in text:
                ok(f"{path.name} contiene: {token}")
            else:
                fail(f"{path.name} NO contiene: {token}")
                errors += 1

    print()
    if errors == 0:
        print(f"{C.OK}{C.BOLD}CONTRACT TEST PASSED{C.RESET}")
        return True
    else:
        print(f"{C.FAIL}{C.BOLD}CONTRACT TEST FAILED ({errors} errores){C.RESET}")
        return False


# ==============================================================================
# TEST: Extraccion legado FS + modularizacion (P5-01)
# ==============================================================================

def test_legacy_fs_extraction_contract():
    """
    Valida contrato estatico P5-01:
    - runtime DB-first no importa fs_repo en app/views/audit
    - app bootstrap no contiene branch filesystem legacy
    - audit tipa GestorCasos desde repo.py (factory DB-first)
    """
    print(f"\n{C.BOLD}{'=' * 60}")
    print("  CONTRACT TEST: legacy FS extraction (P5-01)")
    print(f"{'=' * 60}{C.RESET}\n")

    errors = 0
    app_path = ROOT / "app.py"
    views_path = ROOT / "views.py"
    audit_path = ROOT / "audit.py"
    runtime_targets = [app_path, views_path, audit_path]

    for path in runtime_targets:
        if not path.exists():
            fail(f"No existe {path}")
            errors += 1

    if errors > 0:
        print()
        print(f"{C.FAIL}{C.BOLD}CONTRACT TEST FAILED ({errors} errores){C.RESET}")
        return False

    for path in runtime_targets:
        text = path.read_text(encoding="utf-8", errors="replace")
        if "from fs_repo import" in text:
            fail(f"{path.name} NO debe importar fs_repo en runtime DB-first")
            errors += 1
        else:
            ok(f"{path.name} sin import runtime de fs_repo")

    app_text = app_path.read_text(encoding="utf-8", errors="replace")
    required_app_tokens = [
        "gestor = GestorCasos()",
        "Conectando a base de datos...",
    ]
    forbidden_app_tokens = [
        "GestorCasos(RUTA_BASE)",
        "RUTA_BASE_AUTO_CREATE",
        "_show_ruta_error(",
    ]
    for token in required_app_tokens:
        if token in app_text:
            ok(f"app.py contiene: {token}")
        else:
            fail(f"app.py NO contiene: {token}")
            errors += 1
    for token in forbidden_app_tokens:
        if token in app_text:
            fail(f"app.py contiene legado FS no permitido: {token}")
            errors += 1
        else:
            ok(f"app.py limpio de token legacy: {token}")

    audit_text = audit_path.read_text(encoding="utf-8", errors="replace")
    if "from repo import GestorCasos, is_db_mode, is_db_path" in audit_text:
        ok("audit.py usa GestorCasos desde repo.py (DB-first)")
    else:
        fail("audit.py no declara import DB-first esperado desde repo.py")
        errors += 1

    print()
    if errors == 0:
        print(f"{C.OK}{C.BOLD}CONTRACT TEST PASSED{C.RESET}")
        return True
    else:
        print(f"{C.FAIL}{C.BOLD}CONTRACT TEST FAILED ({errors} errores){C.RESET}")
        return False


# ==============================================================================
# TEST: Contrato alerta degradacion (P2-03)
# ==============================================================================

def test_trend_degradation_alert_contract():
    """
    Valida build_trend_degradation_alert para:
    - not-ready con datos insuficientes
    - estado OK sin degradacion
    - degradacion critica
    """
    print(f"\n{C.BOLD}{'=' * 60}")
    print("  CONTRACT TEST: trend degradation alert (P2-03)")
    print(f"{'=' * 60}{C.RESET}\n")

    errors = 0

    try:
        from audit import build_trend_degradation_alert
        ok("Import build_trend_degradation_alert exitoso")
    except Exception as e:
        fail(f"No se pudo importar build_trend_degradation_alert: {e}")
        return False

    # Caso 1: datos insuficientes
    alert_not_ready = build_trend_degradation_alert(
        [{"date": "2026-02-10", "errores": 1, "warnings": 2}],
        baseline_days=7,
    )
    if not bool(alert_not_ready.get("ready", False)) and not bool(alert_not_ready.get("show_alert", False)):
        ok("Datos insuficientes -> ready=False y show_alert=False")
    else:
        fail(f"Datos insuficientes retorno inesperado: {alert_not_ready}")
        errors += 1

    # Caso 2: sin degradacion (mejora frente al baseline)
    stable_rows = [
        {"date": "2026-02-10", "errores": 3, "warnings": 8},
        {"date": "2026-02-11", "errores": 3, "warnings": 8},
        {"date": "2026-02-12", "errores": 2, "warnings": 7},
        {"date": "2026-02-13", "errores": 1, "warnings": 2},
    ]
    alert_ok = build_trend_degradation_alert(stable_rows, baseline_days=3)
    if bool(alert_ok.get("ready", False)) and not bool(alert_ok.get("show_alert", False)) and alert_ok.get("severity") == "ok":
        ok("Sin degradacion -> show_alert=False, severity=ok")
    else:
        fail(f"Sin degradacion retorno inesperado: {alert_ok}")
        errors += 1

    # Caso 3: degradacion critica
    critical_rows = [
        {"date": "2026-02-10", "errores": 1, "warnings": 1},
        {"date": "2026-02-11", "errores": 1, "warnings": 1},
        {"date": "2026-02-12", "errores": 1, "warnings": 1},
        {"date": "2026-02-13", "errores": 4, "warnings": 12},
    ]
    alert_critical = build_trend_degradation_alert(critical_rows, baseline_days=3)
    if bool(alert_critical.get("show_alert", False)) and str(alert_critical.get("severity", "")).lower() == "critica":
        ok("Degradacion critica detectada")
    else:
        fail(f"No detecto degradacion critica: {alert_critical}")
        errors += 1

    ratio = alert_critical.get("ratio", {}) if isinstance(alert_critical.get("ratio"), dict) else {}
    if float(ratio.get("errores", 0.0)) >= 2.0 or float(ratio.get("warnings", 0.0)) >= 2.0:
        ok("Incluye ratio de degradacion en salida")
    else:
        fail(f"Ratio critico ausente o bajo: {ratio}")
        errors += 1

    message = str(alert_critical.get("message", ""))
    if "Degradacion critica" in message:
        ok("Mensaje incluye severidad critica")
    else:
        fail(f"Mensaje sin severidad esperada: {message!r}")
        errors += 1

    print()
    if errors == 0:
        print(f"{C.OK}{C.BOLD}CONTRACT TEST PASSED{C.RESET}")
        return True
    else:
        print(f"{C.FAIL}{C.BOLD}CONTRACT TEST FAILED ({errors} errores){C.RESET}")
        return False


# ==============================================================================
# TEST: Contrato export operativo de hallazgos (P2-04)
# ==============================================================================

def test_operational_hallazgos_export_contract():
    """
    Valida pipeline de export operativo:
    snapshots -> rows -> filtros -> payload -> serializacion JSON.
    """
    print(f"\n{C.BOLD}{'=' * 60}")
    print("  CONTRACT TEST: operational hallazgos export (P2-04)")
    print(f"{'=' * 60}{C.RESET}\n")

    errors = 0

    try:
        from audit import (
            build_operational_hallazgos_rows,
            filter_operational_hallazgos,
            build_operational_hallazgos_export_payload,
        )
        from exports import payload_to_json_bytes
        ok("Imports de export operativo exitosos")
    except Exception as e:
        fail(f"No se pudieron importar helpers de export operativo: {e}")
        return False

    snapshots = [
        {
            "_snapshot_path": "db/snapshots/audit_daily/audit_snapshot_20260213_000001.json",
            "_snapshot_generated_at": "2026-02-13T00:00:01Z",
            "_snapshot_date": "2026-02-13",
            "source": "nightly_cli",
            "backend_mode": "database",
            "audit_report": {
                "ok": False,
                "resumen": {"errores": 1, "warnings": 1, "info": 0, "casos": 10},
                "hallazgos": [
                    {
                        "nivel": "ERROR",
                        "codigo": "DATA-050",
                        "mensaje": "Falta FECHA_TAREA",
                        "ruta": "db://cases/1",
                        "sugerencia": "Completar FECHA_TAREA",
                    },
                    {
                        "nivel": "WARN",
                        "codigo": "DATA-051",
                        "mensaje": "Falta EXPEDIENTE",
                        "ruta": "db://cases/2",
                        "sugerencia": "Completar EXPEDIENTE",
                    },
                ],
            },
        },
        {
            "_snapshot_path": "db/snapshots/audit_daily/audit_snapshot_20260214_000001.json",
            "_snapshot_generated_at": "2026-02-14T00:00:01Z",
            "_snapshot_date": "2026-02-14",
            "source": "task_scheduler",
            "backend_mode": "database",
            "audit_report": {
                "ok": False,
                "resumen": {"errores": 1, "warnings": 0, "info": 0, "casos": 11},
                "hallazgos": [
                    {
                        "nivel": "ERROR",
                        "codigo": "DATA-050",
                        "mensaje": "Falta FECHA_TAREA",
                        "ruta": "db://cases/3",
                        "sugerencia": "Completar FECHA_TAREA",
                    }
                ],
            },
        },
    ]

    rows = build_operational_hallazgos_rows(snapshots)
    if len(rows) == 3:
        ok("Snapshots -> rows: cantidad esperada (3)")
    else:
        fail(f"Cantidad de rows inesperada: {len(rows)}")
        errors += 1

    required_keys = {
        "date", "generated_at", "source", "backend_mode", "snapshot_path",
        "nivel", "codigo", "mensaje", "ruta", "sugerencia",
    }
    if rows and required_keys.issubset(set(rows[0].keys())):
        ok("Rows incluyen metadata operativa requerida")
    else:
        fail(f"Rows no contienen claves requeridas: {rows[0].keys() if rows else []}")
        errors += 1

    filtered = filter_operational_hallazgos(
        rows,
        level="ERROR",
        code_query="DATA-050",
        date_from="2026-02-14",
        date_to="2026-02-14",
    )
    if len(filtered) == 1 and filtered[0].get("date") == "2026-02-14":
        ok("Filtros nivel/codigo/fecha aplicados correctamente")
    else:
        fail(f"Filtro operativo devolvio resultado inesperado: {filtered}")
        errors += 1

    payload = build_operational_hallazgos_export_payload(
        filtered,
        filters={"level": "ERROR", "code_query": "DATA-050", "date_from": "2026-02-14", "date_to": "2026-02-14"},
        snapshots_count=len(snapshots),
    )
    summary = payload.get("summary", {}) if isinstance(payload.get("summary"), dict) else {}
    if int(summary.get("rows", 0)) == 1 and int(summary.get("snapshots", 0)) == 2:
        ok("Payload summary incluye rows/snapshots esperados")
    else:
        fail(f"Summary inesperado: {summary}")
        errors += 1

    backend_modes = summary.get("backend_modes", [])
    if isinstance(backend_modes, list) and "database" in backend_modes:
        ok("Payload summary incluye backend_modes")
    else:
        fail(f"backend_modes inesperado: {backend_modes}")
        errors += 1

    json_bytes = payload_to_json_bytes(payload, indent=2)
    try:
        decoded = json.loads(json_bytes.decode("utf-8"))
        if int((decoded.get("summary", {}) or {}).get("rows", 0)) == 1:
            ok("payload_to_json_bytes serializa JSON UTF-8 valido")
        else:
            fail(f"JSON serializado con summary invalido: {decoded.get('summary')}")
            errors += 1
    except Exception as e:
        fail(f"payload_to_json_bytes produjo JSON invalido: {e}")
        errors += 1

    print()
    if errors == 0:
        print(f"{C.OK}{C.BOLD}CONTRACT TEST PASSED{C.RESET}")
        return True
    else:
        print(f"{C.FAIL}{C.BOLD}CONTRACT TEST FAILED ({errors} errores){C.RESET}")
        return False


def test_streamlit_width_hardening_contract():
    """
    Guardrail P3-01:
    - runtime no debe usar `use_container_width`
    - alcance: app.py, ui.py, views.py, grids.py
    """
    print(f"\n{C.BOLD}{'=' * 60}")
    print("  CONTRACT TEST: streamlit width hardening (P3-01)")
    print(f"{'=' * 60}{C.RESET}\n")

    runtime_files = [
        ROOT / "app.py",
        ROOT / "ui.py",
        ROOT / "views.py",
        ROOT / "grids.py",
    ]

    missing_files = []
    findings = []

    for path in runtime_files:
        if not path.exists():
            missing_files.append(path)
            continue

        text = path.read_text(encoding="utf-8-sig", errors="replace")
        for lineno, line in enumerate(text.splitlines(), start=1):
            if "use_container_width" in line:
                rel = path.relative_to(ROOT)
                findings.append(f"{rel}:{lineno}")

    if missing_files:
        for path in missing_files:
            fail(f"Archivo runtime ausente: {path}")
    else:
        ok("Archivos runtime presentes para hardening")

    if findings:
        fail("Se detectaron usos de use_container_width en runtime:")
        for item in findings:
            fail(f"  - {item}")
    else:
        ok("Runtime limpio: sin use_container_width en app/ui/views/grids")

    print()
    if not missing_files and not findings:
        print(f"{C.OK}{C.BOLD}CONTRACT TEST PASSED{C.RESET}")
        return True
    else:
        total_issues = len(missing_files) + len(findings)
        print(f"{C.FAIL}{C.BOLD}CONTRACT TEST FAILED ({total_issues} issues){C.RESET}")
        return False


def main():
    print(f"\n{C.BOLD}{'=' * 60}")
    print("  CONTRACT TESTS - VACA & GENTILE ERP")
    print("  Validacion de API entre backends FS y DB")
    print(f"{'=' * 60}{C.RESET}")

    results = {
        "obtener_clientes_existentes": test_obtener_clientes_existentes_contract(),
        "escanear_casos": test_escanear_casos_contract(),
        "_leer_ficha": test_leer_ficha_contract(),
        "actualizar_campos_ficha": test_actualizar_campos_ficha_contract(),
        "Caso_attributes": test_caso_attributes_contract(),
        "Caso_to_dict": test_caso_to_dict_contract(),
        "DB_pseudo_path": test_db_pseudo_path_contract(),
        "Caso_construction": test_caso_construction_contract(),
        "recent_documents_shape": test_recent_documents_contract_shape(),
        "recent_documents_empty": test_recent_documents_empty_behavior(),
        "evento_fields": test_evento_fields_contract(),
        "tarea_fields": test_tarea_fields_contract(),
        "dailyops_runner_contract": test_dailyops_runner_contract(),
        "release_gate_timeout_contract": test_release_gate_timeout_contract(),
        "release_gate_mode_contract": test_release_gate_mode_contract(),
        "env_contract_reproducible_docs_sync": test_env_contract_reproducible_docs_sync_contract(),
        "ops_behavior_suite_contract": test_ops_behavior_suite_contract(),
        "db_suite_isolation_contract": test_db_suite_isolation_contract(),
        "test_env_guard_negative": test_test_env_guard_negative_contract(),
        "ci_postgres_ephemeral_contract": test_ci_postgres_ephemeral_contract(),
        "structured_observability_contract": test_structured_observability_contract(),
        "quality_gate_kpi_contract": test_quality_gate_kpi_contract(),
        "security_baseline_contract": test_security_baseline_contract(),
        "performance_capacity_contract": test_performance_capacity_contract(),
        "backup_restore_drill_contract": test_backup_restore_drill_contract(),
        "legacy_fs_extraction_contract": test_legacy_fs_extraction_contract(),
        "trend_degradation_alert": test_trend_degradation_alert_contract(),
        "operational_hallazgos_export": test_operational_hallazgos_export_contract(),
        "streamlit_width_hardening": test_streamlit_width_hardening_contract(),
    }

    # Resumen final
    print(f"\n{C.BOLD}{'=' * 60}")
    print("  RESUMEN")
    print(f"{'=' * 60}{C.RESET}")

    total = len(results)
    passed = sum(1 for v in results.values() if v)

    for test, ok_test in results.items():
        status = f"{C.OK}PASS{C.RESET}" if ok_test else f"{C.FAIL}FAIL{C.RESET}"
        print(f"  {test:35} [{status}]")

    print()
    if passed == total:
        print(f"{C.OK}{C.BOLD}=== ALL CONTRACT TESTS PASSED ({passed}/{total}) ==={C.RESET}")
        sys.exit(0)
    else:
        print(f"{C.FAIL}{C.BOLD}=== CONTRACT TESTS FAILED ({passed}/{total}) ==={C.RESET}")
        sys.exit(1)


if __name__ == "__main__":
    main()
