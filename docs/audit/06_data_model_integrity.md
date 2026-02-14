# Data Model Integrity (2026-02-14)

## Core schema review
- Core legal entities are normalized in `db/schema.sql` (`clients`, `cases`, `documents`, `tasks`, `audit_log`).
- New security and lineage tables exist (`users`, `roles`, `permissions`, `auth_sessions`, `document_versions`, `case_events`) at `db/schema.sql:212-303`.

## Integrity findings
| ID | Finding | Evidence | Sev | Business risk | Technical risk | Recommended solution | Effort | Dependencies/order |
|---|---|---|---|---|---|---|---|---|
| D01 | Duplicate-case guard now exists but merge policy is still manual | `repo_db.py:713`, `repo_db.py:738`, `db/schema.sql:306` | High | Duplicate legal records and billing confusion | Data inconsistency | Add merge workflow UI + audit event for resolved duplicates | M | Audit strictness |
| D02 | `tasks` table is isolated from runtime agenda | `db/schema.sql:159`, agenda logic in `views.py:3486` uses case fields | High | Missed deadlines | Incomplete domain model usage | Migrate schedule writes/reads to `tasks` and keep legacy flags explicit | L | D01 |
| D03 | Document chain tables are not yet populated by app writes | `db/schema.sql:278`, `db/schema.sql:290`, runtime docs query still `documents` (`repo_db.py:958`) | High | Chain-of-custody gap | No reconstructable history | Add document versioning service and immutable events | L | D01 |
| D04 | Legacy FS backend still writable with silent legacy paths | `fs_repo.py:26`, `fs_repo.py:86`, `repo.py:12` | Medium | Non-uniform behavior by backend | Drift and hidden failures | Keep DB as only runtime backend; isolate FS legacy in compatibility mode only | S | None |
| D05 | KPI completeness confirms large field nullability in production data | `db/snapshots/audit_daily/audit_snapshot_latest.json:431-434` | High | Operational/legal quality issues | Reporting inaccuracies | Add required-field gates in write forms and remediation queues | M | D02 |

## Data migration notes
- Migration script created for security + lineage schema: `db/migrations/20260214_01_security_rbac_audit.sql`.
- Backward compatibility preserved by keeping existing case fields and adding optional actor context in mutator signatures (`repo_db.py:405`, `repo_db.py:604`, `repo_db.py:699`).
