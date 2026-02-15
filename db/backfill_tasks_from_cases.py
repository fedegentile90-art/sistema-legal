"""
Backfill idempotente de agenda legacy (cases.*) hacia tasks.

Regla:
- Crea 1 tarea primaria por caso cuando el caso tenga fecha/tarea/responsable.
- Usa marca extra.legacy_source_case_id + extra.is_primary_legacy para evitar duplicados.
"""

from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass
from typing import Any

from db.health import parse_database_url


@dataclass
class BackfillStats:
    scanned: int = 0
    created: int = 0
    skipped_existing: int = 0
    skipped_empty: int = 0
    errors: int = 0


def _connect():
    import psycopg2  # type: ignore

    url = parse_database_url(os.environ.get("DATABASE_URL", ""))
    if not url:
        raise RuntimeError("DATABASE_URL no configurada.")
    return psycopg2.connect(url, connect_timeout=5)


def _has_content(title: str, due_date: Any, assigned_to: str) -> bool:
    return bool(str(title or "").strip() or due_date or str(assigned_to or "").strip())


def run_backfill(*, dry_run: bool = False, limit: int = 0) -> BackfillStats:
    stats = BackfillStats()
    with _connect() as conn:
        with conn.cursor() as cur:
            query = """
                SELECT
                    c.id,
                    c.causa,
                    c.tarea_pendiente,
                    c.fecha_tarea,
                    c.responsable
                FROM cases c
                ORDER BY c.created_at ASC
            """
            if limit > 0:
                query += " LIMIT %s"
                cur.execute(query, (int(limit),))
            else:
                cur.execute(query)

            rows = cur.fetchall()
            for row in rows:
                stats.scanned += 1
                case_id, causa, tarea_pendiente, fecha_tarea, responsable = row
                case_id_str = str(case_id)

                title = str(tarea_pendiente or "").strip() or f"Seguimiento: {str(causa or '').strip() or 'Caso'}"
                assigned_to = str(responsable or "").strip()
                due_date = fecha_tarea
                if not _has_content(title, due_date, assigned_to):
                    stats.skipped_empty += 1
                    continue

                cur.execute(
                    """
                    SELECT id
                    FROM tasks
                    WHERE (extra->>'legacy_source_case_id') = %s
                      AND (extra->>'is_primary_legacy') = '1'
                    LIMIT 1
                    """,
                    (case_id_str,),
                )
                if cur.fetchone():
                    stats.skipped_existing += 1
                    continue

                extra = {
                    "legacy_source_case_id": case_id_str,
                    "is_primary_legacy": "1",
                    "sync_origin": "backfill_tasks_from_cases",
                }
                if dry_run:
                    stats.created += 1
                    continue

                try:
                    cur.execute(
                        """
                        INSERT INTO tasks (
                            case_id,
                            title,
                            description,
                            due_date,
                            priority,
                            status,
                            assigned_to,
                            extra
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb)
                        """,
                        (
                            case_id_str,
                            title[:255],
                            "",
                            due_date,
                            "normal",
                            "pendiente",
                            assigned_to[:100],
                            json.dumps(extra, ensure_ascii=False),
                        ),
                    )
                    stats.created += 1
                except Exception:
                    stats.errors += 1
    return stats


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill idempotente cases -> tasks.")
    parser.add_argument("--dry-run", action="store_true", help="No escribe cambios, solo simula.")
    parser.add_argument("--limit", type=int, default=0, help="Limita la cantidad de casos procesados.")
    args = parser.parse_args()

    stats = run_backfill(dry_run=bool(args.dry_run), limit=max(0, int(args.limit)))
    print(
        "BACKFILL TASKS RESULT | "
        f"scanned={stats.scanned} created={stats.created} "
        f"skipped_existing={stats.skipped_existing} skipped_empty={stats.skipped_empty} errors={stats.errors}"
    )
    if stats.errors > 0:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
