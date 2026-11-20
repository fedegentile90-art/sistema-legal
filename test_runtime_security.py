"""Synthetic access/configuration checks. No real credentials or database."""
import ast
import hashlib
import tempfile
import unittest
from pathlib import Path, PurePosixPath, PureWindowsPath
from types import SimpleNamespace
from unittest.mock import patch
import access
import runtime_config

PASSWORD = "Fixture de prueba solamente 2026"
SALT = bytes(range(16))
VERIFIER = "pbkdf2_sha256$600000$" + SALT.hex() + "$" + hashlib.pbkdf2_hmac("sha256", PASSWORD.encode(), SALT, 600000).hex()

class Rerun(Exception): pass
class Stopped(Exception): pass
class RepositoryReached(Exception): pass

class FakeStreamlit:
    def __init__(self, password="", submitted=False, logout=False):
        self.session_state = {}
        self.messages = []
        self.password, self.submitted = password, submitted
        self.sidebar = SimpleNamespace(button=lambda *a, **k: logout)
    def error(self, text): self.messages.append(text)
    def info(self, text): self.messages.append(text)
    def title(self, *args): pass
    def subheader(self, *args): pass
    def form(self, *args, **kwargs): return self
    def __enter__(self): return self
    def __exit__(self, *args): return False
    def text_input(self, *args, **kwargs): return self.password
    def form_submit_button(self, *args): return self.submitted
    def rerun(self): raise Rerun()
    def stop(self): raise Stopped()

class RuntimeSecurityTests(unittest.TestCase):
    def test_password_verification(self):
        self.assertTrue(access.verify_password(PASSWORD, VERIFIER))
        self.assertFalse(access.verify_password("incorrecta", VERIFIER))
        self.assertFalse(access.verify_password("", VERIFIER))

    def test_invalid_verifiers_fail_closed(self):
        for value in ("", "x", VERIFIER.replace("$600000$", "$999999999$"), VERIFIER.replace("pbkdf2_sha256", "md5"), "pbkdf2_sha256$600000$00$00"):
            self.assertFalse(access.verify_password(PASSWORD, value))

    def test_missing_private_secret_denies_access(self):
        st = FakeStreamlit()
        st.session_state["_access_grant"] = "old"
        with patch.object(access, "read_verifier", return_value=""):
            self.assertFalse(access.require_access(st))
        self.assertNotIn("_access_grant", st.session_state)

    def test_anonymous_visit_denied(self):
        with patch.object(access, "read_verifier", return_value=VERIFIER):
            self.assertFalse(access.require_access(FakeStreamlit()))

    def test_wrong_password_denied_and_cooldown(self):
        st = FakeStreamlit("incorrecta", True)
        with patch.object(access, "read_verifier", return_value=VERIFIER):
            self.assertFalse(access.require_access(st))
            with patch.object(access, "verify_password") as verifier:
                self.assertFalse(access.require_access(st))
                verifier.assert_not_called()
        self.assertNotIn("_access_grant", st.session_state)

    def test_correct_password_grants_session(self):
        st = FakeStreamlit(PASSWORD, True)
        with patch.object(access, "read_verifier", return_value=VERIFIER):
            with self.assertRaises(Rerun): access.require_access(st)
            st.submitted = False
            self.assertTrue(access.require_access(st))

    def test_changed_verifier_invalidates_session(self):
        st = FakeStreamlit()
        st.session_state["_access_grant"] = "old"
        with patch.object(access, "read_verifier", return_value=VERIFIER):
            self.assertFalse(access.require_access(st))

    def test_logout_removes_access(self):
        st = FakeStreamlit(logout=True)
        st.session_state["_access_grant"] = hashlib.sha256(VERIFIER.encode()).hexdigest()
        with patch.object(access, "read_verifier", return_value=VERIFIER):
            with self.assertRaises(Rerun): access.require_access(st)
        self.assertNotIn("_access_grant", st.session_state)

    def test_secret_file_precedes_development_environment(self):
        with tempfile.TemporaryDirectory() as folder:
            secret = Path(folder) / "database_url"
            secret.write_text("postgresql://fixture.invalid/database?sslmode=require\n", encoding="utf-8")
            with patch.object(runtime_config, "DATABASE_URL_FILE", secret), patch.dict("os.environ", {"DATABASE_URL": "wrong"}):
                self.assertEqual(runtime_config.get_database_url(), "postgresql://fixture.invalid/database?sslmode=require")

    def test_missing_file_preserves_development_configuration(self):
        with tempfile.TemporaryDirectory() as folder:
            with patch.object(runtime_config, "DATABASE_URL_FILE", Path(folder)/"missing"), patch.dict("os.environ", {"DATABASE_URL": "fixture"}):
                self.assertEqual(runtime_config.get_database_url(), "fixture")

    def test_empty_secret_never_falls_back(self):
        with tempfile.TemporaryDirectory() as folder:
            secret = Path(folder) / "database_url"
            secret.write_text("", encoding="utf-8")
            with patch.object(runtime_config, "DATABASE_URL_FILE", secret), patch.dict("os.environ", {"DATABASE_URL": "wrong"}):
                with self.assertRaises(RuntimeError): runtime_config.get_database_url()

    def test_neon_json_copy_is_supported(self):
        import json
        value = "postgresql://fixture.invalid/database?sslmode=require"
        with tempfile.TemporaryDirectory() as folder:
            secret = Path(folder) / "database_url"
            for record in ({"database_url":value}, [{"database_url":value}]):
                secret.write_text(json.dumps(record), encoding="utf-8")
                with patch.object(runtime_config, "DATABASE_URL_FILE", secret):
                    self.assertEqual(runtime_config.get_database_url(), value)

    def test_invalid_json_fails_closed(self):
        with tempfile.TemporaryDirectory() as folder:
            secret = Path(folder) / "database_url"
            for value in ("{broken", "[]", '[{"wrong":"fixture"}]'):
                secret.write_text(value, encoding="utf-8")
                with patch.object(runtime_config, "DATABASE_URL_FILE", secret):
                    with self.assertRaises(RuntimeError): runtime_config.get_database_url()

    def test_public_startup_stops_before_case_repository(self):
        tree = ast.parse((Path(__file__).parent/"app.py").read_text(encoding="utf-8-sig"))
        main = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "main")
        module = ast.Module(body=[main], type_ignores=[])
        st = FakeStreamlit()
        calls = []
        scope = {"st":st, "configurar_pagina":lambda:None, "require_access":lambda st:False, "ensure_state":lambda:calls.append("state"), "GestorCasos":lambda *a:calls.append("repository")}
        exec(compile(module, "app.py", "exec"), scope)
        with self.assertRaises(Stopped): scope["main"]()
        self.assertEqual(calls, [])

    def test_database_paths_from_historical_fix(self):
        tree = ast.parse((Path(__file__).parent/"repo_db.py").read_text(encoding="utf-8-sig"))
        cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "GestorCasosDB")
        method = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == "_get_case_id_from_path")
        scope = {"Path":Path, "Optional": __import__("typing").Optional}
        exec(compile(ast.Module(body=[method], type_ignores=[]), "repo_db.py", "exec"), scope)
        get_id = scope["_get_case_id_from_path"]
        case_id = "123e4567-e89b-12d3-a456-426614174000"
        for value in (PurePosixPath("db://cases/"+case_id), PureWindowsPath("db://cases/"+case_id), "db://cases/"+case_id):
            self.assertEqual(get_id(None, value), case_id)
        for value in ("/tmp/cases/test", "db:/cases/", "db:/cases/"+case_id+"/extra"):
            self.assertIsNone(get_id(None, value))

if __name__ == "__main__":
    unittest.main(verbosity=2)
