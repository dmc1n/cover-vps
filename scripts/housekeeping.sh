#!/usr/bin/env bash
# Daily clean-up after the backup (cron 03:30), so the disk does not fill again (2026-10-12):
# - the local safety copies made before a change (cover-data/backup-*-YYYY-MM-DD) older than
#   SAFETY_DAYS (14); the nightly archives hold the state of those days too;
# - the release folders (~/releases/vX.Y.Z) beyond the newest RELEASES_KEEP (8), never the one
#   ~/releases/current points at; every release can be built again from its tag;
# - price proposals (shop_quotes, b2b_quotes, quotes) older than limits.quotes_keep_days (60)
#   that no order or request names (scripts/quotes_clean.py, ADR-123);
# - scratch older than TMP_DAYS (7) in cover-data/tmp-agents, cover-data/tmp-release and
#   /tmp/pytest-of-$USER, keeping live processes' folders and the workspaces' reports, and the
#   agents' git worktrees merged into main and unchanged for TMP_DAYS (scripts/tmp_clean.py,
#   ADR-153; never forced).
# Prints what it removed and the space freed; --dry-run (or DRY_RUN=1) only prints.
set -euo pipefail
for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY_RUN=1 ;;
    *) echo "usage: $0 [--dry-run]" >&2; exit 2 ;;
  esac
done
DATA=${COVER_DATA_DIR:-$HOME/cover-data}
RELEASES=${COVER_RELEASES:-$HOME/releases}
SAFETY_DAYS=${SAFETY_DAYS:-14}
RELEASES_KEEP=${RELEASES_KEEP:-8}
REPO=$(cd "$(dirname "$0")/.." && pwd)
TMP_DAYS=${TMP_DAYS:-7}
cutoff=$(date -d "-$SAFETY_DAYS days" +%Y-%m-%d)
avail_kb() { df -P -k "$DATA" | awk 'NR==2 {print $4}'; }
before=$(avail_kb)
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
PY="$REPO/.venv/bin/python"; [ -x "$PY" ] || PY=python3
dry=(); [ "${DRY_RUN:-0}" = 1 ] && dry=(--dry-run)
COVER_DATA_DIR="$DATA" "$PY" "$REPO/scripts/quotes_clean.py" --data "$DATA" "${dry[@]}" ||
  echo "proposals: clean-up failed"
"$PY" "$REPO/scripts/tmp_clean.py" --days "$TMP_DAYS" --repo "$REPO" "${dry[@]}" ||
  echo "scratch: clean-up failed"
freed_mb=$(( ($(avail_kb) - before) / 1024 ))
echo "$(date '+%Y-%m-%d %H:%M') housekeeping done; ${freed_mb} MB freed on the data disk;" \
  "$(df -h --output=avail "$DATA" | tail -1 | tr -d ' ') free"
