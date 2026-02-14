# Release and Rollout Strategy (Operar Hoy, Mejorar Cada Dia)

## Politica de release
- Despliegue gradual por modulo y por flag.
- Prioridad: continuidad operativa diaria sobre velocidad de cambio.
- Sin cambios breaking en semana 1.

## Matriz de flags por entorno
| Entorno | VG_AUTH_REQUIRED | VG_RBAC_STRICT | VG_AUDIT_WRITE_STRICT | VG_EXPORT_STRICT | VG_AUTO_SAVE_CHANGES | VG_RELEASE_GATE_MODE |
|---|---:|---:|---:|---:|---:|---|
| Dev local | 1 | 1 | 0 | 1 | 1 | read_only |
| Test | 1 | 1 | 0->1 gradual | 1 | 1 | read_only -> full |
| Preprod | 1 | 1 | 1 | 1 | 1 | full |
| Prod interno | 1 | 1 | 1 (post burn-in) | 1 | 1 | full |

## Go/No-Go por etapa
| Etapa | Go/No-Go |
|---|---|
| D0-D7 | `python db/env_contract.py --profile app`, `python db/contract_test.py`, `python db/release_gate.py --mode read_only` PASS |
| D8-D14 | ademas de lo anterior, KPI intermedio en progreso y sin incidentes P1 abiertos |
| D15-D30 | `python db/env_contract.py --profile daily_ops` y `python db/release_gate.py --mode full --security-mode enforce --performance-mode enforce` PASS |
| D31-D90 | metas KPI por fase cumplidas y disponibilidad >=99.5% mensual |

## Secuencia diaria obligatoria (cierre)
1. `python db/env_contract.py --profile app`
2. `python db/contract_test.py`
3. `python db/nightly_audit.py`
4. `python db/release_gate.py --mode read_only`
5. Semanal: `python db/backup_restore_drill.py --backup-only`

## Secuencia objetivo (cuando DB test este corregida)
1. `python db/env_contract.py --profile daily_ops`
2. `python db/release_gate.py --mode full`
3. `python db/release_gate.py --mode full --security-mode enforce --performance-mode enforce`

## Rollback por modulo
1. Config: revertir flags del lote.
2. Codigo: revertir commit atomico del modulo afectado.
3. Datos: rollback migracion del lote y restore desde backup validado si aplica.
4. Gate: volver temporalmente a `read_only` con ticket de incidente y ETA de remediacion.

## Contingencias clave
- DB test BLOCKED en full gate: mantener `read_only` y priorizar OP-01.
- Friccion por permisos RBAC: ajustar permisos por rol, no desactivar auth.
- KPI sin mejora: ejecutar campana Top-20 diaria y repriorizar backlog.
- Backup sin restore validado: continuar backup-only y bloquear cambios de alto riesgo.
