#!/usr/bin/env bash
# Nightly backup of the data (make backup; cron at 02:30). Keeps BACKUP_KEEP (14) archives in
# BACKUP_DIR (~/backups). If an rclone remote named in COVER_BACKUP_REMOTE exists (for example
# "r2:cover-backups", set up with `rclone config` once the Cloudflare account is there), the
# archive is copied there too. Everything the app needs to restore is in the archive: the model
# folders (with cover.json and seams.json), uploads and job files. The original 3D files of the
# manufacturer stay on this server.
# The archive holds the users (password hashes) and the mail settings: only this account may
# read it (ADR-048). The user database is copied with SQLite's own backup, so a login during the
# backup cannot leave it half written; the archive is tested before the old ones are removed.
set -euo pipefail
umask 077
DATA=${COVER_DATA_DIR:-$HOME/cover-data}
DEST=${BACKUP_DIR:-$HOME/backups}
KEEP=${BACKUP_KEEP:-14}
mkdir -p "$DEST"
chmod 700 "$DEST"
STAMP=$(date +%Y%m%d-%H%M)
ARCHIVE="$DEST/cover-data-$STAMP.tar.gz"
SNAP=$(mktemp -d)
trap 'rm -rf "$SNAP"' EXIT
if [ -f "$DATA/app.db" ]; then
  python3 -c "import sqlite3,sys; s=sqlite3.connect(sys.argv[1]); d=sqlite3.connect(sys.argv[2]); s.backup(d); d.close()" \
    "$DATA/app.db" "$SNAP/app.db"
fi
# follow the models link (the web app's models are the repository's models/ folder)
tar -czhf "$ARCHIVE" -C "$DATA" --exclude='*.tmp' --exclude='./app.db' --exclude='./app.db-*' . \
  -C "$SNAP" $( [ -f "$SNAP/app.db" ] && echo app.db )
gzip -t "$ARCHIVE"
chmod 600 "$ARCHIVE"
ls -1t "$DEST"/cover-data-*.tar.gz | tail -n +$((KEEP + 1)) | xargs -r rm --
if [ -n "${COVER_BACKUP_REMOTE:-}" ] && rclone listremotes | grep -q "^${COVER_BACKUP_REMOTE%%:*}:"; then
  rclone copy "$ARCHIVE" "$COVER_BACKUP_REMOTE"
fi
echo "$(date '+%Y-%m-%d %H:%M') $(basename "$ARCHIVE") $(du -h "$ARCHIVE" | cut -f1)" > "$DATA/last_backup.txt"
echo "backup -> $ARCHIVE ($(du -h "$ARCHIVE" | cut -f1))"
