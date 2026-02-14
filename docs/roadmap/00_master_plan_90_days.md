# Master Plan 90 Days (DB-first)

Reference window: 2026-02-14 to 2026-05-15.

## Goals
- Preserve compatibility while raising security, reliability, and maintainability.
- Close critical legal-tech operational gaps without production breakage.

## Prioritization model
- Priority score = Impact x Risk reduction x (1 / Effort).
- Stage gates enforce go/no-go based on tests, policy flags, and rollback readiness.

## Phases
1. Stage 0 (Day 1-2): freeze baseline and evidence.
2. Stage 1 (Day 3-14): quick wins + initial stabilization.
3. Stage 2 (Day 15-30): strong stabilization.
4. Stage 3 (Day 31-60): functional scaling.
5. Stage 4 (Day 61-90): operational professionalization.

## Stage plan summary
| Stage | Window | Main outcomes | Go/No-Go gate | Rollback |
|---|---|---|---|---|
| 0 | D1-D2 | Reproducible baseline, signed snapshots | `release_gate --mode full` evidence captured | Revert only docs/scripts baseline artifacts |
| 1 | D3-D14 | Logging, audit writes, auth/RBAC flags, XSS fix, duplicate guard, quality CI | `contract`, `ux_gestion`, `ux_phase2`, `smoke` pass; no open criticals F01/F02/F06/F10 for promoted scope | Disable flags: `VG_AUTH_REQUIRED=0`, `VG_RBAC_STRICT=0`, revert stage migrations |
| 2 | D15-D30 | tasks integration, document versions/custody, encrypted backups, security gate enforce in test/preprod | `release_gate --mode full --security-mode enforce --performance-mode enforce` pass | migration down + validated restore drill |
| 3 | D31-D60 | Financial layer (aging/rentability), minimal integrations, KPI lineage dashboard | KPI midpoint met (FT>=25, EXP>=30, EV/FE>=15, FIN>=15) | module-level rollback + controlled `warn` fallback |
| 4 | D61-D90 | Privacy governance hardening, rollout playbooks, 12D objective closure | KPI targets met and availability >=99.5% monthly | major rollback playbook + encrypted restore + postmortem |

## Metrics before/after targets
- KPI completeness targets from `audit_snapshot_latest.json`: move from 7.0/9.3/2.3/2.3 to >=60/70/40/70.
- Security posture: runtime role warnings (SEC-ROLE/SEC-TABLE) reduced to zero in enforce mode.
- Quality gate: CI quality + DB gate all green before production promotion.

## Atomic delivery batches (implemented wave + next)
- commit-01-observabilidad
- commit-02-integridad-legacy
- commit-03-seguridad-minima
- commit-04-performance
- commit-05-ux-consistencia
- commit-06-exportes-reportes

## Dependency order
1. Security and role hardening.
2. Audit strictness and mutation completeness.
3. Data model migration (`tasks`, `document_versions`, `case_events`).
4. Financial/integration expansion.
5. Governance and final rollout controls.
