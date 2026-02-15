from datetime import datetime, timezone

from domain import GoogleCalendarConnection, GoogleEventMap, TaskRecord
from integrations import google_calendar_sync as sync_mod


class _RepoStub:
    def __init__(self):
        self.task = TaskRecord(
            id="task-1",
            case_id="case-1",
            case_ref="db://cases/case-1",
            title="Tarea local",
            due_date="2026-03-10",
            updated_at="2026-03-10T10:00:00+00:00",
        )
        self.mapping = GoogleEventMap(
            id="map-1",
            task_id="task-1",
            connection_id="conn-1",
            google_event_id="ev-1",
            last_local_updated_at="2026-03-10T10:00:00+00:00",
        )
        self.updated_payloads = []
        self.synced_token = ""

    def listar_tareas(self, limit=1000):
        return [self.task]

    def obtener_google_event_mapping_por_task(self, connection_id, task_id):
        return self.mapping

    def upsert_google_event_mapping(self, **kwargs):
        self.mapping.google_event_id = kwargs.get("google_event_id", self.mapping.google_event_id)
        self.mapping.last_local_updated_at = (
            kwargs.get("last_local_updated_at").isoformat() if kwargs.get("last_local_updated_at") else self.mapping.last_local_updated_at
        )
        return self.mapping

    def obtener_google_event_mapping_por_evento(self, connection_id, google_event_id):
        if google_event_id == self.mapping.google_event_id:
            return self.mapping
        return None

    def obtener_tarea_por_id(self, task_id):
        return self.task if task_id == self.task.id else None

    def actualizar_tarea(self, task_id, changes, actor_ctx=None):
        self.updated_payloads.append((task_id, dict(changes)))
        return True

    def marcar_google_calendar_sincronizado(self, connection_id, sync_token="", actor_ctx=None):
        self.synced_token = sync_token
        return True


def test_google_sync_incremental_pulls_remote_updates(monkeypatch) -> None:
    repo = _RepoStub()
    conn = GoogleCalendarConnection(
        id="conn-1",
        user_id="u-1",
        google_email="user@example.com",
        calendar_id="primary",
        refresh_token_enc="enc",
        sync_token="sync-1",
    )

    monkeypatch.setattr(sync_mod, "decrypt_token", lambda _enc: "refresh-token")
    monkeypatch.setattr(sync_mod, "build_credentials", lambda refresh_token: object())
    monkeypatch.setattr(sync_mod, "build_calendar_service", lambda _creds: object())
    monkeypatch.setattr(sync_mod, "upsert_event", lambda *args, **kwargs: {"id": "ev-1", "updated": "2026-03-10T09:00:00Z", "etag": "e1"})

    def _list_events(service, calendar_id, sync_token="", page_token=""):
        event = {
            "id": "ev-1",
            "summary": "Cambio remoto",
            "description": "Editado en Google",
            "updated": "2026-03-10T12:00:00Z",
            "status": "confirmed",
            "start": {"date": "2026-03-11"},
            "etag": "etag-new",
            "extendedProperties": {"private": {"sistemalegal_task_id": "task-1"}},
        }
        return [event], "", "sync-2"

    monkeypatch.setattr(sync_mod, "list_incremental_events", _list_events)

    result = sync_mod.sync_connection(repo, conn, actor_ctx={"user_id": "u-1"})
    assert result["pulled_updates"] == 1
    assert result["conflicts"] == 0
    assert repo.synced_token == "sync-2"
    assert repo.updated_payloads

