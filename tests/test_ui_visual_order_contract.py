from pathlib import Path

from streamlit.testing.v1 import AppTest


ROOT = Path(__file__).resolve().parent.parent


def _boot_app(monkeypatch) -> AppTest:
    monkeypatch.setenv("VG_AUTH_REQUIRED", "0")
    monkeypatch.setenv("VG_RBAC_STRICT", "0")
    monkeypatch.setenv("VG_EXPORT_STRICT", "0")
    monkeypatch.setenv("VG_UI_REVAMP_V2", "1")
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=120)
    at.run()
    assert len(at.exception) == 0
    return at


def _go_route(at: AppTest, route: str) -> None:
    if route == "Dashboard":
        at.run()
        assert len(at.exception) == 0
        return
    at.button(key=f"workspace.nav.{route.lower()}").click()
    at.run()
    assert len(at.exception) == 0


def _assert_order(at: AppTest, route: str) -> None:
    key = f"ui.block_order.{route.lower()}"
    seq = at.session_state.filtered_state.get(key)
    assert isinstance(seq, list)
    assert seq[:3] == ["summary", "actions", "work"]


def test_module_block_order_contract(monkeypatch) -> None:
    at = _boot_app(monkeypatch)

    for route in ("Dashboard", "Gestion", "Agenda", "Finanzas", "Auditoria", "Configuracion"):
        _go_route(at, route)
        _assert_order(at, route)
