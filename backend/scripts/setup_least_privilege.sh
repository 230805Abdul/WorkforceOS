#!/usr/bin/env bash
# Give the running app its own, restricted PostgreSQL user (docs/SECURITY.md, "Least-privilege database access").
#
#   cd backend && source .venv/bin/activate && ./scripts/setup_least_privilege.sh
#
# 1. creates (or re-passwords) the PostgreSQL user workforceos_app with a random password
# 2. grants it only what the app needs (scripts/grant_app_privileges.sql)
# 3. updates backend/.env: MIGRATION_DATABASE_URL = the owner (for alembic), DATABASE_URL = the new app user
#    (the previous .env is kept as .env.before-least-privilege)
# 4. checks the result
# Needs sudo (to act as the PostgreSQL superuser). Safe to run again.
set -euo pipefail
cd "$(dirname "$0")/.."
APP_USER="${APP_DB_USER:-workforceos_app}"
[ -f .env ] || { echo "backend/.env not found. Create it first (cp .env.example .env)."; exit 1; }
command -v python >/dev/null || { echo "Activate the virtual environment first: source .venv/bin/activate"; exit 1; }

eval "$(python -m app.db_env)"   # the OWNER's connection settings (MIGRATION_DATABASE_URL, else DATABASE_URL)
OWNER="$PGUSER"; DB="$PGDATABASE"; HOST="$PGHOST"; PORT="$PGPORT"
if [ "$OWNER" = "$APP_USER" ]; then
  echo "MIGRATION_DATABASE_URL must point to the database OWNER, not to $APP_USER. Fix backend/.env first."; exit 1
fi
APP_PASSWORD="$(python -c 'import secrets; print(secrets.token_urlsafe(24))')"

echo "Database: $DB on $HOST:$PORT   owner: $OWNER   app user: $APP_USER"
sudo -u postgres psql -q -v ON_ERROR_STOP=1 -v app="$APP_USER" -v pw="$APP_PASSWORD" <<'SQL'
SELECT format('CREATE ROLE %I LOGIN', :'app') WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = :'app') \gexec
ALTER ROLE :"app" WITH LOGIN PASSWORD :'pw' NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
SQL
sudo -u postgres psql -q -d "$DB" -v db="$DB" -v owner="$OWNER" -v app="$APP_USER" -f scripts/grant_app_privileges.sql
echo "Privileges granted."

# Update .env (keep a copy, readable only by you).
umask 077
cp .env .env.before-least-privilege
OWNER_URL="$(python -c 'from app.config import MIGRATION_DATABASE_URL as u; print(u)')"
APP_URL="$(python - "$APP_USER" "$APP_PASSWORD" <<'PY'
import sys
from sqlalchemy.engine import make_url
from app.config import MIGRATION_DATABASE_URL
print(make_url(MIGRATION_DATABASE_URL).set(username=sys.argv[1], password=sys.argv[2]).render_as_string(hide_password=False))
PY
)"
python - "$OWNER_URL" "$APP_URL" <<'PY'
import re, sys
owner_url, app_url = sys.argv[1], sys.argv[2]
text = open(".env").read()
def put(text, key, value):
    line = f"{key}={value}"
    return re.sub(rf"(?m)^#?\s*{key}=.*$", line, text, count=1) if re.search(rf"(?m)^#?\s*{key}=", text) else text.rstrip("\n") + f"\n{line}\n"
text = put(text, "MIGRATION_DATABASE_URL", owner_url)
text = put(text, "DATABASE_URL", app_url)
open(".env", "w").write(text)
PY
chmod 600 .env .env.before-least-privilege
echo "backend/.env updated (previous version: .env.before-least-privilege)."

echo "Checking..."
eval "$(python -m app.db_env --app)"
psql -q -t -A -c "SELECT 'app user can read users: ' || has_table_privilege(current_user, 'users', 'SELECT')"
psql -q -t -A -c "SELECT 'app user can delete audit records: ' || has_table_privilege(current_user, 'audit_events', 'DELETE')"
if psql -q -c "CREATE TABLE should_fail (x int)" >/dev/null 2>&1; then
  echo "WARNING: the app user can still create tables"; exit 1
else
  echo "app user can create tables: false"
fi
echo "Done. Restart the backend. Migrations (alembic) keep using the owner via MIGRATION_DATABASE_URL."
