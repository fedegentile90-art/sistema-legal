# Executive Summary (2026-02-14)

## Scope and method
- Scope audited: runtime app, DB repo, views, audit/export pipelines, DB ops scripts, CI quality pipeline.
- Evidence-only rule applied: each finding references concrete repo paths and line numbers.
- Baseline quality and validation executed in this iteration:
  - `ruff check security.py exports.py repo_db.py app.py views.py ui.py audit.py tests` -> PASS.
  - `mypy security.py exports.py repo_db.py --follow-imports skip` -> PASS.
  - `pytest -q tests` -> PASS (8 tests).
  - `python db/env_contract.py --profile app` -> PASS.
  - `python db/env_contract.py --profile daily_ops` -> PASS when `VG_TEST_DATABASE_URL` is defined.
  - `python db/contract_test.py` -> PASS (29/29).

## Current operational baseline
- DB-first backend is active by design (`repo.py:4`, `repo.py:12`, `repo.py:15`).
- KPI baseline remains below target (`db/snapshots/audit_daily/audit_snapshot_latest.json:388`, `:396`, `:404`, `:412`, `:431`).
- Security gate defaults still permissive (`db/release_gate.py:748`, `:753`, `:757`).

## Top findings and closure plan
| ID | Finding | Evidence (path:line) | Sev | Business risk | Technical risk | Recommended solution | Effort | Dependencies | Status |
|---|---|---|---|---|---|---|---|---|---|
| F01 | Runtime had no enforced identity/role checks in app routing | `app.py:187`, `app.py:243`, `security.py:534`, `security.py:523` | Critical | Unauthorized legal data access | Horizontal abuse in UI actions | Enforce local auth gate + route RBAC via feature flags | M | None | Mitigated in this iteration |
| F02 | `audit_log` existed but mutation coverage was incomplete | `db/schema.sql:190`, `repo_db.py:405`, `repo_db.py:500`, `repo_db.py:604`, `repo_db.py:699`, `repo_db.py:791` | Critical | No forensic trace for business writes | Non-repudiation gap | Write-through `audit_log` on all business mutators + strict mode flag | M | F01 | Mitigated for core mutators |
| F03 | `tasks` table modeled but not used by agenda runtime | `db/schema.sql:159`, no runtime SQL usage (`rg` result only indexes at `db/schema.sql:180-184`) | High | Deadline tracking risk | Dual source of truth (`cases.fecha_tarea` only) | Move agenda engine to `tasks` with legacy fallback state | L | F02 | Open |
| F04 | Document custody/version model not wired in runtime | `db/schema.sql:278`, `db/schema.sql:290`, runtime docs still from `documents` (`repo_db.py:943`, `repo_db.py:958`) | High | Evidentiary chain weakness | Cannot reconstruct documentary history | Implement `document_versions` + `case_events` writes on document updates | L | F02 | Open |
| F05 | Backup drill writes clear JSON snapshots with PII | `db/backup_restore_drill.py:203`, sample payload `db/snapshots/db_backup/db_backup_20260213_225420.json:14` | Critical | Sensitive data leak | Artifact exfiltration risk | Encrypt backup artifacts and add retention/rotation purge | M | F12 | Open |
| F06 | Runtime role posture still high privilege | `logs/ops_20260213.log:15307` to `:15315` | Critical | Full DB compromise blast radius | Privilege escalation | Split runtime/test roles and least-privilege grants; enforce security gate | M | None | Open |
| F07 | Gate policies default to `warn` | `db/release_gate.py:748`, `:753`, `:757` | High | Critical debt can ship | Policy drift | Stage-based switch to `enforce` with explicit thresholds | S | F06 | Open |
| F08 | Case duplicate creation needed deterministic guard | `repo_db.py:713`, `repo_db.py:738`, `db/schema.sql:306` | High | Duplicate expediente/client effort | Data consistency erosion | Keep pre-check + unique guard + merge policy | M | None | Mitigated in this iteration |
| F09 | Silent exception handling existed in critical paths (legacy still remains) | Runtime modules now log (`audit.py:949`, `views.py:3726`, `exports.py:94`), legacy FS still has silent paths (`fs_repo.py:86`, `:144`, `:372`) | High | Invisible incidents | Slow diagnosis | Eliminate `except: pass` from legacy paths or isolate behind explicit compatibility contract | S | None | Partially mitigated |
| F10 | Legacy badge rendering had HTML injection risk | `views.py:272`, `views.py:2992`, test `tests/test_views_security.py:4` | High | UI script injection risk | Session integrity impact | Escape all legacy badge values (`html.escape`) and test payloads | S | None | Mitigated in this iteration |
| F11 | Economic layer remains minimal | `db/schema.sql:102`, `views.py:3709` | High | Low visibility of profitability/cashflow | Weak financial model coupling | Add ledger, invoice/collection, aging and margin metrics | L | F02 | Open |
| F12 | Privacy and retention controls are not codified end-to-end | `docs/README.md:1`, `.env.example:1`, backup plaintext evidence at `db/backup_restore_drill.py:203` | High | Regulatory and client confidentiality exposure | Unbounded retention | Add policy-as-code retention and access logs by role | M | F01/F02 | Open |
| F13 | Standard quality pipeline was missing | Added `quality.yml` (`.github/workflows/quality.yml:12`), toolchain in `requirements.txt:62-64`, config `pyproject.toml:1` | Medium | Delivery confidence gap | Quality drift | Keep CI quality as required gate for PR/merge | M | None | Mitigated in this iteration |
| F14 | KPI operational completeness far below goals | `db/snapshots/audit_daily/audit_snapshot_latest.json:431-434` | High | SLA and deadline breach risk | Persistent incomplete data | Campaign for mandatory capture + guided completion queue | M | F03/F11 | Open |
| F15 | Legacy FS backend still present and mutable | `fs_repo.py:26`, `repo.py:12` | Medium | Future operational confusion | Dual-maintenance cost | Keep explicit compatibility boundary and deprecate mutating legacy paths in phases | S | None | Open |

## Recommended implementation order
1. Close remaining Criticals: F05, F06, F07.
2. Stabilize legal core integrity: F03, F04, F14.
3. Extend business layer and governance: F11, F12, F15.
