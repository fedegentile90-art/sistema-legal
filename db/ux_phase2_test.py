#!/usr/bin/env python3
"""
Smoke UX fase 2 (headless) para Gestion > Casos > Editar.

Valida:
1) Guardar sin cambios => no llama actualizar_campos_ficha.
2) Guardar con cambios => llama actualizar_campos_ficha y no crashea.
"""

import os
import sys
import uuid
from pathlib import Path

from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from db.test_env import (  # noqa: E402
    TEST_DATABASE_URL_ENV,
    mask_dsn,
    require_isolated_test_database_env,
)
from repo_db import GestorCasosDB, get_conn  # noqa: E402


class C:
    OK = "\033[92m"
    FAIL = "\033[91m"
    INFO = "\033[94m"
    RESET = "\033[0m"


def ok(msg: str):
    print(f"{C.OK}[OK] {msg}{C.RESET}")


def fail(msg: str):
    print(f"{C.FAIL}[FAIL] {msg}{C.RESET}")


def info(msg: str):
    print(f"{C.INFO}[INFO] {msg}{C.RESET}")


def _has_button(at: AppTest, key: str) -> bool:
    try:
        at.button(key=key)
        return True
    except KeyError:
        return False


def _ensure_case_available() -> dict | None:
    """Crea un caso temporal si la DB no tiene casos para ejecutar el smoke."""
    gestor = GestorCasosDB()
    if gestor.escanear_casos():
        return None

    suffix = uuid.uuid4().hex[:8]
    client_name = f"UX Phase2 {suffix}"
    case_name = f"Caso UX Phase2 {suffix}"
    ok_create, msg = gestor.crear_caso(
        "2026",
        "02. Activos",
        client_name,
        "99. OTROS",
        case_name,
    )
    if not ok_create:
        raise RuntimeError(f"No se pudo crear caso temporal: {msg}")

    info("DB sin casos: creado caso temporal para smoke UX")
    return {"client_name": client_name, "case_name": case_name}


def _cleanup_temp_case(temp_case: dict | None):
    """Elimina el caso temporal creado por el smoke (si aplica)."""
    if not temp_case:
        return

    client_name = temp_case["client_name"]
    case_name = temp_case["case_name"]

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                DELETE FROM cases c
                USING clients cl
                WHERE c.client_id = cl.id
                  AND cl.name = %s
                  AND c.causa = %s
                """,
                (client_name, case_name),
            )
            cur.execute(
                """
                DELETE FROM clients cl
                WHERE cl.name = %s
                  AND NOT EXISTS (
                      SELECT 1 FROM cases c WHERE c.client_id = cl.id
                  )
                """,
                (client_name,),
            )
    info("Cleanup: caso temporal eliminado")


def _go_primary_route(at: AppTest, route_label: str):
    route_to_button = {
        "Dashboard": "workspace.nav.dashboard",
        "Gestion": "workspace.nav.gestion",
        "Agenda": "workspace.nav.agenda",
        "Finanzas": "workspace.nav.finanzas",
        "Auditoria": "workspace.nav.auditoria",
        "Configuracion": "workspace.nav.configuracion",
    }
    button_key = route_to_button.get(str(route_label), "")
    if button_key:
        try:
            at.button(key=button_key).click()
            at.run()
            return
        except KeyError:
            pass

    try:
        at.radio(key="_sidebar_nav").set_value(route_label)
        at.run()
        return
    except KeyError:
        pass

    at.session_state["nav_route"] = route_label
    at.run()


def _goto_casos_editar(at: AppTest) -> str:
    at.run()
    _go_primary_route(at, "Gestion")

    state = at.session_state.filtered_state
    df = state.get("df_full")
    if df is None or getattr(df, "empty", True):
        raise RuntimeError("No hay casos en df_full para test UX")

    selected = str(df.iloc[0]["_RUTA"])
    at.session_state["gestion.section"] = "casos"
    at.session_state["gestion.tab"] = "casos"
    at.session_state["gestion.selected.case_id"] = selected
    at.session_state["gestion.casos.selected_case_id"] = selected
    at.session_state["selected_case_id"] = selected
    at.session_state["gestion.widgets.tabbar.label"] = "Casos"
    at.session_state["gestion.widgets.modebar.casos.label"] = "Editar"
    at.session_state["gestion.mode.casos"] = "editar"
    at.session_state["route_mode"] = "editar"
    at.run()

    if len(at.exception) > 0:
        raise RuntimeError(f"App exception en ir a editar: {[e.value for e in at.exception]}")

    if not _has_button(at, "gestion.casos.editar.guardar") and _has_button(at, "gestion.casos.detalle.editar"):
        at.button(key="gestion.casos.detalle.editar").click()
        at.run()
        if len(at.exception) > 0:
            raise RuntimeError(f"App exception en detalle->editar: {[e.value for e in at.exception]}")

    if not _has_button(at, "gestion.casos.editar.guardar"):
        raise RuntimeError("No se renderizo boton guardar en modo editar")

    return selected


def test_auditoria_degradacion_y_export_operativo() -> tuple[bool, str]:
    """
    Valida en UI de Auditoria:
    - alerta critica de degradacion visible
    - controles de filtro de export operativo renderizados
    - conteo de hallazgos cambia al filtrar
    """
    import views as views_mod

    original_ensure_daily = views_mod._ensure_daily_audit_snapshot_ui
    original_load_trend = views_mod._load_daily_audit_trend_rows
    original_load_snapshots = views_mod.load_daily_audit_snapshots

    def fake_ensure_daily(gestor, casos):
        return {
            "created": False,
            "date": "2026-02-13",
            "snapshot_path": "db/snapshots/audit_daily/audit_snapshot_latest.json",
            "history_path": "db/snapshots/audit_history.csv",
        }

    def fake_load_trend(limit: int = 14):
        return [
            {
                "date": "2026-02-10",
                "errores": 1,
                "warnings": 1,
                "info": 0,
                "casos": 10,
                "source": "nightly_cli",
                "kpi_fecha_tarea_pct": 80.0,
                "kpi_expediente_pct": 80.0,
                "kpi_evento_fecha_evento_pct": 80.0,
                "kpi_cobertura_financiera_pct": 80.0,
            },
            {
                "date": "2026-02-11",
                "errores": 1,
                "warnings": 1,
                "info": 0,
                "casos": 10,
                "source": "nightly_cli",
                "kpi_fecha_tarea_pct": 80.0,
                "kpi_expediente_pct": 80.0,
                "kpi_evento_fecha_evento_pct": 80.0,
                "kpi_cobertura_financiera_pct": 80.0,
            },
            {
                "date": "2026-02-12",
                "errores": 1,
                "warnings": 1,
                "info": 0,
                "casos": 10,
                "source": "nightly_cli",
                "kpi_fecha_tarea_pct": 80.0,
                "kpi_expediente_pct": 80.0,
                "kpi_evento_fecha_evento_pct": 80.0,
                "kpi_cobertura_financiera_pct": 80.0,
            },
            {
                "date": "2026-02-13",
                "errores": 4,
                "warnings": 12,
                "info": 0,
                "casos": 10,
                "source": "nightly_cli",
                "kpi_fecha_tarea_pct": 70.0,
                "kpi_expediente_pct": 70.0,
                "kpi_evento_fecha_evento_pct": 70.0,
                "kpi_cobertura_financiera_pct": 70.0,
            },
        ]

    def fake_load_snapshots(limit: int = 120):
        return [
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
            }
        ]

    views_mod._ensure_daily_audit_snapshot_ui = fake_ensure_daily
    views_mod._load_daily_audit_trend_rows = fake_load_trend
    views_mod.load_daily_audit_snapshots = fake_load_snapshots

    try:
        at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=120)
        at.run()
        _go_primary_route(at, "Auditoria")

        if len(at.exception) > 0:
            return False, f"Excepcion al abrir Auditoria: {[e.value for e in at.exception]}"

        error_msgs = [x.value for x in at.error]
        if not any("Degradacion critica" in str(msg) for msg in error_msgs):
            return False, f"No se renderizo alerta critica de degradacion (errors={error_msgs})"

        try:
            at.selectbox(key="audit.ops_export.filter.level")
            at.text_input(key="audit.ops_export.filter.code")
            at.date_input(key="audit.ops_export.filter.date_from")
            at.date_input(key="audit.ops_export.filter.date_to")
        except KeyError as e:
            return False, f"No se renderizaron controles de filtro operativo: {e}"

        captions_before = [c.value for c in at.caption if "Hallazgos filtrados:" in str(c.value)]
        if not any("2 de 2" in str(c) for c in captions_before):
            return False, f"Conteo inicial inesperado de hallazgos: {captions_before}"

        at.selectbox(key="audit.ops_export.filter.level").set_value("ERROR")
        at.run()
        if len(at.exception) > 0:
            return False, f"Excepcion al aplicar filtro nivel ERROR: {[e.value for e in at.exception]}"

        captions_after = [c.value for c in at.caption if "Hallazgos filtrados:" in str(c.value)]
        if not any("1 de 2" in str(c) for c in captions_after):
            return False, f"Conteo filtrado inesperado (esperado 1 de 2): {captions_after}"

        return True, "Auditoria renderiza degradacion critica y export operativo filtrable"
    finally:
        views_mod._ensure_daily_audit_snapshot_ui = original_ensure_daily
        views_mod._load_daily_audit_trend_rows = original_load_trend
        views_mod.load_daily_audit_snapshots = original_load_snapshots


def run() -> int:
    ok_env, value_or_reason = require_isolated_test_database_env(sync_database_url=True)
    if not ok_env:
        fail(value_or_reason)
        return 1
    info(f"{TEST_DATABASE_URL_ENV} validada: {mask_dsn(value_or_reason)}")

    os.environ.setdefault("VG_DEBUG", "0")
    os.environ["VG_AUTH_REQUIRED"] = "0"
    os.environ["VG_RBAC_STRICT"] = "0"
    os.environ["VG_EXPORT_STRICT"] = "0"
    # Esta suite valida comportamiento de Guardar manual (no auto-save).
    os.environ["VG_AUTO_SAVE_CHANGES"] = "0"

    original_update = GestorCasosDB.actualizar_campos_ficha
    calls = []
    temp_case = None

    def counting_update(self, ruta_caso, cambios, actor_ctx=None):
        calls.append({"ruta": str(ruta_caso), "cambios": dict(cambios)})
        return original_update(self, ruta_caso, cambios, actor_ctx=actor_ctx)

    GestorCasosDB.actualizar_campos_ficha = counting_update

    original_obs = None
    canonical_path = None

    try:
        try:
            temp_case = _ensure_case_available()
        except Exception as e:
            fail(f"No se pudo preparar datos para smoke UX: {e}")
            return 1

        # Caso 1: guardar sin cambios
        info("Caso 1: Guardar sin cambios")
        at1 = AppTest.from_file(str(ROOT / "app.py"), default_timeout=120)
        _goto_casos_editar(at1)

        before = len(calls)
        at1.button(key="gestion.casos.editar.guardar").click()
        at1.run()

        if len(at1.exception) > 0:
            fail(f"Excepcion en guardar sin cambios: {[e.value for e in at1.exception]}")
            return 1

        after = len(calls)
        if after != before:
            fail(f"Guardar sin cambios llamo a actualizar_campos_ficha ({before} -> {after})")
            return 1

        info_msgs = [x.value for x in at1.info]
        if not any("Sin cambios para guardar." in m for m in info_msgs):
            fail("No se mostro mensaje 'Sin cambios para guardar.'")
            return 1
        ok("Guardar sin cambios: no escribe DB")

        # Caso 2: guardar con cambios reales
        info("Caso 2: Guardar con cambios")
        at2 = AppTest.from_file(str(ROOT / "app.py"), default_timeout=120)
        _goto_casos_editar(at2)

        canonical_path = (
            at2.session_state.filtered_state.get("gestion.selected.case_id")
            or at2.session_state.filtered_state.get("gestion.casos.selected_case_id")
            or at2.session_state.filtered_state.get("selected_case_id")
        )
        original_obs = at2.session_state.filtered_state.get("gestion.casos.editar.field.observaciones", "")

        nuevo_obs = f"{original_obs} [ux-phase2]".strip()
        at2.text_area(key="gestion.casos.editar.field.observaciones").set_value(nuevo_obs)
        at2.run()

        before = len(calls)
        at2.button(key="gestion.casos.editar.guardar").click()
        at2.run()

        if len(at2.exception) > 0:
            fail(f"Excepcion en guardar con cambios: {[e.value for e in at2.exception]}")
            return 1

        after = len(calls)
        if after <= before:
            fail(f"Guardar con cambios NO llamo a actualizar_campos_ficha ({before} -> {after})")
            return 1

        mode_after_save = at2.session_state.filtered_state.get("gestion.mode.casos")
        if mode_after_save != "detalle":
            fail(f"Guardar con cambios no regreso a detalle (modo={mode_after_save!r})")
            return 1

        # Caso 3: Auditoria con degradacion + export operativo
        info("Caso 3: Auditoria degradacion y export operativo")
        ok_audit, msg_audit = test_auditoria_degradacion_y_export_operativo()
        if not ok_audit:
            fail(msg_audit)
            return 1
        ok(msg_audit)

        ok("Guardar con cambios: escribe DB y no crashea")
        ok("UX fase 2 headless: PASS")
        return 0

    finally:
        GestorCasosDB.actualizar_campos_ficha = original_update
        if canonical_path and original_obs is not None:
            try:
                gestor = GestorCasosDB()
                original_update(gestor, canonical_path, {"OBSERVACIONES": original_obs})
                info("Cleanup: observaciones restauradas")
            except Exception as e:
                fail(f"Cleanup no pudo restaurar observaciones: {e}")
        try:
            _cleanup_temp_case(temp_case)
        except Exception as e:
            fail(f"Cleanup no pudo eliminar caso temporal: {e}")


if __name__ == "__main__":
    raise SystemExit(run())
