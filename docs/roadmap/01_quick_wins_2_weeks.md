# Quick Wins (2 weeks)

Window: 2026-02-14 to 2026-02-28.

## Ticket backlog (impact/risk/effort)
| Ticket | Objective | I/R/E | Evidence baseline | Files | Acceptance |
|---|---|---|---|---|---|
| QW01 | Structured logging and no silent critical exceptions | 4/4/1 | Legacy silent paths still in `fs_repo.py:86` etc | `app.py`, `views.py`, `audit.py`, `exports.py`, `ui.py` | No silent exception in critical runtime modules; smoke tests pass |
| QW02 | Audit write-through for business mutators | 5/5/2 | `audit_log` table exists (`db/schema.sql:190`) | `repo_db.py` | Core mutators create `audit_log` entry |
| QW03 | Local auth + minimum RBAC with toggles | 5/5/3 | routing/auth gap prior baseline | `security.py`, `app.py`, `views.py` | Restricted routes/actions under strict mode |
| QW04 | XSS and unsafe UI output mitigation | 4/4/1 | badge injection path in `views.py:2992` | `views.py`, tests | payload escaped test pass |
| QW05 | Duplicate-case guard | 4/4/2 | duplicate risk in create flow | `repo_db.py`, `db/schema.sql` | duplicate creation blocked under default policy |
| QW06 | Quality pipeline (ruff/mypy/pytest) | 4/3/2 | missing standard quality gate | `.github/workflows/quality.yml`, `requirements.txt`, `pyproject.toml`, tests | CI quality green |

## Execution sequence
1. QW06 first (safety net).
2. QW01 and QW04 in parallel.
3. QW02 and QW05.
4. QW03 last in quick wins with feature flags default permissive.

## Go/No-Go
- Required: `pytest -q tests`, `python db/contract_test.py`, `python db/smoke_test.py`.
- Required: no new critical security finding introduced.

## Rollback
- Disable flags: `VG_AUTH_REQUIRED=0`, `VG_RBAC_STRICT=0`, `VG_EXPORT_STRICT=0`.
- Revert migration batch if write paths fail; keep read-only operations available.
