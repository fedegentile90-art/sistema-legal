# Release and Rollout Strategy

## Release policy
- Deploy by stage with feature flags and migration gates.
- Promote only when quality, contract, UX regression, smoke, and release gate criteria are green.

## Environment flag matrix
| Environment | VG_AUTH_REQUIRED | VG_RBAC_STRICT | VG_AUDIT_WRITE_STRICT | VG_EXPORT_STRICT | Gate mode |
|---|---:|---:|---:|---:|---|
| Dev | 0/1 (test both) | 0/1 (test both) | 0 | 0 | warn |
| Test | 1 | 1 | 1 | 1 | security/performance enforce |
| Preprod | 1 | 1 | 1 | 1 | full enforce |
| Prod (gradual) | 1 | 1 | 1 | 1 | enforce after burn-in |

## Go/No-Go checks per stage
| Stage | Mandatory checks |
|---|---|
| D1-D14 | `db/contract_test.py`, `db/ux_gestion_regression_test.py`, `db/ux_phase2_test.py`, `db/smoke_test.py` pass; no open criticals F01/F02/F06/F10 in promoted scope |
| D15-D30 | `db/release_gate.py --mode full --security-mode enforce --performance-mode enforce` pass |
| D31-D60 | Midpoint KPI threshold achieved (FT>=25, EXP>=30, EV/FE>=15, FIN>=15) |
| D61-D90 | Final KPI and availability target met |

## Rollback plan
1. Configuration rollback: disable strict flags only under incident.
2. Schema rollback: execute migration down scripts by batch.
3. Data rollback: restore latest encrypted backup and verify counts.
4. Validation rollback gate: rerun smoke + contract + release gate in read_only then full.

## Contingency scenarios
- DB auth failure in test gate: block release and run `env_contract` diagnostics first.
- Security gate failure on privileges: keep deployment frozen until DBA fixes grants.
- KPI regression after release: revert module-level feature flags, keep app read paths online, run postmortem.

## Post-change verification checklist
- [ ] `python db/env_contract.py --profile app`
- [ ] `python db/env_contract.py --profile daily_ops`
- [ ] `python db/contract_test.py`
- [ ] `python db/ux_gestion_regression_test.py`
- [ ] `python db/ux_phase2_test.py`
- [ ] `python db/smoke_test.py`
- [ ] `python db/release_gate.py --mode full`
- [ ] `python db/release_gate.py --mode full --security-mode enforce --performance-mode enforce`
- [ ] `python db/backup_restore_drill.py`
- [ ] `RUN_ERP.ps1 -DailyOps`
