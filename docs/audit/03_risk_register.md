# Risk Register (2026-02-14)

| Risk ID | Finding | Evidence | Sev | Owner | Business risk | Technical risk | Mitigation | Effort | Dependencies | Target date |
|---|---|---|---|---|---|---|---|---|---|---|
| R01 | Plain backup snapshots expose PII | `db/backup_restore_drill.py:203`, `db/snapshots/db_backup/db_backup_20260213_225420.json:14` | Critical | Security Lead | Confidentiality breach | Artifact leak | Encrypt backup payload + signed checksum + retention purge | M | R06 | 2026-03-06 |
| R02 | Runtime DB role excessive privileges | `logs/ops_20260213.log:15307-15315` | Critical | DBA/Ops | Full data compromise | Blast radius maximum | Role split runtime/test + revoke superuser/create/truncate | M | None | 2026-03-10 |
| R03 | Security/performance gates permissive by default | `db/release_gate.py:748`, `:753`, `:757` | High | Release Manager | Risky releases pass | Risk debt accumulation | Stage policy to `enforce` in test/preprod/prod | S | R02 | 2026-03-15 |
| R04 | Tasks model not used by agenda | `db/schema.sql:159`, `views.py:3486` | High | Product Architect | Deadline misses | Dual source of truth | Migrate agenda to `tasks` with compatibility fallback | L | R07 | 2026-04-05 |
| R05 | Document chain tables not wired | `db/schema.sql:278`, `db/schema.sql:290`, `repo_db.py:943` | High | Legal Ops Eng | Weak evidentiary support | No custody lineage | Wire writes to `document_versions` and `case_events` | L | R07 | 2026-04-10 |
| R06 | Privacy/retention policy not codified | `docs/README.md:1`, `.env.example:1` | High | Security+Legal | Regulatory exposure | Unlimited retention | Policy-as-code retention + role-based access audit | M | R02 | 2026-03-20 |
| R07 | Audit coverage of all mutations not complete | `repo_db.py:405`, `:500`, `:604`, `:699`, `:791`; no document-events writes | High | Backend Lead | Incomplete forensic trail | Missing event coverage | Extend audit instrumentation to docs/tasks/events | M | R01/R04/R05 | 2026-03-28 |
| R08 | Legacy FS module still has silent exception paths | `fs_repo.py:86`, `:144`, `:372`, `:450` | Medium | Backend Lead | Hidden failures in fallback mode | Troubleshooting delay | Replace silent pass with structured logs | S | None | 2026-03-01 |
| R09 | Economic layer limited to basic fields | `db/schema.sql:102`, `views.py:3709` | High | Product/Finance | Poor profitability decisions | Financial reporting gaps | Implement ledger + invoices + aging | L | R07 | 2026-04-20 |
| R10 | Operational KPI completeness remains low | `db/snapshots/audit_daily/audit_snapshot_latest.json:431-434` | High | Ops Lead | SLA and legal follow-up risk | Data quality drift | Mandatory capture workflow + campaign queue | M | R04/R09 | 2026-04-15 |

## Implementation order
1. R02 -> R03 -> R06.
2. R01 -> R07.
3. R04 + R05 in parallel after R07 baseline.
4. R09 + R10.
