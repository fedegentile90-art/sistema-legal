#!/usr/bin/env python3
"""
Regresion UX Gestion (headless) para Streamlit AppTest.

Casos minimos:
1) test_gestion_render_exclusivo_por_seccion
2) test_no_editar_caso_sin_seleccion
3) test_listado_detalle_editar_guardar_vuelve_detalle
4) test_guardar_sin_cambios_no_write
5) test_persistencia_filtros_por_seccion
6) test_agenda_finanzas_fuera_de_gestion
7) test_agenda_empty_state_clear_filters
8) test_wizard_minimos_guardar_actualiza
9) test_finanzas_csv_import_plan_apply
"""

import os
import sys
import uuid
import re
from pathlib import Path

import pandas as pd
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from config import CAMPOS_FICHA  # noqa: E402
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


def _assert_no_exception(at: AppTest, context: str):
    if len(at.exception) > 0:
        raise RuntimeError(f"{context}: {[e.value for e in at.exception]}")


def _has_button(at: AppTest, key: str) -> bool:
    try:
        at.button(key=key)
        return True
    except KeyError:
        return False


def _has_widget(at: AppTest, widget_type: str, key: str) -> bool:
    try:
        if widget_type == "selectbox":
            at.selectbox(key=key)
            return True
        if widget_type == "radio":
            at.radio(key=key)
            return True
        if widget_type == "text_area":
            at.text_area(key=key)
            return True
        if widget_type == "text_input":
            at.text_input(key=key)
            return True
    except KeyError:
        return False
    return False


def _ensure_case_available() -> dict | None:
    gestor = GestorCasosDB()
    if gestor.escanear_casos():
        return None

    suffix = uuid.uuid4().hex[:8]
    client_name = f"UX Gestion {suffix}"
    case_name = f"Caso UX Gestion {suffix}"
    ok_create, msg = gestor.crear_caso(
        "2026",
        "02. Activos",
        client_name,
        "99. OTROS",
        case_name,
    )
    if not ok_create:
        raise RuntimeError(f"No se pudo crear caso temporal: {msg}")

    info("DB sin casos: creado caso temporal para regresion UX Gestion")
    return {"client_name": client_name, "case_name": case_name}


def _cleanup_temp_case(temp_case: dict | None):
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
                  AND NOT EXISTS (SELECT 1 FROM cases c WHERE c.client_id = cl.id)
                """,
                (client_name,),
            )
    info("Cleanup: caso temporal eliminado")


def _open_gestion(at: AppTest) -> str:
    at.run()
    at.radio(key="_sidebar_nav").set_value("Gestion")
    at.run()
    _assert_no_exception(at, "open_gestion")

    state = at.session_state.filtered_state
    df = state.get("df_full")
    if df is None or getattr(df, "empty", True):
        raise RuntimeError("No hay casos en df_full para pruebas UX")
    return str(df.iloc[0]["_RUTA"])


def _set_selected_case(at: AppTest, selected: str):
    at.session_state["gestion.section"] = "casos"
    at.session_state["gestion.tab"] = "casos"
    at.session_state["gestion.selected.case_id"] = selected
    at.session_state["gestion.casos.selected_case_id"] = selected
    at.session_state["selected_case_id"] = selected


def _go_section(at: AppTest, label: str):
    at.radio(key="gestion.widgets.tabbar.label").set_value(label)
    at.run()
    _assert_no_exception(at, f"go_section:{label}")


def _wizard_prefix_for_case(case_ref: str) -> str:
    safe_case = re.sub(r"[^a-zA-Z0-9]+", "_", str(case_ref or "case")).strip("_")
    safe_case = safe_case[-80:] if safe_case else "case"
    return f"gestion.casos.minwizard.{safe_case}"


def test_gestion_render_exclusivo_por_seccion() -> tuple[bool, str]:
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=120)
    _open_gestion(at)

    expected_any = {
        "Casos": [("button", "gestion.casos.filters.limpiar"), ("button", "gestion.context.casos.nuevo")],
        "Clientes": [("selectbox", "gestion.cliente.selector"), ("button", "gestion.cliente.listado.detalle")],
    }
    forbidden = {
        "Casos": ["gestion.agenda.filtro.ver", "gestion.finanzas.filtro_pago"],
        "Clientes": ["gestion.casos.filters.limpiar", "gestion.finanzas.filtro_pago", "gestion.agenda.filtro.ver"],
    }

    for label in ("Casos", "Clientes"):
        _go_section(at, label)
        state = at.session_state.filtered_state
        section = state.get("gestion.section")
        if label == "Casos" and section != "casos":
            return False, f"Seccion invalida para Casos ({section!r})"
        if label == "Clientes" and section != "clientes":
            return False, f"Seccion invalida para Clientes ({section!r})"

        found_expected = False
        for wtype, key in expected_any[label]:
            if wtype == "button" and _has_button(at, key):
                found_expected = True
                break
            if wtype in {"selectbox", "radio", "text_area", "text_input"} and _has_widget(at, wtype, key):
                found_expected = True
                break
        if not found_expected:
            return False, f"No se renderizo contenido esperado en seccion {label}"

        for key in forbidden[label]:
            if _has_button(at, key) or _has_widget(at, "selectbox", key):
                return False, f"Encimado detectado en {label}: aparece control {key}"

    return True, "Render exclusivo por seccion OK"


def test_no_editar_caso_sin_seleccion() -> tuple[bool, str]:
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=120)
    _open_gestion(at)

    at.session_state["gestion.section"] = "casos"
    at.session_state["gestion.tab"] = "casos"
    at.session_state["gestion.mode.casos"] = "editar"
    at.session_state["route_mode"] = "editar"
    at.session_state["gestion.selected.case_id"] = ""
    at.session_state["gestion.casos.selected_case_id"] = ""
    at.session_state["selected_case_id"] = None
    at.session_state["gestion.widgets.tabbar.label"] = "Casos"
    at.session_state["gestion.widgets.modebar.casos.label"] = "Editar"
    at.run()
    _assert_no_exception(at, "test_no_editar_caso_sin_seleccion")

    if not _has_button(at, "gestion.empty.guard.casos.editar"):
        return False, "No se renderizo empty-state en editar sin seleccion"
    if _has_button(at, "gestion.casos.editar.guardar"):
        return False, "No debe renderizarse formulario de edicion sin seleccion"
    return True, "Editar sin seleccion muestra guardia"


def test_listado_detalle_editar_guardar_vuelve_detalle(calls: list, original_update) -> tuple[bool, str]:
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=120)
    selected = _open_gestion(at)
    _set_selected_case(at, selected)

    at.session_state["gestion.mode.casos"] = "detalle"
    at.session_state["route_mode"] = "detalle"
    at.session_state["gestion.widgets.tabbar.label"] = "Casos"
    at.session_state["gestion.widgets.modebar.casos.label"] = "Detalle"
    at.run()
    _assert_no_exception(at, "detalle setup")

    if not _has_button(at, "gestion.casos.detalle.editar"):
        return False, "No existe boton Editar en detalle"
    at.button(key="gestion.casos.detalle.editar").click()
    at.run()
    _assert_no_exception(at, "detalle->editar")

    if not _has_widget(at, "text_area", "gestion.casos.editar.field.observaciones"):
        return False, "No se renderizo campo observaciones en editar"

    orig_obs = at.session_state.filtered_state.get("gestion.casos.editar.field.observaciones", "")
    new_obs = f"{orig_obs} [ux-gestion-reg]".strip()
    at.text_area(key="gestion.casos.editar.field.observaciones").set_value(new_obs)
    at.run()
    _assert_no_exception(at, "editar change obs")

    before = len(calls)
    at.button(key="gestion.casos.editar.guardar").click()
    at.run()
    _assert_no_exception(at, "editar guardar")
    after = len(calls)
    if after <= before:
        return False, f"Guardar con cambios no llamo actualizar_campos_ficha ({before}->{after})"

    state = at.session_state.filtered_state
    if state.get("gestion.mode.casos") != "detalle":
        return False, "Tras guardar debe volver a modo detalle"

    canonical = (
        state.get("gestion.selected.case_id")
        or state.get("gestion.casos.selected_case_id")
        or state.get("selected_case_id")
    )
    try:
        gestor = GestorCasosDB()
        original_update(gestor, canonical, {"OBSERVACIONES": orig_obs})
    except Exception as e:
        return False, f"Cleanup observaciones fallo: {e}"
    return True, "Listado->Detalle->Editar->Guardar vuelve a detalle"


def test_guardar_sin_cambios_no_write(calls: list) -> tuple[bool, str]:
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=120)
    selected = _open_gestion(at)
    _set_selected_case(at, selected)

    at.session_state["gestion.mode.casos"] = "editar"
    at.session_state["route_mode"] = "editar"
    at.session_state["gestion.widgets.tabbar.label"] = "Casos"
    at.session_state["gestion.widgets.modebar.casos.label"] = "Editar"
    at.run()
    _assert_no_exception(at, "setup editar sin cambios")

    before = len(calls)
    at.button(key="gestion.casos.editar.guardar").click()
    at.run()
    _assert_no_exception(at, "guardar sin cambios")
    after = len(calls)
    if after != before:
        return False, f"Guardar sin cambios escribio en DB ({before}->{after})"

    info_msgs = [x.value for x in at.info]
    if not any("Sin cambios para guardar." in m for m in info_msgs):
        return False, "No se mostro mensaje de sin cambios"
    return True, "Guardar sin cambios no escribe"


def test_persistencia_filtros_por_seccion() -> tuple[bool, str]:
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=120)
    selected = _open_gestion(at)
    _set_selected_case(at, selected)

    at.session_state["gestion.section"] = "casos"
    at.session_state["gestion.mode.casos"] = "listado"
    at.session_state["gestion.casos.filters.busqueda"] = "test-filtro"
    at.session_state["gestion.casos.filters.atajo"] = "Solo vencidos"
    at.session_state["gestion.filters.casos"] = {
        "busqueda": "test-filtro",
        "atajo": "Solo vencidos",
    }
    at.session_state["gestion.filters.clientes"] = {
        "busqueda": "cliente-filtro",
        "estado": "Todos",
    }
    at.run()
    _assert_no_exception(at, "setup filtros")

    _go_section(at, "Clientes")
    _go_section(at, "Casos")

    state = at.session_state.filtered_state
    casos_filters = state.get("gestion.filters.casos", {}) or {}
    clientes_filters = state.get("gestion.filters.clientes", {}) or {}

    if state.get("gestion.casos.filters.busqueda") != "test-filtro":
        return False, "Busqueda de Casos no persistio al volver de otra seccion"
    if state.get("gestion.casos.filters.atajo") != "Solo vencidos":
        return False, "Atajo de Casos no persistio al volver de otra seccion"
    if casos_filters.get("busqueda") != "test-filtro":
        return False, "gestion.filters.casos no persistio"
    if clientes_filters.get("busqueda") != "cliente-filtro":
        return False, "gestion.filters.clientes no persistio"
    return True, "Persistencia de filtros por seccion OK"


def test_agenda_finanzas_fuera_de_gestion() -> tuple[bool, str]:
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=120)
    _open_gestion(at)

    tabbar = at.radio(key="gestion.widgets.tabbar.label")
    options = list(getattr(tabbar, "options", []))
    if "Agenda" in options or "Finanzas" in options:
        return False, f"Gestion no debe incluir Agenda/Finanzas en tabbar (options={options})"

    _go_section(at, "Casos")
    if _has_widget(at, "selectbox", "gestion.finanzas.filtro_pago") or _has_widget(at, "selectbox", "gestion.agenda.filtro.ver"):
        return False, "Casos no debe renderizar controles de Agenda/Finanzas dentro de Gestion"

    at.radio(key="_sidebar_nav").set_value("Agenda")
    at.run()
    _assert_no_exception(at, "route_agenda")
    if not (
        _has_widget(at, "selectbox", "gestion.agenda.filtro.ver")
        or _has_button(at, "agenda.route.empty")
        or _has_button(at, "gestion.agenda.empty")
    ):
        return False, "Ruta Agenda no renderiza contenido esperado"

    at.radio(key="_sidebar_nav").set_value("Finanzas")
    at.run()
    _assert_no_exception(at, "route_finanzas")
    if not (_has_widget(at, "selectbox", "gestion.finanzas.filtro_pago") or _has_button(at, "finanzas.route.empty")):
        return False, "Ruta Finanzas no renderiza contenido esperado"

    return True, "Agenda/Finanzas fuera de Gestion y disponibles como rutas primarias"


def test_agenda_empty_state_clear_filters() -> tuple[bool, str]:
    import views as views_mod

    original_render_modulo_agenda = views_mod.render_modulo_agenda

    def _forced_empty_agenda(gestor, casos, mode="listado"):
        if mode != "listado":
            return None
        return views_mod._render_agenda_listado(
            tareas_filtradas=[],
            tareas_total=[object(), object()],
            gestor=gestor,
            agenda_ver="Solo vencidas",
            solo_activos=False,
        )

    views_mod.render_modulo_agenda = _forced_empty_agenda
    try:
        at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=120)
        at.run()
        at.radio(key="_sidebar_nav").set_value("Agenda")
        at.session_state["gestion.filters.agenda"] = {"ver": "Solo vencidas", "solo_activos": False}
        at.session_state["gestion.agenda.filtro.ver"] = "Solo vencidas"
        at.session_state["gestion.agenda.filtro.activos"] = False
        at.run()
        _assert_no_exception(at, "agenda_empty_setup")

        if not _has_button(at, "gestion.agenda.empty.clear_filters"):
            return False, "Agenda vacia no renderiza CTA Limpiar filtros"

        at.button(key="gestion.agenda.empty.clear_filters").click()
        at.run()
        _assert_no_exception(at, "agenda_empty_clear_filters")

        state = at.session_state.filtered_state
        filters = state.get("gestion.filters.agenda", {}) or {}
        if filters.get("ver") != "Todas":
            return False, f"No se restauro filtro 'ver' ({filters.get('ver')!r})"
        if bool(filters.get("solo_activos", False)) is not True:
            return False, f"No se restauro filtro 'solo_activos' ({filters.get('solo_activos')!r})"
        return True, "Agenda vacia: CTA Limpiar filtros restablece defaults"
    finally:
        views_mod.render_modulo_agenda = original_render_modulo_agenda


def test_wizard_minimos_guardar_actualiza() -> tuple[bool, str]:
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=120)
    selected = _open_gestion(at)
    _set_selected_case(at, selected)

    original_leer_ficha = GestorCasosDB._leer_ficha
    original_update = GestorCasosDB.actualizar_campos_ficha
    update_calls: list[dict] = []

    def fake_leer_ficha(self, ruta_caso):
        data = {campo: "" for campo in CAMPOS_FICHA}
        data.update({
            "TIPO_PROCESO": "Proceso Test",
            "JURISDICCION": "Nacional",
            "ORGANISMO": "Juzgado Test",
            "CARATULA": "Caratula Test",
            "CONTROL": "Control Test",
            "OBSERVACIONES": "Obs Test",
        })
        return data

    def fake_update(self, ruta_caso, cambios, actor_ctx=None):
        update_calls.append({
            "ruta": str(ruta_caso),
            "cambios": dict(cambios),
            "actor_ctx": dict(actor_ctx or {}),
        })
        return True

    GestorCasosDB._leer_ficha = fake_leer_ficha
    GestorCasosDB.actualizar_campos_ficha = fake_update
    try:
        at.session_state["gestion.section"] = "casos"
        at.session_state["gestion.tab"] = "casos"
        at.session_state["gestion.mode.casos"] = "detalle"
        at.session_state["route_mode"] = "detalle"
        at.session_state["gestion.widgets.tabbar.label"] = "Casos"
        at.session_state["gestion.widgets.modebar.casos.label"] = "Detalle"
        at.run()
        _assert_no_exception(at, "wizard_minimos_setup")

        state = at.session_state.filtered_state
        case_ref = (
            state.get("gestion.selected.case_id")
            or state.get("gestion.casos.selected_case_id")
            or state.get("selected_case_id")
            or selected
        )
        prefix = _wizard_prefix_for_case(case_ref)
        responsable_key = f"{prefix}.responsable"
        save_key = f"{prefix}.save"

        if not _has_widget(at, "text_input", responsable_key):
            return False, f"No se renderizo campo wizard esperado ({responsable_key})"
        if not _has_button(at, save_key):
            return False, f"No se renderizo submit del wizard ({save_key})"

        at.text_input(key=responsable_key).set_value("Responsable Wizard Test")
        at.run()
        _assert_no_exception(at, "wizard_minimos_set_value")

        before = len(update_calls)
        at.button(key=save_key).click()
        at.run()
        _assert_no_exception(at, "wizard_minimos_save")

        after = len(update_calls)
        if after <= before:
            return False, f"Wizard no llamo actualizar_campos_ficha ({before}->{after})"

        cambios = update_calls[-1]["cambios"]
        if cambios.get("RESPONSABLE") != "Responsable Wizard Test":
            return False, f"Wizard guardo RESPONSABLE inesperado ({cambios.get('RESPONSABLE')!r})"

        mode_after = at.session_state.filtered_state.get("gestion.mode.casos")
        if mode_after != "detalle":
            return False, f"Wizard no regreso a detalle (modo={mode_after!r})"

        return True, "Wizard mínimos guarda cambios y mantiene flujo en detalle"
    finally:
        GestorCasosDB._leer_ficha = original_leer_ficha
        GestorCasosDB.actualizar_campos_ficha = original_update


def test_finanzas_csv_import_plan_apply() -> tuple[bool, str]:
    import views as views_mod

    known_case_ref = "db://cases/11111111-1111-4111-8111-111111111111"
    unknown_case_ref = "db://cases/33333333-3333-4333-8333-333333333333"
    df_fin = pd.DataFrame([{
        "Cliente": "Cliente Test",
        "Causa": "Causa Test",
        "Estado": "02. Activos",
        "Monto Demandado": "1000.00",
        "Honorarios Pactados": "200.00",
        "Estado Pago": "Pendiente",
        "_RUTA": known_case_ref,
    }])
    df_csv = pd.DataFrame([
        {
            "_RUTA": known_case_ref,
            "MONTO_DEMANDADO": "1200.00",
            "HONORARIOS_PACTADOS": "200.00",
            "ESTADO_PAGO": "Parcial",
        },
        {
            "_RUTA": known_case_ref,
            "MONTO_DEMANDADO": "1100.00",
            "HONORARIOS_PACTADOS": "abc",
            "ESTADO_PAGO": "Parcial",
        },
        {
            "_RUTA": unknown_case_ref,
            "MONTO_DEMANDADO": "900.00",
            "HONORARIOS_PACTADOS": "100.00",
            "ESTADO_PAGO": "Pendiente",
        },
        {
            "_RUTA": known_case_ref,
            "MONTO_DEMANDADO": "1000.00",
            "HONORARIOS_PACTADOS": "200.00",
            "ESTADO_PAGO": "Pendiente",
        },
    ])

    plan = views_mod._build_finanzas_import_plan(df_csv, df_fin)
    if plan.get("fatal_error"):
        return False, f"Dry-run devolvio fatal_error inesperado: {plan.get('fatal_error')}"

    summary = plan.get("summary", {}) if isinstance(plan.get("summary"), dict) else {}
    if int(summary.get("total", 0)) != 4:
        return False, f"Dry-run total inesperado ({summary})"
    if int(summary.get("to_update", 0)) != 1:
        return False, f"Dry-run to_update inesperado ({summary})"
    if int(summary.get("omitted", 0)) != 1:
        return False, f"Dry-run omitted inesperado ({summary})"
    if int(summary.get("errors", 0)) != 2:
        return False, f"Dry-run errors inesperado ({summary})"

    class FakeGestor:
        def __init__(self):
            self.calls: list[dict] = []

        def guardar_datos_financieros(self, ruta_caso, datos_fin, actor_ctx=None):
            self.calls.append({
                "ruta": str(ruta_caso),
                "datos_fin": dict(datos_fin),
                "actor_ctx": dict(actor_ctx or {}),
            })
            return True

    fake = FakeGestor()
    result = views_mod._apply_finanzas_import_plan(plan, fake)

    if len(fake.calls) != 1:
        return False, f"Apply deberia escribir 1 fila y escribio {len(fake.calls)}"

    call0 = fake.calls[0]
    if "11111111-1111-4111-8111-111111111111" not in call0.get("ruta", ""):
        return False, f"Apply escribio ruta inesperada ({call0.get('ruta')!r})"

    result_summary = result.get("summary", {}) if isinstance(result.get("summary"), dict) else {}
    if int(result_summary.get("total", 0)) != 4:
        return False, f"Resultado total inesperado ({result_summary})"
    if int(result_summary.get("updated", 0)) != 1:
        return False, f"Resultado updated inesperado ({result_summary})"
    if int(result_summary.get("omitted", 0)) != 1:
        return False, f"Resultado omitted inesperado ({result_summary})"
    if int(result_summary.get("errors", 0)) != 2:
        return False, f"Resultado errors inesperado ({result_summary})"

    return True, "Finanzas CSV dry-run/apply reportan y aplican correctamente"


def run() -> int:
    ok_env, value_or_reason = require_isolated_test_database_env(sync_database_url=True)
    if not ok_env:
        fail(value_or_reason)
        return 1
    info(f"{TEST_DATABASE_URL_ENV} validada: {mask_dsn(value_or_reason)}")

    os.environ.setdefault("VG_DEBUG", "0")
    temp_case = None
    calls: list[dict] = []

    original_update = GestorCasosDB.actualizar_campos_ficha

    def counting_update(self, ruta_caso, cambios, actor_ctx=None):
        calls.append({"ruta": str(ruta_caso), "cambios": dict(cambios)})
        return original_update(self, ruta_caso, cambios, actor_ctx=actor_ctx)

    GestorCasosDB.actualizar_campos_ficha = counting_update
    try:
        temp_case = _ensure_case_available()

        tests = [
            ("test_gestion_render_exclusivo_por_seccion", lambda: test_gestion_render_exclusivo_por_seccion()),
            ("test_no_editar_caso_sin_seleccion", lambda: test_no_editar_caso_sin_seleccion()),
            ("test_listado_detalle_editar_guardar_vuelve_detalle", lambda: test_listado_detalle_editar_guardar_vuelve_detalle(calls, original_update)),
            ("test_guardar_sin_cambios_no_write", lambda: test_guardar_sin_cambios_no_write(calls)),
            ("test_persistencia_filtros_por_seccion", lambda: test_persistencia_filtros_por_seccion()),
            ("test_agenda_finanzas_fuera_de_gestion", lambda: test_agenda_finanzas_fuera_de_gestion()),
            ("test_agenda_empty_state_clear_filters", lambda: test_agenda_empty_state_clear_filters()),
            ("test_wizard_minimos_guardar_actualiza", lambda: test_wizard_minimos_guardar_actualiza()),
            ("test_finanzas_csv_import_plan_apply", lambda: test_finanzas_csv_import_plan_apply()),
        ]

        for name, fn in tests:
            info(f"Ejecutando {name}")
            ok_test, msg = fn()
            if not ok_test:
                fail(f"{name}: {msg}")
                return 1
            ok(f"{name}: {msg}")

        ok("ux_gestion_regression_test: PASS")
        return 0
    except Exception as e:
        fail(f"Error ejecutando regresion UX Gestion: {e}")
        return 1
    finally:
        GestorCasosDB.actualizar_campos_ficha = original_update
        try:
            _cleanup_temp_case(temp_case)
        except Exception as e:
            fail(f"Cleanup de caso temporal fallo: {e}")


if __name__ == "__main__":
    raise SystemExit(run())
