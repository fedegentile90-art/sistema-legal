# Scaling 60-90 Days

Window: 2026-03-31 to 2026-05-15.

## Day 31-60 (functional scaling)
| Ticket | Objective | I/R/E | Files/modules | Acceptance |
|---|---|---|---|---|
| SC01 | Economic layer complete (collections/profitability/aging) | 5/4/4 | schema migrations, `repo_db.py`, `views.py` | per-client and per-case margin + aging reports |
| SC02 | Minimal integrations (email/calendar reminders) | 3/3/3 | new integrations module + UI hooks | deadline reminders sync and traceable delivery |
| SC03 | Executive KPI lineage dashboard | 4/3/3 | `audit.py`, `db/kpi_snapshot.py`, `views.py` | KPI definitions traceable to source rows |

## Day 61-90 (professionalization)
| Ticket | Objective | I/R/E | Files/modules | Acceptance |
|---|---|---|---|---|
| PR01 | Privacy and data governance hardening | 5/5/3 | policy scripts + docs | active retention jobs and access audit by role |
| PR02 | Environment-specific go-live and rollback playbooks | 4/5/2 | rollout docs/scripts | rollback simulation pass |
| PR03 | Close 12D maturity gaps | 5/4/2 | `docs/audit/02_maturity_matrix_12D.md` updates | target scores met or residual risk formally accepted |

## KPI targets by end of day 90
- FECHA_TAREA >= 60
- EXPEDIENTE >= 70
- EVENTO/FECHA_EVENTO >= 40
- COBERTURA_FINANCIERA >= 70
- Availability >= 99.5% monthly
