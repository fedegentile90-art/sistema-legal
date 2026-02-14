# Scaling 60-90 Days (D31-D90)

Ventana: 2026-03-31 a 2026-05-15.

## D31-D60: escalado funcional
| Ticket | Objetivo | I/R/E | Archivos | Aceptacion |
|---|---|---|---|---|
| SC01 | Capa economica completa (cobranzas, aging, rentabilidad) | 5/4/4 | migraciones, `repo_db.py`, `views.py` | reporte por cliente/asunto y aging operativo |
| SC02 | Integraciones minimas (email/calendario) | 3/3/3 | modulo integraciones + UI | recordatorios de vencimiento sincronizados y auditables |
| SC03 | KPI ejecutivos trazables | 4/3/3 | `audit.py`, `db/kpi_snapshot.py`, `views.py` | dashboard con lineage por fuente de datos |

## D61-D90: profesionalizacion
| Ticket | Objetivo | I/R/E | Archivos | Aceptacion |
|---|---|---|---|---|
| PR01 | Hardening final de privacidad y gobierno de datos | 5/5/3 | scripts/docs politica datos | retencion activa y auditoria de acceso por rol |
| PR02 | Go-live playbook por entorno + rollback certificado | 4/5/2 | `docs/roadmap/04_release_and_rollout_strategy.md`, scripts | simulacro de rollback PASS |
| PR03 | Cierre de brecha de madurez 12D | 5/4/2 | `docs/audit/02_maturity_matrix_12D.md` | objetivo alcanzado o riesgo residual aprobado |

## KPI objetivo final
- FECHA_TAREA >= 60
- EXPEDIENTE >= 70
- EVENTO_FECHA_EVENTO >= 40
- COBERTURA_FINANCIERA >= 70
- Disponibilidad mensual >= 99.5%

## Regla operativa
Ningun ticket de escalado entra en produccion si rompe la rutina diaria D0-D14.
