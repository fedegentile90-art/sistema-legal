from app import workspace_route_access
from nav import available_routes


def test_available_routes_filters_and_fallback() -> None:
    visible = available_routes(lambda route: route in {"Dashboard", "Agenda"})
    assert visible == ["Dashboard", "Agenda"]

    fallback = available_routes(lambda _route: False)
    assert fallback == ["Dashboard"]


def test_workspace_route_access_rejects_unknown_route() -> None:
    enabled, reason = workspace_route_access("NoExiste", db_ready=True)
    assert enabled is False
    assert "no valida" in reason.lower()


def test_workspace_route_access_respects_rbac(monkeypatch) -> None:
    monkeypatch.setattr("app.can_access_route", lambda route: route != "Gestion")
    monkeypatch.setattr("app.is_db_mode", lambda: False)

    enabled, reason = workspace_route_access("Gestion", db_ready=True)
    assert enabled is False
    assert "rol" in reason.lower()


def test_workspace_route_access_db_degraded_blocks_operational_routes(monkeypatch) -> None:
    monkeypatch.setattr("app.can_access_route", lambda route: True)
    monkeypatch.setattr("app.is_db_mode", lambda: True)

    enabled_gestion, _ = workspace_route_access("Gestion", db_ready=False)
    enabled_agenda, _ = workspace_route_access("Agenda", db_ready=False)
    enabled_dashboard, _ = workspace_route_access("Dashboard", db_ready=False)
    enabled_auditoria, _ = workspace_route_access("Auditoria", db_ready=False)

    assert enabled_gestion is False
    assert enabled_agenda is False
    assert enabled_dashboard is True
    assert enabled_auditoria is True


def test_workspace_route_access_non_db_mode_allows_route(monkeypatch) -> None:
    monkeypatch.setattr("app.can_access_route", lambda route: True)
    monkeypatch.setattr("app.is_db_mode", lambda: False)

    enabled, reason = workspace_route_access("Gestion", db_ready=False)
    assert enabled is True
    assert reason == ""
