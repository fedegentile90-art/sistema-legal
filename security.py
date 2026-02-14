"""
Auth local + RBAC minimo para SistemaLegal (rollout gradual por flags).
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Set, Tuple

import streamlit as st

from db.health import parse_database_url

AUTH_REQUIRED_ENV = "VG_AUTH_REQUIRED"
RBAC_STRICT_ENV = "VG_RBAC_STRICT"
EXPORT_STRICT_ENV = "VG_EXPORT_STRICT"

AUTH_BOOTSTRAP_USER_ENV = "VG_AUTH_BOOTSTRAP_USER"
AUTH_BOOTSTRAP_PASSWORD_ENV = "VG_AUTH_BOOTSTRAP_PASSWORD"
AUTH_BOOTSTRAP_ROLE_ENV = "VG_AUTH_BOOTSTRAP_ROLE"
AUTH_PASSWORD_PEPPER_ENV = "VG_AUTH_PASSWORD_PEPPER"

AUTH_FALLBACK_USER_ENV = "VG_AUTH_FALLBACK_USER"
AUTH_FALLBACK_PASSWORD_ENV = "VG_AUTH_FALLBACK_PASSWORD"
AUTH_FALLBACK_ROLE_ENV = "VG_AUTH_FALLBACK_ROLE"

SESSION_USER_KEY = "auth.user"
SESSION_READY_KEY = "auth.backend.ready"
SESSION_REQUEST_ID_KEY = "auth.request_id"

logger = logging.getLogger(__name__)


ROLE_PERMISSIONS: Dict[str, Set[str]] = {
    "admin": {"*"},
    "abogado": {
        "dashboard:view",
        "gestion:view",
        "agenda:view",
        "finanzas:view",
        "auditoria:view",
        "configuracion:view",
        "cases:create",
        "cases:write",
        "finance:write",
        "exports:download",
    },
    "asistente": {
        "dashboard:view",
        "gestion:view",
        "agenda:view",
        "finanzas:view",
        "auditoria:view",
        "cases:write",
        "finance:write",
        "exports:download",
    },
    "auditor": {
        "dashboard:view",
        "auditoria:view",
        "exports:download",
    },
    "readonly": {
        "dashboard:view",
        "gestion:view",
        "agenda:view",
        "finanzas:view",
        "auditoria:view",
    },
    "system": {"*"},
}


ROUTE_PERMISSIONS = {
    "Dashboard": "dashboard:view",
    "Gestion": "gestion:view",
    "Agenda": "agenda:view",
    "Finanzas": "finanzas:view",
    "Auditoria": "auditoria:view",
    "Configuracion": "configuracion:view",
}


@dataclass
class UserIdentity:
    user_id: str
    username: str
    role: str
    display_name: str
    session_id: str = ""

    def to_session(self) -> Dict[str, str]:
        return {
            "user_id": self.user_id,
            "username": self.username,
            "role": self.role,
            "display_name": self.display_name,
            "session_id": self.session_id,
        }


def _env_bool(name: str, default: bool = False) -> bool:
    raw = str(os.environ.get(name, "")).strip().lower()
    if not raw:
        return bool(default)
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off"}:
        return False
    return bool(default)


def is_auth_required() -> bool:
    return _env_bool(AUTH_REQUIRED_ENV, default=False)


def is_rbac_strict() -> bool:
    return _env_bool(RBAC_STRICT_ENV, default=False)


def is_export_strict() -> bool:
    return _env_bool(EXPORT_STRICT_ENV, default=False)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _password_pepper() -> str:
    return str(os.environ.get(AUTH_PASSWORD_PEPPER_ENV, "sistemalegal-local-pepper"))


def hash_password(raw_password: str, username: str) -> str:
    """Hash PBKDF2 estable para auth local."""
    salt = f"sistemalegal:{username.lower()}:{_password_pepper()}".encode("utf-8")
    derived = hashlib.pbkdf2_hmac("sha256", str(raw_password).encode("utf-8"), salt, 150_000)
    return f"pbkdf2_sha256$150000${salt.decode('utf-8')}${derived.hex()}"


def verify_password(raw_password: str, username: str, stored_hash: str) -> bool:
    if not stored_hash:
        return False
    if "$" not in stored_hash:
        # Compatibilidad legado simple.
        return hmac.compare_digest(stored_hash, str(raw_password))
    try:
        algo, rounds, salt, expected = stored_hash.split("$", 3)
        if algo != "pbkdf2_sha256":
            return False
        derived = hashlib.pbkdf2_hmac(
            "sha256",
            str(raw_password).encode("utf-8"),
            salt.encode("utf-8"),
            int(rounds),
        )
        return hmac.compare_digest(derived.hex(), expected)
    except Exception:
        # Fallback por si hay hashes previos corruptos.
        return hmac.compare_digest(hash_password(raw_password, username), stored_hash)


def _get_connection():
    url = parse_database_url(os.environ.get("DATABASE_URL", ""))
    if not url:
        return None
    try:
        import psycopg2  # type: ignore
    except Exception:
        return None
    try:
        return psycopg2.connect(url, connect_timeout=3)
    except Exception as exc:
        logger.warning("auth db connection unavailable: %s", exc)
        return None


def _ensure_security_schema(conn: Any) -> None:
    statements = [
        """
        CREATE TABLE IF NOT EXISTS roles (
            id UUID PRIMARY KEY,
            name VARCHAR(80) UNIQUE NOT NULL,
            description TEXT,
            created_at TIMESTAMPTZ DEFAULT NOW()
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS permissions (
            id UUID PRIMARY KEY,
            code VARCHAR(120) UNIQUE NOT NULL,
            description TEXT,
            created_at TIMESTAMPTZ DEFAULT NOW()
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS users (
            id UUID PRIMARY KEY,
            username VARCHAR(120) UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            display_name VARCHAR(255),
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            last_login_at TIMESTAMPTZ,
            extra JSONB DEFAULT '{}',
            created_at TIMESTAMPTZ DEFAULT NOW(),
            updated_at TIMESTAMPTZ DEFAULT NOW()
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS user_roles (
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            role_id UUID NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            PRIMARY KEY (user_id, role_id)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS role_permissions (
            role_id UUID NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
            permission_id UUID NOT NULL REFERENCES permissions(id) ON DELETE CASCADE,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            PRIMARY KEY (role_id, permission_id)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS auth_sessions (
            id UUID PRIMARY KEY,
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            role VARCHAR(80) NOT NULL,
            ip_address INET,
            user_agent TEXT,
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            last_seen_at TIMESTAMPTZ DEFAULT NOW()
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_users_username ON users(username)",
        "CREATE INDEX IF NOT EXISTS idx_auth_sessions_user ON auth_sessions(user_id, created_at DESC)",
    ]
    with conn.cursor() as cur:
        for stmt in statements:
            cur.execute(stmt)


def _bootstrap_roles_permissions(conn: Any) -> None:
    all_permissions: Set[str] = set()
    for perms in ROLE_PERMISSIONS.values():
        for code in perms:
            if code != "*":
                all_permissions.add(code)

    with conn.cursor() as cur:
        role_ids: Dict[str, str] = {}
        for role in ROLE_PERMISSIONS.keys():
            cur.execute("SELECT id FROM roles WHERE name = %s", (role,))
            row = cur.fetchone()
            if row and row[0]:
                role_ids[role] = str(row[0])
            else:
                rid = str(uuid.uuid4())
                cur.execute(
                    "INSERT INTO roles (id, name, description) VALUES (%s, %s, %s)",
                    (rid, role, f"Rol local {role}"),
                )
                role_ids[role] = rid

        permission_ids: Dict[str, str] = {}
        for code in sorted(all_permissions):
            cur.execute("SELECT id FROM permissions WHERE code = %s", (code,))
            row = cur.fetchone()
            if row and row[0]:
                permission_ids[code] = str(row[0])
            else:
                pid = str(uuid.uuid4())
                cur.execute(
                    "INSERT INTO permissions (id, code, description) VALUES (%s, %s, %s)",
                    (pid, code, f"Permiso {code}"),
                )
                permission_ids[code] = pid

        for role, perms in ROLE_PERMISSIONS.items():
            role_id = role_ids.get(role)
            if not role_id:
                continue
            if "*" in perms:
                continue
            for perm in sorted(perms):
                perm_id = permission_ids.get(perm)
                if not perm_id:
                    continue
                cur.execute(
                    """
                    INSERT INTO role_permissions (role_id, permission_id)
                    VALUES (%s, %s)
                    ON CONFLICT DO NOTHING
                    """,
                    (role_id, perm_id),
                )


def _bootstrap_default_user(conn: Any) -> None:
    username = str(os.environ.get(AUTH_BOOTSTRAP_USER_ENV, "admin")).strip() or "admin"
    raw_password = str(os.environ.get(AUTH_BOOTSTRAP_PASSWORD_ENV, "admin-change-now")).strip() or "admin-change-now"
    role = str(os.environ.get(AUTH_BOOTSTRAP_ROLE_ENV, "admin")).strip().lower() or "admin"
    role = role if role in ROLE_PERMISSIONS else "admin"

    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM users WHERE is_active = TRUE")
        active_count = int((cur.fetchone() or [0])[0] or 0)
        if active_count > 0:
            return

        user_id = str(uuid.uuid4())
        role_id = None
        cur.execute("SELECT id FROM roles WHERE name = %s", (role,))
        row = cur.fetchone()
        if row and row[0]:
            role_id = str(row[0])
        if not role_id:
            role_id = str(uuid.uuid4())
            cur.execute(
                "INSERT INTO roles (id, name, description) VALUES (%s, %s, %s)",
                (role_id, role, f"Rol local {role}"),
            )

        cur.execute(
            """
            INSERT INTO users (id, username, password_hash, display_name, is_active, extra)
            VALUES (%s, %s, %s, %s, TRUE, %s::jsonb)
            """,
            (
                user_id,
                username.lower(),
                hash_password(raw_password, username),
                username,
                '{"bootstrap": true}',
            ),
        )
        cur.execute(
            "INSERT INTO user_roles (user_id, role_id) VALUES (%s, %s) ON CONFLICT DO NOTHING",
            (user_id, role_id),
        )
    logger.warning(
        "Auth bootstrap user created username=%s role=%s. Cambiar credenciales por variables seguras.",
        username,
        role,
    )


def prepare_auth_backend() -> None:
    if st.session_state.get(SESSION_READY_KEY):
        return
    conn = _get_connection()
    if conn is None:
        st.session_state[SESSION_READY_KEY] = True
        return
    try:
        with conn:
            _ensure_security_schema(conn)
            _bootstrap_roles_permissions(conn)
            _bootstrap_default_user(conn)
    except Exception as exc:
        logger.warning("auth backend bootstrap failed: %s", exc)
    finally:
        conn.close()
        st.session_state[SESSION_READY_KEY] = True


def _fallback_auth(username: str, password: str) -> Optional[UserIdentity]:
    fallback_user = str(os.environ.get(AUTH_FALLBACK_USER_ENV, "admin")).strip().lower()
    fallback_password = str(os.environ.get(AUTH_FALLBACK_PASSWORD_ENV, "admin-change-now"))
    fallback_role = str(os.environ.get(AUTH_FALLBACK_ROLE_ENV, "admin")).strip().lower() or "admin"
    if username.strip().lower() != fallback_user:
        return None
    if password != fallback_password:
        return None
    return UserIdentity(
        user_id=f"fallback-{fallback_user}",
        username=fallback_user,
        role=fallback_role if fallback_role in ROLE_PERMISSIONS else "admin",
        display_name=fallback_user,
    )


def authenticate_local_user(username: str, password: str) -> Tuple[Optional[UserIdentity], str]:
    user_norm = str(username or "").strip().lower()
    if not user_norm or not password:
        return None, "Usuario y contraseña son obligatorios."

    conn = _get_connection()
    if conn is None:
        fallback = _fallback_auth(user_norm, password)
        if fallback is None:
            return None, "Credenciales inválidas."
        return fallback, ""

    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT u.id, u.username, u.password_hash, COALESCE(u.display_name, u.username), u.is_active
                    FROM users u
                    WHERE lower(u.username) = %s
                    LIMIT 1
                    """,
                    (user_norm,),
                )
                row = cur.fetchone()
                if not row:
                    return None, "Credenciales inválidas."
                user_id, db_username, password_hash, display_name, is_active = row
                if not bool(is_active):
                    return None, "Usuario inactivo."
                if not verify_password(password, str(db_username), str(password_hash or "")):
                    return None, "Credenciales inválidas."

                cur.execute(
                    """
                    SELECT r.name
                    FROM roles r
                    JOIN user_roles ur ON ur.role_id = r.id
                    WHERE ur.user_id = %s
                    ORDER BY CASE r.name
                        WHEN 'admin' THEN 0
                        WHEN 'abogado' THEN 1
                        WHEN 'asistente' THEN 2
                        WHEN 'auditor' THEN 3
                        ELSE 99
                    END ASC, r.name ASC
                    LIMIT 1
                    """,
                    (user_id,),
                )
                role_row = cur.fetchone()
                role = str((role_row or ["readonly"])[0] or "readonly").lower()
                if role not in ROLE_PERMISSIONS:
                    role = "readonly"

                session_id = str(uuid.uuid4())
                cur.execute(
                    """
                    INSERT INTO auth_sessions (id, user_id, role, user_agent)
                    VALUES (%s, %s, %s, %s)
                    """,
                    (session_id, user_id, role, "streamlit"),
                )
                cur.execute(
                    "UPDATE users SET last_login_at = NOW() WHERE id = %s",
                    (user_id,),
                )
                identity = UserIdentity(
                    user_id=str(user_id),
                    username=str(db_username),
                    role=role,
                    display_name=str(display_name),
                    session_id=session_id,
                )
                return identity, ""
    except Exception as exc:
        logger.warning("auth query failed: %s", exc)
        fallback = _fallback_auth(user_norm, password)
        if fallback is None:
            return None, "No se pudo validar credenciales."
        return fallback, ""
    finally:
        conn.close()


def _system_identity() -> UserIdentity:
    role = str(os.environ.get("VG_ACTOR_ROLE", "system")).strip().lower() or "system"
    if role not in ROLE_PERMISSIONS:
        role = "system"
    return UserIdentity(
        user_id=str(os.environ.get("VG_ACTOR_USER_ID", "system")),
        username=str(os.environ.get("VG_ACTOR_USER_NAME", "system")),
        role=role,
        display_name=str(os.environ.get("VG_ACTOR_USER_NAME", "System")),
        session_id="",
    )


def current_user() -> UserIdentity:
    raw = st.session_state.get(SESSION_USER_KEY)
    if isinstance(raw, dict):
        return UserIdentity(
            user_id=str(raw.get("user_id", "")),
            username=str(raw.get("username", "")),
            role=str(raw.get("role", "readonly")).lower(),
            display_name=str(raw.get("display_name", raw.get("username", ""))),
            session_id=str(raw.get("session_id", "")),
        )
    if not is_auth_required():
        identity = _system_identity()
        st.session_state[SESSION_USER_KEY] = identity.to_session()
        return identity
    return UserIdentity("", "", "readonly", "")


def _normalize_ui_preferences(raw: Any) -> Dict[str, str]:
    prefs: Dict[str, str] = {}
    if not isinstance(raw, dict):
        return prefs
    theme_mode = str(raw.get("theme_mode", "")).strip().lower()
    density_mode = str(raw.get("density_mode", "")).strip().lower()
    if theme_mode in {"dark", "light"}:
        prefs["theme_mode"] = theme_mode
    if density_mode in {"compact", "balanced", "wide"}:
        prefs["density_mode"] = density_mode
    return prefs


def load_user_ui_preferences(user_id: str) -> Dict[str, str]:
    """
    Carga preferencias de UI persistidas por usuario desde users.extra.
    Formato almacenado: extra.ui_preferences = {theme_mode, density_mode}.
    """
    target_user = str(user_id or "").strip()
    if not target_user:
        return {}
    if target_user.lower() == "system":
        return {}
    conn = _get_connection()
    if conn is None:
        return {}
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT extra FROM users WHERE id = %s LIMIT 1",
                    (target_user,),
                )
                row = cur.fetchone()
                if not row:
                    return {}
                extra = row[0]
                if isinstance(extra, str):
                    try:
                        extra = json.loads(extra)
                    except Exception:
                        extra = {}
                if not isinstance(extra, dict):
                    return {}
                ui_prefs = extra.get("ui_preferences", {})
                return _normalize_ui_preferences(ui_prefs)
    except Exception as exc:
        logger.warning("load user ui preferences failed user_id=%s err=%s", target_user, exc)
        return {}
    finally:
        conn.close()


def save_user_ui_preferences(user_id: str, prefs: Dict[str, Any]) -> bool:
    """
    Persiste preferencias de UI por usuario en users.extra.ui_preferences.
    Retorna True solo cuando la actualización queda escrita.
    """
    target_user = str(user_id or "").strip()
    if not target_user:
        return False
    if target_user.lower() == "system":
        return False
    normalized = _normalize_ui_preferences(dict(prefs or {}))
    if not normalized:
        return False
    conn = _get_connection()
    if conn is None:
        return False
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT extra FROM users WHERE id = %s LIMIT 1",
                    (target_user,),
                )
                row = cur.fetchone()
                if not row:
                    return False
                extra = row[0]
                if isinstance(extra, str):
                    try:
                        extra = json.loads(extra)
                    except Exception:
                        extra = {}
                if not isinstance(extra, dict):
                    extra = {}
                current = extra.get("ui_preferences", {})
                if not isinstance(current, dict):
                    current = {}
                current.update(normalized)
                extra["ui_preferences"] = current
                payload = json.dumps(extra, ensure_ascii=False)
                cur.execute(
                    "UPDATE users SET extra = %s::jsonb, updated_at = NOW() WHERE id = %s",
                    (payload, target_user),
                )
                return cur.rowcount > 0
    except Exception as exc:
        logger.warning("save user ui preferences failed user_id=%s err=%s", target_user, exc)
        return False
    finally:
        conn.close()


def logout_current_user() -> None:
    st.session_state.pop(SESSION_USER_KEY, None)


def has_permission(permission: str, user: Optional[UserIdentity] = None) -> bool:
    if not permission:
        return True
    # Rollout gradual: modo no estricto permite continuidad.
    if not is_rbac_strict():
        return True
    target = user or current_user()
    role = str(target.role or "readonly").lower()
    allowed = ROLE_PERMISSIONS.get(role, set())
    if "*" in allowed:
        return True
    return permission in allowed


def can_access_route(route: str) -> bool:
    perm = ROUTE_PERMISSIONS.get(str(route), "")
    return has_permission(perm)


def can_export() -> bool:
    if not is_export_strict():
        return True
    return has_permission("exports:download")


def render_login_gate() -> bool:
    """
    Renderiza login y devuelve True cuando la sesion esta autenticada
    o cuando auth no es obligatoria.
    """
    if not is_auth_required():
        current_user()
        return True

    prepare_auth_backend()

    user = current_user()
    if user.user_id:
        return True

    st.markdown("<div class='vg-login-shell'>", unsafe_allow_html=True)
    st.markdown("<div class='vg-login-kicker'>Control de acceso</div>", unsafe_allow_html=True)
    st.markdown("<div class='vg-login-title'>Acceso seguro</div>", unsafe_allow_html=True)
    st.markdown(
        "<div class='vg-login-subtitle'>Ingrese con su usuario para continuar el trabajo diario.</div>",
        unsafe_allow_html=True,
    )
    with st.form("auth.login.form", clear_on_submit=False):
        username = st.text_input("Usuario", key="auth.login.username")
        password = st.text_input("Contrasena", type="password", key="auth.login.password")
        submit_kwargs = {"width": "stretch"}
        try:
            import inspect

            params = inspect.signature(st.form_submit_button).parameters
            if "type" in params:
                submit_kwargs["type"] = "primary"
        except Exception:
            pass
        submitted = st.form_submit_button("Ingresar", **submit_kwargs)
        if submitted:
            identity, reason = authenticate_local_user(username, password)
            if identity is None:
                st.error(reason or "No se pudo autenticar.")
            else:
                st.session_state[SESSION_USER_KEY] = identity.to_session()
                st.success(f"Sesion iniciada: {identity.display_name} ({identity.role})")
                st.rerun()
    st.markdown("</div>", unsafe_allow_html=True)
    return False


def render_sidebar_identity() -> None:
    user = current_user()
    if not user.user_id:
        return
    with st.sidebar.expander("Sesion", expanded=True):
        st.caption(f"Usuario: {user.display_name} - Rol: {user.role}")
        if is_auth_required():
            if st.sidebar.button("Cerrar sesion", key="auth.logout", width="stretch", type="secondary"):
                logout_current_user()
                st.rerun()


def build_actor_context() -> Dict[str, str]:
    user = current_user()
    request_id = str(st.session_state.get(SESSION_REQUEST_ID_KEY, "")).strip()
    if not request_id:
        request_id = str(uuid.uuid4())
        st.session_state[SESSION_REQUEST_ID_KEY] = request_id
    return {
        "user_id": user.user_id or "system",
        "user_name": user.display_name or user.username or "system",
        "role": user.role or "readonly",
        "ip": str(os.environ.get("VG_ACTOR_IP", "")),
        "user_agent": "streamlit",
        "request_id": request_id,
    }
