# Performance Baseline (2026-02-14)

## Baseline evidence
- Performance gate framework and thresholds are present in `db/performance_capacity.py:95`, `db/performance_capacity.py:234`.
- Release gate integrates performance mode with default `warn` (`db/release_gate.py:639`, `db/release_gate.py:757`).
- Runtime performance snapshot entries are logged (`logs/ops_20260213.log:14535`, `logs/ops_20260213.log:15323`).

## Hotspots observed
| Hotspot ID | Evidence | Symptom | Sev | Business risk | Technical risk | Recommended fix | Effort | Dependencies/order |
|---|---|---|---|---|---|---|---|---|
| P01 | Prior finance list loaded per-case data; now batch path in `views.py:3721` and `views.py:3724` with repo support `repo_db.py:893` | N+1 risk on finance listing | High | Slow user workflows | DB round-trip amplification | Keep batch read as default and add benchmark guard | M | None |
| P02 | Gate defaults to warn (`db/release_gate.py:757`) | Performance regressions not blocking release | High | Degraded UX in production | Latency drift | Enable `--performance-mode enforce` in preprod/prod | S | Security role split |
| P03 | Backup drill full JSON serialization `db/backup_restore_drill.py:203` | Heavy I/O + large artifacts | Medium | Extended maintenance window | High disk churn | Add compression+encryption stream and retention | M | Privacy policy |

## Baseline command results from this iteration
- `python db/release_gate.py --mode read_only` -> PASS with warnings.
- `python db/release_gate.py --mode full` -> FAIL in local run when test DB auth is invalid (environment issue, not code path).

## Target metrics by stage
- D1-D14: no finance N+1 path in UI (`render_modulo_finanzas`) and < 1 query batch per list render.
- D15-D30: performance gate in `enforce` for test/preprod.
- D31-D90: p95 list render latency < 800 ms for 1k active cases.
