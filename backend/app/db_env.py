"""Print PostgreSQL connection settings as shell variables for the backup/restore scripts:

    eval "$(python -m app.db_env)"            # owner (MIGRATION_DATABASE_URL): backups must read every table
    eval "$(python -m app.db_env --app)"      # the app's own user (DATABASE_URL)

Variables (PGHOST, PGPORT, PGUSER, PGDATABASE, PGPASSWORD) instead of a URL on the command line: command lines are
visible to every user of the machine (`ps`), a process's environment only to its owner.
"""
import shlex
import sys

from sqlalchemy.engine import make_url

from app.config import DATABASE_URL, MIGRATION_DATABASE_URL

url = make_url(DATABASE_URL if "--app" in sys.argv else MIGRATION_DATABASE_URL)
if not url.drivername.startswith("postgresql"):
    sys.exit("This only works with PostgreSQL (DATABASE_URL points elsewhere).")
values = {"PGHOST": url.host or "localhost", "PGPORT": str(url.port or 5432), "PGUSER": url.username or "",
          "PGDATABASE": url.database or "", "PGPASSWORD": url.password or ""}
print(" ".join(f"export {k}={shlex.quote(v)};" for k, v in values.items()))
