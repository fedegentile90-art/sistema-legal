# Architecture Map (as-is, 2026-02-14)

## Runtime topology
- Entry point and shell: `app.py:176` (`main`).
- Backend abstraction: `repo.py:4`, `repo.py:12`, `repo.py:15` (DB-first fixed backend).
- Business views/router: `views.py` (`render_dashboard`, `render_gestion`, `render_modulo_agenda`, `render_modulo_finanzas`).
- DB repository: `repo_db.py:116` (`GestorCasosDB`) for reads/writes.
- Security layer: `security.py:534` (`render_login_gate`), `security.py:523` (`can_access_route`), `security.py:509` (`has_permission`).
- Audit/KPI snapshot: `audit.py:294` (`build_daily_audit_snapshot`), `audit.py:323` (`save_daily_audit_snapshot`).
- Exports: `exports.py:122`, `exports.py:133`.
- Ops controls: `db/env_contract.py`, `db/release_gate.py`, `db/security_baseline.py`, `db/performance_capacity.py`, `db/backup_restore_drill.py`.

## Data model map
- Core entities: `clients`, `cases`, `documents`, `tasks`, `audit_log` (`db/schema.sql:72-206`).
- Security entities: `users`, `roles`, `permissions`, `user_roles`, `role_permissions`, `auth_sessions` (`db/schema.sql:212-272`).
- Legal traceability extensions: `document_versions`, `case_events` (`db/schema.sql:278-303`).
- Duplicate guard: `idx_cases_duplicate_guard` (`db/schema.sql:306`).

## Request/response flow
1. User enters app -> `app.py:176` initializes state and DB health.
2. Auth gate runs -> `app.py:187` calls `render_login_gate`.
3. Sidebar routing -> `app.py:236` plus RBAC check `app.py:243`.
4. View dispatch by route (`Dashboard/Gestion/Agenda/Finanzas/Auditoria/Configuracion`) in `app.py:252-270`.
5. View invokes repository mutator/read methods (`views.py:2235`, `views.py:3965`, `views.py:4051`, etc.).
6. DB mutator writes business data and audit entry (`repo_db.py:474`, `:551`, `:664`, `:771`, `:834`).

## Hotspots and findings
| Area | Evidence | Symptom | Sev | Business risk | Technical risk | Recommended fix | Effort | Dependencies/order |
|---|---|---|---|---|---|---|---|---|
| Agenda engine | `views.py:3486`, `db/schema.sql:159`, and no runtime SQL over `tasks` | Agenda still depends on case fields (`FECHA_TAREA`) | High | Deadline misses | Wrong abstraction boundary | Introduce task CRUD/service and migrate agenda views to `tasks` | L | After audit strictness (F02) |
| Document chain | `repo_db.py:943`, `db/schema.sql:278`, `db/schema.sql:290` | New custody tables exist but are unused | High | Weak evidence chain | Missing event lineage | Wire document uploads/edits to `document_versions` + `case_events` | L | After auth/audit baseline |
| Backup safety | `db/backup_restore_drill.py:203` | Plain JSON snapshot with sensitive rows | Critical | Confidentiality breach | Artifact leak | Add encryption at rest and retention cleanup | M | After policy definition |
| Legacy backend path | `fs_repo.py:26`, `repo.py:12` | Legacy code still mutable and contains silent paths | Medium | Operational confusion | Split-brain maintenance | Freeze legacy writes behind explicit compatibility mode | S | Parallel with stabilization |

## Dependencies graph (high level)
1. Security foundation (`security.py`, `app.py`) -> enables permissioned write paths.
2. Audit write strictness (`repo_db.py`, `audit_log`) -> required for compliance trace.
3. Data integrity (duplicate guard, tasks migration, document events).
4. Performance/exports hardening.
5. Operational gates (`release_gate enforce`) and rollout controls.
