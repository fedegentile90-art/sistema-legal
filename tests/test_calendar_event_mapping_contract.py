from domain import TaskRecord
from integrations.google_calendar_client import build_google_event_payload


def test_calendar_event_payload_maps_task_fields() -> None:
    task = TaskRecord(
        id="t-1",
        case_id="c-1",
        case_ref="db://cases/c-1",
        title="Audiencia preliminar",
        description="Revisar expediente y preparar estrategia.",
        due_date="2026-03-10",
    )
    payload = build_google_event_payload(
        task,
        timezone_name="America/Argentina/Buenos_Aires",
        reminder_minutes=[1440, 60],
        connection_id="conn-1",
    )
    assert payload["summary"] == "Audiencia preliminar"
    assert payload["description"].startswith("Revisar expediente")
    assert payload["start"]["date"] == "2026-03-10"
    assert payload["extendedProperties"]["private"]["sistemalegal_task_id"] == "t-1"
    assert payload["extendedProperties"]["private"]["sistemalegal_case_id"] == "c-1"
    assert len(payload["reminders"]["overrides"]) == 2

