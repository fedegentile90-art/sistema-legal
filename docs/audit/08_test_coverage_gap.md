# Test Coverage Gap (2026-02-14)

## Current coverage evidence
- DB contract and UX suites exist: `db/contract_test.py`, `db/ux_gestion_regression_test.py`, `db/ux_phase2_test.py`, `db/smoke_test.py`.
- Quality pipeline now includes lint/type/unit: `.github/workflows/quality.yml:31`, `:35`, `:39`.
- New targeted unit tests added:
  - Security: `tests/test_security.py:10`, `:19`, `:31`.
  - Audit actor context: `tests/test_repo_db_actor_ctx.py:4`.
  - XSS sanitizer: `tests/test_views_security.py:4`.
  - Export determinism/hash: `tests/test_exports.py:4`, `:12`.

## Gaps and closure plan
| Gap ID | Finding | Evidence | Sev | Business risk | Technical risk | Recommended test strategy | Effort | Dependencies/order |
|---|---|---|---|---|---|---|---|---|
| T01 | No integration test proving every mutator writes `audit_log` row | Core writes in `repo_db.py:405`, `:500`, `:604`, `:699`, `:791` | High | Missing forensic evidence in production | Partial instrumentation regression | Add DB integration suite `test_audit_write_strict.py` with per-mutator assertions | M | Test DB isolation |
| T02 | No end-to-end test for auth-required route protection across all routes | Auth gate at `app.py:187`, route check `app.py:243` | High | Unauthorized data exposure | Misconfigured flags undetected | Add app-level route matrix tests for roles in strict mode | M | Security flags |
| T03 | No tests for `tasks` workflow (table is unused) | `db/schema.sql:159`, no runtime tasks SQL usage | High | Deadlines process not validated | Domain model drift | Add task CRUD + agenda migration tests before cutover | L | Tasks implementation |
| T04 | Backup encryption/retention tests absent | Backup write path `db/backup_restore_drill.py:203` | Critical | Data leak undetected | Compliance breach | Add encrypted backup roundtrip test and retention purge checks | M | Encryption implementation |
| T05 | Performance regression threshold tests not enforced in CI | `db/release_gate.py:757` default warn | Medium | UX degradation | Latency regressions ship | Add CI lane with `--performance-mode enforce` and baseline dataset | M | Stable CI DB |

## Risk -> test -> expected result matrix
| Risk | Test | Expected result |
|---|---|---|
| Unauthorized access | auth/rbac route tests | Deny non-permitted role in strict mode |
| Mutation without audit | per-mutator integration tests | `audit_log` row exists for each write |
| Duplicate case creation | duplicate creation integration | second create blocked unless policy allow |
| XSS on legacy badge | sanitizer unit test | escaped payload, no executable HTML |
| Finance regression | batch finance tests | totals correct, no per-case query loop |
| Backup leak | encrypted backup drill test | encrypted artifact + successful restore |
