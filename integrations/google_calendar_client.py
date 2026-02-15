"""Cliente Google Calendar API para sincronizacion de tareas."""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Tuple

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from domain import TaskRecord


DEFAULT_TIMEZONE = "America/Argentina/Buenos_Aires"
DEFAULT_SCOPES = ["https://www.googleapis.com/auth/calendar"]


def _oauth_client_config() -> tuple[str, str]:
    client_id = str(os.environ.get("VG_GOOGLE_OAUTH_CLIENT_ID", "")).strip()
    client_secret = str(os.environ.get("VG_GOOGLE_OAUTH_CLIENT_SECRET", "")).strip()
    if not (client_id and client_secret):
        raise RuntimeError("Falta configurar VG_GOOGLE_OAUTH_CLIENT_ID / VG_GOOGLE_OAUTH_CLIENT_SECRET.")
    return client_id, client_secret


def build_credentials(
    *,
    refresh_token: str,
    scopes: Iterable[str] | None = None,
) -> Credentials:
    token = str(refresh_token or "").strip()
    if not token:
        raise ValueError("Refresh token vacio.")
    client_id, client_secret = _oauth_client_config()
    creds = Credentials(
        token=None,
        refresh_token=token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=client_id,
        client_secret=client_secret,
        scopes=list(scopes or DEFAULT_SCOPES),
    )
    creds.refresh(Request())
    return creds


def build_calendar_service(credentials: Credentials):
    return build("calendar", "v3", credentials=credentials, cache_discovery=False)


def _due_date_iso(task: TaskRecord) -> str:
    raw = str(task.due_date or "").strip()
    if not raw:
        return datetime.now(tz=timezone.utc).date().isoformat()
    if "T" in raw:
        return raw.split("T", 1)[0]
    return raw


def build_google_event_payload(
    task: TaskRecord,
    *,
    timezone_name: str = DEFAULT_TIMEZONE,
    reminder_minutes: List[int] | None = None,
    connection_id: str = "",
) -> Dict[str, Any]:
    due_iso = _due_date_iso(task)
    reminders = reminder_minutes or [24 * 60, 60]
    payload: Dict[str, Any] = {
        "summary": str(task.title or "Tarea legal").strip()[:250],
        "description": str(task.description or "").strip(),
        "start": {"date": due_iso},
        "end": {"date": due_iso},
        "transparency": "opaque",
        "extendedProperties": {
            "private": {
                "sistemalegal_task_id": str(task.id),
                "sistemalegal_case_id": str(task.case_id),
                "sistemalegal_connection_id": str(connection_id or ""),
            }
        },
        "reminders": {
            "useDefault": False,
            "overrides": [{"method": "popup", "minutes": int(m)} for m in reminders if int(m) >= 0],
        },
    }
    if timezone_name:
        payload["start"]["timeZone"] = timezone_name
        payload["end"]["timeZone"] = timezone_name
    return payload


def upsert_event(
    service: Any,
    *,
    calendar_id: str,
    payload: Dict[str, Any],
    event_id: str = "",
) -> Dict[str, Any]:
    calendar = str(calendar_id or "primary").strip() or "primary"
    if event_id:
        return (
            service.events()
            .update(calendarId=calendar, eventId=str(event_id), body=payload)
            .execute()
        )
    return (
        service.events()
        .insert(calendarId=calendar, body=payload)
        .execute()
    )


def list_incremental_events(
    service: Any,
    *,
    calendar_id: str,
    sync_token: str = "",
    page_token: str = "",
) -> Tuple[List[Dict[str, Any]], str, str]:
    calendar = str(calendar_id or "primary").strip() or "primary"
    kwargs: Dict[str, Any] = {
        "calendarId": calendar,
        "singleEvents": True,
        "showDeleted": True,
        "maxResults": 250,
    }
    if page_token:
        kwargs["pageToken"] = str(page_token)
    if sync_token:
        kwargs["syncToken"] = str(sync_token)
    else:
        time_min = (datetime.now(tz=timezone.utc) - timedelta(days=180)).isoformat().replace("+00:00", "Z")
        kwargs["timeMin"] = time_min
        kwargs["orderBy"] = "updated"
    result = service.events().list(**kwargs).execute()
    items = list(result.get("items", []) or [])
    next_page = str(result.get("nextPageToken", "") or "")
    next_sync = str(result.get("nextSyncToken", "") or "")
    return items, next_page, next_sync

