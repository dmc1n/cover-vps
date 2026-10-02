#!/usr/bin/env bash
# Back to an earlier release of Cover Studio (ADR-053), in about ten seconds: the app is
# switched to that release's folder and restarted. The data is not touched.
#
#   scripts/rollback.sh             the release that was live before this one
#   scripts/rollback.sh v1.0.0      a chosen release
#   scripts/rollback.sh --list      the releases on this server, the live one marked
set -euo pipefail

RELEASES=${COVER_RELEASES:-$HOME/releases}
here=$(dirname "$(readlink -f "$0")")
live=$(basename "$(readlink "$RELEASES/current" 2>/dev/null || echo none)")

if [ "${1:-}" = "--list" ]; then
  for d in $(ls -1d "$RELEASES"/v* 2>/dev/null | sort -V); do
    v=${d##*/}
    if [ "$v" = "$live" ]; then echo "$v  (live)"; else echo "$v"; fi
  done
  exit 0
fi

target=${1:-}
if [ -z "$target" ]; then  # the one before the live one, from the history
  target=$(grep " live " "$RELEASES/history.log" | awk '{print $3}' | grep -vx "$live" | tail -1)
  [ -n "$target" ] || { echo "rollback: no earlier release" >&2; exit 1; }
fi
echo "rollback: $live -> $target"
exec "$here/release.sh" --switch "$target"
