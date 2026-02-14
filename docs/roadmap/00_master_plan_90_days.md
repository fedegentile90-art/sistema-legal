# Plan Maestro 90 Dias (DB-first)

Ventana de referencia: 2026-02-14 a 2026-05-15.

## Estrategia
1. Carril Operacion: trabajar todos los dias sin cortes.
2. Carril Mejora Diaria: 1 lote pequeno por dia, verificable y reversible.

## Decisiones cerradas
- Alcance inicial: MVP operativo.
- Ritmo: lote diario.
- Riesgo: seguridad progresiva.
- Compatibilidad: sin cambios breaking en semana 1.

## Baseline verificable (evidencia)
- Rutas operativas activas: `app.py:254`, `app.py:257`, `app.py:260`, `app.py:263`, `app.py:266`, `app.py:269`.
- Login gate habilitado: `app.py:187`, `security.py:534`.
- Modulos productivos presentes:
  - Casos: `views.py:2537`
  - Agenda: `views.py:3667`
  - Finanzas: `views.py:3890`
  - Auditoria: `views.py:4359`
- Wizard de completitud minima: `views.py:2278`.
- Importador CSV financiero: `views.py:1423`.
- Contratos operativos listos: `db/env_contract.py:6`, `db/env_contract.py:10`, `db/release_gate.py:7`, `db/release_gate.py:8`.
- Baseline KPI bajo por deuda legacy:
  - `FECHA_TAREA`: `db/snapshots/audit_daily/audit_snapshot_latest.json:388`
  - `EXPEDIENTE`: `db/snapshots/audit_daily/audit_snapshot_latest.json:396`
  - `EVENTO_FECHA_EVENTO`: `db/snapshots/audit_daily/audit_snapshot_latest.json:404`
  - `COBERTURA_FINANCIERA`: `db/snapshots/audit_daily/audit_snapshot_latest.json:412`

## Configuracion operativa por defecto
- Runtime:
  - `VG_AUTH_REQUIRED=1`
  - `VG_RBAC_STRICT=1`
  - `VG_EXPORT_STRICT=1`
  - `VG_AUTO_SAVE_CHANGES=1`
- Gate diario:
  - `VG_RELEASE_GATE_MODE=read_only` hasta corregir preflight de DB test.
- Endurecimiento progresivo:
  - Semana 2: mover a `full` cuando `VG_TEST_DATABASE_URL` pase `env_contract`.

## Plan por fases (Impacto x Riesgo x Esfuerzo)
| Fase | Dias | Objetivo | Go/No-Go | Rollback |
|---|---|---|---|---|
| F0 | D0 | Operar hoy (MVP) | `env_contract --profile app` + flujo casos/agenda/finanzas/auditoria OK | volver a `RUN_ERP.cmd` + flags permissive solo por incidente |
| F1 | D1-D14 | Estabilizacion diaria con backlog cerrado | secuencia diaria PASS y primer salto KPI | revertir lote diario (docs/flags/script), mantener operacion |
| F2 | D15-D30 | Hardening estructural sin ruptura | gate `full` y controles seguridad/performance en enforce en test/preprod | rollback por migracion + restore drill |
| F3 | D31-D60 | Escalado funcional (economico/KPI/integraciones minimas) | KPI intermedio FT>=25 EXP>=30 EV/FE>=15 FIN>=15 | fallback modular con flags |
| F4 | D61-D90 | Profesionalizacion operativa y cierre de brechas | KPI final FT>=60 EXP>=70 EV/FE>=40 FIN>=70 y disponibilidad >=99.5% | rollback mayor documentado + postmortem |

## Objetivos medibles (90 dias)
- KPI completitud: `7.0/9.3/2.3/2.3` -> `>=60/70/40/70`.
- Disponibilidad mensual: `>=99.5%`.
- Gate de seguridad en enforce sin hallazgos criticos abiertos.
- Rutina diaria ejecutada sin cortes no planificados.

## Orden de implementacion
1. Operacion diaria estable y segura (auth/rbac/autosave/export strict, gate read_only).
2. Calidad de datos operativa (campana Top-20 + agenda critica + finanzas base).
3. Hardening de auditoria y release gate full.
4. Especificaciones cerradas para migraciones estructurales (`tasks`, custodia documental).
5. Escalado funcional y gobernanza final.
