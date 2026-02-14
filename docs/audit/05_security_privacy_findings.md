# Security and Privacy Findings (2026-02-14)

## Findings
| ID | Finding | Evidence | Sev | Business risk | Technical risk | Recommended solution | Effort | Dependencies/order |
|---|---|---|---|---|---|---|---|---|
| S01 | Auth and RBAC are now implemented but still flag-driven | `security.py:20-22`, `security.py:509`, `security.py:523`, `security.py:534`, `app.py:187`, `app.py:243` | High | Misconfiguration can leave access too open | Strictness drift by env | Force `VG_AUTH_REQUIRED=1` and `VG_RBAC_STRICT=1` in preprod/prod after UAT | M | Role hardening first |
| S02 | Audit log writes exist for core mutators | `repo_db.py:185`, `repo_db.py:405`, `repo_db.py:500`, `repo_db.py:604`, `repo_db.py:699`, `repo_db.py:791` | High | Better non-repudiation, still partial for docs/tasks | Coverage gaps outside core mutators | Extend mandatory writes to document/task/event mutations | M | S01 |
| S03 | Runtime DB role remains privileged | `logs/ops_20260213.log:15307-15315` | Critical | Total dataset compromise in breach | Excessive grants | Split runtime/test identities and revoke dangerous grants | M | None |
| S04 | Backup artifacts store sensitive data in clear JSON | `db/backup_restore_drill.py:203`, backup sample `db/snapshots/db_backup/db_backup_20260213_225420.json:14` | Critical | Confidentiality/legal breach | Artifact exfiltration | Encrypt backups, sign hash, enforce retention windows | M | S06 |
| S05 | XSS risk in legacy badge path mitigated | `views.py:272`, `views.py:2992`, `tests/test_views_security.py:4` | Medium | UI session safety improved | Residual unsafe-html paths may remain elsewhere | Keep escaped rendering tests and ban unsafe dynamic HTML inputs | S | None |
| S06 | Privacy/retention governance not codified end-to-end | `docs/README.md:1`, `.env.example:1` | High | Regulatory and contractual exposure | Retention drift | Add retention schedules, minimization checks, access audit by role | M | S03 |

## Control map
- Identity: local auth backend with DB bootstrap and fallback (`security.py:310`, `security.py:385`).
- Authorization: role-permission matrix (`security.py:40`) and route permission map (`security.py:80`).
- Session traceability: `auth_sessions` schema (`db/schema.sql:258`) and optional login session writes (`security.py:451`).
- Audit writes: strict mode env `VG_AUDIT_WRITE_STRICT` (`repo_db.py:30`) with write-through helper (`repo_db.py:185`).

## Immediate actions
1. Enforce security flags per environment contract.
2. Remove fallback credentials outside dev.
3. Encrypt/rotate backup artifacts and scrub old plaintext snapshots.
