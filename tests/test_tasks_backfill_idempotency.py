from db import backfill_tasks_from_cases


class _FakeCursor:
    def __init__(self, conn):
        self.conn = conn
        self._rows = []
        self._one = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, query, params=None):
        q = str(query)
        params = params or ()
        if "FROM cases" in q:
            self._rows = [
                ("case-1", "Causa A", "Tarea A", "2026-03-10", "Ana"),
                ("case-2", "Causa B", "Tarea B", "2026-03-11", "Luis"),
            ]
            self._one = None
            return
        if "FROM tasks" in q:
            case_id = str(params[0])
            self._one = ("task-existing",) if case_id in self.conn.existing_case_ids else None
            self._rows = []
            return
        if "INSERT INTO tasks" in q:
            case_id = str(params[0])
            self.conn.existing_case_ids.add(case_id)
            self.conn.insert_calls += 1
            self._one = None
            self._rows = []
            return

    def fetchall(self):
        return list(self._rows)

    def fetchone(self):
        return self._one


class _FakeConnection:
    def __init__(self):
        self.existing_case_ids = {"case-1"}
        self.insert_calls = 0

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def cursor(self):
        return _FakeCursor(self)


def test_backfill_tasks_is_idempotent(monkeypatch) -> None:
    fake_conn = _FakeConnection()
    monkeypatch.setattr(backfill_tasks_from_cases, "_connect", lambda: fake_conn)

    first = backfill_tasks_from_cases.run_backfill(dry_run=False)
    assert first.scanned == 2
    assert first.created == 1
    assert first.skipped_existing == 1
    assert fake_conn.insert_calls == 1

    second = backfill_tasks_from_cases.run_backfill(dry_run=False)
    assert second.scanned == 2
    assert second.created == 0
    assert second.skipped_existing == 2
    assert fake_conn.insert_calls == 1

