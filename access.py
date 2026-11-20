"""Private access gate; the password verifier is supplied as a Render secret file."""
import hashlib
import hmac
import time
from pathlib import Path

ACCESS_HASH_FILE = Path("/etc/secrets/app_access_hash")
MIN_ITERATIONS = 600_000
MAX_ITERATIONS = 1_000_000

def parse_verifier(encoded):
    try:
        algorithm, rounds, salt_hex, digest_hex = encoded.strip().split("$")
        iterations = int(rounds)
        salt, digest = bytes.fromhex(salt_hex), bytes.fromhex(digest_hex)
        if algorithm != "pbkdf2_sha256" or not MIN_ITERATIONS <= iterations <= MAX_ITERATIONS:
            return None
        if not 16 <= len(salt) <= 32 or len(digest) != 32:
            return None
        return iterations, salt, digest
    except (ValueError, TypeError, AttributeError):
        return None

def verify_password(password, encoded):
    parsed = parse_verifier(encoded)
    if parsed is None or not isinstance(password, str) or not password or len(password) > 1024:
        return False
    iterations, salt, expected = parsed
    actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return hmac.compare_digest(actual, expected)

def read_verifier():
    try:
        with ACCESS_HASH_FILE.open("r", encoding="utf-8-sig") as source:
            encoded = source.read(4097).strip()
        return encoded if len(encoded) <= 4096 else ""
    except (OSError, UnicodeError):
        return ""

def require_access(st):
    encoded = read_verifier()
    if parse_verifier(encoded) is None:
        st.session_state.pop("_access_grant", None)
        st.error("El acceso privado de Sistema Legal todavía no está configurado.")
        return False
    fingerprint = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
    if hmac.compare_digest(str(st.session_state.get("_access_grant", "")), fingerprint):
        if st.sidebar.button("Cerrar sesión", key="_access_logout"):
            st.session_state.pop("_access_grant", None)
            st.rerun()
            return False
        return True
    st.session_state.pop("_access_grant", None)
    st.title("Sistema Legal")
    st.subheader("Acceso privado")
    with st.form("_access_login", clear_on_submit=True):
        password = st.text_input("Contraseña", type="password")
        submitted = st.form_submit_button("Ingresar")
    if submitted:
        if time.monotonic() < st.session_state.get("_access_retry_after", 0):
            st.error("Esperá unos segundos antes de volver a intentar.")
            return False
        if verify_password(password, encoded):
            st.session_state["_access_grant"] = fingerprint
            st.session_state.pop("_access_retry_after", None)
            st.rerun()
            return True
        st.session_state["_access_retry_after"] = time.monotonic() + 2
        st.error("No se pudo iniciar sesión.")
    return False
