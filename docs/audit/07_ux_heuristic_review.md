# UX Heuristic Review (2026-02-14)

## Heuristic findings
| ID | Finding | Evidence | Sev | Business risk | Technical risk | Recommended solution | Effort | Dependencies/order |
|---|---|---|---|---|---|---|---|---|
| U01 | Unsafe legacy badge rendering path fixed with escaped output | `views.py:272`, `views.py:2992`, test `tests/test_views_security.py:4` | High | UI injection and trust loss | Script execution in browser | Keep escaped helper and regression tests | S | None |
| U02 | Access-denied UX now explicit in strict RBAC mode | `views.py:263`, `views.py:267`, `app.py:243` | Medium | Unauthorized actions confusion | Hidden authorization errors | Keep consistent denied messaging + audit log event | S | Auth/RBAC flags |
| U03 | Export controls now role-aware and traceable | `views.py:2771`, `views.py:2784`, `views.py:3615`, `exports.py:133` | Medium | Data leakage via download | Uncontrolled export channel | Enforce `VG_EXPORT_STRICT=1` on sensitive environments | S | Auth enforcement |
| U04 | Finance module latency risk reduced by batch fetch | `views.py:3721`, `views.py:3724`, `repo_db.py:893` | Medium | Slower workflows | UI timeout on large datasets | Preserve batch path and measure p95 list load | M | None |
| U05 | Some UI modules still rely on `unsafe_allow_html=True` for static styles | `views.py:1790`, `views.py:1948`, `views.py:1970` | Low | Limited if static only | Future misuse risk | Restrict dynamic content in unsafe blocks and lint for unsafe_html usage | S | None |

## Accessibility and consistency notes
- Positive: route structure and mode handling are unified in views state model (`views.py:477`, `views.py:520`).
- Gap: no explicit automated a11y checks in CI.
- Recommendation: add lightweight UI smoke/a11y assertions in `db/ux_*` suites before strict rollout.
