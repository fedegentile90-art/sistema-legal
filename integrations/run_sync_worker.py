"""Worker CLI para sincronizacion incremental Google Calendar."""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone

from integrations.google_calendar_sync import sync_all_active_connections
from repo import GestorCasos


def _env_bool(name: str, default: bool = False) -> bool:
    raw = str(os.environ.get(name, "")).strip().lower()
    if not raw:
        return bool(default)
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off"}:
        return False
    return bool(default)


def main() -> int:
    parser = argparse.ArgumentParser(description="Google Calendar sync worker.")
    parser.add_argument("--json", action="store_true", help="Imprime salida JSON compacta.")
    args = parser.parse_args()

    if not _env_bool("VG_GOOGLE_CALENDAR_ENABLED", default=False):
        print("SYNC SKIPPED | VG_GOOGLE_CALENDAR_ENABLED=0")
        return 0
    if not _env_bool("VG_GOOGLE_CALENDAR_SYNC_ENABLED", default=False):
        print("SYNC SKIPPED | VG_GOOGLE_CALENDAR_SYNC_ENABLED=0")
        return 0

    gestor = GestorCasos()
    actor_ctx = {
        "user_id": "system",
        "user_name": "google-sync-worker",
        "role": "system",
        "request_id": datetime.now(timezone.utc).isoformat(),
        "user_agent": "google-calendar-sync-worker",
    }
    rows = sync_all_active_connections(gestor, actor_ctx=actor_ctx)
    total = len(rows)
    ok_count = sum(1 for r in rows if r.get("ok"))
    err_count = sum(1 for r in rows if not r.get("ok"))
    payload = {"total": total, "ok": ok_count, "errors": err_count, "rows": rows}

    if args.json:
        print(json.dumps(payload, ensure_ascii=False))
    else:
        print(f"SYNC RESULT | total={total} ok={ok_count} errors={err_count}")
        for row in rows:
            print(
                " - "
                f"user={row.get('user_id', '')} conn={row.get('connection_id', '')} "
                f"ok={row.get('ok', False)} created={row.get('created_events', 0)} "
                f"updated={row.get('updated_events', 0)} pulled={row.get('pulled_updates', 0)} "
                f"conflicts={row.get('conflicts', 0)} errors={row.get('errors', 0)}"
            )
    return 0 if err_count == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())

