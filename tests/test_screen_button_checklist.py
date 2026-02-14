from pathlib import Path

from streamlit.testing.v1 import AppTest


ROOT = Path(__file__).resolve().parent.parent


def _boot_app(monkeypatch) -> AppTest:
    monkeypatch.setenv("VG_AUTH_REQUIRED", "0")
    monkeypatch.setenv("VG_RBAC_STRICT", "0")
    monkeypatch.setenv("VG_EXPORT_STRICT", "0")
    monkeypatch.setenv("VG_AUTO_SAVE_CHANGES", "1")
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=120)
    at.run()
    return at


def _assert_no_exception(at: AppTest, context: str) -> None:
    if len(at.exception) > 0:
        raise AssertionError(f"{context}: {[e.value for e in at.exception]}")


def _has_button(at: AppTest, key: str) -> bool:
    try:
        at.button(key=key)
        return True
    except KeyError:
        return False


def _has_radio(at: AppTest, key: str) -> bool:
    try:
        at.radio(key=key)
        return True
    except KeyError:
        return False


def _go_route(at: AppTest, route: str) -> None:
    key = f"workspace.nav.{route.lower()}"
    at.button(key=key).click()
    at.run()
    _assert_no_exception(at, f"route {route}")
    assert at.session_state.filtered_state.get("nav_route") == route


def test_screen_button_checklist_by_route(monkeypatch) -> None:
    at = _boot_app(monkeypatch)
    _assert_no_exception(at, "initial render")

    # Dashboard
    _go_route(at, "Dashboard")
    assert _has_button(at, "dash_empty_go_gestion") or _has_button(at, "dash_go_gestion")
    if _has_button(at, "dash_go_gestion"):
        assert _has_button(at, "dash_go_agenda")
        assert _has_button(at, "dash_go_finanzas")
        assert _has_button(at, "dash_go_audit")

    # Gestion
    _go_route(at, "Gestion")
    assert _has_radio(at, "gestion.widgets.tabbar.label")
    assert _has_radio(at, "gestion.widgets.modebar.casos.label")
    assert _has_button(at, "gestion.context.casos.go_agenda")
    assert _has_button(at, "gestion.context.casos.go_dashboard")

    # Agenda
    _go_route(at, "Agenda")
    assert _has_radio(at, "gestion.widgets.modebar.agenda.label")
    assert _has_button(at, "gestion.context.agenda.go_gestion")
    assert _has_button(at, "gestion.context.agenda.go_dashboard")

    # Finanzas
    _go_route(at, "Finanzas")
    assert _has_radio(at, "gestion.widgets.modebar.finanzas.label")
    assert _has_button(at, "gestion.context.finanzas.go_gestion")
    assert _has_button(at, "gestion.context.finanzas.go_dashboard")

    # Auditoria
    _go_route(at, "Auditoria")
    assert _has_button(at, "audit.nav.dashboard")
    assert _has_button(at, "audit.nav.gestion")
    assert _has_button(at, "audit.nav.agenda")
    assert _has_button(at, "audit.nav.configuracion")

    # Configuracion
    _go_route(at, "Configuracion")
    assert _has_button(at, "config.ops.reload_cache")
    assert _has_button(at, "config.ops.go_dashboard")
    assert _has_button(at, "config.ops.retry_db")
    assert _has_button(at, "config.quick.nav.dashboard")
    assert _has_button(at, "config.quick.nav.gestion")
    assert _has_button(at, "config.quick.nav.agenda")
    assert _has_button(at, "config.quick.nav.finanzas")
    assert _has_button(at, "config.quick.nav.auditoria")
