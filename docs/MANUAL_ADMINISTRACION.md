# Manual Operativo - Rol Administracion

Fecha de referencia: 2026-02-13

## 1) Inicio rapido

1. Abrir la app con `RUN_ERP.cmd` o `python -m streamlit run app.py`.
2. (Recomendado) Crear acceso directo en Escritorio:
   - desde UI: `Configuracion > Operativo > Crear acceso directo en Escritorio`;
   - o por script: `CREATE_DESKTOP_SHORTCUT.cmd`.
3. Si se va a ejecutar gate/suites DB en modo `full`, preparar DB de pruebas:
   - desde UI: `Configuracion > Operativo > Preparar DB de pruebas`;
   - o por script: `python db/setup_test_db.py --write-dotenv`.
4. Verificar acceso a rutas:
   - `Gestion`
   - `Agenda`
   - `Finanzas`
   - `Auditoria`
5. Confirmar autoload de `.env` en launcher:
   - `VG_DOTENV_AUTOLOAD=1` en `.env` (default recomendado).
6. Confirmar experiencia visual:
   - `VG_UI_REVAMP_V2=1` para rediseño profundo activo.
   - rollback visual inmediato: `VG_UI_REVAMP_V2=0`.

## 2) Alta y mantenimiento administrativo (Gestion)

### Alta administrativa de caso

1. Ir a `Gestion > Casos`.
2. Crear caso con datos base:
   - anio, estado, cliente, fuero, causa.
3. Guardar y confirmar visibilidad en listado.

### Edicion administrativa

1. Seleccionar caso en `Gestion > Casos`.
2. Modo `Editar`.
3. Completar al menos:
   - `RESPONSABLE`,
   - `TAREA_PENDIENTE`,
   - `FECHA_TAREA`,
   - `EXPEDIENTE` (si ya existe en mesa/organismo).
4. Guardar y verificar que no haya errores de persistencia.

## 3) Rutina de agenda diaria (Agenda)

1. Ir a `Agenda` al inicio de jornada.
2. Priorizar:
   - vencidas;
   - proximas 7 dias;
   - proximas 30 dias.
3. Si no hay resultados y existen tareas:
   - ejecutar `Limpiar filtros`.
4. Confirmar responsable y fecha de cada tarea pendiente.

## 4) Carga financiera (Finanzas)

### Carga manual por caso

1. Ir a `Finanzas`.
2. Seleccionar caso.
3. Cargar:
   - `MONTO_DEMANDADO`,
   - `HONORARIOS_PACTADOS`,
   - `ESTADO_PAGO`.
4. Guardar.

### Carga masiva por CSV

1. Preparar CSV con columnas requeridas:
   - referencia de caso (`_RUTA` o alias aceptado),
   - `MONTO_DEMANDADO`,
   - `HONORARIOS_PACTADOS`,
   - `ESTADO_PAGO`.
2. Ir a `Finanzas` y cargar archivo.
3. Ejecutar `dry-run` y corregir filas invalidas.
4. Ejecutar `apply`.
5. Confirmar resumen:
   - total,
   - updated,
   - omitted,
   - errors.

## 5) Auditoria operativa y tendencia

### Auditoria manual desde UI

1. Ir a `Auditoria`.
2. Ejecutar `Ejecutar auditoria`.
3. Revisar:
   - resumen,
   - hallazgos,
   - KPI operativo,
   - tendencia diaria.

### Auditoria diaria/nocturna programada

1. Ejecutar al menos una vez por dia:
   - `RUN_ERP.ps1 -DailyOps`
   - (alternativa) `RUN_ERP.cmd ops`
   - (preflight manual recomendado) `python db/env_contract.py --profile daily_ops`
   - (verificacion conductual semanal) `python db/ops_behavior_test.py`
2. Si falla preflight DB (stage `connect` o `query`), revisar:
   - `DATABASE_URL`;
   - `VG_TEST_DATABASE_URL` (debe apuntar a DB de pruebas dedicada para suites DB);
   - conectividad de red/firewall;
   - disponibilidad del servicio PostgreSQL.
3. Si aparece `TIMEOUT` en log operativo:
   - revisar saturacion de host/DB;
   - aumentar timeout si corresponde:
     - `set VG_STEP_TIMEOUT_SEC=1200` (runner DailyOps),
     - `set VG_SUITE_TIMEOUT_SEC=900` (release gate).
4. Si se necesita gate de lectura (sin suites DB), usar:
   - `python db/release_gate.py --mode read_only`
   - o `set VG_RELEASE_GATE_MODE=read_only`
5. Para gate completo de release, usar:
    - `python db/release_gate.py --mode full`
    - y asegurar `VG_TEST_DATABASE_URL` valida + DB de pruebas disponible.
6. Si `VG_TEST_DATABASE_URL` no existe o no cumple contrato:
   - correr `python db/setup_test_db.py --write-dotenv`;
   - volver a validar `python db/env_contract.py --profile daily_ops`.
7. Politica KPI del gate:
   - modo visible (no bloqueante): `set VG_QUALITY_GATE_KPI_MODE=warn`
   - modo bloqueante: `set VG_QUALITY_GATE_KPI_MODE=enforce`
   - muestra minima para evaluar KPI: `set VG_QUALITY_GATE_KPI_MIN_CASES=1`
   - override por comando: `python db/release_gate.py --mode full --kpi-mode enforce --kpi-min-cases 10`
8. Politica de seguridad del gate (auth/roles/least privilege):
   - modo visible (no bloqueante): `set VG_SECURITY_GATE_MODE=warn`
   - modo bloqueante: `set VG_SECURITY_GATE_MODE=enforce`
   - rol esperado runtime (opcional): `set VG_DB_APP_ROLE=vg_app`
   - rol esperado test (opcional): `set VG_DB_TEST_ROLE=vg_test`
   - exigir roles runtime/test distintos: `set VG_SECURITY_GATE_REQUIRE_TEST_ROLE_SPLIT=1`
   - override por comando: `python db/release_gate.py --mode full --security-mode enforce`
9. Politica de performance/capacidad del gate:
   - modo visible (no bloqueante): `set VG_PERFORMANCE_GATE_MODE=warn`
   - modo bloqueante: `set VG_PERFORMANCE_GATE_MODE=enforce`
   - umbral select_1: `set VG_PERFORMANCE_GATE_MAX_SELECT1_MS=250`
   - umbral conteos core: `set VG_PERFORMANCE_GATE_MAX_CORE_COUNTS_MS=600`
   - umbral docs recientes: `set VG_PERFORMANCE_GATE_MAX_RECENT_DOCS_MS=800`
   - umbral casos recientes: `set VG_PERFORMANCE_GATE_MAX_RECENT_CASES_MS=600`
   - umbral docs/caso: `set VG_PERFORMANCE_GATE_MAX_DOCS_PER_CASE=300`
   - umbral audit_log: `set VG_PERFORMANCE_GATE_MAX_AUDIT_ROWS=200000`
   - override por comando: `python db/release_gate.py --mode full --performance-mode enforce`
10. Confirmar generacion de artefactos:
   - `db/snapshots/audit_daily/audit_snapshot_latest.json`
   - `db/snapshots/audit_history.csv`
11. Revisar trazabilidad estructurada del run:
   - abrir `logs/ops_YYYYMMDD.log`;
   - ubicar lineas `[OBS]` y tomar `run_id`;
   - seguir `stage`/`suite` hasta detectar primer `status=FAIL|TIMEOUT|BLOCKED`.
12. Validar que la tendencia en UI refleje el ultimo dia.
13. Si aparece alerta de degradacion (leve/moderada/critica), priorizar correccion segun sugerencias del panel.
14. Ejecutar drill de backup/restore al menos semanalmente:
   - `python db/backup_restore_drill.py`
   - validar cierre con `BACKUP RESTORE DRILL: PASS`.

### Codigos de salida del runner diario

- `0`: auditoria y gate en PASS.
- `20`: fallo en `nightly_audit` (incluye preflight DB).
- `30`: `release_gate` en FAIL/BLOCKED.
- `99`: error de runtime del launcher.

Notas:
- contrato de entorno diario: `python db/env_contract.py --profile daily_ops`.
- timeout en `nightly_audit` retorna `20`.
- timeout en `release_gate` retorna `30`.
- para correlacion operativa, usar `run_id` de lineas `[OBS]` (campos: `run_id`, `stage`, `suite`).

### Export operativo de hallazgos

1. Ir a `Auditoria`.
2. En el bloque `Export operativo de hallazgos`, aplicar filtros:
   - nivel (`ERROR/WARN/INFO`);
   - codigo (parcial);
   - fecha desde/hasta.
3. Descargar:
   - CSV operativo para planilla;
   - JSON operativo con metadata de snapshot/backend.

## 6) Gate de release (cuando aplique)

Antes de una entrega interna/externa ejecutar:

- `python db/env_contract.py --profile release_gate_full`
- `python db/env_contract.py --profile backup_restore_drill`
- `python db/release_gate.py`
- `python db/release_gate.py --mode full`
- `python db/security_baseline.py --mode warn`
- `python db/performance_capacity.py --mode warn`
- `python db/backup_restore_drill.py`

Criterio:

- `PASS` habilita release.
- `FAIL` bloquea release hasta resolver suites core.
- En `full`, si una suite DB figura `BLOCKED`, tratarlo como bloqueo operativo (env de test o conectividad DB de pruebas).
- En `read_only`, suites DB figuran `SKIPPED`; usar solo para verificacion no destructiva.
- Variables esperadas:
  - runtime: `DATABASE_URL`;
  - suites DB (`full`): `VG_TEST_DATABASE_URL` (no debe coincidir con `DATABASE_URL`);
  - modo gate opcional: `VG_RELEASE_GATE_MODE` (`read_only`/`full`, default `full`).
  - politica KPI gate: `VG_QUALITY_GATE_KPI_MODE` (`off`/`warn`/`enforce`, default `warn`).
  - muestra minima KPI gate: `VG_QUALITY_GATE_KPI_MIN_CASES` (entero >= 0, default `1`).
  - politica security gate: `VG_SECURITY_GATE_MODE` (`off`/`warn`/`enforce`, default `warn`).
  - roles esperados opcionales: `VG_DB_APP_ROLE`, `VG_DB_TEST_ROLE`.
  - exigir roles runtime/test distintos: `VG_SECURITY_GATE_REQUIRE_TEST_ROLE_SPLIT` (`0`/`1`, default `0`).
  - politica performance gate: `VG_PERFORMANCE_GATE_MODE` (`off`/`warn`/`enforce`, default `warn`).
  - umbral select_1: `VG_PERFORMANCE_GATE_MAX_SELECT1_MS`.
  - umbral conteos core: `VG_PERFORMANCE_GATE_MAX_CORE_COUNTS_MS`.
  - umbral docs recientes: `VG_PERFORMANCE_GATE_MAX_RECENT_DOCS_MS`.
  - umbral casos recientes: `VG_PERFORMANCE_GATE_MAX_RECENT_CASES_MS`.
  - umbral docs por caso: `VG_PERFORMANCE_GATE_MAX_DOCS_PER_CASE`.
  - umbral volumen audit_log: `VG_PERFORMANCE_GATE_MAX_AUDIT_ROWS`.
  - backup drill opcional: `VG_BACKUP_DIR` y `VG_BACKUP_DRILL_SCHEMA_PREFIX`.
- KPI gate:
  - en `warn` reporta desvio KPI sin bloquear release;
  - en `enforce` bloquea release cuando KPI objetivo no se cumple;
  - en `read_only` se reporta `SKIPPED`.
- Security gate:
  - en `warn` reporta desvio auth/roles/least-privilege sin bloquear release;
  - en `enforce` bloquea release por desvio de seguridad;
  - en `off` se reporta `SKIPPED`.
- Performance gate:
  - en `warn` reporta desvio de latencia/capacidad sin bloquear release;
  - en `enforce` bloquea release por desvio de performance/capacidad;
  - en `off` se reporta `SKIPPED`.
- CI recomendado:
  - usar `.github/workflows/ci-db.yml` para validar el gate con PostgreSQL efimero;
  - el workflow aplica `db/schema.sql` en DB runtime y DB test, y ejecuta `release_gate --mode full`.
