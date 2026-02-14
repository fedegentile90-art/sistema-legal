import json

import security


class _FakeCursor:
    def __init__(self, store: dict[str, dict]):
        self._store = store
        self._row = None
        self.rowcount = 0

    def execute(self, sql: str, params=None):
        params = params or ()
        stmt = " ".join(str(sql).strip().split()).lower()
        if stmt.startswith("select extra from users where id ="):
            user_id = str(params[0])
            if user_id in self._store:
                self._row = (self._store[user_id],)
            else:
                self._row = None
            return
        if stmt.startswith("update users set extra ="):
            payload = json.loads(str(params[0]))
            user_id = str(params[1])
            if user_id in self._store:
                self._store[user_id] = payload
                self.rowcount = 1
            else:
                self.rowcount = 0
            return
        raise AssertionError(f"SQL no esperado: {sql}")

    def fetchone(self):
        return self._row

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class _FakeConn:
    def __init__(self, store: dict[str, dict]):
        self._store = store

    def cursor(self):
        return _FakeCursor(self._store)

    def close(self):
        return None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def test_load_user_ui_preferences_reads_normalized_payload(monkeypatch) -> None:
    store = {
        "u-1": {
            "ui_preferences": {
                "theme_mode": "light",
                "density_mode": "compact",
                "unexpected": "ignored",
            }
        }
    }
    monkeypatch.setattr(security, "_get_connection", lambda: _FakeConn(store))
    prefs = security.load_user_ui_preferences("u-1")
    assert prefs == {"theme_mode": "light", "density_mode": "compact"}


def test_save_user_ui_preferences_updates_users_extra(monkeypatch) -> None:
    store = {"u-1": {"ui_preferences": {"theme_mode": "dark", "density_mode": "balanced"}}}
    monkeypatch.setattr(security, "_get_connection", lambda: _FakeConn(store))
    ok = security.save_user_ui_preferences("u-1", {"theme_mode": "light", "density_mode": "compact"})
    assert ok is True
    assert store["u-1"]["ui_preferences"]["theme_mode"] == "light"
    assert store["u-1"]["ui_preferences"]["density_mode"] == "compact"
