# Stabilization (30 days)

Window: 2026-03-01 to 2026-03-30.

## Tickets
| Ticket | Objective | I/R/E | Evidence baseline | Files/modules | Acceptance |
|---|---|---|---|---|---|
| ST01 | Migrate agenda engine to `tasks` with compatibility fallback | 5/5/4 | `tasks` exists but unused (`db/schema.sql:159`) | `repo_db.py`, `views.py`, migration scripts | Agenda reads/writes via `tasks`, legacy state explicit |
| ST02 | Document versions and custody events | 5/4/4 | `document_versions`/`case_events` not wired | `repo_db.py`, `views.py`, migrations | Immutable document history per case |
| ST03 | Encrypted backups + retention policy | 5/5/3 | clear JSON backup writes (`db/backup_restore_drill.py:203`) | `db/backup_restore_drill.py`, policy docs/scripts | encrypted artifacts and successful restore drill |
| ST04 | Security gate enforce in test/preprod | 5/5/2 | gate defaults warn (`db/release_gate.py:748`) | `db/release_gate.py`, `db/env_contract.py` | release blocked for privilege deviations |

## Go/No-Go criteria
- `python db/release_gate.py --mode full --security-mode enforce --performance-mode enforce` must pass in preprod.
- `VG_TEST_DATABASE_URL` isolation validated by `db/env_contract.py --profile daily_ops` and `--profile release_gate_full`.

## Rollback strategy
1. Rollback migrations down in reverse order.
2. Restore from encrypted backup drill target.
3. Switch gate mode to `warn` only with incident ticket and explicit approval.

## Dependencies
- ST03 depends on policy completion from privacy/governance work.
- ST01 and ST02 depend on stable audit instrumentation from quick wins.
