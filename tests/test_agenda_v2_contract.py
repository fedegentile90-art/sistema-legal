from pathlib import Path

from streamlit.testing.v1 import AppTest


ROOT = Path(__file__).resolve().parent.parent


def _boot_app(monkeypatch) -> AppTest:
    monkeypatch.setenv("VG_AUTH_REQUIRED", "0")
    monkeypatch.setenv("VG_RBAC_STRICT", "0")
    monkeypatch.setenv("VG_EXPORT_STRICT", "0")
    monkeypatch.setenv("VG_GESTION_AGENDA_V2", "1")
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=120)
    at.run()
    return at


def _assert_no_exception(at: AppTest, context: str) -> None:
    if len(at.exception) > 0:
        raise AssertionError(f"{context}: {[e.value for e in at.exception]}")


def test_agenda_v2_renders_modebar_and_context_buttons(monkeypatch) -> None:
    at = _boot_app(monkeypatch)
    _assert_no_exception(at, "initial render")

    at.button(key="workspace.nav.agenda").click()
    at.run()
    _assert_no_exception(at, "agenda v2 route")

    assert at.radio(key="gestion.widgets.modebar.agenda.label")
    assert at.button(key="gestion.context.agenda.go_gestion")
    assert at.button(key="gestion.context.agenda.go_dashboard")

