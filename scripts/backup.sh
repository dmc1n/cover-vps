#!/usr/bin/env bash
# Nightly backup of the data (make backup; cron at 02:30). Keeps BACKUP_KEEP (14) archives in
# BACKUP_DIR (~/backups). If an rclone remote named in COVER_BACKUP_REMOTE exists (for example
# "r2:cover-backups", set up with `rclone config` once the Cloudflare account is there), the
# archive is copied there too. Everything the app needs to restore is in the archive: the model
# folders (with cover.json and seams.json), uploads and job files. The original 3D files of the
# manufacturer stay on this server.
set -euo pipefail
DATA=${COVER_DATA_DIR:-$HOME/cover-data}
DEST=${BACKUP_DIR:-$HOME/backups}
KEEP=${BACKUP_KEEP:-14}
mkdir -p "$DEST"
STAMP=$(date +%Y%m%d-%H%M)
ARCHIVE="$DEST/cover-data-$STAMP.tar.gz"
# follow the models link (the web app's models are the repository's models/ folder)
tar -czhf "$ARCHIVE" -C "$DATA" --exclude='*.tmp' .
ls -1t "$DEST"/cover-data-*.tar.gz | tail -n +$((KEEP + 1)) | xargs -r rm --
if [ -n "${COVER_BACKUP_REMOTE:-}" ] && rclone listremotes | grep -q "^${COVER_BACKUP_REMOTE%%:*}:"; then
  rclone copy "$ARCHIVE" "$COVER_BACKUP_REMOTE"
fi
echo "backup -> $ARCHIVE ($(du -h "$ARCHIVE" | cut -f1))"
