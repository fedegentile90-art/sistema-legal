# Assumptions (explicit)

Reference date: 2026-02-14.

| ID | Assumption | Impact | Validation plan | Owner |
|---|---|---|---|---|
| A01 | Deployment is on-prem single-tenant | Simplifies data segmentation and network controls | Validate infra diagram and host topology during Stage 0 | Ops |
| A02 | Local auth + minimum RBAC is accepted for 90-day horizon | No dependency on external IdP for first rollout | Validate with security/legal stakeholders by 2026-02-20 | Security Lead |
| A03 | Gradual rollout with feature flags is mandatory | Reduces production regression risk | Validate flags in `.env` contract and release checklist | Release Manager |
| A04 | Regulatory baseline includes legal privilege + local data law | Sets minimum privacy and audit controls | Legal sign-off of controls by 2026-02-28 | Legal + Security |
| A05 | Availability target is 99.5% monthly | Drives resilience and observability priorities | Track monthly SLO via ops snapshots/logs | Ops |
| A06 | No legacy functionality removed without equivalent replacement | Preserves operational continuity | Use compatibility tests before each cutover | Product Architect |
| A07 | Primary DB is PostgreSQL 12+ | Enables migrations and JSONB/event features | Verify runtime/test versions at env contract start | DBA |
| A08 | `VG_TEST_DATABASE_URL` remains isolated and dedicated | Prevents test impact on operational data | Enforce env contract (`db/env_contract.py`) in CI and daily ops | QA/Ops |

## Assumption risk notes
- If A02 fails (external IdP becomes mandatory), security sprint scope and timeline increase.
- If A08 fails, DB suites must be blocked (`release_gate` already supports blocking modes).
