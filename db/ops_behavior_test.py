#!/usr/bin/env python3
"""
Ops Behavior Test - flujos operativos DB-first.

Objetivo:
- Validar comportamiento real de contratos operativos (no solo tokens estaticos).
- Cubrir rutas de corte de DailyOps y modos de release gate.

Uso:
  python db/ops_behavior_test.py
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


class C:
    OK = "\033[92m"
    FAIL = "\033[91m"
    WARN = "\033[93m"
    INFO = "\033[94m"
    RESET = "\033[0m"
    BOLD = "\033[1m"


def ok(msg: str) -> None:
    print(f"{C.OK}[OK] {msg}{C.RESET}")


def fail(msg: str) -> None:
    print(f"{C.FAIL}[FAIL] {msg}{C.RESET}")


def info(msg: str) -> None:
    print(f"{C.INFO}[INFO] {msg}{C.RESET}")


def section(title: str) -> None:
    print(f"\n{C.BOLD}{'=' * 72}")
    print(f"  {title}")
    print(f"{'=' * 72}{C.RESET}")


def _run_python(args: list[str], env: dict[str, str], timeout: int = 180) -> subprocess.CompletedProcess:
    cmd = [sys.executable] + args
    return subprocess.run(
        cmd,
        cwd=str(ROOT),
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=max(1, int(timeout)),
    )


def _run_daily_ops(env: dict[str, str], timeout: int = 900) -> subprocess.CompletedProcess:
    cmd = [
        "powershell",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        "RUN_ERP.ps1",
        "-DailyOps",
    ]
    return subprocess.run(
        cmd,
        cwd=str(ROOT),
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=max(1, int(timeout)),
    )


def test_env_contract_rejects_invalid_mode() -> bool:
    section("1. env_contract rechaza VG_RELEASE_GATE_MODE invalido")
    env = os.environ.copy()
    if not str(env.get("DATABASE_URL", "")).strip():
        fail("DATABASE_URL no disponible para test operacional")
        return False
    env["VG_RELEASE_GATE_MODE"] = "invalid_mode"
    env.pop("VG_TEST_DATABASE_URL", None)

    proc = _run_python(["db/env_contract.py", "--profile", "daily_ops"], env=env, timeout=120)
    out = f"{proc.stdout}\n{proc.stderr}"
    if proc.returncode != 2:
        fail(f"env_contract returncode={proc.returncode} (esperado=2)")
        info(out[-1600:])
        return False
    if "VG_RELEASE_GATE_MODE invalida" not in out:
        fail("No se detecto mensaje de modo invalido")
        info(out[-1600:])
        return False
    ok("env_contract falla con modo invalido (returncode=2)")
    return True


def test_env_contract_read_only_without_test_dsn() -> bool:
    section("2. env_contract daily_ops read_only sin VG_TEST_DATABASE_URL")
    env = os.environ.copy()
    if not str(env.get("DATABASE_URL", "")).strip():
        fail("DATABASE_URL no disponible para test operacional")
        return False
    env["VG_RELEASE_GATE_MODE"] = "read_only"
    env.pop("VG_TEST_DATABASE_URL", None)

    proc = _run_python(["db/env_contract.py", "--profile", "daily_ops"], env=env, timeout=120)
    out = f"{proc.stdout}\n{proc.stderr}"
    if proc.returncode != 0:
        fail(f"env_contract returncode={proc.returncode} (esperado=0)")
        info(out[-1600:])
        return False
    if "ENV CONTRACT: PASS" not in out:
        fail("No se detecto PASS en env_contract read_only")
        info(out[-1600:])
        return False
    ok("env_contract read_only PASS sin VG_TEST_DATABASE_URL")
    return True


def test_dailyops_cuts_on_invalid_mode() -> bool:
    section("3. DailyOps normaliza modo invalido y continua en read_only")
    env = os.environ.copy()
    if not str(env.get("DATABASE_URL", "")).strip():
        fail("DATABASE_URL no disponible para test operacional")
        return False
    env["VG_RELEASE_GATE_MODE"] = "invalid_mode"
    env.pop("VG_TEST_DATABASE_URL", None)

    try:
        proc = _run_daily_ops(env=env, timeout=300)
    except Exception as exc:
        fail(f"No se pudo ejecutar RUN_ERP.ps1 -DailyOps: {exc}")
        return False

    out = f"{proc.stdout}\n{proc.stderr}"
    if proc.returncode != 0:
        fail(f"DailyOps returncode={proc.returncode} (esperado=0)")
        info(out[-2200:])
        return False
    if "Se fuerza 'read_only' para DailyOps." not in out:
        fail("No se detecto normalizacion de modo invalido -> read_only")
        info(out[-2200:])
        return False
    if "RELEASE QA GATE: PASS" not in out:
        fail("DailyOps normalizado no completo gate PASS")
        info(out[-2200:])
        return False
    ok("DailyOps normaliza modo invalido y completa flujo en read_only")
    return True


def test_dailyops_read_only_without_test_dsn_passes() -> bool:
    section("4. DailyOps read_only PASS sin VG_TEST_DATABASE_URL")
    env = os.environ.copy()
    if not str(env.get("DATABASE_URL", "")).strip():
        fail("DATABASE_URL no disponible para test operacional")
        return False
    env["VG_RELEASE_GATE_MODE"] = "read_only"
    env.pop("VG_TEST_DATABASE_URL", None)

    try:
        proc = _run_daily_ops(env=env, timeout=900)
    except Exception as exc:
        fail(f"No se pudo ejecutar RUN_ERP.ps1 -DailyOps: {exc}")
        return False

    out = f"{proc.stdout}\n{proc.stderr}"
    if proc.returncode != 0:
        fail(f"DailyOps returncode={proc.returncode} (esperado=0)")
        info(out[-2600:])
        return False
    if "RELEASE QA GATE: PASS" not in out:
        fail("DailyOps read_only no reporto gate PASS")
        info(out[-2600:])
        return False
    ok("DailyOps read_only pasa sin VG_TEST_DATABASE_URL")
    return True


def main() -> int:
    print(f"\n{C.BOLD}{'=' * 72}")
    print("  OPS BEHAVIOR TEST - SISTEMALEGAL")
    print(f"{'=' * 72}{C.RESET}")

    if sys.platform != "win32":
        fail("Suite operativa requiere Windows (RUN_ERP.ps1).")
        return 1

    tests = {
        "env_contract_invalid_mode": test_env_contract_rejects_invalid_mode(),
        "env_contract_read_only_without_test_dsn": test_env_contract_read_only_without_test_dsn(),
        "dailyops_cut_invalid_mode": test_dailyops_cuts_on_invalid_mode(),
        "dailyops_read_only_without_test_dsn": test_dailyops_read_only_without_test_dsn_passes(),
    }

    section("RESUMEN")
    total = len(tests)
    passed = sum(1 for v in tests.values() if v)
    for name, result in tests.items():
        status = f"{C.OK}PASS{C.RESET}" if result else f"{C.FAIL}FAIL{C.RESET}"
        print(f"  {name:40} [{status}]")

    print()
    if passed == total:
        print(f"{C.OK}{C.BOLD}=== OPS BEHAVIOR TEST PASS ({passed}/{total}) ==={C.RESET}")
        return 0
    print(f"{C.FAIL}{C.BOLD}=== OPS BEHAVIOR TEST FAIL ({passed}/{total}) ==={C.RESET}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
