#!/usr/bin/env bash
# Restore a backup into a NEW database and verify it. Never overwrites the database you're using.
#
#   ./scripts/restore_db.sh ~/workforceos-backups/workforceos-20261115-101500.dump [new_database_name]
#
# Then, to switch the app over: put the new name at the end of DATABASE_URL and MIGRATION_DATABASE_URL in
# backend/.env, run ./scripts/setup_least_privilege.sh if you use it, and restart the backend.
set -euo pipefail
cd "$(dirname "$0")/.."
command -v python >/dev/null || { echo "Activate the virtual environment first: source .venv/bin/activate"; exit 1; }
FILE="${1:?Usage: $0 <backup.dump> [new_database_name]}"
[ -f "$FILE" ] || { echo "No such file: $FILE"; exit 1; }
if [ -f "$FILE.sha256" ]; then
  (cd "$(dirname "$FILE")" && sha256sum --quiet -c "$(basename "$FILE").sha256") || { echo "CHECKSUM MISMATCH: the backup file was damaged or altered."; exit 1; }
  echo "Checksum OK."
fi

eval "$(python -m app.db_env)"
TARGET="${2:-${PGDATABASE}_restored_$(date +%Y%m%d_%H%M%S)}"
[ "$TARGET" != "$PGDATABASE" ] || { echo "Refusing to restore over the live database '$PGDATABASE'. Choose another name."; exit 1; }

echo "Creating database $TARGET (owner $PGUSER) ..."
sudo -u postgres createdb -O "$PGUSER" "$TARGET"
echo "Restoring ..."
pg_restore --dbname="$TARGET" --no-owner --role="$PGUSER" --exit-on-error "$FILE"

echo "Verifying ..."
psql -d "$TARGET" -q -t -A -c "SELECT 'schema version: ' || version_num FROM alembic_version"
for table in users employees departments jobs candidates audit_events; do
  printf "  %-14s %s rows\n" "$table" "$(psql -d "$TARGET" -q -t -A -c "SELECT count(*) FROM $table")"
done
MIGRATION_DATABASE_URL= DATABASE_URL="$(python - "$TARGET" <<'PY'
import sys
from sqlalchemy.engine import make_url
from app.config import MIGRATION_DATABASE_URL
print(make_url(MIGRATION_DATABASE_URL).set(database=sys.argv[1]).render_as_string(hide_password=False))
PY
)" python -m app.audit_verify | tail -1
echo "Restored into '$TARGET'. Your live database '$PGDATABASE' was not touched."
