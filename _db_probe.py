import os, sys
import psycopg2

dsn = os.getenv("DATABASE_URL","").strip()
print("DATABASE_URL set:", bool(dsn))
if dsn:
    safe = dsn
    if "://" in safe and "@" in safe:
        # redacción básica usuario:pass@
        import re
        safe = re.sub(r"://([^:]+):([^@]+)@", r"://\1:***@", safe)
    print("DATABASE_URL:", safe)

if not dsn:
    sys.exit(2)

try:
    conn = psycopg2.connect(dsn, connect_timeout=3)
    cur = conn.cursor()
    cur.execute("SELECT version();")
    print("version:", cur.fetchone()[0])
    cur.execute("SELECT current_database(), current_user;")
    print("db/user:", cur.fetchone())
    cur.execute("SELECT to_regclass('public.cases'), to_regclass('public.clients'), to_regclass('public.documents'), to_regclass('public.tasks');")
    print("tables:", cur.fetchone())
    conn.close()
    print("OK")
except Exception as e:
    print("FAIL:", type(e).__name__, str(e))
    raise
