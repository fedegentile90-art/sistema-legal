from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
MODULE_PATH = ROOT / "db" / "setup_test_db.py"


def _load_setup_module():
    spec = importlib.util.spec_from_file_location("setup_test_db_module", str(MODULE_PATH))
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_script_file_exists() -> None:
    assert MODULE_PATH.exists()


def test_derive_test_dsn_suffix() -> None:
    mod = _load_setup_module()
    runtime = "postgresql://postgres:secret@localhost:5432/sistemalegal"
    derived = mod._derive_test_dsn(runtime)
    assert derived.endswith("/sistemalegal_test")
    assert "postgres:secret@localhost:5432" in derived


def test_update_env_file_replaces_existing_key(tmp_path: Path) -> None:
    mod = _load_setup_module()
    env_file = tmp_path / ".env"
    env_file.write_text("DATABASE_URL=postgresql://runtime\nVG_TEST_DATABASE_URL=old\n", encoding="utf-8")

    mod._update_env_file(env_file, "VG_TEST_DATABASE_URL", "postgresql://new/test")
    text = env_file.read_text(encoding="utf-8")

    assert "VG_TEST_DATABASE_URL=postgresql://new/test" in text
    assert "VG_TEST_DATABASE_URL=old" not in text


def test_update_env_file_appends_key_if_missing(tmp_path: Path) -> None:
    mod = _load_setup_module()
    env_file = tmp_path / ".env"
    env_file.write_text("DATABASE_URL=postgresql://runtime\n", encoding="utf-8")

    mod._update_env_file(env_file, "VG_TEST_DATABASE_URL", "postgresql://new/test")
    lines = env_file.read_text(encoding="utf-8").splitlines()

    assert lines[-1] == "VG_TEST_DATABASE_URL=postgresql://new/test"


def test_main_fails_without_runtime_dsn(monkeypatch) -> None:
    mod = _load_setup_module()
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("VG_TEST_DATABASE_URL", raising=False)

    code = mod.main([])
    assert code == 2


def test_main_rejects_non_isolated_test_dsn(monkeypatch) -> None:
    mod = _load_setup_module()
    runtime = "postgresql://postgres:secret@localhost:5432/sistemalegal"
    monkeypatch.setenv("DATABASE_URL", runtime)
    monkeypatch.setenv("VG_TEST_DATABASE_URL", runtime)

    code = mod.main([])
    assert code == 2
