"""Reglas de dominio para agenda tasks-first."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Dict, Iterable, List

from domain import Caso, TaskRecord


SUPPORTED_DATE_FORMATS = ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y")
TASK_STATUSES = {"pendiente", "en_progreso", "completada", "cancelada"}
TASK_PRIORITIES = {"baja", "normal", "alta", "critica"}


@dataclass(frozen=True)
class TaskUrgency:
    bucket: str
    score: int
    days_delta: int | None


def parse_task_date(raw: Any) -> date | None:
    text = str(raw or "").strip()
    if not text:
        return None
    for fmt in SUPPORTED_DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def format_task_date(value: date | None) -> str:
    if not value:
        return ""
    return value.strftime("%Y-%m-%d")


def normalize_task_status(raw: str, default: str = "pendiente") -> str:
    value = str(raw or "").strip().lower()
    if value in TASK_STATUSES:
        return value
    return default


def normalize_task_priority(raw: str, default: str = "normal") -> str:
    value = str(raw or "").strip().lower()
    if value in TASK_PRIORITIES:
        return value
    return default


def build_primary_task_payload_from_case(caso: Caso) -> Dict[str, str]:
    title = str(caso.tarea_pendiente or "").strip() or f"Seguimiento: {str(caso.causa or '').strip() or 'Caso'}"
    return {
        "title": title[:255],
        "description": "",
        "due_date": format_task_date(parse_task_date(caso.fecha_tarea)),
        "priority": "normal",
        "status": "pendiente",
        "assigned_to": str(caso.responsable or "").strip()[:100],
    }


def compute_task_urgency(task: TaskRecord, today: date | None = None) -> TaskUrgency:
    base = today or date.today()
    due = parse_task_date(task.due_date)
    if not due:
        return TaskUrgency(bucket="sin_fecha", score=50, days_delta=None)
    delta = (due - base).days
    if delta < 0:
        return TaskUrgency(bucket="vencida", score=100 + abs(delta), days_delta=delta)
    if delta <= 2:
        return TaskUrgency(bucket="critica", score=90 - delta, days_delta=delta)
    if delta <= 7:
        return TaskUrgency(bucket="proxima", score=70 - delta, days_delta=delta)
    return TaskUrgency(bucket="futura", score=max(1, 40 - min(delta, 30)), days_delta=delta)


def sort_tasks_for_agenda(tasks: Iterable[TaskRecord], today: date | None = None) -> List[TaskRecord]:
    base = today or date.today()

    def _key(task: TaskRecord):
        urgency = compute_task_urgency(task, today=base)
        due = parse_task_date(task.due_date)
        due_key = due or date.max
        assigned = str(task.assigned_to or "").upper()
        client = str(task.client_name or "").upper()
        title = str(task.title or "").upper()
        status_rank = {
            "pendiente": 0,
            "en_progreso": 1,
            "completada": 2,
            "cancelada": 3,
        }.get(normalize_task_status(task.status), 9)
        return (-urgency.score, status_rank, due_key, assigned, client, title)

    return sorted(list(tasks), key=_key)


def filter_tasks(
    tasks: Iterable[TaskRecord],
    *,
    status: str = "todas",
    due_window: str = "todas",
    assigned_to: str = "",
    only_active_cases: bool = False,
) -> List[TaskRecord]:
    base = date.today()
    status_filter = str(status or "todas").strip().lower()
    due_filter = str(due_window or "todas").strip().lower()
    assigned_filter = str(assigned_to or "").strip().lower()

    out: List[TaskRecord] = []
    for task in tasks:
        task_status = normalize_task_status(task.status)
        if status_filter not in {"", "todas"} and task_status != status_filter:
            continue

        if assigned_filter and assigned_filter not in str(task.assigned_to or "").strip().lower():
            continue

        due = parse_task_date(task.due_date)
        if due_filter == "solo_vencidas":
            if due is None or due >= base:
                continue
        elif due_filter == "proximos_7":
            if due is None or not (base <= due <= base.fromordinal(base.toordinal() + 7)):
                continue
        elif due_filter == "proximos_30":
            if due is None or not (base <= due <= base.fromordinal(base.toordinal() + 30)):
                continue

        if only_active_cases:
            if "activo" not in str(task.case_estado or "").strip().lower():
                continue

        out.append(task)
    return out

