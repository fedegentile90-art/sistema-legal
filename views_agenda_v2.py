"""Agenda v2 basada en tasks (DB-first)."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any, Callable, Dict, List

import pandas as pd
import streamlit as st

from domain import Caso, TaskRecord
from grids import render_aggrid
from security import has_permission
from services.tasks_service import filter_tasks, sort_tasks_for_agenda
from ui import card_begin, card_end, open_path, section_header, vg_empty_state


TASK_SELECTED_KEY = "gestion.selected.agenda.task_id"
TASK_MODE_KEY = "gestion.widgets.modebar.agenda.label"
TASK_FILTER_STATUS_KEY = "gestion.agenda.v2.filter.status"
TASK_FILTER_DUE_KEY = "gestion.agenda.v2.filter.due"
TASK_FILTER_ASSIGNED_KEY = "gestion.agenda.v2.filter.assigned"
TASK_FILTER_ACTIVE_KEY = "gestion.agenda.v2.filter.active"


def _extract_grid_value(value: Any, key: str) -> str:
    if value is None:
        return ""
    if isinstance(value, dict):
        rows = value.get("selected_rows")
        if isinstance(rows, list) and rows and isinstance(rows[0], dict):
            return str(rows[0].get(key, "") or "").strip()
    rows_attr = getattr(value, "selected_rows", None)
    if rows_attr is not None:
        rows = rows_attr
        if hasattr(rows, "to_dict"):
            try:
                rows = rows.to_dict("records")
            except Exception:
                rows = []
        if isinstance(rows, list) and rows and isinstance(rows[0], dict):
            return str(rows[0].get(key, "") or "").strip()
    return ""


def _load_tasks(gestor: Any) -> List[TaskRecord]:
    if not hasattr(gestor, "listar_tareas"):
        return []
    try:
        return gestor.listar_tareas(limit=1500)
    except Exception:
        return []


def _render_task_create(gestor: Any, actor_ctx_fn: Callable[[], Dict[str, str]]) -> None:
    if not has_permission("tasks:write"):
        st.caption("Sin permiso para crear tareas.")
        return
    with st.expander("Nueva tarea", expanded=False):
        c1, c2 = st.columns(2)
        with c1:
            case_ref = st.text_input(
                "Caso (db://cases/<uuid>)",
                key="gestion.agenda.v2.create.case_ref",
                placeholder="db://cases/...",
            )
            title = st.text_input("Titulo", key="gestion.agenda.v2.create.title")
            due_date = st.text_input("Fecha (YYYY-MM-DD)", key="gestion.agenda.v2.create.due")
        with c2:
            assigned_to = st.text_input("Responsable", key="gestion.agenda.v2.create.assigned")
            priority = st.selectbox("Prioridad", ["baja", "normal", "alta", "critica"], key="gestion.agenda.v2.create.priority")
            description = st.text_area("Descripcion", key="gestion.agenda.v2.create.desc", height=80)
        if st.button("Crear tarea", key="gestion.agenda.v2.create.submit", width="stretch", type="secondary"):
            try:
                if not case_ref.strip():
                    st.error("Debe indicar un caso en formato db://cases/<uuid>.")
                    return
                created = gestor.crear_tarea(
                    case_ref.strip(),
                    title=title,
                    description=description,
                    due_date=due_date,
                    priority=priority,
                    status="pendiente",
                    assigned_to=assigned_to,
                    extra={"created_from": "agenda_v2_ui"},
                    actor_ctx=actor_ctx_fn(),
                )
                if created:
                    st.success("Tarea creada.")
                    st.rerun()
                else:
                    st.error("No se pudo crear la tarea.")
            except Exception as exc:
                st.error(f"Error creando tarea: {exc}")


def _render_listado(
    gestor: Any,
    tasks: List[TaskRecord],
) -> None:
    card_begin("Agenda v2", subtitle=f"{len(tasks)} tareas activas", variant="tight")
    f1, f2, f3, f4 = st.columns([1.2, 1.2, 1.4, 1.2])
    with f1:
        status_filter = st.selectbox(
            "Estado",
            ["todas", "pendiente", "en_progreso", "completada", "cancelada"],
            key=TASK_FILTER_STATUS_KEY,
        )
    with f2:
        due_filter = st.selectbox(
            "Ventana",
            ["todas", "solo_vencidas", "proximos_7", "proximos_30"],
            key=TASK_FILTER_DUE_KEY,
        )
    with f3:
        assigned = st.text_input("Responsable contiene", key=TASK_FILTER_ASSIGNED_KEY)
    with f4:
        only_active = st.checkbox("Solo casos activos", value=True, key=TASK_FILTER_ACTIVE_KEY)

    filtered = filter_tasks(
        tasks,
        status=status_filter,
        due_window=due_filter,
        assigned_to=assigned,
        only_active_cases=only_active,
    )
    filtered = sort_tasks_for_agenda(filtered, today=date.today())

    if not filtered:
        st.info("Sin tareas para los filtros seleccionados.")
        card_end()
        return

    df = pd.DataFrame(
        [
            {
                "ESTADO": t.status,
                "FECHA": t.due_date,
                "TITULO": t.title,
                "RESPONSABLE": t.assigned_to,
                "CLIENTE": t.client_name,
                "CAUSA": t.case_causa,
                "CASO_ESTADO": t.case_estado,
                "_TASK_ID": t.id,
                "_RUTA": t.case_ref,
            }
            for t in filtered
        ]
    )
    selected = render_aggrid(df, key="gestion.agenda.listado.grid", height=520)
    task_id = _extract_grid_value(selected, "_TASK_ID")
    case_ref = _extract_grid_value(selected, "_RUTA")
    if task_id:
        st.session_state[TASK_SELECTED_KEY] = task_id
        if case_ref:
            st.session_state["gestion.selected.agenda_id"] = case_ref
            st.session_state["selected_item_id"] = case_ref
        st.session_state[TASK_MODE_KEY] = "Detalle"
        st.rerun()
    card_end()


def _render_detalle(gestor: Any, actor_ctx_fn: Callable[[], Dict[str, str]]) -> None:
    task_id = str(st.session_state.get(TASK_SELECTED_KEY, "") or "").strip()
    if not task_id:
        st.info("Seleccione una tarea desde listado.")
        st.session_state[TASK_MODE_KEY] = "Listado"
        st.rerun()
        return
    task = gestor.obtener_tarea_por_id(task_id) if hasattr(gestor, "obtener_tarea_por_id") else None
    if not task:
        st.warning("La tarea seleccionada ya no existe.")
        st.session_state[TASK_MODE_KEY] = "Listado"
        st.rerun()
        return

    card_begin("Detalle tarea", subtitle=f"{task.client_name} · {task.case_causa}", variant="tight")
    c1, c2 = st.columns(2)
    with c1:
        st.write(f"**Titulo:** {task.title}")
        st.write(f"**Estado:** {task.status}")
        st.write(f"**Vence:** {task.due_date or 'S/D'}")
    with c2:
        st.write(f"**Responsable:** {task.assigned_to or 'S/D'}")
        st.write(f"**Caso:** {task.case_ref}")
        st.write(f"**Prioridad:** {task.priority}")
    if task.description:
        st.caption(task.description)
    a1, a2, a3 = st.columns(3)
    with a1:
        if st.button("Abrir carpeta", key="gestion.agenda.v2.detail.open", width="stretch", type="secondary"):
            if task.case_ref:
                open_path(Path(task.case_ref))
    with a2:
        if st.button("Marcar completada", key="gestion.agenda.v2.detail.done", width="stretch", type="secondary"):
            if has_permission("tasks:write") and hasattr(gestor, "completar_tarea"):
                if gestor.completar_tarea(task.id, actor_ctx=actor_ctx_fn()):
                    st.success("Tarea completada.")
                    st.rerun()
    with a3:
        if st.button("Volver", key="gestion.agenda.detalle.volver", width="stretch", type="secondary"):
            st.session_state[TASK_MODE_KEY] = "Listado"
            st.rerun()
    card_end()


def _render_editar(gestor: Any, actor_ctx_fn: Callable[[], Dict[str, str]]) -> None:
    task_id = str(st.session_state.get(TASK_SELECTED_KEY, "") or "").strip()
    if not task_id:
        st.info("Seleccione una tarea desde listado.")
        st.session_state[TASK_MODE_KEY] = "Listado"
        st.rerun()
        return
    task = gestor.obtener_tarea_por_id(task_id) if hasattr(gestor, "obtener_tarea_por_id") else None
    if not task:
        st.warning("La tarea seleccionada ya no existe.")
        st.session_state[TASK_MODE_KEY] = "Listado"
        st.rerun()
        return
    if not has_permission("tasks:write"):
        st.error("No tiene permiso para editar tareas.")
        return

    card_begin("Editar tarea", subtitle=task.title, variant="tight")
    with st.form("gestion.agenda.v2.edit.form"):
        c1, c2 = st.columns(2)
        with c1:
            title = st.text_input("Titulo", value=task.title)
            due_date = st.text_input("Fecha (YYYY-MM-DD)", value=task.due_date or "")
            status = st.selectbox("Estado", ["pendiente", "en_progreso", "completada", "cancelada"], index=max(0, ["pendiente", "en_progreso", "completada", "cancelada"].index(task.status) if task.status in ["pendiente", "en_progreso", "completada", "cancelada"] else 0))
        with c2:
            assigned_to = st.text_input("Responsable", value=task.assigned_to or "")
            priority = st.selectbox("Prioridad", ["baja", "normal", "alta", "critica"], index=max(0, ["baja", "normal", "alta", "critica"].index(task.priority) if task.priority in ["baja", "normal", "alta", "critica"] else 1))
            description = st.text_area("Descripcion", value=task.description or "", height=90)
        b1, b2 = st.columns(2)
        with b1:
            save = st.form_submit_button("Guardar", width="stretch")
        with b2:
            cancel = st.form_submit_button("Cancelar", width="stretch")
    if cancel:
        st.session_state[TASK_MODE_KEY] = "Detalle"
        st.rerun()
    if save:
        ok = gestor.actualizar_tarea(
            task.id,
            {
                "title": title,
                "description": description,
                "due_date": due_date,
                "status": status,
                "priority": priority,
                "assigned_to": assigned_to,
            },
            actor_ctx=actor_ctx_fn(),
        )
        if ok:
            st.success("Tarea actualizada.")
            st.session_state[TASK_MODE_KEY] = "Detalle"
            st.rerun()
        st.error("No se pudo actualizar la tarea.")
    card_end()


def render_agenda_v2(
    gestor: Any,
    casos: List[Caso],
    *,
    go_route: Callable[[str, str, str | None], None],
    actor_ctx_fn: Callable[[], Dict[str, str]],
) -> None:
    tasks = _load_tasks(gestor)
    section_header(
        "Agenda",
        subtitle="Agenda v2 (tasks-first)",
        meta=[f"Tareas {len(tasks)}", f"Casos {len(casos)}", "Fuente tasks"],
    )

    c1, c2, c3 = st.columns(3)
    with c1:
        if st.button("Ir a Gestion", key="gestion.context.agenda.go_gestion", width="stretch", type="secondary"):
            go_route("Gestion", "listado", None)
    with c2:
        if st.button("Ir a Dashboard", key="gestion.context.agenda.go_dashboard", width="stretch", type="secondary"):
            go_route("Dashboard", "listado", None)
    with c3:
        if st.button("Ir a Configuracion", key="gestion.agenda.v2.go_config", width="stretch", type="secondary"):
            go_route("Configuracion", "listado", None)

    mode = st.radio(
        "Modo",
        ["Listado", "Detalle", "Editar"],
        key=TASK_MODE_KEY,
        horizontal=True,
        label_visibility="collapsed",
    )

    _render_task_create(gestor, actor_ctx_fn)

    if not tasks:
        if mode != "Listado":
            st.session_state[TASK_MODE_KEY] = "Listado"
        vg_empty_state(
            "No hay tareas en la tabla tasks.",
            "Ir a Gestion",
            lambda: go_route("Gestion", "listado", None),
            key="gestion.agenda.v2.empty",
        )
        return

    if mode == "Listado":
        _render_listado(gestor, tasks)
    elif mode == "Detalle":
        _render_detalle(gestor, actor_ctx_fn)
    else:
        _render_editar(gestor, actor_ctx_fn)
