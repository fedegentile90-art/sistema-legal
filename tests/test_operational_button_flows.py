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


def test_gestion_context_navigation_buttons_work(monkeypatch) -> None:
    at = _boot_app(monkeypatch)
    _assert_no_exception(at, "initial render")

    at.button(key="workspace.nav.gestion").click()
    at.run()
    _assert_no_exception(at, "gestion route")

    assert at.button(key="gestion.context.casos.go_agenda")
    at.button(key="gestion.context.casos.go_agenda").click()
    at.run()
    _assert_no_exception(at, "gestion -> agenda")
    assert at.session_state.filtered_state.get("nav_route") == "Agenda"

    assert at.button(key="gestion.context.agenda.go_gestion")
    at.button(key="gestion.context.agenda.go_gestion").click()
    at.run()
    _assert_no_exception(at, "agenda -> gestion")
    assert at.session_state.filtered_state.get("nav_route") == "Gestion"


def test_auditoria_navigation_buttons_work(monkeypatch) -> None:
    at = _boot_app(monkeypatch)
    _assert_no_exception(at, "initial render")

    at.button(key="workspace.nav.auditoria").click()
    at.run()
    _assert_no_exception(at, "auditoria route")

    assert at.button(key="audit.nav.agenda")
    assert at.button(key="audit.nav.configuracion")

    at.button(key="audit.nav.agenda").click()
    at.run()
    _assert_no_exception(at, "auditoria -> agenda")
    assert at.session_state.filtered_state.get("nav_route") == "Agenda"

    at.button(key="workspace.nav.auditoria").click()
    at.run()
    _assert_no_exception(at, "back to auditoria")

    at.button(key="audit.nav.configuracion").click()
    at.run()
    _assert_no_exception(at, "auditoria -> configuracion")
    assert at.session_state.filtered_state.get("nav_route") == "Configuracion"


def test_configuracion_quick_navigation_buttons_work(monkeypatch) -> None:
    at = _boot_app(monkeypatch)
    _assert_no_exception(at, "initial render")

    at.button(key="workspace.nav.configuracion").click()
    at.run()
    _assert_no_exception(at, "config route")

    for key in (
        "config.quick.nav.dashboard",
        "config.quick.nav.gestion",
        "config.quick.nav.agenda",
        "config.quick.nav.finanzas",
        "config.quick.nav.auditoria",
    ):
        assert at.button(key=key)

    at.button(key="config.quick.nav.agenda").click()
    at.run()
    _assert_no_exception(at, "config -> agenda")
    assert at.session_state.filtered_state.get("nav_route") == "Agenda"
