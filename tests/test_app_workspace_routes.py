import os
from pathlib import Path

from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parent.parent


def _assert_no_exception(at: AppTest, context: str) -> None:
    if len(at.exception) > 0:
        raise AssertionError(f"{context}: {[e.value for e in at.exception]}")


def test_workspace_switcher_buttons_render(monkeypatch) -> None:
    monkeypatch.setenv("VG_AUTH_REQUIRED", "0")
    monkeypatch.setenv("VG_RBAC_STRICT", "0")
    monkeypatch.setenv("VG_EXPORT_STRICT", "0")

    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=120)
    at.run()
    _assert_no_exception(at, "initial render")

    for key in (
        "workspace.nav.dashboard",
        "workspace.nav.gestion",
        "workspace.nav.agenda",
        "workspace.nav.finanzas",
        "workspace.nav.auditoria",
        "workspace.nav.configuracion",
    ):
        at.button(key=key)


def test_workspace_switcher_navigates_to_auditoria_and_back(monkeypatch) -> None:
    monkeypatch.setenv("VG_AUTH_REQUIRED", "0")
    monkeypatch.setenv("VG_RBAC_STRICT", "0")
    monkeypatch.setenv("VG_EXPORT_STRICT", "0")

    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=120)
    at.run()
    _assert_no_exception(at, "initial render")

    at.button(key="workspace.nav.auditoria").click()
    at.run()
    _assert_no_exception(at, "go auditoria")
    assert at.session_state.filtered_state.get("nav_route") == "Auditoria"

    at.button(key="workspace.nav.dashboard").click()
    at.run()
    _assert_no_exception(at, "go dashboard")
    assert at.session_state.filtered_state.get("nav_route") == "Dashboard"
