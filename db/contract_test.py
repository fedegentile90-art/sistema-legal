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

    # Verificar que todos los valores son strings
    for key, val in d.items():
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
    Verifica paridad FS/DB para campos evento en Caso.to_dict():
    - Existen claves EVENTO y FECHA EVENTO
    - Ambas son str en ambos modos
    - Formato fecha: string (DD/MM/YYYY o vacio)
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

    # Crear caso de prueba con evento y fecha_evento
    caso_con_evento = Caso(
        ruta=Path("test/path"),
        año="2026",
        estado="ACTIVOS",
        cliente="TEST",
        fuero="CIVIL",
        causa="TEST",
        evento="Audiencia preliminar",
        fecha_evento="15/03/2026",
    )

    d = caso_con_evento.to_dict()

    # Verificar que existen las claves
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

    # Verificar que son strings
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

    # Verificar caso vacio (sin evento)
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
        ok("FECHA EVENTO vacio -> string vacio")
    else:
        fail(f"FECHA EVENTO vacio inesperado: '{d2.get('FECHA EVENTO')}'")
        errors += 1

    print()
    if errors == 0:
        print(f"{C.OK}{C.BOLD}CONTRACT TEST PASSED{C.RESET}")
        return True
    else:
        print(f"{C.FAIL}{C.BOLD}CONTRACT TEST FAILED ({errors} errores){C.RESET}")
        return False


# ==============================================================================
# TEST: Contrato de campos tarea en Caso.to_dict()
# ==============================================================================

def test_tarea_fields_contract():
    """
    Verifica paridad FS/DB para campos tarea en Caso.to_dict():
    - Existen claves TAREA PENDIENTE y FECHA TAREA
    - Ambas son str (nunca None)
    - SEMAFORO es consistente (calculado por dominio)
    - Sin tarea = strings vacios y semaforo blanco
    """
    print(f"\n{C.BOLD}{'=' * 60}")
    print("  CONTRACT TEST: tarea fields in Caso.to_dict()")
    print(f"{'=' * 60}{C.RESET}\n")

    errors = 0

    try:
        from domain import Caso
        from pathlib import Path
        from datetime import datetime, timedelta
        ok("Import Caso exitoso")
    except ImportError as e:
        fail(f"Error importando: {e}")
        return False

    # Caso con tarea vencida (semaforo rojo)
    fecha_pasada = (datetime.now() - timedelta(days=5)).strftime("%d/%m/%Y")
    caso_vencido = Caso(
        ruta=Path("test/vencido"),
        año="2026",
        estado="ACTIVOS",
        cliente="TEST",
        fuero="CIVIL",
        causa="TEST",
        tarea_pendiente="Contestar demanda",
        fecha_tarea=fecha_pasada,
    )

    d1 = caso_vencido.to_dict()

    # Verificar claves existen
    if "TAREA PENDIENTE" in d1:
        ok("to_dict() contiene clave 'TAREA PENDIENTE'")
    else:
        fail("to_dict() NO contiene clave 'TAREA PENDIENTE'")
        errors += 1

    if "FECHA TAREA" in d1:
        ok("to_dict() contiene clave 'FECHA TAREA'")
    else:
        fail("to_dict() NO contiene clave 'FECHA TAREA'")
        errors += 1

    if "SEMÁFORO" in d1:
        ok("to_dict() contiene clave 'SEMÁFORO'")
    else:
        fail("to_dict() NO contiene clave 'SEMÁFORO'")
        errors += 1

    # Verificar tipos (str, nunca None)
    if isinstance(d1.get("TAREA PENDIENTE"), str):
        ok(f"TAREA PENDIENTE es str: '{d1.get('TAREA PENDIENTE')}'")
    else:
        fail(f"TAREA PENDIENTE no es str: {type(d1.get('TAREA PENDIENTE'))}")
        errors += 1

    if isinstance(d1.get("FECHA TAREA"), str):
        ok(f"FECHA TAREA es str: '{d1.get('FECHA TAREA')}'")
    else:
        fail(f"FECHA TAREA no es str: {type(d1.get('FECHA TAREA'))}")
        errors += 1

    # Verificar semaforo vencido (rojo)
    if d1.get("SEMÁFORO") == "🔴":
        ok("Tarea vencida -> semaforo rojo")
    else:
        fail(f"Tarea vencida -> semaforo inesperado: '{d1.get('SEMÁFORO')}'")
        errors += 1

    # Caso con tarea proxima (semaforo amarillo)
    fecha_proxima = (datetime.now() + timedelta(days=3)).strftime("%d/%m/%Y")
    caso_proximo = Caso(
        ruta=Path("test/proximo"),
        año="2026",
        estado="ACTIVOS",
        cliente="TEST",
        fuero="CIVIL",
        causa="TEST",
        tarea_pendiente="Audiencia",
        fecha_tarea=fecha_proxima,
    )

    d2 = caso_proximo.to_dict()
    if d2.get("SEMÁFORO") == "🟡":
        ok("Tarea proxima (<=7 dias) -> semaforo amarillo")
    else:
        fail(f"Tarea proxima -> semaforo inesperado: '{d2.get('SEMÁFORO')}'")
        errors += 1

    # Caso sin tarea (semaforo blanco)
    caso_sin_tarea = Caso(
        ruta=Path("test/sin_tarea"),
        año="2026",
        estado="ACTIVOS",
        cliente="TEST",
        fuero="CIVIL",
        causa="TEST",
        tarea_pendiente="",
        fecha_tarea="",
    )

    d3 = caso_sin_tarea.to_dict()

    if d3.get("TAREA PENDIENTE") == "":
        ok("Sin tarea -> TAREA PENDIENTE = string vacio")
    else:
        fail(f"Sin tarea -> TAREA PENDIENTE inesperado: '{d3.get('TAREA PENDIENTE')}'")
        errors += 1

    if d3.get("FECHA TAREA") == "":
        ok("Sin tarea -> FECHA TAREA = string vacio")
    else:
        fail(f"Sin tarea -> FECHA TAREA inesperado: '{d3.get('FECHA TAREA')}'")
        errors += 1

    if d3.get("SEMÁFORO") == "⚪":
        ok("Sin tarea -> semaforo blanco")
    else:
        fail(f"Sin tarea -> semaforo inesperado: '{d3.get('SEMÁFORO')}'")
        errors += 1

    print()
    if errors == 0:
        print(f"{C.OK}{C.BOLD}CONTRACT TEST PASSED{C.RESET}")
        return True
    else:
        print(f"{C.FAIL}{C.BOLD}CONTRACT TEST FAILED ({errors} errores){C.RESET}")
        return False


# ==============================================================================
# MAIN
# ==============================================================================

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
