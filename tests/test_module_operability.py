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


def test_config_operational_controls_render_and_toggle(monkeypatch) -> None:
    at = _boot_app(monkeypatch)
    _assert_no_exception(at, "initial render")

    at.button(key="workspace.nav.configuracion").click()
    at.run()
    _assert_no_exception(at, "config route")

    assert at.button(key="config.ops.shortcut.desktop")
    assert at.button(key="config.ops.setup_test_db")
    assert at.toggle(key="ui.auto_save.enabled").value is True
    at.toggle(key="ui.auto_save.enabled").set_value(False)
    at.run()
    _assert_no_exception(at, "config toggle autosave")
    assert at.session_state.filtered_state.get("ui.auto_save.enabled") is False

    at.button(key="config.ops.go_dashboard").click()
    at.run()
    _assert_no_exception(at, "back to dashboard")
    assert at.session_state.filtered_state.get("nav_route") == "Dashboard"


def test_dashboard_shortcuts_visible_when_cases_exist(monkeypatch) -> None:
    at = _boot_app(monkeypatch)
    _assert_no_exception(at, "initial render")

    button_keys = {b.key for b in at.button if b.key}
    assert "dash_empty_go_gestion" in button_keys or "dash_go_gestion" in button_keys
    if "dash_go_gestion" in button_keys:
        assert "dash_go_agenda" in button_keys
        assert "dash_go_finanzas" in button_keys
        assert "dash_go_audit" in button_keys


def test_primary_routes_render_without_runtime_errors(monkeypatch) -> None:
    at = _boot_app(monkeypatch)
    _assert_no_exception(at, "initial render")

    routes = [
        ("workspace.nav.dashboard", "Dashboard"),
        ("workspace.nav.gestion", "Gestion"),
        ("workspace.nav.agenda", "Agenda"),
        ("workspace.nav.finanzas", "Finanzas"),
        ("workspace.nav.auditoria", "Auditoria"),
        ("workspace.nav.configuracion", "Configuracion"),
    ]
    for key, expected_route in routes:
        at.button(key=key).click()
        at.run()
        _assert_no_exception(at, f"route {expected_route}")
        assert at.session_state.filtered_state.get("nav_route") == expected_route


def test_standalone_modebars_fallback_to_listado_without_selection(monkeypatch) -> None:
    at = _boot_app(monkeypatch)
    _assert_no_exception(at, "initial render")

    at.button(key="workspace.nav.agenda").click()
    at.run()
    _assert_no_exception(at, "agenda route")
    at.radio(key="gestion.widgets.modebar.agenda.label").set_value("Detalle")
    at.run()
    _assert_no_exception(at, "agenda mode guard")
    assert at.radio(key="gestion.widgets.modebar.agenda.label").value == "Listado"

    at.button(key="workspace.nav.finanzas").click()
    at.run()
    _assert_no_exception(at, "finanzas route")
    at.radio(key="gestion.widgets.modebar.finanzas.label").set_value("Editar")
    at.run()
    _assert_no_exception(at, "finanzas mode guard")
    assert at.radio(key="gestion.widgets.modebar.finanzas.label").value == "Listado"
