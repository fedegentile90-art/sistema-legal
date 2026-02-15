import inspect

from repo_db import GestorCasosDB


def test_case_updates_include_dual_write_sync_hook() -> None:
    src = inspect.getsource(GestorCasosDB.actualizar_campos_ficha)
    assert "_sync_primary_task_for_case" in src


def test_task_updates_include_case_sync_hook() -> None:
    src = inspect.getsource(GestorCasosDB.actualizar_tarea)
    assert "_sync_case_fields_from_primary_task" in src

