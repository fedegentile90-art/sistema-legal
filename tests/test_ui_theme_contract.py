from pathlib import Path

from streamlit.testing.v1 import AppTest

import ui


ROOT = Path(__file__).resolve().parent.parent


def test_tokens_have_dark_light_palettes() -> None:
    colors = ui.TOKENS.get("colors", {})
    assert "dark" in colors
    assert "light" in colors
    required = {
        "bg_app",
        "bg_sidebar",
        "bg_card",
        "bg_card_hover",
        "border",
        "text_main",
        "text_muted",
        "primary",
        "primary_hover",
        "success",
        "warning",
        "danger",
        "badge_bg",
        "bg_glow_1",
        "bg_glow_2",
    }
    assert required.issubset(set(colors["dark"].keys()))
    assert required.issubset(set(colors["light"].keys()))


def test_theme_selector_switches_to_light(monkeypatch) -> None:
    monkeypatch.setenv("VG_AUTH_REQUIRED", "0")
    monkeypatch.setenv("VG_RBAC_STRICT", "0")
    monkeypatch.setenv("VG_EXPORT_STRICT", "0")

    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=120)
    at.run()
    assert len(at.exception) == 0

    selector = at.radio(key="stitch_theme_selector")
    selector.set_value("Claro")
    at.run()
    assert len(at.exception) == 0
    assert at.session_state.filtered_state.get("theme_mode") == "light"


def test_shell_classes_present_in_runtime_files() -> None:
    app_text = (ROOT / "app.py").read_text(encoding="utf-8", errors="replace")
    ui_text = (ROOT / "ui.py").read_text(encoding="utf-8", errors="replace")
    assert "vg-shell-header" in app_text
    assert "vg-workspace-title" in app_text
    assert "vg-shell-header" in ui_text
    assert "vg-sidebar-brand" in ui_text
