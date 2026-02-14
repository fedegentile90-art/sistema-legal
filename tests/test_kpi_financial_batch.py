from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import audit
import db.release_gate as release_gate


def _case(ref: str, *, fecha_tarea: str = "", expediente: str = "", evento: str = "", fecha_evento: str = ""):
    return SimpleNamespace(
        ruta=Path(ref),
        fecha_tarea=fecha_tarea,
        expediente=expediente,
        evento=evento,
        fecha_evento=fecha_evento,
    )


def test_audit_uses_batch_financial_reader_when_available() -> None:
    cases = [
        _case("db://cases/1", fecha_tarea="2026-02-14", expediente="A", evento="Aud", fecha_evento="2026-02-15"),
        _case("db://cases/2"),
    ]

    class FakeGestor:
        def __init__(self) -> None:
            self.single_calls = 0

        def leer_datos_financieros_batch(self, rutas):
            return {
                str(rutas[0]): {"MONTO_DEMANDADO": "100"},
                str(rutas[1]): {"MONTO_DEMANDADO": ""},
            }

        def leer_datos_financieros(self, _ruta):
            self.single_calls += 1
            return {"MONTO_DEMANDADO": "999"}

    gestor = FakeGestor()
    snapshot = audit.build_operational_kpi_snapshot(gestor, cases)
    kpi = snapshot["kpis"]["COBERTURA_FINANCIERA"]
    assert kpi["completed"] == 1
    assert gestor.single_calls == 0


def test_audit_falls_back_to_single_financial_reader_on_batch_error() -> None:
    cases = [_case("db://cases/1"), _case("db://cases/2")]

    class FakeGestor:
        def __init__(self) -> None:
            self.single_calls = 0

        def leer_datos_financieros_batch(self, _rutas):
            raise RuntimeError("batch unavailable")

        def leer_datos_financieros(self, _ruta):
            self.single_calls += 1
            return {"ESTADO_PAGO": "Pendiente"}

    gestor = FakeGestor()
    snapshot = audit.build_operational_kpi_snapshot(gestor, cases)
    kpi = snapshot["kpis"]["COBERTURA_FINANCIERA"]
    assert kpi["completed"] == 2
    assert gestor.single_calls == 2


def test_release_gate_runtime_kpi_uses_batch_financial_reader(monkeypatch) -> None:
    cases = [
        _case("db://cases/1", fecha_tarea="2026-02-14", expediente="A", evento="Aud", fecha_evento="2026-02-15"),
        _case("db://cases/2"),
    ]

    class FakeGestor:
        def __init__(self) -> None:
            self.single_calls = 0

        def escanear_casos(self):
            return cases

        def leer_datos_financieros_batch(self, rutas):
            return {
                str(rutas[0]): {"HONORARIOS_PACTADOS": "500"},
                str(rutas[1]): {"HONORARIOS_PACTADOS": ""},
            }

        def leer_datos_financieros(self, _ruta):
            self.single_calls += 1
            return {"HONORARIOS_PACTADOS": "999"}

    gestor = FakeGestor()
    monkeypatch.setattr(release_gate, "GestorCasos", lambda: gestor)

    snapshot = release_gate._build_runtime_kpi_snapshot()
    kpi = snapshot["kpis"]["COBERTURA_FINANCIERA"]
    assert kpi["completed"] == 1
    assert gestor.single_calls == 0


def test_release_gate_runtime_kpi_falls_back_on_batch_error(monkeypatch) -> None:
    cases = [_case("db://cases/1"), _case("db://cases/2")]

    class FakeGestor:
        def __init__(self) -> None:
            self.single_calls = 0

        def escanear_casos(self):
            return cases

        def leer_datos_financieros_batch(self, _rutas):
            raise RuntimeError("batch unavailable")

        def leer_datos_financieros(self, _ruta):
            self.single_calls += 1
            return {"ESTADO_PAGO": "Pendiente"}

    gestor = FakeGestor()
    monkeypatch.setattr(release_gate, "GestorCasos", lambda: gestor)

    snapshot = release_gate._build_runtime_kpi_snapshot()
    kpi = snapshot["kpis"]["COBERTURA_FINANCIERA"]
    assert kpi["completed"] == 2
    assert gestor.single_calls == 2
