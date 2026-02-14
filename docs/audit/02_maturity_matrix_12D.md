# Maturity Matrix 12D (Current vs Target)

Reference date: 2026-02-14.

| Dimension | Current (0-5) | Target (90d) | Evidence (path:line) | Gap closure plan | Sev | Business risk | Technical risk | Effort | Dependencies |
|---|---:|---:|---|---|---|---|---|---|---|
| A Operacion juridica | 2.5 | 4.2 | `views.py:3486`, `domain.py:146` | Persist legal workflow states and milestones in DB events | High | Process slippage | Inconsistent state transitions | M | F02/F03 |
| B Documental/probatoria | 1.5 | 3.8 | `repo_db.py:943`, `db/schema.sql:278` | Implement `document_versions` + custody audit trail | High | Evidentiary weakness | No version lineage | L | F02/F04 |
| C Motor procesal/plazos | 2.0 | 4.0 | `views.py:3486`, `db/schema.sql:159` | Move agenda from case fields to `tasks` engine + alerts | High | Deadline misses | Dual-source schedule | L | F03 |
| D Capa economica | 2.0 | 3.8 | `views.py:3709`, `db/schema.sql:102` | Add invoices/collections/aging and profitability per case/client | High | Revenue visibility gap | Fragmented financial state | L | F11 |
| E Relacion cliente/comercial | 1.8 | 3.5 | `repo_db.py:699`, `views.py:3965` | Intake, onboarding and conflict-check workflow | Medium | Intake errors | Missing lifecycle records | M | F01/F02 |
| F IA/automatizacion | 0.5 | 2.5 | no production IA module in repo | Controlled extraction/classification with guardrails and audit | Medium | Manual load | Unsafe automation if rushed | M | F01/F02 |
| G Seguridad app | 3.2 | 4.0 | `app.py:187`, `app.py:243`, `security.py:509` | Enforce flags in stages, remove fallback creds in prod | High | Unauthorized access | Misconfigured strictness | M | F06/F07 |
| H Resiliencia operativa | 3.4 | 4.3 | `RUN_ERP.ps1:275`, `db/release_gate.py:748` | Keep cutoffs + enforce gates + restore drills | Medium | Failed runs impact ops | Environment drift | M | F07 |
| I Privacidad/gobierno datos | 1.4 | 3.8 | `db/backup_restore_drill.py:203`, `docs/README.md:1` | Encrypt backups + retention/minimization policy-as-code | High | Regulatory exposure | Data over-retention | M | F05/F12 |
| J Integraciones | 1.0 | 3.0 | No email/calendar integration module; exports only (`exports.py:122`) | Add minimal email/calendar sync for deadlines | Medium | Manual coordination overhead | Integration debt | M | F03 |
| K Analitica | 2.6 | 4.0 | `audit.py:144`, `db/kpi_snapshot.py:138` | Add lineage metadata and executive KPI dashboard | Medium | KPI mistrust | Incomplete metric definitions | M | F14 |
| L UX profesional | 3.4 | 4.2 | `views.py:272`, `views.py:2992`, `tests/test_views_security.py:4` | Keep secure rendering + accessibility and density consistency | Medium | Usability friction | UI regression risk | S | F10 |

## Prioritized closure sequence
1. Security + audit strictness (G, I).
2. Core legal model integrity (A, B, C).
3. Financial/analytics depth (D, K).
4. Commercial/integration and UX refinements (E, J, L).
