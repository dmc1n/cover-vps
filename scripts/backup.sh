#!/usr/bin/env bash
# Nightly backup of the data (make backup; cron at 02:30). Keeps BACKUP_KEEP (5) archives in
# BACKUP_DIR (~/backups). If an rclone remote named in COVER_BACKUP_REMOTE exists (for example
# "r2:cover-backups", set up with `rclone config` once the Cloudflare account is there), the
# archive is copied there too. Everything the app needs to restore is in the archive: the model
# folders (with cover.json and seams.json), uploads and job files. The original 3D files of the
# manufacturer stay on this server.
# Not in the archive: the local safety copies made before a change (cover-data/backup-*; the
# archive of the night before already holds that state) and logs. Before writing, the disk must
# keep room for the new archive (the size of the last one) plus BACKUP_MIN_FREE_GB; old archives
# are removed first (never the newest BACKUP_MIN_KEEP), else the backup stops and says so in
# last_backup.txt, which the watchdog mails (2026-10-12: 8.5 GB archives x 14 filled the disk).
# The archive holds the users (password hashes) and the mail settings: only this account may
# read it (ADR-048). The user database is copied with SQLite's own backup, so a login during the
# backup cannot leave it half written; the archive is tested before the old ones are removed.
set -euo pipefail
umask 077
DATA=${COVER_DATA_DIR:-$HOME/cover-data}
DEST=${BACKUP_DIR:-$HOME/backups}
KEEP=${BACKUP_KEEP:-5}
MIN_KEEP=${BACKUP_MIN_KEEP:-2}
MIN_FREE_GB=${BACKUP_MIN_FREE_GB:-20}
mkdir -p "$DEST"
chmod 700 "$DEST"
STAMP=$(date +%Y%m%d-%H%M)
ARCHIVE="$DEST/cover-data-$STAMP.tar.gz"
PARTIAL="$ARCHIVE.partial"
SNAP=$(mktemp -d)
trap 'rm -rf "$SNAP" "$PARTIAL"' EXIT
fail() {
  echo "$(date '+%Y-%m-%d %H:%M') FAILED: $1" > "$DATA/last_backup.txt"
  echo "backup FAILED: $1" >&2
  exit 1
}
free_gb() { df -P --block-size=1G "$DEST" | awk 'NR==2 {print $4}'; }
archives() { ls -1t "$DEST"/cover-data-*.tar.gz 2>/dev/null || true; }
last=$(archives | head -1)
need=$MIN_FREE_GB
[ -n "$last" ] && need=$(( MIN_FREE_GB + $(du --block-size=1G "$last" | cut -f1) ))
while [ "$(free_gb)" -lt "$need" ] && [ "$(archives | wc -l)" -gt "$MIN_KEEP" ]; do
  rm -- "$(archives | tail -1)"
done
[ "$(free_gb)" -ge "$need" ] || fail "only $(free_gb) GB free, need $need GB; nothing written"
if [ -f "$DATA/app.db" ]; then
  python3 -c "import sqlite3,sys; s=sqlite3.connect(sys.argv[1]); d=sqlite3.connect(sys.argv[2]); s.backup(d); d.close()" \
    "$DATA/app.db" "$SNAP/app.db"
fi
# follow the models link (the web app's models are the repository's models/ folder)
tar -czhf "$PARTIAL" -C "$DATA" --exclude='*.tmp' --exclude='./app.db' --exclude='./app.db-*' \
  --exclude='./backup-*' --exclude='*.log' . \
  -C "$SNAP" $( [ -f "$SNAP/app.db" ] && echo app.db ) || fail "tar stopped (disk full?)"
gzip -t "$PARTIAL" || fail "the archive does not test"
chmod 600 "$PARTIAL"
mv "$PARTIAL" "$ARCHIVE"
archives | tail -n +$((KEEP + 1)) | xargs -r rm --
if [ -n "${COVER_BACKUP_REMOTE:-}" ] && rclone listremotes | grep -q "^${COVER_BACKUP_REMOTE%%:*}:"; then
  rclone copy "$ARCHIVE" "$COVER_BACKUP_REMOTE"
fi
echo "$(date '+%Y-%m-%d %H:%M') $(basename "$ARCHIVE") $(du -h "$ARCHIVE" | cut -f1)" > "$DATA/last_backup.txt"
echo "backup -> $ARCHIVE ($(du -h "$ARCHIVE" | cut -f1))"
