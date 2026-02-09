#!/usr/bin/env python3
"""
Contrato de entorno reproducible para SistemaLegal (DB-first).

Uso:
  python db/env_contract.py --profile app
  python db/env_contract.py --profile db_suite
  python db/env_contract.py --profile release_gate_full
  python db/env_contract.py --profile release_gate_read_only
  python db/env_contract.py --profile daily_ops
  python db/env_contract.py --profile backup_restore_drill
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from db.health import parse_database_url
from db.test_env import (
    TEST_DATABASE_URL_ENV,
    RUNTIME_DATABASE_URL_ENV,
    RUNTIME_REFERENCE_ENV,
    mask_dsn,
    resolve_test_database_url_from_env,
)
from db.security_baseline import (
    SECURITY_GATE_MODE_ENV,
    SECURITY_MODE_OFF,
    SECURITY_MODE_WARN,
    SECURITY_MODE_ENFORCE,
    DB_APP_ROLE_ENV,
    DB_TEST_ROLE_ENV,
    SECURITY_REQUIRE_TEST_ROLE_SPLIT_ENV,
)
from db.performance_capacity import (
    PERFORMANCE_GATE_MODE_ENV,
    PERFORMANCE_MODE_OFF,
    PERFORMANCE_MODE_WARN,
    PERFORMANCE_MODE_ENFORCE,
    PERFORMANCE_MAX_SELECT1_MS_ENV,
    PERFORMANCE_MAX_CORE_COUNTS_MS_ENV,
    PERFORMANCE_MAX_RECENT_DOCS_MS_ENV,
    PERFORMANCE_MAX_RECENT_CASES_MS_ENV,
    PERFORMANCE_MAX_DOCS_PER_CASE_ENV,
    PERFORMANCE_MAX_AUDIT_ROWS_ENV,
    DEFAULT_MAX_SELECT1_MS,
    DEFAULT_MAX_CORE_COUNTS_MS,
    DEFAULT_MAX_RECENT_DOCS_MS,
    DEFAULT_MAX_RECENT_CASES_MS,
    DEFAULT_MAX_DOCS_PER_CASE,
    DEFAULT_MAX_AUDIT_ROWS,
)

RELEASE_GATE_MODE_ENV = "VG_RELEASE_GATE_MODE"
SUITE_TIMEOUT_ENV = "VG_SUITE_TIMEOUT_SEC"
STEP_TIMEOUT_ENV = "VG_STEP_TIMEOUT_SEC"
QUALITY_GATE_KPI_MODE_ENV = "VG_QUALITY_GATE_KPI_MODE"
QUALITY_GATE_KPI_MIN_CASES_ENV = "VG_QUALITY_GATE_KPI_MIN_CASES"
BACKUP_DIR_ENV = "VG_BACKUP_DIR"
BACKUP_DRILL_SCHEMA_PREFIX_ENV = "VG_BACKUP_DRILL_SCHEMA_PREFIX"

PROFILE_APP = "app"
PROFILE_DB_SUITE = "db_suite"
PROFILE_RELEASE_GATE_FULL = "release_gate_full"
PROFILE_RELEASE_GATE_READ_ONLY = "release_gate_read_only"
PROFILE_DAILY_OPS = "daily_ops"
PROFILE_BACKUP_RESTORE_DRILL = "backup_restore_drill"

VALID_PROFILES = {
    PROFILE_APP,
    PROFILE_DB_SUITE,
    PROFILE_RELEASE_GATE_FULL,
    PROFILE_RELEASE_GATE_READ_ONLY,
    PROFILE_DAILY_OPS,
    PROFILE_BACKUP_RESTORE_DRILL,
}

VALID_RELEASE_MODES = {"read_only", "full"}
VALID_KPI_GATE_MODES = {"off", "warn", "enforce"}
VALID_SECURITY_GATE_MODES = {SECURITY_MODE_OFF, SECURITY_MODE_WARN, SECURITY_MODE_ENFORCE}
VALID_PERFORMANCE_GATE_MODES = {
    PERFORMANCE_MODE_OFF,
    PERFORMANCE_MODE_WARN,
    PERFORMANCE_MODE_ENFORCE,
}
_ROLE_NAME_RE = re.compile(r"^[a-z_][a-z0-9_]{0,62}$")
_SCHEMA_PREFIX_RE = re.compile(r"^[a-z_][a-z0-9_]{0,62}$")


class C:
    OK = "\033[92m"
    FAIL = "\033[91m"
    WARN = "\033[93m"
    INFO = "\033[94m"
    RESET = "\033[0m"
    BOLD = "\033[1m"


def _emit(msg: str = "") -> None:
    print(msg, flush=True)


def _ok(msg: str) -> None:
    _emit(f"{C.OK}[OK] {msg}{C.RESET}")


def _fail(msg: str) -> None:
    _emit(f"{C.FAIL}[FAIL] {msg}{C.RESET}")


def _warn(msg: str) -> None:
    _emit(f"{C.WARN}[WARN] {msg}{C.RESET}")


def _info(msg: str) -> None:
    _emit(f"{C.INFO}[INFO] {msg}{C.RESET}")


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Valida contrato de entorno DB-first")
    parser.add_argument(
        "--profile",
        default=PROFILE_DAILY_OPS,
        choices=sorted(VALID_PROFILES),
        help="Perfil de validacion de entorno.",
    )
    return parser.parse_args(argv)


def _extract_db_name(dsn: str) -> str:
    normalized = parse_database_url(dsn)
    if not normalized:
        return ""
    parsed = urlparse(normalized)
    path = (parsed.path or "").strip()
    if path.startswith("/"):
        path = path[1:]
    return path.split("/", 1)[0] if path else ""


def _require_runtime_database_url(env: dict[str, str], errors: list[str]) -> str:
    runtime_dsn = parse_database_url(str(env.get(RUNTIME_DATABASE_URL_ENV, "")).strip())
    if not runtime_dsn:
        errors.append(f"{RUNTIME_DATABASE_URL_ENV} no esta configurada.")
        return ""
    db_name = _extract_db_name(runtime_dsn)
    _ok(f"{RUNTIME_DATABASE_URL_ENV} presente: {mask_dsn(runtime_dsn)}")
    if db_name:
        _info(f"DB runtime: {db_name}")
    return runtime_dsn


def _resolve_release_mode(env: dict[str, str], errors: list[str]) -> str:
    raw = str(env.get(RELEASE_GATE_MODE_ENV, "full")).strip().lower() or "full"
    if raw not in VALID_RELEASE_MODES:
        errors.append(
            f"{RELEASE_GATE_MODE_ENV} invalida ({raw!r}). "
            "Use 'read_only' o 'full'."
        )
        return ""
    _ok(f"{RELEASE_GATE_MODE_ENV}={raw}")
    return raw


def _validate_positive_int_env(
    env: dict[str, str],
    name: str,
    default_value: int,
    errors: list[str],
) -> None:
    raw = str(env.get(name, "")).strip()
    if not raw:
        _info(f"{name} no definida. Se usa default={int(default_value)}.")
        return
    try:
        value = int(raw)
    except ValueError:
        errors.append(f"{name} debe ser entero positivo (valor={raw!r}).")
        return
    if value <= 0:
        errors.append(f"{name} debe ser > 0 (valor={value}).")
        return
    _ok(f"{name}={value}")


def _validate_choice_env(
    env: dict[str, str],
    name: str,
    valid_values: set[str],
    default_value: str,
    errors: list[str],
) -> str:
    raw = str(env.get(name, default_value)).strip().lower()
    if not raw:
        raw = str(default_value).strip().lower()
    if raw not in valid_values:
        options = ", ".join(sorted(valid_values))
        errors.append(f"{name} invalida ({raw!r}). Valores validos: {options}.")
        return ""
    _ok(f"{name}={raw}")
    return raw


def _validate_role_name_env(
    env: dict[str, str],
    name: str,
    errors: list[str],
) -> str:
    raw = str(env.get(name, "")).strip()
    if not raw:
        _info(f"{name} no definida. Se omite validacion de rol esperado.")
        return ""
    if not _ROLE_NAME_RE.match(raw):
        errors.append(
            f"{name} invalida ({raw!r}). "
            "Use formato PostgreSQL simple: [a-z_][a-z0-9_]{0,62}."
        )
        return ""
    _ok(f"{name}={raw}")
    return raw


def _validate_bool_toggle_env(
    env: dict[str, str],
    name: str,
    default_value: bool,
    errors: list[str],
) -> bool:
    raw = str(env.get(name, "")).strip().lower()
    if not raw:
        _info(f"{name} no definida. Se usa default={1 if default_value else 0}.")
        return bool(default_value)
    if raw in {"1", "true", "yes", "on"}:
        _ok(f"{name}=1")
        return True
    if raw in {"0", "false", "no", "off"}:
        _ok(f"{name}=0")
        return False
    errors.append(
        f"{name} invalida ({raw!r}). Use 0|1|true|false|yes|no|on|off."
    )
    return bool(default_value)


def _validate_backup_schema_prefix_env(
    env: dict[str, str],
    errors: list[str],
) -> str:
    raw = str(env.get(BACKUP_DRILL_SCHEMA_PREFIX_ENV, "")).strip().lower()
    if not raw:
        _info(f"{BACKUP_DRILL_SCHEMA_PREFIX_ENV} no definida. Se usa default=restore_drill.")
        return ""
    if not _SCHEMA_PREFIX_RE.match(raw):
        errors.append(
            f"{BACKUP_DRILL_SCHEMA_PREFIX_ENV} invalida ({raw!r}). "
            "Use formato PostgreSQL simple: [a-z_][a-z0-9_]{0,62}."
        )
        return ""
    _ok(f"{BACKUP_DRILL_SCHEMA_PREFIX_ENV}={raw}")
    return raw


def _validate_backup_dir_env(env: dict[str, str]) -> str:
    raw = str(env.get(BACKUP_DIR_ENV, "")).strip()
    if not raw:
        _info(f"{BACKUP_DIR_ENV} no definida. Se usa default interno del script.")
        return ""
    _ok(f"{BACKUP_DIR_ENV}={raw}")
    return raw


def _validate_performance_gate_env(env: dict[str, str], errors: list[str]) -> None:
    _validate_choice_env(
        env,
        PERFORMANCE_GATE_MODE_ENV,
        VALID_PERFORMANCE_GATE_MODES,
        PERFORMANCE_MODE_WARN,
        errors,
    )
    _validate_positive_int_env(env, PERFORMANCE_MAX_SELECT1_MS_ENV, DEFAULT_MAX_SELECT1_MS, errors)
    _validate_positive_int_env(env, PERFORMANCE_MAX_CORE_COUNTS_MS_ENV, DEFAULT_MAX_CORE_COUNTS_MS, errors)
    _validate_positive_int_env(env, PERFORMANCE_MAX_RECENT_DOCS_MS_ENV, DEFAULT_MAX_RECENT_DOCS_MS, errors)
    _validate_positive_int_env(env, PERFORMANCE_MAX_RECENT_CASES_MS_ENV, DEFAULT_MAX_RECENT_CASES_MS, errors)
    _validate_positive_int_env(env, PERFORMANCE_MAX_DOCS_PER_CASE_ENV, DEFAULT_MAX_DOCS_PER_CASE, errors)
    _validate_positive_int_env(env, PERFORMANCE_MAX_AUDIT_ROWS_ENV, DEFAULT_MAX_AUDIT_ROWS, errors)


def _require_isolated_test_database_env(env: dict[str, str], errors: list[str]) -> str:
    ok, normalized_test, reason = resolve_test_database_url_from_env(env)
    if not ok:
        errors.append(reason or f"{TEST_DATABASE_URL_ENV} invalida.")
        return ""
    test_name = _extract_db_name(normalized_test)
    _ok(f"{TEST_DATABASE_URL_ENV} valida: {mask_dsn(normalized_test)}")
    if test_name:
        _info(f"DB test: {test_name}")
    return normalized_test


def _validate_profile(profile: str, env: dict[str, str]) -> tuple[bool, list[str]]:
    errors: list[str] = []

    if profile == PROFILE_APP:
        _require_runtime_database_url(env, errors)
        return len(errors) == 0, errors

    if profile == PROFILE_DB_SUITE:
        _require_runtime_database_url(env, errors)
        _require_isolated_test_database_env(env, errors)
        return len(errors) == 0, errors

    if profile == PROFILE_RELEASE_GATE_FULL:
        _require_isolated_test_database_env(env, errors)
        _validate_choice_env(
            env,
            QUALITY_GATE_KPI_MODE_ENV,
            VALID_KPI_GATE_MODES,
            "warn",
            errors,
        )
        _validate_choice_env(
            env,
            SECURITY_GATE_MODE_ENV,
            VALID_SECURITY_GATE_MODES,
            SECURITY_MODE_WARN,
            errors,
        )
        _validate_role_name_env(env, DB_APP_ROLE_ENV, errors)
        _validate_role_name_env(env, DB_TEST_ROLE_ENV, errors)
        _validate_bool_toggle_env(
            env,
            SECURITY_REQUIRE_TEST_ROLE_SPLIT_ENV,
            False,
            errors,
        )
        _validate_performance_gate_env(env, errors)
        _validate_positive_int_env(env, QUALITY_GATE_KPI_MIN_CASES_ENV, 1, errors)
        _validate_positive_int_env(env, SUITE_TIMEOUT_ENV, 900, errors)
        return len(errors) == 0, errors

    if profile == PROFILE_RELEASE_GATE_READ_ONLY:
        mode = _resolve_release_mode(env, errors)
        if mode and mode != "read_only":
            _warn(
                "Perfil release_gate_read_only usado con modo distinto a read_only. "
                "El gate permite override por CLI."
            )
        _validate_choice_env(
            env,
            QUALITY_GATE_KPI_MODE_ENV,
            VALID_KPI_GATE_MODES,
            "warn",
            errors,
        )
        _validate_choice_env(
            env,
            SECURITY_GATE_MODE_ENV,
            VALID_SECURITY_GATE_MODES,
            SECURITY_MODE_WARN,
            errors,
        )
        _validate_role_name_env(env, DB_APP_ROLE_ENV, errors)
        _validate_bool_toggle_env(
            env,
            SECURITY_REQUIRE_TEST_ROLE_SPLIT_ENV,
            False,
            errors,
        )
        _validate_performance_gate_env(env, errors)
        _validate_positive_int_env(env, QUALITY_GATE_KPI_MIN_CASES_ENV, 1, errors)
        _validate_positive_int_env(env, SUITE_TIMEOUT_ENV, 900, errors)
        return len(errors) == 0, errors

    if profile == PROFILE_DAILY_OPS:
        _require_runtime_database_url(env, errors)
        mode = _resolve_release_mode(env, errors)
        if mode == "full":
            _require_isolated_test_database_env(env, errors)
            _validate_positive_int_env(env, SUITE_TIMEOUT_ENV, 900, errors)
        else:
            _info("Modo read_only: no se exige VG_TEST_DATABASE_URL para daily_ops.")
        _validate_choice_env(
            env,
            QUALITY_GATE_KPI_MODE_ENV,
            VALID_KPI_GATE_MODES,
            "warn",
            errors,
        )
        _validate_choice_env(
            env,
            SECURITY_GATE_MODE_ENV,
            VALID_SECURITY_GATE_MODES,
            SECURITY_MODE_WARN,
            errors,
        )
        _validate_role_name_env(env, DB_APP_ROLE_ENV, errors)
        _validate_role_name_env(env, DB_TEST_ROLE_ENV, errors)
        _validate_bool_toggle_env(
            env,
            SECURITY_REQUIRE_TEST_ROLE_SPLIT_ENV,
            False,
            errors,
        )
        _validate_performance_gate_env(env, errors)
        _validate_positive_int_env(env, QUALITY_GATE_KPI_MIN_CASES_ENV, 1, errors)
        _validate_positive_int_env(env, STEP_TIMEOUT_ENV, 1200, errors)
        return len(errors) == 0, errors

    if profile == PROFILE_BACKUP_RESTORE_DRILL:
        _require_runtime_database_url(env, errors)
        _require_isolated_test_database_env(env, errors)
        _validate_backup_schema_prefix_env(env, errors)
        _validate_backup_dir_env(env)
        return len(errors) == 0, errors

    errors.append(f"Perfil no soportado: {profile!r}")
    return False, errors


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    env = os.environ.copy()

    _emit(f"\n{C.BOLD}ENV CONTRACT CHECK{C.RESET}")
    _emit(f"Profile: {args.profile}")
    if RUNTIME_REFERENCE_ENV in env:
        _info(
            f"{RUNTIME_REFERENCE_ENV} detectada (mask): "
            f"{mask_dsn(str(env.get(RUNTIME_REFERENCE_ENV, '')).strip())}"
        )

    ok, errors = _validate_profile(args.profile, env)
    if ok:
        _emit(f"\n{C.OK}{C.BOLD}ENV CONTRACT: PASS{C.RESET}")
        return 0

    for err in errors:
        _fail(err)
    _emit(f"\n{C.FAIL}{C.BOLD}ENV CONTRACT: FAIL{C.RESET}")
    return 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        _fail("Interrumpido por usuario.")
        raise SystemExit(130)
    except SystemExit:
        raise
    except Exception as exc:  # pragma: no cover - fallback defensivo
        _fail(f"Error inesperado: {type(exc).__name__}: {exc}")
        raise SystemExit(1)
