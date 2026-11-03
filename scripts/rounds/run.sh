#!/usr/bin/env bash
# A scheduled round by Claude Code without a session (crontab; 3 Nov 2026). Usage: run.sh daily|weekly
# One round at a time (flock); the prompt is <name>.md next to this script plus common.md; the
# log goes to ~/cover-data/rounds/<name>-<stamp>.log. Permission mode "auto": the same safety
# checks as an interactive session; a refused action is not worked around (common.md).
set -uo pipefail
name=${1:?daily or weekly}
here=$(cd "$(dirname "$0")" && pwd)
logs=$HOME/cover-data/rounds
mkdir -p "$logs"
log="$logs/$name-$(date +%Y%m%d-%H%M).log"
exec 9>"$logs/.lock"
if ! flock -w 3600 9; then echo "$(date -Is) another round still runs; skipped" >> "$logs/skipped.log"; exit 0; fi
export PATH=$HOME/.local/bin:/usr/local/bin:/usr/bin:/bin LANG=C.UTF-8 COVER_DATA_DIR=$HOME/cover-data
cd "$HOME" || exit 1
prompt="$(cat "$here/common.md" "$here/$name.md")"
timeout 4h claude -p "$prompt" --permission-mode auto > "$log" 2>&1
rc=$?
echo "$(date -Is) $name rc=$rc $log" >> "$logs/rounds.log"
find "$logs" -name '*.log' ! -name rounds.log ! -name skipped.log -mtime +30 -delete
exit $rc
