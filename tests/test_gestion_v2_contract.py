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


def test_gestion_v2_renders_core_controls(monkeypatch) -> None:
    at = _boot_app(monkeypatch)
    _assert_no_exception(at, "initial render")

    at.button(key="workspace.nav.gestion").click()
    at.run()
    _assert_no_exception(at, "gestion v2 route")

    assert at.radio(key="gestion.widgets.tabbar.label")
    assert at.radio(key="gestion.widgets.modebar.casos.label")
    assert at.button(key="gestion.context.casos.go_agenda")
    assert at.button(key="gestion.context.casos.go_dashboard")

