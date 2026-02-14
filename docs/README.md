# Manuales Operativos por Rol

Fecha de referencia: 2026-02-13

Este directorio concentra guias cortas para operacion diaria del sistema:

- `docs/MANUAL_ABOGADO.md`
- `docs/MANUAL_ADMINISTRACION.md`

Backend operativo actual:
- DB-first (`repo.py` delega en `repo_db.py`).
- `DATABASE_URL` es requisito para operacion runtime (app/procesos operativos).
- `VG_TEST_DATABASE_URL` es requisito para suites DB (`release_gate`, `ux_*`, `smoke_test`).
- Plantilla reproducible sugerida: `.env.example` (copiar a `.env` con valores locales).

## Alcance

Los dos manuales cubren:

- alta y edicion de casos;
- rutina de agenda diaria;
- carga financiera (manual y CSV);
- auditoria operativa y tendencia diaria.

## Comandos utiles

- Abrir la app:
  - `RUN_ERP.cmd` (Windows)
  - `python -m streamlit run app.py`
  - UI revamp toggle: `VG_UI_REVAMP_V2=1` (nuevo) / rollback visual inmediato `VG_UI_REVAMP_V2=0`
- Crear acceso directo en Escritorio (Windows):
  - `CREATE_DESKTOP_SHORTCUT.cmd`
  - `powershell -NoProfile -ExecutionPolicy Bypass -File .\CREATE_DESKTOP_SHORTCUT.ps1 -Force`
- Runner operativo diario (auditoria + gate):
  - `RUN_ERP.ps1 -DailyOps`
  - `RUN_ERP.cmd ops`
- Auditoria diaria/nocturna:
  - `python db/nightly_audit.py`
- QA gate de release:
  - `python db/release_gate.py`
  - `python db/release_gate.py --mode read_only`
  - `python db/release_gate.py --mode full`
  - `python db/release_gate.py --mode full --kpi-mode enforce`
  - `python db/release_gate.py --mode full --security-mode enforce`
  - `python db/release_gate.py --mode full --performance-mode enforce`
- Contrato de entorno reproducible:
  - `python db/env_contract.py --profile app`
  - `python db/env_contract.py --profile daily_ops`
  - `python db/env_contract.py --profile release_gate_full`
  - `python db/env_contract.py --profile backup_restore_drill`
- Bootstrap de DB de pruebas aislada:
  - `python db/setup_test_db.py --write-dotenv`
  - (alternativa UI) `Configuracion > Operativo > Preparar DB de pruebas`
- Baseline de seguridad DB:
  - `python db/security_baseline.py --mode warn`
- Baseline de performance/capacidad DB:
  - `python db/performance_capacity.py --mode warn`
- Backup + restore drill:
  - `python db/backup_restore_drill.py`
  - `python db/backup_restore_drill.py --backup-only`
- Suite conductual operativa:
  - `python db/ops_behavior_test.py`
- Contratos UI (visual/orden/texto/persistencia):
  - `python -m pytest -q tests/test_ui_theme_contract.py tests/test_ui_visual_order_contract.py tests/test_ui_text_encoding_contract.py tests/test_ui_theme_persistence_db.py`
- CI DB-first (PostgreSQL efimero):
  - workflow `.github/workflows/ci-db.yml`
  - ejecuta `python db/env_contract.py --profile release_gate_full`
  - ejecuta `python db/release_gate.py --mode full`
- Trazabilidad de corrida (observabilidad):
- `RUN_ERP.ps1 -DailyOps` emite lineas `[OBS]` con `run_id`, `stage`, `suite`
- `db/release_gate.py` y `db/nightly_audit.py` comparten `run_id` via env `VG_RUN_ID`
- `RUN_ERP.ps1` auto-carga variables desde `.env` por defecto (`VG_DOTENV_AUTOLOAD=1`).
- Si ejecutas `python db/*.py` directo desde consola, debes tener variables exportadas en esa sesion.

Notas operativas:
- `db/nightly_audit.py` ejecuta preflight DB (conexion + `SELECT 1`) y falla temprano si la DB no esta disponible.
- `db/release_gate.py` soporta modos `read_only` y `full` (default `full`, env `VG_RELEASE_GATE_MODE`).
- En `full`, `db/release_gate.py` bloquea suites DB (`BLOCKED`) si falta `VG_TEST_DATABASE_URL`, si no cumple contrato de aislamiento o si el preflight DB de pruebas falla.
- En `read_only`, suites DB quedan `SKIPPED` por seguridad y solo corren suites de lectura.
- `db/release_gate.py` integra quality gate KPI configurable:
  - `VG_QUALITY_GATE_KPI_MODE=off|warn|enforce` (default `warn`),
  - `VG_QUALITY_GATE_KPI_MIN_CASES` (default `1`).
- En `warn` informa desvio KPI sin bloquear; en `enforce` bloquea release si KPI objetivo no se cumple.
- `db/release_gate.py` integra security gate configurable:
  - `VG_SECURITY_GATE_MODE=off|warn|enforce` (default `warn`),
  - `VG_DB_APP_ROLE` / `VG_DB_TEST_ROLE` para validar rol esperado,
  - `VG_SECURITY_GATE_REQUIRE_TEST_ROLE_SPLIT=0|1` para exigir roles runtime/test distintos.
- En `warn` informa desvio de auth/roles/least-privilege sin bloquear; en `enforce` bloquea release.
- `db/release_gate.py` integra performance gate configurable:
  - `VG_PERFORMANCE_GATE_MODE=off|warn|enforce` (default `warn`),
  - `VG_PERFORMANCE_GATE_MAX_SELECT1_MS`,
  - `VG_PERFORMANCE_GATE_MAX_CORE_COUNTS_MS`,
  - `VG_PERFORMANCE_GATE_MAX_RECENT_DOCS_MS`,
  - `VG_PERFORMANCE_GATE_MAX_RECENT_CASES_MS`,
  - `VG_PERFORMANCE_GATE_MAX_DOCS_PER_CASE`,
  - `VG_PERFORMANCE_GATE_MAX_AUDIT_ROWS`.
- En `warn` informa desvio de performance/capacidad sin bloquear; en `enforce` bloquea release.
- `db/performance_capacity.py` ejecuta baseline standalone de latencia/capacidad runtime.
- `db/backup_restore_drill.py` ejecuta backup logico y restore drill en schema temporal de DB test.
- Variables opcionales de drill:
  - `VG_BACKUP_DIR` (directorio de artefactos backup),
  - `VG_BACKUP_DRILL_SCHEMA_PREFIX` (prefijo de schema temporal).
- `db/env_contract.py` valida coherencia de entorno por perfil y devuelve `0` (PASS) o `2` (FAIL de contrato).
- `db/ops_behavior_test.py` valida comportamiento real de `env_contract` y `RUN_ERP.ps1 -DailyOps` (cortes y PASS por modo).
- `.github/workflows/ci-db.yml` valida gate DB-first en CI con PostgreSQL efimero y DB de pruebas aislada.
- `RUN_ERP.ps1 -DailyOps` corta flujo si falla `nightly_audit` o `release_gate`.
- `RUN_ERP.ps1 -DailyOps` corta flujo antes de nightly si falla `env_contract_daily_ops`.
- `RUN_ERP.ps1 -DailyOps` escribe logs en `logs/ops_YYYYMMDD.log`.
- `RUN_ERP.ps1 -DailyOps`, `db/nightly_audit.py` y `db/release_gate.py` emiten eventos `[OBS]` con `run_id/stage/suite`.
- En `Auditoria > Tendencia diaria`, el sistema muestra alerta de degradacion (leve/moderada/critica) contra baseline de 7 dias.
- En `Auditoria`, se puede exportar hallazgos operativos filtrando por nivel/codigo/fecha en CSV y JSON (con metadata de snapshot/backend).
- En `Configuracion > Operativo`, hay acciones directas para:
  - crear acceso directo del launcher en Escritorio;
  - preparar DB de pruebas y persistir `VG_TEST_DATABASE_URL` en `.env`;
  - activar/desactivar auto-guardado en runtime.
