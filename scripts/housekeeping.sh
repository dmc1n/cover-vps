#!/usr/bin/env bash
# Daily clean-up after the backup (cron 03:30), so the disk does not fill again (2026-10-12):
# - the local safety copies made before a change (cover-data/backup-*-YYYY-MM-DD) older than
#   SAFETY_DAYS (14); the nightly archives hold the state of those days too;
# - the release folders (~/releases/vX.Y.Z) beyond the newest RELEASES_KEEP (8), never the one
#   ~/releases/current points at; every release can be built again from its tag.
# Prints what it removed; DRY_RUN=1 only prints.
set -euo pipefail
DATA=${COVER_DATA_DIR:-$HOME/cover-data}
RELEASES=${COVER_RELEASES:-$HOME/releases}
SAFETY_DAYS=${SAFETY_DAYS:-14}
RELEASES_KEEP=${RELEASES_KEEP:-8}
REPO=$(cd "$(dirname "$0")/.." && pwd)
cutoff=$(date -d "-$SAFETY_DAYS days" +%Y-%m-%d)
run() { if [ "${DRY_RUN:-0}" = 1 ]; then echo "would: $*"; return 1; fi; "$@"; }
for d in "$DATA"/backup-*; do
  [ -d "$d" ] || continue
  day=$(basename "$d" | grep -oE '20[0-9]{2}-[0-9]{2}-[0-9]{2}$' || true)
  [ -n "$day" ] && [[ "$day" < "$cutoff" ]] || continue
  run rm -rf -- "$d" && echo "safety copy removed: $(basename "$d")"
done
current=$(readlink -f "$RELEASES/current" || true)
ls -1 "$RELEASES" | grep -E '^v[0-9]+\.[0-9]+\.[0-9]+$' | sort -V | head -n -"$RELEASES_KEEP" |
  while read -r v; do
    [ "$(readlink -f "$RELEASES/$v")" = "$current" ] && continue
    run git -C "$REPO" worktree remove --force "$RELEASES/$v" && echo "release folder removed: $v"
  done
run git -C "$REPO" worktree prune || true
echo "$(date '+%Y-%m-%d %H:%M') housekeeping done; $(df -h --output=avail "$DATA" | tail -1 | tr -d ' ') free"
