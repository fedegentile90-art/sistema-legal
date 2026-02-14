from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def test_run_erp_ps1_has_port_fallback_and_streamlit_probe() -> None:
    text = (ROOT / "RUN_ERP.ps1").read_text(encoding="utf-8", errors="replace")
    assert "function Test-StreamlitServer" in text
    assert "function Get-FreePort" in text
    assert 'Get-PositiveIntEnv -Name "VG_APP_PORT" -DefaultValue $DefaultPort' in text
    assert "Puerto {0} ocupado por otro proceso. Se usara puerto alternativo {1}." in text
    assert "--server.port=$selectedPort" in text


def test_run_erp_ps1_normalizes_dailyops_release_mode() -> None:
    text = (ROOT / "RUN_ERP.ps1").read_text(encoding="utf-8", errors="replace")
    assert '$ReleaseModeEnvName = "VG_RELEASE_GATE_MODE"' in text
    assert "Se fuerza '{2}' para DailyOps." in text
    assert "Release gate mode efectivo: {0} (env {1})" in text


def test_run_erp_ps1_loads_dotenv_for_launcher_and_ops() -> None:
    text = (ROOT / "RUN_ERP.ps1").read_text(encoding="utf-8", errors="replace")
    assert '$DotEnvAutoLoadEnvName = "VG_DOTENV_AUTOLOAD"' in text
    assert "function Initialize-EnvFromDotEnv" in text
    assert "Variables cargadas desde .env" in text
    assert "Auto-load .env desactivado" in text


def test_run_erp_cmd_delegates_launcher_to_ps1() -> None:
    text = (ROOT / "RUN_ERP.cmd").read_text(encoding="utf-8", errors="replace")
    assert 'powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0RUN_ERP.ps1"' in text
    assert 'if /I "%~1"=="ops" goto run_ops' in text
    assert 'powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0RUN_ERP.ps1" -DailyOps' in text


def test_audit_uses_timezone_aware_utc_helper() -> None:
    text = (ROOT / "audit.py").read_text(encoding="utf-8", errors="replace")
    assert "def _utc_now_iso()" in text
    assert "datetime.utcnow()" not in text


def test_desktop_shortcut_installers_exist_and_point_to_launcher() -> None:
    ps1 = (ROOT / "CREATE_DESKTOP_SHORTCUT.ps1").read_text(encoding="utf-8", errors="replace")
    cmd = (ROOT / "CREATE_DESKTOP_SHORTCUT.cmd").read_text(encoding="utf-8", errors="replace")

    assert 'param(' in ps1
    assert 'RUN_ERP.cmd' in ps1
    assert 'WScript.Shell' in ps1
    assert 'CreateShortcut' in ps1
    assert 'CREATED::' in ps1

    assert 'CREATE_DESKTOP_SHORTCUT.ps1' in cmd
    assert 'powershell -NoProfile -ExecutionPolicy Bypass -File' in cmd
