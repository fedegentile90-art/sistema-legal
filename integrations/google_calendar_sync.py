"""Sincronizacion bidireccional controlada SistemaLegal <-> Google Calendar."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from googleapiclient.errors import HttpError

from domain import GoogleCalendarConnection, TaskRecord
from integrations.google_calendar_client import (
    DEFAULT_TIMEZONE,
    build_calendar_service,
    build_credentials,
    build_google_event_payload,
    list_incremental_events,
    upsert_event,
)
from integrations.google_calendar_crypto import decrypt_token


def _parse_iso(raw: str) -> Optional[datetime]:
    text = str(raw or "").strip()
    if not text:
        return None
    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def _event_due_date(event: Dict[str, Any]) -> str:
    start = event.get("start", {}) if isinstance(event.get("start"), dict) else {}
    date_val = start.get("date")
    if date_val:
        return str(date_val)
    date_time = str(start.get("dateTime", "") or "")
    if "T" in date_time:
        return date_time.split("T", 1)[0]
    return ""


def _event_to_task_changes(event: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "title": str(event.get("summary", "") or "").strip(),
        "description": str(event.get("description", "") or "").strip(),
        "due_date": _event_due_date(event),
        "status": "cancelada" if str(event.get("status", "")).strip().lower() == "cancelled" else "pendiente",
    }


def _task_updated_at(task: TaskRecord) -> datetime:
    dt = _parse_iso(task.updated_at)
    if dt:
        return dt
    return datetime.min.replace(tzinfo=timezone.utc)


def sync_connection(
    repo: Any,
    connection: GoogleCalendarConnection,
    *,
    actor_ctx: Optional[Dict[str, str]] = None,
    timezone_name: str = DEFAULT_TIMEZONE,
) -> Dict[str, Any]:
    refresh_token = decrypt_token(connection.refresh_token_enc)
    creds = build_credentials(refresh_token=refresh_token)
    service = build_calendar_service(creds)
    result = {
        "connection_id": connection.id,
        "user_id": connection.user_id,
        "created_events": 0,
        "updated_events": 0,
        "pulled_updates": 0,
        "conflicts": 0,
        "errors": 0,
    }

    local_tasks = repo.listar_tareas(limit=1000)
    task_by_id = {task.id: task for task in local_tasks}

    # Local -> Google
    for task in local_tasks:
        try:
            mapping = repo.obtener_google_event_mapping_por_task(connection.id, task.id)
            local_updated = _task_updated_at(task)
            payload = build_google_event_payload(
                task,
                timezone_name=timezone_name,
                reminder_minutes=[24 * 60, 60],
                connection_id=connection.id,
            )

            if mapping is None:
                event = upsert_event(service, calendar_id=connection.calendar_id, payload=payload, event_id="")
                repo.upsert_google_event_mapping(
                    task_id=task.id,
                    connection_id=connection.id,
                    google_event_id=str(event.get("id", "") or ""),
                    google_etag=str(event.get("etag", "") or ""),
                    google_updated_at=_parse_iso(str(event.get("updated", "") or "")),
                    last_local_updated_at=local_updated,
                    actor_ctx=actor_ctx,
                )
                result["created_events"] += 1
                continue

            mapped_local = _parse_iso(mapping.last_local_updated_at)
            if mapped_local is None or local_updated > mapped_local:
                event = upsert_event(
                    service,
                    calendar_id=connection.calendar_id,
                    payload=payload,
                    event_id=mapping.google_event_id,
                )
                repo.upsert_google_event_mapping(
                    task_id=task.id,
                    connection_id=connection.id,
                    google_event_id=mapping.google_event_id,
                    google_etag=str(event.get("etag", "") or ""),
                    google_updated_at=_parse_iso(str(event.get("updated", "") or "")),
                    last_local_updated_at=local_updated,
                    actor_ctx=actor_ctx,
                )
                result["updated_events"] += 1
        except Exception:
            result["errors"] += 1

    # Google -> Local incremental
    sync_token = str(connection.sync_token or "").strip()
    next_sync_token = sync_token
    page_token = ""
    while True:
        try:
            items, next_page, next_sync = list_incremental_events(
                service,
                calendar_id=connection.calendar_id,
                sync_token=sync_token,
                page_token=page_token,
            )
        except HttpError as err:
            # 410 Gone => reset incremental token and full delta window.
            if getattr(err, "status_code", None) == 410 or "410" in str(err):
                sync_token = ""
                page_token = ""
                items, next_page, next_sync = list_incremental_events(
                    service,
                    calendar_id=connection.calendar_id,
                    sync_token="",
                    page_token="",
                )
            else:
                result["errors"] += 1
                break
        except Exception:
            result["errors"] += 1
            break

        for event in items:
            event_id = str(event.get("id", "") or "")
            if not event_id:
                continue
            mapping = repo.obtener_google_event_mapping_por_evento(connection.id, event_id)
            if mapping is None:
                ext = (event.get("extendedProperties", {}) or {}).get("private", {}) or {}
                task_id = str(ext.get("sistemalegal_task_id", "") or "")
                if not task_id:
                    continue
                task = task_by_id.get(task_id) or repo.obtener_tarea_por_id(task_id)
                if not task:
                    continue
                event_updated = _parse_iso(str(event.get("updated", "") or ""))
                local_updated = _task_updated_at(task)
                if event_updated and event_updated > local_updated:
                    repo.actualizar_tarea(task.id, _event_to_task_changes(event), actor_ctx=actor_ctx)
                    result["pulled_updates"] += 1
                repo.upsert_google_event_mapping(
                    task_id=task.id,
                    connection_id=connection.id,
                    google_event_id=event_id,
                    google_etag=str(event.get("etag", "") or ""),
                    google_updated_at=event_updated,
                    last_local_updated_at=_task_updated_at(task),
                    actor_ctx=actor_ctx,
                )
                continue

            task = repo.obtener_tarea_por_id(mapping.task_id)
            if not task:
                continue
            local_updated = _task_updated_at(task)
            event_updated = _parse_iso(str(event.get("updated", "") or ""))
            if event_updated and event_updated > local_updated:
                repo.actualizar_tarea(task.id, _event_to_task_changes(event), actor_ctx=actor_ctx)
                result["pulled_updates"] += 1
                updated_task = repo.obtener_tarea_por_id(task.id) or task
                repo.upsert_google_event_mapping(
                    task_id=task.id,
                    connection_id=connection.id,
                    google_event_id=event_id,
                    google_etag=str(event.get("etag", "") or ""),
                    google_updated_at=event_updated,
                    last_local_updated_at=_task_updated_at(updated_task),
                    actor_ctx=actor_ctx,
                )
            elif event_updated and local_updated > event_updated:
                payload = build_google_event_payload(
                    task,
                    timezone_name=timezone_name,
                    reminder_minutes=[24 * 60, 60],
                    connection_id=connection.id,
                )
                event_push = upsert_event(
                    service,
                    calendar_id=connection.calendar_id,
                    payload=payload,
                    event_id=event_id,
                )
                repo.upsert_google_event_mapping(
                    task_id=task.id,
                    connection_id=connection.id,
                    google_event_id=event_id,
                    google_etag=str(event_push.get("etag", "") or ""),
                    google_updated_at=_parse_iso(str(event_push.get("updated", "") or "")),
                    last_local_updated_at=local_updated,
                    actor_ctx=actor_ctx,
                )
                result["conflicts"] += 1

        if next_sync:
            next_sync_token = next_sync
        if not next_page:
            break
        page_token = next_page

    repo.marcar_google_calendar_sincronizado(
        connection.id,
        sync_token=next_sync_token,
        actor_ctx=actor_ctx,
    )
    return result


def sync_user(repo: Any, user_id: str, *, actor_ctx: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    conn = repo.obtener_google_calendar_connection_by_user(user_id)
    if not conn:
        return {"ok": False, "reason": "connection_not_found", "user_id": str(user_id or "")}
    result = sync_connection(repo, conn, actor_ctx=actor_ctx)
    result["ok"] = result.get("errors", 0) == 0
    return result


def sync_all_active_connections(repo: Any, *, actor_ctx: Optional[Dict[str, str]] = None) -> List[Dict[str, Any]]:
    results: List[Dict[str, Any]] = []
    for connection in repo.listar_google_calendar_connections(only_active=True):
        try:
            row = sync_connection(repo, connection, actor_ctx=actor_ctx)
            row["ok"] = row.get("errors", 0) == 0
            results.append(row)
        except Exception as exc:
            results.append(
                {
                    "ok": False,
                    "connection_id": connection.id,
                    "user_id": connection.user_id,
                    "errors": 1,
                    "reason": str(exc),
                }
            )
    return results

