#!/usr/bin/env bash
# StatMind — daily SQLite backup. Cron:
#   15 3 * * * /opt/statmind/scripts/backup_db.sh >> /var/log/statmind-backup.log 2>&1
set -euo pipefail
DATA_DIR="${STATMIND_DATA_DIR:-/opt/statmind/data}"
DB_FILE="${DATA_DIR}/statmind.db"
BACKUP_DIR="${STATMIND_BACKUP_DIR:-/opt/statmind/backups}"
RETENTION_DAYS="${RETENTION_DAYS:-14}"
S3_BUCKET="${S3_BUCKET:-}"
ts="$(date +%Y%m%d_%H%M%S)"
mkdir -p "$BACKUP_DIR"
if [ ! -f "$DB_FILE" ]; then echo "ERROR: DB not found at $DB_FILE" >&2; exit 1; fi
out="${BACKUP_DIR}/statmind_${ts}.db"
if command -v sqlite3 >/dev/null 2>&1; then sqlite3 "$DB_FILE" ".backup '${out}'"; else cp "$DB_FILE" "$out"; fi
gzip -f "$out"
echo "backup: ${out}.gz"
if [ -n "$S3_BUCKET" ] && command -v aws >/dev/null 2>&1; then aws s3 cp "${out}.gz" "${S3_BUCKET}/"; fi
find "$BACKUP_DIR" -name 'statmind_*.db.gz' -mtime +"$RETENTION_DAYS" -delete
echo "pruned backups older than ${RETENTION_DAYS}d"
