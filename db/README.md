# Base de Datos PostgreSQL - VACA & GENTILE ERP

## Estado actual

**INTEGRADO (DB-first)** - Backend operativo activo sobre PostgreSQL.

La app usa `repo.py -> repo_db.py` como backend principal.
`DATABASE_URL` debe estar configurada para operacion runtime.
`VG_TEST_DATABASE_URL` debe estar configurada para suites DB aisladas.
Plantilla reproducible: `.env.example` (raiz del repo).

## Requisitos de extensiones

| Extension | Uso | Disponibilidad |
|-----------|-----|----------------|
| `uuid-ossp` | `uuid_generate_v4()` para PKs | Supabase ✓, Render ✓, Railway ✓ |

`CREATE EXTENSION` requiere permisos elevados y se ejecuta **fuera** de la transaccion.
Si falla, usar `pgcrypto` con `gen_random_uuid()` (editar las tablas en schema.sql).

## Proposito

Este directorio contiene:
- schema SQL operativo de PostgreSQL;
- scripts de health/gate/auditoria nocturna;
- pruebas de contrato, smoke y UX para validar operacion DB-first.

## Estructura del schema

### Tablas principales

| Tabla | Descripcion |
|-------|-------------|
| `clients` | Clientes del estudio juridico |
| `cases` | Casos/causas juridicas |
| `documents` | Documentos asociados a casos |
| `tasks` | Tareas y agenda |
| `audit_log` | Log de auditoria de cambios |

### Caracteristicas

- **UUIDs** como claves primarias (portabilidad, no colision)
- **Columna `extra JSONB`** en cada tabla para campos flexibles
- **Triggers `updated_at`** automaticos en todas las tablas
- **Indices** optimizados para consultas frecuentes
- **Vistas** para reportes comunes (tareas vencidas, agenda semanal)

### Mapeo filesystem → base de datos

```
Jerarquia actual:
  AÑO / ESTADO / CLIENTE / FUERO / CAUSA
    └── ficha.json
    └── 01. PRUEBA/
    └── 02. ESCRITOS/
    └── 03. RECIBOS/
    └── 04. OTROS/

Mapeo a tablas:
  cases.year     ← AÑO
  cases.status   ← ESTADO
  clients.name   ← CLIENTE (se creara cliente si no existe)
  cases.fuero    ← FUERO
  cases.causa    ← CAUSA (nombre carpeta)
  cases.*        ← campos de ficha.json
  documents.*    ← archivos en subcarpetas
```

## Como usar (operacion actual)

### 1. Crear la base de datos

```bash
# En Render/Railway, se crea automaticamente
# En local:
createdb vaca_gentile
psql -d vaca_gentile -f db/schema.sql
```

### 2. Configurar variables de entorno

```bash
# Recomendado: copiar .env.example -> .env y ajustar valores
DATABASE_URL=postgresql://user:pass@host:5432/vaca_gentile
VG_TEST_DATABASE_URL=postgresql://user:pass@host:5432/vaca_gentile_test
VG_RELEASE_GATE_MODE=full
VG_QUALITY_GATE_KPI_MODE=warn
VG_QUALITY_GATE_KPI_MIN_CASES=1
VG_SECURITY_GATE_MODE=warn
VG_DB_APP_ROLE=vg_app
VG_DB_TEST_ROLE=vg_test
VG_SECURITY_GATE_REQUIRE_TEST_ROLE_SPLIT=0
VG_PERFORMANCE_GATE_MODE=warn
VG_PERFORMANCE_GATE_MAX_SELECT1_MS=250
VG_PERFORMANCE_GATE_MAX_CORE_COUNTS_MS=600
VG_PERFORMANCE_GATE_MAX_RECENT_DOCS_MS=800
VG_PERFORMANCE_GATE_MAX_RECENT_CASES_MS=600
VG_PERFORMANCE_GATE_MAX_DOCS_PER_CASE=300
VG_PERFORMANCE_GATE_MAX_AUDIT_ROWS=200000
VG_BACKUP_DIR=
VG_BACKUP_DRILL_SCHEMA_PREFIX=restore_drill
VG_SUITE_TIMEOUT_SEC=900
VG_STEP_TIMEOUT_SEC=1200
VG_DOTENV_AUTOLOAD=1
```

Validar contrato de entorno (reproducible):

```bash
python db/env_contract.py --profile app
python db/env_contract.py --profile daily_ops
python db/env_contract.py --profile release_gate_full
python db/env_contract.py --profile backup_restore_drill
```

Bootstrap opcional de DB de pruebas (crea DB test si no existe, aplica schema y puede persistir `.env`):

```bash
python db/setup_test_db.py --write-dotenv
```

### 3. Validar operacion DB-first

```bash
python db/contract_test.py
python db/ops_behavior_test.py
python db/ux_gestion_regression_test.py
python db/ux_phase2_test.py
python db/smoke_test.py
```

## Archivos

| Archivo | Descripcion |
|---------|-------------|
| `schema.sql` | DDL completo (tablas, indices, triggers, vistas) |
| `kpi_snapshot.py` | Snapshot KPI operativo (`FECHA_TAREA`, `EXPEDIENTE`, `EVENTO/FECHA_EVENTO`, cobertura financiera) |
| `security_baseline.py` | Auditoria base de seguridad DB (auth/roles/least privilege) |
| `performance_capacity.py` | Baseline de performance/capacidad DB (latencia + volumen core) |
| `backup_restore_drill.py` | Backup logico + drill de restore en schema temporal de DB test |
| `setup_test_db.py` | Bootstrap de `VG_TEST_DATABASE_URL` (create DB + schema + preflight) |
| `nightly_audit.py` | Auditoria diaria/nocturna + persistencia de historial (`audit_history.csv`) |
| `release_gate.py` | QA Gate de release (`contract`, `ux`, `smoke`) |
| `env_contract.py` | Contrato ejecutable de entorno por perfil (`app`, `daily_ops`, `release_gate`, `db_suite`) |
| `ops_behavior_test.py` | Suite conductual operativa (env_contract + DailyOps por modo) |
| `README.md` | Este archivo |

## Snapshot KPI operativo

Comando:

```bash
python db/kpi_snapshot.py
```

Salidas:
- resumen por consola con estado vs objetivos;
- `db/snapshots/kpi_snapshot_YYYYMMDD_HHMMSS.json`;
- `db/snapshots/kpi_snapshot_YYYYMMDD_HHMMSS.csv`.

## QA Gate de release

Comando unico:

```bash
python db/release_gate.py
python db/release_gate.py --mode read_only
python db/release_gate.py --mode full
python db/release_gate.py --mode full --kpi-mode enforce
python db/release_gate.py --mode full --security-mode enforce
python db/release_gate.py --mode full --performance-mode enforce
```

Suites core ejecutadas por el gate:
- `python db/contract_test.py`
- `python db/ux_gestion_regression_test.py`
- `python db/ux_phase2_test.py`
- `python db/smoke_test.py`

Modo del gate:
- `full` (default): ejecuta todas las suites core.
- `read_only`: ejecuta suites de lectura y marca suites DB como `SKIPPED`.
- configuracion por env opcional: `VG_RELEASE_GATE_MODE=read_only|full` (CLI `--mode` tiene prioridad).

Quality gate KPI:
- evalua KPI operativo sobre `DATABASE_URL` runtime con objetivos:
  - `FECHA_TAREA >= 60%`
  - `EXPEDIENTE >= 70%`
  - `EVENTO/FECHA_EVENTO >= 40%`
  - `COBERTURA_FINANCIERA >= 70%`
- modo configurable por env/CLI:
  - `VG_QUALITY_GATE_KPI_MODE=off|warn|enforce` (CLI `--kpi-mode` tiene prioridad; default `warn`).
  - `VG_QUALITY_GATE_KPI_MIN_CASES` define muestra minima para evaluar KPI (default `1`).
- comportamiento:
  - `warn`: reporta desvio KPI sin bloquear release.
  - `enforce`: si algun KPI queda bajo objetivo, el gate finaliza en `FAIL`.
  - `off`: omite evaluacion KPI.
- en `read_only`, el KPI gate se informa como `SKIPPED`.

Security gate base:
- audita postura auth/roles/least-privilege sobre DB runtime/test.
- detecta desvio en:
  - superuser/CREATEROLE/CREATEDB activos en rol operativo;
  - permiso `CREATE` en schema `public`;
  - permiso `TRUNCATE` en tablas core (`clients`, `cases`, `documents`, `tasks`, `audit_log`);
  - faltantes de privilegios CRUD requeridos para operacion.
- modo configurable:
  - `VG_SECURITY_GATE_MODE=off|warn|enforce` (CLI `--security-mode` tiene prioridad; default `warn`).
  - `VG_DB_APP_ROLE` y `VG_DB_TEST_ROLE` permiten validar rol esperado por entorno.
  - `VG_SECURITY_GATE_REQUIRE_TEST_ROLE_SPLIT=0|1` permite exigir roles distintos runtime/test.
- comportamiento:
  - `warn`: reporta desvio de seguridad sin bloquear release.
  - `enforce`: bloquea release ante desvio de seguridad.
  - `off`: omite auditoria de seguridad.

Comando standalone opcional:
```bash
python db/security_baseline.py --mode warn
```

Performance/capacidad gate:
- audita latencia de consultas core read-only sobre DB runtime.
- revisa guardrails de capacidad:
  - `documents_per_case`;
  - volumen de `audit_log`.
- modo configurable:
  - `VG_PERFORMANCE_GATE_MODE=off|warn|enforce` (CLI `--performance-mode` tiene prioridad; default `warn`).
  - umbrales opcionales:
    - `VG_PERFORMANCE_GATE_MAX_SELECT1_MS`
    - `VG_PERFORMANCE_GATE_MAX_CORE_COUNTS_MS`
    - `VG_PERFORMANCE_GATE_MAX_RECENT_DOCS_MS`
    - `VG_PERFORMANCE_GATE_MAX_RECENT_CASES_MS`
    - `VG_PERFORMANCE_GATE_MAX_DOCS_PER_CASE`
    - `VG_PERFORMANCE_GATE_MAX_AUDIT_ROWS`
- comportamiento:
  - `warn`: reporta desvio de performance/capacidad sin bloquear release.
  - `enforce`: bloquea release ante desvio de performance/capacidad.
  - `off`: omite auditoria de performance/capacidad.

Comando standalone opcional:
```bash
python db/performance_capacity.py --mode warn
```

## Backup + restore drills (P5-03)

Comando recomendado (drill completo):

```bash
python db/backup_restore_drill.py
```

Modos utiles:

```bash
python db/backup_restore_drill.py --backup-only
python db/backup_restore_drill.py --restore-only --backup-file db/snapshots/db_backup/db_backup_YYYYMMDD_HHMMSS.json
```

Contrato operativo:
- exporta backup logico JSON de tablas core (`clients`, `cases`, `documents`, `tasks`, `audit_log`);
- restaura backup en una schema temporal de `VG_TEST_DATABASE_URL`;
- valida conteos por tabla (`expected_rows == restored_rows`);
- por default elimina la schema temporal al finalizar (no toca datos runtime).

Variables opcionales:
- `VG_BACKUP_DIR`: directorio de salida del backup (default `db/snapshots/db_backup`);
- `VG_BACKUP_DRILL_SCHEMA_PREFIX`: prefijo para schema temporal de restore drill.

Timeout por suite:
- env opcional `VG_SUITE_TIMEOUT_SEC` (default: `900` segundos).
- si una suite excede el timeout, se marca `TIMEOUT` y el gate finaliza en `FAIL`.

Politica de suites DB:
- `contract_test` se ejecuta siempre.
- En modo `full`, las suites DB (`ux_*` y `smoke_test`) requieren `VG_TEST_DATABASE_URL`.
- `VG_TEST_DATABASE_URL` debe apuntar a una DB de pruebas dedicada (ej: `*_test`, `*_qa`, `*_ci`, `*_sandbox`) y no debe coincidir con `DATABASE_URL`.
- En modo `full`, si falta `VG_TEST_DATABASE_URL` o viola el contrato, esas suites quedan `BLOCKED` y el resultado final del gate es `FAIL` (exit code != 0).
- En modo `full`, si `VG_TEST_DATABASE_URL` existe pero la DB de pruebas no responde, el preflight bloquea suites DB (`BLOCKED`) y el gate finaliza `FAIL`.
- En modo `read_only`, las suites DB no se ejecutan y figuran `SKIPPED` por seguridad operativa.

Salida final del gate:
- `RELEASE QA GATE: PASS` con exit code `0`.
- `RELEASE QA GATE: FAIL` con exit code distinto de `0`.

## Auditoria diaria + tendencia

Comando:

```bash
python db/nightly_audit.py
```

Resultado:
- ejecuta auditoria integral + snapshot KPI operativo;
- guarda snapshot JSON en `db/snapshots/audit_daily/`;
- actualiza historial CSV en `db/snapshots/audit_history.csv`.
- en modo DB corre preflight (SELECT 1) y falla temprano si la conexion no esta disponible.

Uso operativo:
- ejecutar este comando de forma programada 1 vez por dia (cron/Task Scheduler);
- la vista `Auditoria` consume `audit_history.csv` para mostrar tendencia de errores/warnings.
- la UI marca alerta de degradacion cuando errores/warnings del dia empeoran vs baseline de 7 dias.
- la UI permite export operativo de hallazgos con filtros por nivel/codigo/fecha en CSV/JSON.

## Runner operativo diario (Task Scheduler)

Comando recomendado en Windows:

```bash
RUN_ERP.ps1 -DailyOps
```

Alternativa:

```bash
RUN_ERP.cmd ops
```

Comportamiento:
- valida contrato de entorno: `python db/env_contract.py --profile daily_ops`;
- ejecuta `python db/nightly_audit.py`;
- si falla, corta flujo y no ejecuta gate;
- si pasa, ejecuta `python db/release_gate.py`;
- el gate aplica quality gate KPI (segun `VG_QUALITY_GATE_KPI_MODE`);
- guarda log diario en `logs/ops_YYYYMMDD.log`.
- aplica timeout por paso con env opcional `VG_STEP_TIMEOUT_SEC` (default: `1200` segundos).
- ante timeout en `nightly_audit` o `release_gate`, corta flujo con causa explicita en log.
- si falla `env_contract_daily_ops`, corta flujo antes de `nightly_audit`.
- emite eventos estructurados `[OBS]` con `run_id`, `stage`, `suite` para correlacion de pasos.

Codigos de salida:
- `0`: nightly + gate en PASS.
- `20`: fallo en nightly audit (incluye preflight DB).
- `30`: fallo/bloqueo en release gate.
- `99`: error de runtime del runner.

## CI con PostgreSQL efimero (P4-02)

Workflow:
- `.github/workflows/ci-db.yml`

Contrato CI:
- levanta PostgreSQL efimero (`postgres:16`) como servicio del job;
- define `DATABASE_URL` runtime y `VG_TEST_DATABASE_URL` aislada (`*_ci_test`);
- aplica `db/schema.sql` en ambas DBs (runtime + test);
- valida `python db/env_contract.py --profile release_gate_full`;
- ejecuta `python db/release_gate.py --mode full`.

Objetivo:
- ejecutar suites DB en entorno limpio y reproducible, sin depender de datos operativos.

## Observabilidad estructurada (P4-03)

Campos base de correlacion:
- `run_id`: identificador unico por corrida operativa/gate.
- `stage`: etapa de ejecucion (`gate_start`, `db_preflight`, `suite_start`, `suite_end`, `daily_ops_start`, `daily_ops_end`, etc.).
- `suite`: unidad ejecutada (`contract_test`, `smoke_test`, `nightly_audit`, `release_gate`, etc.).

Donde se emite:
- `RUN_ERP.ps1 -DailyOps` agrega lineas `[OBS]` al log diario `logs/ops_YYYYMMDD.log`.
- `db/release_gate.py` imprime eventos `[OBS]` en consola por suite y resumen final.
- `db/nightly_audit.py` imprime eventos `[OBS]` para preflight, snapshot y cierre.

Uso rapido:
- buscar una corrida especifica: filtrar por `run_id` en `logs/ops_YYYYMMDD.log`.
- diagnosticar etapa fallida: revisar `stage` + `suite` con `status=FAIL|TIMEOUT|BLOCKED`.

## Notas tecnicas

### Por que JSONB en `extra`?

Permite agregar campos sin modificar el schema:
```sql
-- Agregar campo personalizado a un caso
UPDATE cases
SET extra = extra || '{"prioridad_interna": "alta"}'::jsonb
WHERE id = '...';

-- Consultar campo personalizado
SELECT * FROM cases
WHERE extra->>'prioridad_interna' = 'alta';
```

### Por que UUIDs?

- No dependen de secuencias (facil migracion)
- No revelan informacion de orden
- Funcionan en entornos distribuidos
- Compatibles con sincronizacion offline

### Compatibilidad con filesystem

La columna `cases.fs_path` guarda la ruta original del filesystem.
Esto permite:
- Migracion gradual
- Rollback si hay problemas
- Referencia para archivos que siguen en disco

## Proximos pasos (P3+)

1. [x] Timeouts operativos en `release_gate` y `RUN_ERP.ps1 -DailyOps`.
2. [x] Aislamiento estricto de suites DB para no tocar datos operativos.
3. [x] Release gate seguro por modo (`read_only`/`full`).
4. [x] Contrato de entorno reproducible + sync documental.
5. [x] Tests operativos conductuales.
6. [x] CI con PostgreSQL efimero.
7. [x] Observabilidad estructurada (`run_id`, `stage`, `suite`).
8. [x] Quality gate KPI configurable (`off|warn|enforce`).
9. [x] Seguridad base auth/roles/least privilege (`off|warn|enforce`).
10. [x] Performance/capacidad DB (`off|warn|enforce` + umbrales por env).

---
