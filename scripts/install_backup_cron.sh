#!/usr/bin/env bash
# install_backup_cron.sh — one-time install of the nightly backup cron entry.
# Run once on the EC2 box:  bash /opt/statmind/scripts/install_backup_cron.sh
# Idempotent: re-running replaces the existing entry.
set -euo pipefail

SCRIPT="/opt/statmind/scripts/backup_statmind_db.sh"
LOG="/opt/statmind/backups/backup.log"
ENTRY="17 3 * * * /usr/bin/env bash $SCRIPT >> $LOG 2>&1"

chmod +x "$SCRIPT"
mkdir -p /opt/statmind/backups

# Robust against an EMPTY crontab: `crontab -l` exits non-zero when no
# crontab exists, and under `set -euo pipefail` the previous one-liner died
# silently before installing anything (found live on EC2, 2026-07-08).
TMP=$(mktemp)
crontab -l 2>/dev/null | grep -v 'backup_statmind_db.sh' > "$TMP" || true
echo "$ENTRY" >> "$TMP"
crontab "$TMP"
rm -f "$TMP"
echo "Installed nightly backup cron (03:17 UTC). Current crontab:"
crontab -l | grep backup_statmind_db.sh
echo
echo "Run one now to verify:  bash $SCRIPT"
