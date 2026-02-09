"""
Contrato de aislamiento para suites DB.

Objetivo:
- Las suites DB deben usar una base dedicada de test.
- Nunca deben reutilizar implicitamente la DB operativa.
"""

from __future__ import annotations

import os
import re
from urllib.parse import urlparse

from db.health import parse_database_url


TEST_DATABASE_URL_ENV = "VG_TEST_DATABASE_URL"
RUNTIME_DATABASE_URL_ENV = "DATABASE_URL"
RUNTIME_REFERENCE_ENV = "VG_RUNTIME_DATABASE_URL"

_DBNAME_ISOLATED_RE = re.compile(r"(?:^|[_-])(test|tests|qa|ci|sandbox)(?:$|[_-])", re.IGNORECASE)


def mask_dsn(dsn: str) -> str:
    value = (dsn or "").strip()
    if not value:
        return ""
    parsed = urlparse(value)
    if "@" not in parsed.netloc:
        return value
    auth, host = parsed.netloc.rsplit("@", 1)
    if ":" not in auth:
        return value
    user = auth.split(":", 1)[0]
    masked_netloc = f"{user}:***@{host}"
    return parsed._replace(netloc=masked_netloc).geturl()


def extract_database_name(dsn: str) -> str:
    value = parse_database_url(dsn)
    if not value:
        return ""
    parsed = urlparse(value)
    path = (parsed.path or "").strip()
    if path.startswith("/"):
        path = path[1:]
    if "/" in path:
        path = path.split("/", 1)[0]
    return path


def validate_isolated_test_database_url(
    test_dsn: str,
    runtime_reference_dsn: str = "",
    runtime_source_label: str = RUNTIME_DATABASE_URL_ENV,
) -> tuple[bool, str, str]:
    normalized_test = parse_database_url(test_dsn)
    if not normalized_test:
        reason = (
            f"{TEST_DATABASE_URL_ENV} no esta configurada. "
            f"Debe apuntar a una DB de pruebas dedicada."
        )
        return False, "", reason

    db_name = extract_database_name(normalized_test)
    if not db_name:
        reason = f"{TEST_DATABASE_URL_ENV} no incluye nombre de base de datos."
        return False, "", reason
    if not _DBNAME_ISOLATED_RE.search(db_name):
        reason = (
            f"{TEST_DATABASE_URL_ENV} apunta a DB no aislada ({db_name!r}). "
            "Use un nombre con sufijo/prefijo test|qa|ci|sandbox."
        )
        return False, "", reason

    normalized_runtime = parse_database_url(runtime_reference_dsn)
    if normalized_runtime and normalized_runtime == normalized_test:
        reason = (
            f"{TEST_DATABASE_URL_ENV} coincide con {runtime_source_label}. "
            "Debe usar una DB distinta a la operativa."
        )
        return False, "", reason

    return True, normalized_test, ""


def resolve_test_database_url_from_env(
    env: dict[str, str] | None = None,
) -> tuple[bool, str, str]:
    env_map = env if env is not None else os.environ
    test_dsn = str(env_map.get(TEST_DATABASE_URL_ENV, "")).strip()

    runtime_source_label = RUNTIME_REFERENCE_ENV
    runtime_reference_dsn = str(env_map.get(RUNTIME_REFERENCE_ENV, "")).strip()
    if not runtime_reference_dsn:
        runtime_source_label = RUNTIME_DATABASE_URL_ENV
        runtime_reference_dsn = str(env_map.get(RUNTIME_DATABASE_URL_ENV, "")).strip()

    return validate_isolated_test_database_url(
        test_dsn=test_dsn,
        runtime_reference_dsn=runtime_reference_dsn,
        runtime_source_label=runtime_source_label,
    )


def require_isolated_test_database_env(sync_database_url: bool = True) -> tuple[bool, str]:
    ok, normalized_test, reason = resolve_test_database_url_from_env()
    if not ok:
        return False, reason
    if sync_database_url:
        os.environ[RUNTIME_DATABASE_URL_ENV] = normalized_test
    os.environ[TEST_DATABASE_URL_ENV] = normalized_test
    return True, normalized_test


def build_isolated_suite_env(base_env: dict[str, str] | None = None) -> tuple[bool, dict[str, str], str]:
    env = dict(base_env or os.environ)
    runtime_value = parse_database_url(str(env.get(RUNTIME_DATABASE_URL_ENV, "")).strip())
    if runtime_value:
        env[RUNTIME_REFERENCE_ENV] = runtime_value

    ok, normalized_test, reason = resolve_test_database_url_from_env(env)
    if not ok:
        return False, env, reason

    env[TEST_DATABASE_URL_ENV] = normalized_test
    env[RUNTIME_DATABASE_URL_ENV] = normalized_test
    return True, env, ""
