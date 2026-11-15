#!/usr/bin/env bash
# Back up the WorkforceOS database: compressed, timestamped, private, checked, old ones pruned.
#
#   cd backend && source .venv/bin/activate && ./scripts/backup_db.sh
#
# Settings (environment variables):
#   BACKUP_DIR   where to put them   (default: ~/workforceos-backups; keep it OUTSIDE the project folder)
#   KEEP_DAYS    delete backups older than this many days   (default: 14)
#
# A backup contains everything: names, e-mails, password HASHES, the audit log. Treat it like the database itself:
# the folder is created readable only by you; copy backups off this machine (encrypted) for real protection.
set -euo pipefail
cd "$(dirname "$0")/.."
command -v python >/dev/null || { echo "Activate the virtual environment first: source .venv/bin/activate"; exit 1; }
BACKUP_DIR="${BACKUP_DIR:-$HOME/workforceos-backups}"
KEEP_DAYS="${KEEP_DAYS:-14}"

eval "$(python -m app.db_env)"   # owner credentials: a backup must be able to read every table
umask 077                        # files and folders created from here on: owner-only
mkdir -p "$BACKUP_DIR"
chmod 700 "$BACKUP_DIR"
FILE="$BACKUP_DIR/${PGDATABASE}-$(date +%Y%m%d-%H%M%S).dump"

echo "Backing up database '$PGDATABASE' to $FILE ..."
pg_dump --format=custom --compress=6 --file="$FILE" "$PGDATABASE"

# Check: the archive must be readable and contain the core tables.
pg_restore --list "$FILE" > "$FILE.contents"
for table in users employees departments audit_events; do
  grep -q "TABLE DATA public $table " "$FILE.contents" || { echo "CHECK FAILED: table $table missing in backup"; exit 1; }
done
rm "$FILE.contents"
sha256sum "$FILE" > "$FILE.sha256"   # lets you detect a damaged or altered file later: sha256sum -c <file>.sha256
echo "OK: $(du -h "$FILE" | cut -f1), checksum in $(basename "$FILE").sha256"

# Retention: remove backups older than KEEP_DAYS.
find "$BACKUP_DIR" -maxdepth 1 -name "${PGDATABASE}-*.dump*" -type f -mtime "+$KEEP_DAYS" -print -delete | sed 's/^/Removed old backup: /'
echo "Backups in $BACKUP_DIR: $(find "$BACKUP_DIR" -maxdepth 1 -name "${PGDATABASE}-*.dump" | wc -l)"
