#!/usr/bin/env python3
"""
Smoke Test - Backend PostgreSQL para VACA & GENTILE ERP.

Valida:
  a) DATABASE_URL configurada
  b) Conexion y SELECT 1
  c) Existencia de tablas minimas (clients, cases, documents, tasks)
  d) CRUD basico: insertar client + case de prueba
  e) Funciones de repo.py: escanear_casos, _leer_ficha, actualizar_campos_ficha, etc.
  f) Cleanup de registros de prueba

Uso:
  set DATABASE_URL=postgresql://user:pass@host:5432/dbname
  python db/smoke_test.py
"""

import os
import sys
import io
import uuid
import json
from pathlib import Path

# Forzar UTF-8 en stdout para Windows
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# Agregar raiz al path para imports
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


# ==============================================================================
# COLORES PARA OUTPUT
# ==============================================================================

class Colors:
    OK = "\033[92m"      # Verde
    FAIL = "\033[91m"    # Rojo
    WARN = "\033[93m"    # Amarillo
    INFO = "\033[94m"    # Azul
    RESET = "\033[0m"
    BOLD = "\033[1m"


def ok(msg: str):
    print(f"{Colors.OK}[OK] {msg}{Colors.RESET}")


def fail(msg: str):
    print(f"{Colors.FAIL}[FAIL] {msg}{Colors.RESET}")


def info(msg: str):
    print(f"{Colors.INFO}[INFO] {msg}{Colors.RESET}")


def section(title: str):
    print(f"\n{Colors.BOLD}{'=' * 60}")
    print(f"  {title}")
    print(f"{'=' * 60}{Colors.RESET}")


# ══════════════════════════════════════════════════════════════════════════════
# TEST: Verificar DATABASE_URL
# ══════════════════════════════════════════════════════════════════════════════

def test_database_url() -> bool:
    section("1. Verificando DATABASE_URL")

    db_url = os.environ.get("DATABASE_URL", "")

    if not db_url:
        fail("DATABASE_URL no esta configurada.")
        info("Configura la variable de entorno:")
        info("  Windows: set DATABASE_URL=postgresql://user:pass@host:5432/db")
        info("  Linux:   export DATABASE_URL=postgresql://user:pass@host:5432/db")
        return False

    # Ocultar password en output
    safe_url = db_url
    if "@" in db_url:
        parts = db_url.split("@")
        pre_at = parts[0]
        if ":" in pre_at:
            # postgresql://user:PASSWORD@host
            idx = pre_at.rfind(":")
            safe_url = pre_at[:idx+1] + "****@" + "@".join(parts[1:])

    ok(f"DATABASE_URL configurada: {safe_url[:60]}...")
    return True


# ══════════════════════════════════════════════════════════════════════════════
# TEST: Conexion y SELECT 1
# ══════════════════════════════════════════════════════════════════════════════

def test_connection() -> bool:
    section("2. Probando conexion (SELECT 1)")

    try:
        import psycopg2
    except ImportError:
        fail("psycopg2 no instalado. Ejecuta: pip install psycopg2-binary")
        return False

    try:
        from repo_db import get_conn

        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1 AS test")
                result = cur.fetchone()

                if result and result[0] == 1:
                    ok("SELECT 1 exitoso - Conexion funcionando")
                    return True
                else:
                    fail(f"SELECT 1 retorno inesperado: {result}")
                    return False

    except Exception as e:
        fail(f"Error de conexion: {e}")
        return False


# ══════════════════════════════════════════════════════════════════════════════
# TEST: Verificar existencia de tablas
# ══════════════════════════════════════════════════════════════════════════════

def test_tables_exist() -> bool:
    section("3. Verificando tablas minimas")

    required_tables = ["clients", "cases", "documents", "tasks"]

    try:
        from repo_db import get_conn

        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT table_name
                    FROM information_schema.tables
                    WHERE table_schema = 'public'
                      AND table_type = 'BASE TABLE'
                """)
                existing = {row[0] for row in cur.fetchall()}

        all_ok = True
        for table in required_tables:
            if table in existing:
                ok(f"Tabla '{table}' existe")
            else:
                fail(f"Tabla '{table}' NO existe")
                all_ok = False

        if not all_ok:
            info("Ejecuta el schema: psql -d tu_db -f db/schema.sql")

        return all_ok

    except Exception as e:
        fail(f"Error verificando tablas: {e}")
        return False


# ══════════════════════════════════════════════════════════════════════════════
# TEST: CRUD basico (insert client + case)
# ══════════════════════════════════════════════════════════════════════════════

# IDs de prueba (constantes para cleanup)
TEST_CLIENT_ID = "00000000-test-smok-e000-000000000001"
TEST_CASE_ID = "00000000-test-smok-e000-000000000002"


def test_insert_test_data() -> bool:
    section("4. Insertando datos de prueba")

    try:
        from repo_db import get_conn

        with get_conn() as conn:
            with conn.cursor() as cur:
                # Limpiar datos previos (por si quedo de una ejecucion anterior)
                cur.execute("DELETE FROM cases WHERE id = %s", (TEST_CASE_ID,))
                cur.execute("DELETE FROM clients WHERE id = %s", (TEST_CLIENT_ID,))

                # Insertar cliente de prueba
                cur.execute("""
                    INSERT INTO clients (id, name, type, status, extra)
                    VALUES (%s, %s, %s, %s, %s)
                """, (
                    TEST_CLIENT_ID,
                    "SMOKE_TEST_CLIENT",
                    "persona_fisica",
                    "activo",
                    json.dumps({"test": True, "created_by": "smoke_test"})
                ))
                ok("Cliente de prueba insertado")

                # Insertar caso de prueba con JSONB extra (ficha + financieros)
                extra_data = {
                    "TIPO_PROCESO": "Juicio Ordinario",
                    "JURISDICCION": "Nacional",
                    "ORGANISMO": "Juzgado Civil 99",
                    "EXPEDIENTE": "SMOKE-001/2026",
                    "CARATULA": "SMOKE TEST c/ BACKEND s/ Validacion",
                    "RESPONSABLE": "Test Runner",
                    "CONTROL": "Automatico",
                    "EVENTO": "Smoke test ejecutado",
                    "FECHA_EVENTO": "05/02/2026",
                    "TAREA_PENDIENTE": "Verificar CRUD",
                    "FECHA_TAREA": "10/02/2026",
                    "OBSERVACIONES": "Datos de prueba para smoke test",
                    # Financieros
                    "MONTO_DEMANDADO": "100000.50",
                    "HONORARIOS_PACTADOS": "15000.00",
                    "ESTADO_PAGO": "Pendiente",
                }

                cur.execute("""
                    INSERT INTO cases (
                        id, client_id, year, status, fuero, causa,
                        tipo_proceso, jurisdiccion, organismo, expediente,
                        caratula, responsable, control, evento,
                        tarea_pendiente, observaciones,
                        monto_demandado, honorarios_pactados, estado_pago,
                        extra
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s,
                        %s, %s, %s, %s,
                        %s, %s,
                        %s, %s, %s,
                        %s
                    )
                """, (
                    TEST_CASE_ID,
                    TEST_CLIENT_ID,
                    "2026",
                    "02. Activos",
                    "02. CIVIL",
                    "SMOKE_TEST_CASE",
                    extra_data["TIPO_PROCESO"],
                    extra_data["JURISDICCION"],
                    extra_data["ORGANISMO"],
                    extra_data["EXPEDIENTE"],
                    extra_data["CARATULA"],
                    extra_data["RESPONSABLE"],
                    extra_data["CONTROL"],
                    extra_data["EVENTO"],
                    extra_data["TAREA_PENDIENTE"],
                    extra_data["OBSERVACIONES"],
                    100000.50,
                    15000.00,
                    extra_data["ESTADO_PAGO"],
                    json.dumps(extra_data, ensure_ascii=False)
                ))
                ok("Caso de prueba insertado con campos ficha + financieros")

        return True

    except Exception as e:
        fail(f"Error insertando datos: {e}")
        return False


# ══════════════════════════════════════════════════════════════════════════════
# TEST: Funciones de repo.py
# ══════════════════════════════════════════════════════════════════════════════

def test_repo_functions() -> bool:
    section("5. Probando funciones de repo.py")

    all_ok = True

    try:
        # Importar desde repo.py (el factory)
        from repo import GestorCasos, is_db_mode

        if not is_db_mode():
            fail("repo.py no esta en modo DB. Verifica DATABASE_URL antes de importar.")
            return False

        ok(f"repo.py en modo DB (clase: {GestorCasos.__name__})")

        gestor = GestorCasos()

        # ─────────────────────────────────────────────────────────────────────
        # 5a. obtener_clientes_existentes()
        # ─────────────────────────────────────────────────────────────────────
        info("Probando obtener_clientes_existentes()...")
        clientes = gestor.obtener_clientes_existentes()

        if "SMOKE_TEST_CLIENT" in clientes:
            ok(f"obtener_clientes_existentes() -> {len(clientes)} clientes, incluye SMOKE_TEST_CLIENT")
        else:
            fail(f"obtener_clientes_existentes() no encontro SMOKE_TEST_CLIENT")
            all_ok = False

        # ─────────────────────────────────────────────────────────────────────
        # 5b. escanear_casos()
        # ─────────────────────────────────────────────────────────────────────
        info("Probando escanear_casos()...")
        casos = gestor.escanear_casos()

        caso_test = None
        for c in casos:
            if "SMOKE_TEST" in str(c.causa):
                caso_test = c
                break

        if caso_test:
            ok(f"escanear_casos() -> {len(casos)} casos, encontro SMOKE_TEST_CASE")
            info(f"  Pseudo-ruta: {caso_test.ruta}")
        else:
            fail("escanear_casos() no encontro SMOKE_TEST_CASE")
            all_ok = False

        # ─────────────────────────────────────────────────────────────────────
        # 5c. _leer_ficha(db://cases/<uuid>)
        # ─────────────────────────────────────────────────────────────────────
        test_path = Path(f"db://cases/{TEST_CASE_ID}")

        info(f"Probando _leer_ficha({test_path})...")
        ficha = gestor._leer_ficha(test_path)

        if ficha.get("TIPO_PROCESO") == "Juicio Ordinario":
            ok(f"_leer_ficha() -> TIPO_PROCESO={ficha.get('TIPO_PROCESO')}")
        else:
            fail(f"_leer_ficha() retorno inesperado: {ficha.get('TIPO_PROCESO')}")
            all_ok = False

        # ─────────────────────────────────────────────────────────────────────
        # 5d. actualizar_campos_ficha()
        # ─────────────────────────────────────────────────────────────────────
        info("Probando actualizar_campos_ficha()...")
        cambios = {"OBSERVACIONES": "Actualizado por smoke test"}
        result = gestor.actualizar_campos_ficha(test_path, cambios)

        if result:
            # Verificar que se guardo
            ficha2 = gestor._leer_ficha(test_path)
            if "Actualizado por smoke test" in ficha2.get("OBSERVACIONES", ""):
                ok("actualizar_campos_ficha() -> merge JSONB exitoso")
            else:
                fail("actualizar_campos_ficha() no persistio el cambio")
                all_ok = False
        else:
            fail("actualizar_campos_ficha() retorno False")
            all_ok = False

        # ─────────────────────────────────────────────────────────────────────
        # 5e. leer_datos_financieros()
        # ─────────────────────────────────────────────────────────────────────
        info("Probando leer_datos_financieros()...")
        fin = gestor.leer_datos_financieros(test_path)

        if fin.get("MONTO_DEMANDADO"):
            ok(f"leer_datos_financieros() -> MONTO={fin.get('MONTO_DEMANDADO')}")
        else:
            fail(f"leer_datos_financieros() no trajo MONTO_DEMANDADO")
            all_ok = False

        # ─────────────────────────────────────────────────────────────────────
        # 5f. guardar_datos_financieros()
        # ─────────────────────────────────────────────────────────────────────
        info("Probando guardar_datos_financieros()...")
        new_fin = {
            "MONTO_DEMANDADO": "200000.99",
            "HONORARIOS_PACTADOS": "30000.00",
            "ESTADO_PAGO": "Parcial"
        }
        result = gestor.guardar_datos_financieros(test_path, new_fin)

        if result:
            # Verificar
            fin2 = gestor.leer_datos_financieros(test_path)
            if "200000" in str(fin2.get("MONTO_DEMANDADO", "")):
                ok(f"guardar_datos_financieros() -> MONTO actualizado a {fin2.get('MONTO_DEMANDADO')}")
            else:
                fail("guardar_datos_financieros() no persistio MONTO_DEMANDADO")
                all_ok = False
        else:
            fail("guardar_datos_financieros() retorno False")
            all_ok = False

        return all_ok

    except Exception as e:
        fail(f"Error en funciones de repo: {e}")
        import traceback
        traceback.print_exc()
        return False


# ══════════════════════════════════════════════════════════════════════════════
# CLEANUP: Borrar datos de prueba
# ══════════════════════════════════════════════════════════════════════════════

def cleanup_test_data() -> bool:
    section("6. Limpieza de datos de prueba")

    try:
        from repo_db import get_conn

        with get_conn() as conn:
            with conn.cursor() as cur:
                # Borrar caso primero (FK)
                cur.execute("DELETE FROM cases WHERE id = %s", (TEST_CASE_ID,))
                deleted_cases = cur.rowcount

                # Borrar cliente
                cur.execute("DELETE FROM clients WHERE id = %s", (TEST_CLIENT_ID,))
                deleted_clients = cur.rowcount

        ok(f"Cleanup: {deleted_cases} caso(s), {deleted_clients} cliente(s) eliminados")
        return True

    except Exception as e:
        fail(f"Error en cleanup: {e}")
        return False


# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════

def main():
    print(f"\n{Colors.BOLD}{'=' * 60}")
    print("  SMOKE TEST - Backend PostgreSQL")
    print("  VACA & GENTILE ERP")
    print(f"{'=' * 60}{Colors.RESET}")

    results = {}

    # 1. DATABASE_URL
    results["database_url"] = test_database_url()
    if not results["database_url"]:
        print(f"\n{Colors.FAIL}ABORTADO: DATABASE_URL no configurada{Colors.RESET}")
        sys.exit(1)

    # 2. Conexion
    results["connection"] = test_connection()
    if not results["connection"]:
        print(f"\n{Colors.FAIL}ABORTADO: No se puede conectar a la DB{Colors.RESET}")
        sys.exit(1)

    # 3. Tablas
    results["tables"] = test_tables_exist()
    if not results["tables"]:
        print(f"\n{Colors.FAIL}ABORTADO: Faltan tablas requeridas{Colors.RESET}")
        sys.exit(1)

    # 4. Insert datos de prueba
    results["insert"] = test_insert_test_data()

    # 5. Funciones de repo.py
    if results["insert"]:
        results["repo_functions"] = test_repo_functions()
    else:
        results["repo_functions"] = False

    # 6. Cleanup (siempre intentar)
    results["cleanup"] = cleanup_test_data()

    # ═══════════════════════════════════════════════════════════════════════════
    # RESUMEN
    # ═══════════════════════════════════════════════════════════════════════════
    section("RESUMEN")

    total = len(results)
    passed = sum(1 for v in results.values() if v)

    for test, passed_test in results.items():
        status = f"{Colors.OK}PASS{Colors.RESET}" if passed_test else f"{Colors.FAIL}FAIL{Colors.RESET}"
        print(f"  {test:20} [{status}]")

    print()
    if passed == total:
        print(f"{Colors.OK}{Colors.BOLD}=== SMOKE TEST EXITOSO ({passed}/{total}) ==={Colors.RESET}")
        sys.exit(0)
    else:
        print(f"{Colors.FAIL}{Colors.BOLD}=== SMOKE TEST FALLIDO ({passed}/{total}) ==={Colors.RESET}")
        sys.exit(1)


if __name__ == "__main__":
    main()
