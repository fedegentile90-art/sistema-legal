# Quick Wins 2 Weeks (Operar Hoy, Mejorar Cada Dia)

Ventana: 2026-02-14 a 2026-02-28.

## Objetivo quincenal
- Dia 0: operar en produccion interna sin friccion.
- Dia 1-7: estabilizar rutina diaria y controles basicos.
- Dia 8-14: primer salto KPI y preparar hardening estructural.

## Backlog diario ejecutable (D0-D14)
| Dia | Ticket | Objetivo / por que ahora | Dependencias | Archivos objetivo | Aceptacion medible | Validacion exacta | Riesgo / mitigacion | Estimacion |
|---|---|---|---|---|---|---|---|---|
| D0 | GO-01 | Arrancar operacion real hoy | Ninguna | `.env`, `RUN_ERP.cmd` | Usuario entra, crea/edita caso y ve agenda | `python db/env_contract.py --profile app` | Error de arranque -> fallback `RUN_ERP.cmd` | 1h |
| D0 | GO-02 | Checklist diario operativo | GO-01 | `docs/MANUAL_*` | Checklist apertura/cierre adoptado | `python db/contract_test.py` | Omision humana -> checklist fijo | 1h |
| D1 | OP-01 | Corregir contrato DB test para habilitar `full` | GO-01 | `.env`, `db/env_contract.py` | `release_gate --mode full` sin BLOCKED por auth | `python db/env_contract.py --profile daily_ops` | Credenciales invalidas -> mantener `read_only` 48h | 2h |
| D2 | DATA-01 | Campana Top-20 incompletos (wizard) | GO-02 | uso `views.py`, datos | 20 casos con minimos completos | `python db/nightly_audit.py` | Calidad heterogenea -> lote controlado | 2h |
| D3 | DATA-02 | Completar agenda critica (vencidas +7 dias) | DATA-01 | datos operativos | 100% vencidas con responsable/fecha/tarea | `python db/nightly_audit.py` | Sobrecarga -> priorizar por semaforo | 2h |
| D4 | FIN-01 | Cobertura financiera basica en activos | DATA-02 | uso `views.py` finanzas | >=50% activos con dato financiero | `python db/nightly_audit.py` | Errores de carga -> dry-run CSV | 2h |
| D5 | SEC-01 | Revisar matriz real de roles del estudio | GO-01 | `security.py`, operacion | Roles asignados y probados | `python -m pytest -q tests` | Bloqueo de acciones -> ajustar permisos | 2h |
| D6 | OPS-01 | Estabilizar DailyOps diario | OP-01 | `RUN_ERP.ps1`, `logs/` | 3 corridas consecutivas sin corte | `RUN_ERP.ps1 -DailyOps` | Timeouts -> ajustar `VG_STEP_TIMEOUT_SEC` | 2h |
| D7 | BDR-01 | Backup drill semanal operativo | OP-01 | `db/backup_restore_drill.py` | Backup semanal generado/verificado | `python db/backup_restore_drill.py --backup-only` | Restore bloqueado -> registrar incidente | 1.5h |
| D8 | QA-01 | Gate release en `full` si DB test OK | OP-01 | `db/release_gate.py` | `full` PASS sin BLOCKED DB | `python db/release_gate.py --mode full` | Si falla -> seguir `read_only` + fix plan | 2h |
| D9 | KPI-01 | Primer objetivo intermedio de datos | DATA-01..FIN-01 | datos + auditoria | FT>=20, EXP>=25, EV/FE>=10, FIN>=15 | `python db/nightly_audit.py` | Meta baja -> repetir Top-20 | 2h |
| D10 | HARD-01 | Activar `VG_AUDIT_WRITE_STRICT=1` en test/preprod | QA-01 | `.env`, `repo_db.py` | Mutaciones fallan sin auditoria | `python db/contract_test.py` | Falsos bloqueos -> rollback flag | 1.5h |
| D11 | SPEC-01 | Especificacion cerrada migracion `tasks` | KPI-01 | `db/schema.sql`, `views.py`, `repo_db.py` | Diseno aprobado sin TBD | `python db/contract_test.py` | Alcance excesivo -> limitar agenda | 2h |
| D12 | SPEC-02 | Especificacion cerrada custodia documental | SPEC-01 | `db/schema.sql`, `repo_db.py` | Plan `document_versions/case_events` aprobado | `python db/contract_test.py` | Complejidad legal -> rollout por flag | 2h |
| D13 | REL-01 | Plan rollout/rollback por modulo | SPEC-01/02 | `docs/roadmap/*` | Playbook por entorno listo | `python db/release_gate.py --mode read_only` | Riesgo de corte -> rollback scriptado | 1.5h |
| D14 | KPI-02 | Cierre quincenal y replanificacion D15-D30 | D0-D13 | `docs/roadmap/*` | KPIs/incidentes/backlog cerrados | `python db/nightly_audit.py` | Deriva -> freeze + repriorizar | 2h |

## Secuencia diaria obligatoria (cierre)
1. `python db/env_contract.py --profile app`
2. `python db/contract_test.py`
3. `python db/nightly_audit.py`
4. `python db/release_gate.py --mode read_only`
5. Semanal: `python db/backup_restore_drill.py --backup-only`

## Criterios de Done (D0-D14)
- D0: flujo productivo habilitado (casos/agenda/finanzas/auditoria) con auth local activo.
- D1-D7: rutina diaria estable y sin bloqueos criticos.
- D8-D14: primer salto KPI y especificaciones estructurales listas para ejecutar.
