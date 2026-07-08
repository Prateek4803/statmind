#!/usr/bin/env bash
# backup_statmind_db.sh — nightly online-safe backup of the StatMind auth DB.
#
# Session 6 (ops floor): the auth/user SQLite DB previously lived on one EC2
# disk with no backup of any kind — one volume failure would lose every
# registered user. This script:
#   1. Uses `sqlite3 .backup` (safe against concurrent writes — never cp a
#      live SQLite file) to snapshot the DB
#   2. Gzips the snapshot with a UTC timestamp
#   3. Prunes snapshots older than RETENTION_DAYS
#   4. Optionally syncs to S3 if S3_BUCKET is set and aws-cli is present
#
# Config (env vars, all optional):
#   DB_PATH        default /opt/statmind/data/auth.db
#   BACKUP_DIR     default /opt/statmind/backups
#   RETENTION_DAYS default 14
#   S3_BUCKET      e.g. s3://my-bucket/statmind-backups (off if unset)
#
# Install nightly: see scripts/install_backup_cron.sh
# Restore: see OPS.md ("Restoring the auth DB")
set -euo pipefail

DB_PATH="${DB_PATH:-/opt/statmind/data/auth.db}"
BACKUP_DIR="${BACKUP_DIR:-/opt/statmind/backups}"
RETENTION_DAYS="${RETENTION_DAYS:-14}"
S3_BUCKET="${S3_BUCKET:-}"

log() { echo "[$(date -u '+%Y-%m-%d %H:%M:%S UTC')] $*"; }

if ! command -v sqlite3 >/dev/null 2>&1; then
  log "ERROR: sqlite3 not installed (sudo yum install -y sqlite || sudo apt-get install -y sqlite3)"
  exit 1
fi

if [ ! -f "$DB_PATH" ]; then
  log "ERROR: DB not found at $DB_PATH"
  log "Hint: the container writes /app/data/auth.db — check the volume mapping:"
  log "  docker inspect statmind --format '{{ json .Mounts }}'"
  log "Then re-run with DB_PATH=<host path> $0"
  exit 1
fi

mkdir -p "$BACKUP_DIR"
STAMP=$(date -u '+%Y%m%d_%H%M%S')
SNAP="$BACKUP_DIR/auth_${STAMP}.db"

# Online-safe snapshot
sqlite3 "$DB_PATH" ".backup '$SNAP'"

# Integrity check on the snapshot before trusting it
CHECK=$(sqlite3 "$SNAP" "PRAGMA integrity_check;")
if [ "$CHECK" != "ok" ]; then
  log "ERROR: snapshot failed integrity check: $CHECK"
  rm -f "$SNAP"
  exit 1
fi

gzip -f "$SNAP"
SIZE=$(du -h "${SNAP}.gz" | cut -f1)
log "Backup OK: ${SNAP}.gz ($SIZE)"

# Rotation
DELETED=$(find "$BACKUP_DIR" -name 'auth_*.db.gz' -mtime "+${RETENTION_DAYS}" -print -delete | wc -l)
[ "$DELETED" -gt 0 ] && log "Pruned $DELETED snapshot(s) older than ${RETENTION_DAYS}d"

# Optional S3
if [ -n "$S3_BUCKET" ]; then
  if command -v aws >/dev/null 2>&1; then
    aws s3 cp "${SNAP}.gz" "$S3_BUCKET/" --only-show-errors
    log "Synced to $S3_BUCKET/"
  else
    log "WARN: S3_BUCKET set but aws-cli not installed — local backup only"
  fi
fi

log "Done. $(ls "$BACKUP_DIR"/auth_*.db.gz 2>/dev/null | wc -l) snapshot(s) retained."
