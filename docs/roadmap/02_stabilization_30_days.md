# Stabilization 30 Days (D15-D30)

Ventana: 2026-03-01 a 2026-03-30.

## Objetivo
Ejecutar hardening estructural sin romper el flujo diario que ya esta en produccion interna.

## Tickets de estabilizacion
| Ticket | Objetivo | I/R/E | Evidencia base | Archivos | Aceptacion |
|---|---|---|---|---|---|
| ST01 | Integrar agenda sobre `tasks` con compatibilidad legacy | 5/5/4 | `tasks` existe y agenda actual sigue legacy (`db/schema.sql:159`, `views.py:3667`) | `repo_db.py`, `views.py`, migraciones | agenda lee/escribe en `tasks` y fallback legacy explicito |
| ST02 | Modelo documental con versionado + custodia | 5/4/4 | modulo documental sin custodia completa | `db/schema.sql`, `repo_db.py`, `views.py`, migraciones | historial documental por caso trazable y auditable |
| ST03 | Backup cifrado + retencion | 5/5/3 | backup JSON plano en drill | `db/backup_restore_drill.py`, docs operativas | artefacto cifrado, retencion aplicada, restore validado |
| ST04 | Gate seguridad/performance en enforce (test/preprod) | 5/5/2 | gate soporta enforce (`db/release_gate.py`) | `db/release_gate.py`, `.env`, `db/env_contract.py` | `release_gate --mode full --security-mode enforce --performance-mode enforce` PASS |

## Go/No-Go
- Obligatorio: `python db/env_contract.py --profile daily_ops` PASS.
- Obligatorio: `python db/release_gate.py --mode full` PASS sin suites BLOCKED.
- Obligatorio: no incidentes P1 abiertos por auth/rbac/auditoria.

## Rollback
1. Revertir migraciones del lote en orden inverso.
2. Restaurar ultimo backup validado.
3. Volver gate a `read_only` solo con ticket de incidente.

## Dependencias
- Requiere D0-D14 estable y checklist diario cumplido.
- ST03 depende de politica de retencion definida en docs operativas.
- ST01/ST02 requieren auditoria de mutaciones activa.
