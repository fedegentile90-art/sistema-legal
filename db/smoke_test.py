#!/usr/bin/env python3
"""
Smoke Test - Backend PostgreSQL para VACA & GENTILE ERP.

Valida:
  a) contrato de DB de pruebas (VG_TEST_DATABASE_URL) valido
  b) contrato de entorno reproducible (db/env_contract.py)
  c) Conexion y SELECT 1
  d) Existencia de tablas minimas (clients, cases, documents, tasks)
  e) CRUD basico: insertar client + case de prueba
  f) Funciones de repo.py: escanear_casos, _leer_ficha, actualizar_campos_ficha, etc.
  g) Cleanup de registros de prueba

Uso:
  set VG_TEST_DATABASE_URL=postgresql://user:pass@host:5432/sistemalegal_test
  python db/smoke_test.py
"""

import os
import sys
import io
import uuid
import json
import subprocess
from pathlib import Path

# Forzar UTF-8 en stdout para Windows
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# Agregar raiz al path para imports
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from db.test_env import (  # noqa: E402
    TEST_DATABASE_URL_ENV,
    mask_dsn,
    require_isolated_test_database_env,
)


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
# TEST: Verificar contrato de DB de pruebas
# ══════════════════════════════════════════════════════════════════════════════

def test_isolated_test_database_contract() -> bool:
    section(f"1. Verificando {TEST_DATABASE_URL_ENV}")

    ok_env, value_or_reason = require_isolated_test_database_env(sync_database_url=True)
    if not ok_env:
        fail(value_or_reason)
        info("Configura una DB de pruebas dedicada:")
        info(f"  Windows: set {TEST_DATABASE_URL_ENV}=postgresql://user:pass@host:5432/sistemalegal_test")
        info(f"  Linux:   export {TEST_DATABASE_URL_ENV}=postgresql://user:pass@host:5432/sistemalegal_test")
        return False

    ok(f"{TEST_DATABASE_URL_ENV} validada: {mask_dsn(value_or_reason)}")
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

# TEST: Nightly Audit operacional en modo no-save

def test_nightly_audit_operational_no_save() -> bool:
    section("4. Nightly audit operacional (--no-save)")

    try:
        proc = subprocess.run(
            [sys.executable, "db/nightly_audit.py", "--no-save"],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=180,
        )
    except Exception as e:
        fail(f"No se pudo ejecutar nightly_audit --no-save: {e}")
        return False

    output = f"{proc.stdout}\n{proc.stderr}"
    if proc.returncode != 0:
        fail(f"nightly_audit --no-save retorno {proc.returncode}")
        info(output[-1200:])
        return False

    if "Preflight DB: OK" not in output:
        fail("nightly_audit --no-save no reporto preflight DB OK")
        info(output[-1200:])
        return False

    ok("nightly_audit --no-save retorno 0 con preflight DB OK")
    return True


# TEST: Gate bloqueado sin VG_TEST_DATABASE_URL

def test_ops_behavior_suite_runs() -> bool:
    section("9. Ops behavior suite (P4-01)")

    env = os.environ.copy()
    if not str(env.get("DATABASE_URL", "")).strip():
        fail("DATABASE_URL no esta disponible para ops_behavior_test")
        return False

    # Forzar modo no destructivo para corrida de comportamiento operativo.
    env["VG_RELEASE_GATE_MODE"] = "read_only"
    env.pop(TEST_DATABASE_URL_ENV, None)

    try:
        proc = subprocess.run(
            [sys.executable, "db/ops_behavior_test.py"],
            cwd=str(ROOT),
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=1200,
        )
    except Exception as e:
        fail(f"No se pudo ejecutar ops_behavior_test: {e}")
        return False

    output = f"{proc.stdout}\n{proc.stderr}"
    if proc.returncode != 0:
        fail(f"ops_behavior_test retorno {proc.returncode} (esperado=0)")
        info(output[-2600:])
        return False

    if "OPS BEHAVIOR TEST PASS" not in output:
        fail("ops_behavior_test no reporto PASS")
        info(output[-2600:])
        return False

    ok("ops_behavior_test PASS")
    return True


def test_env_contract_daily_ops_blocked_without_runtime_dsn() -> bool:
    section("5. Env contract daily_ops bloqueado sin DATABASE_URL")

    env = os.environ.copy()
    env.pop("DATABASE_URL", None)
    env.pop("VG_RUNTIME_DATABASE_URL", None)
    env.pop("VG_TEST_DATABASE_URL", None)

    try:
        proc = subprocess.run(
            [sys.executable, "db/env_contract.py", "--profile", "daily_ops"],
            cwd=str(ROOT),
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
        )
    except Exception as e:
        fail(f"No se pudo ejecutar env_contract daily_ops sin DATABASE_URL: {e}")
        return False

    output = f"{proc.stdout}\n{proc.stderr}"
    if proc.returncode != 2:
        fail(f"env_contract daily_ops sin DATABASE_URL retorno {proc.returncode} (esperado=2)")
        info(output[-1600:])
        return False

    if "DATABASE_URL" not in output:
        fail("env_contract daily_ops no reporto DATABASE_URL faltante")
        info(output[-1600:])
        return False

    ok("env_contract daily_ops bloquea sin DATABASE_URL (retorno=2)")
    return True


def test_env_contract_daily_ops_read_only_without_test_dsn() -> bool:
    section(f"6. Env contract daily_ops read_only sin {TEST_DATABASE_URL_ENV}")

    env = os.environ.copy()
    if not str(env.get("DATABASE_URL", "")).strip():
        fail("DATABASE_URL no esta disponible en entorno para test read_only")
        return False
    env["VG_RELEASE_GATE_MODE"] = "read_only"
    env.pop(TEST_DATABASE_URL_ENV, None)

    try:
        proc = subprocess.run(
            [sys.executable, "db/env_contract.py", "--profile", "daily_ops"],
            cwd=str(ROOT),
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
        )
    except Exception as e:
        fail(f"No se pudo ejecutar env_contract daily_ops read_only sin {TEST_DATABASE_URL_ENV}: {e}")
        return False

    output = f"{proc.stdout}\n{proc.stderr}"
    if proc.returncode != 0:
        fail(
            f"env_contract daily_ops read_only sin {TEST_DATABASE_URL_ENV} "
            f"retorno {proc.returncode} (esperado=0)"
        )
        info(output[-1600:])
        return False

    if "ENV CONTRACT: PASS" not in output:
        fail("env_contract daily_ops read_only no reporto PASS")
        info(output[-1600:])
        return False

    ok(f"env_contract daily_ops read_only pasa sin {TEST_DATABASE_URL_ENV}")
    return True


def test_release_gate_blocked_without_test_database_url() -> bool:
    section(f"8. Release gate bloqueado sin {TEST_DATABASE_URL_ENV}")

    env = os.environ.copy()
    env.pop("DATABASE_URL", None)
    env.pop(TEST_DATABASE_URL_ENV, None)
    env.pop("VG_RUNTIME_DATABASE_URL", None)

    try:
        proc = subprocess.run(
            [sys.executable, "db/release_gate.py"],
            cwd=str(ROOT),
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=240,
        )
    except Exception as e:
        fail(f"No se pudo ejecutar release_gate sin {TEST_DATABASE_URL_ENV}: {e}")
        return False

    output = f"{proc.stdout}\n{proc.stderr}"
    if proc.returncode != 2:
        fail(f"release_gate sin {TEST_DATABASE_URL_ENV} retorno {proc.returncode} (esperado=2)")
        info(output[-1600:])
        return False

    if "BLOCKED" not in output or TEST_DATABASE_URL_ENV not in output:
        fail(f"release_gate no mostro bloqueo esperado por {TEST_DATABASE_URL_ENV} ausente")
        info(output[-1600:])
        return False

    ok(f"release_gate sin {TEST_DATABASE_URL_ENV} retorna 2 y bloquea suites DB")
    return True


def test_release_gate_read_only_without_test_database_url() -> bool:
    section(f"9. Release gate read_only sin {TEST_DATABASE_URL_ENV}")

    env = os.environ.copy()
    env.pop("DATABASE_URL", None)
    env.pop(TEST_DATABASE_URL_ENV, None)
    env.pop("VG_RUNTIME_DATABASE_URL", None)
    env.pop("VG_RELEASE_GATE_MODE", None)

    try:
        proc = subprocess.run(
            [sys.executable, "db/release_gate.py", "--mode", "read_only"],
            cwd=str(ROOT),
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=240,
        )
    except Exception as e:
        fail(f"No se pudo ejecutar release_gate read_only sin {TEST_DATABASE_URL_ENV}: {e}")
        return False

    output = f"{proc.stdout}\n{proc.stderr}"
    if proc.returncode != 0:
        fail(f"release_gate read_only sin {TEST_DATABASE_URL_ENV} retorno {proc.returncode} (esperado=0)")
        info(output[-1600:])
        return False

    if "SKIPPED" not in output or "read_only" not in output:
        fail("release_gate read_only no reporto SKIPPED para suites DB")
        info(output[-1600:])
        return False

    ok(f"release_gate read_only sin {TEST_DATABASE_URL_ENV} retorna 0 y salta suites DB")
    return True


# IDs de prueba (UUID validos y estables para cleanup idempotente)
TEST_CLIENT_ID = "11111111-1111-4111-8111-111111111111"
TEST_CASE_ID = "22222222-2222-4222-8222-222222222222"


def test_insert_test_data() -> bool:
    section("10. Insertando datos de prueba")

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
    section("11. Probando funciones de repo.py")

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
    section("12. Limpieza de datos de prueba")

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

    # 1. Contrato de DB de pruebas
    results["test_db_contract"] = test_isolated_test_database_contract()
    if not results["test_db_contract"]:
        print(f"\n{Colors.FAIL}ABORTADO: contrato de DB de pruebas invalido{Colors.RESET}")
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

    # 4. Nightly no-save (operacional)
    results["nightly_no_save"] = test_nightly_audit_operational_no_save()
    if not results["nightly_no_save"]:
        print(f"\n{Colors.FAIL}ABORTADO: nightly_audit --no-save fallo{Colors.RESET}")
        sys.exit(1)

    # 5. Env contract daily_ops sin DATABASE_URL (fallo controlado)
    results["env_contract_daily_ops_missing_runtime_dsn"] = test_env_contract_daily_ops_blocked_without_runtime_dsn()
    if not results["env_contract_daily_ops_missing_runtime_dsn"]:
        print(
            f"\n{Colors.FAIL}ABORTADO: env_contract daily_ops sin DATABASE_URL "
            f"no cumplio politica FAIL{Colors.RESET}"
        )
        sys.exit(1)

    # 6. Env contract daily_ops read_only sin VG_TEST_DATABASE_URL (fallo controlado -> PASS)
    results["env_contract_daily_ops_read_only_missing_test_dsn"] = test_env_contract_daily_ops_read_only_without_test_dsn()
    if not results["env_contract_daily_ops_read_only_missing_test_dsn"]:
        print(
            f"\n{Colors.FAIL}ABORTADO: env_contract daily_ops read_only sin {TEST_DATABASE_URL_ENV} "
            f"no cumplio politica PASS{Colors.RESET}"
        )
        sys.exit(1)

    # 7. Ops behavior suite (P4-01)
    results["ops_behavior_suite"] = test_ops_behavior_suite_runs()
    if not results["ops_behavior_suite"]:
        print(
            f"\n{Colors.FAIL}ABORTADO: ops_behavior_test no cumplio contrato operacional{Colors.RESET}"
        )
        sys.exit(1)

    # 8. Gate bloqueado sin VG_TEST_DATABASE_URL (fallo controlado)
    results["release_gate_blocked_missing_test_dsn"] = test_release_gate_blocked_without_test_database_url()
    if not results["release_gate_blocked_missing_test_dsn"]:
        print(
            f"\n{Colors.FAIL}ABORTADO: release_gate sin {TEST_DATABASE_URL_ENV} "
            f"no cumplio politica BLOCKED{Colors.RESET}"
        )
        sys.exit(1)

    # 9. Gate read_only sin VG_TEST_DATABASE_URL (fallo controlado -> PASS)
    results["release_gate_read_only_missing_test_dsn"] = test_release_gate_read_only_without_test_database_url()
    if not results["release_gate_read_only_missing_test_dsn"]:
        print(
            f"\n{Colors.FAIL}ABORTADO: release_gate read_only sin {TEST_DATABASE_URL_ENV} "
            f"no cumplio politica SKIPPED{Colors.RESET}"
        )
        sys.exit(1)

    # 10. Insert datos de prueba
    results["insert"] = test_insert_test_data()

    # 11. Funciones de repo.py
    if results["insert"]:
        results["repo_functions"] = test_repo_functions()
    else:
        results["repo_functions"] = False

    # 12. Cleanup (siempre intentar)
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
