#!/usr/bin/env bash
# A release of Cover Studio (ADR-053): the tested main gets a version tag, is built in its own
# folder (~/releases/<version>, with its own Python environment and web pages) and the app is
# switched over to it. The data (models, users, uploads) stays where it is, outside the
# releases, so every release sees the same data.
#
#   scripts/release.sh v1.0.0 "what is new, in one line"
#   scripts/release.sh --switch v1.0.0      only switch the app to a release built before
#   scripts/rollback.sh                     back to the release before (see there)
#
# If the app does not answer after the switch, it is switched back at once.
set -euo pipefail

REPO=${COVER_REPO:-$HOME/cover-pattern-engine}
RELEASES=${COVER_RELEASES:-$HOME/releases}
HEALTH=http://127.0.0.1:8080/api/health

die() { echo "release: $*" >&2; exit 1; }

healthy() {  # the app answers within 60 s
  for _ in $(seq 60); do
    if curl -fsS -m 2 "$HEALTH" >/dev/null 2>&1; then return 0; fi
    sleep 1
  done
  return 1
}

switch() {  # point ~/releases/current at $1 and restart the app; back to the one before if it fails
  local target=$RELEASES/$1 before
  [ -d "$target/.venv" ] || die "$1 is not built in $RELEASES"
  before=$(readlink "$RELEASES/current" 2>/dev/null || true)
  ln -sfn "$target" "$RELEASES/current.new"
  mv -T "$RELEASES/current.new" "$RELEASES/current"
  if [ "$(systemctl show -p WorkingDirectory --value cover-web)" != "$RELEASES/current" ]; then
    # the first release: the service runs from ~/releases/current from now on (the old
    # service file is kept, to go back to if this release does not answer)
    cp /etc/systemd/system/cover-web.service "$RELEASES/cover-web.service.before"
    sudo cp "$target/deploy/cover-web.service" /etc/systemd/system/cover-web.service
    sudo systemctl daemon-reload
  fi
  sudo systemctl restart cover-web
  if healthy; then
    echo "$(date '+%F %T') $1 live (before: ${before##*/})" >> "$RELEASES/history.log"
    echo "release: $1 is live"
    return 0
  fi
  echo "release: $1 does not answer; back to ${before##*/}" >&2
  if [ -n "$before" ]; then
    ln -sfn "$before" "$RELEASES/current.new"
    mv -T "$RELEASES/current.new" "$RELEASES/current"
    sudo systemctl restart cover-web
    healthy || echo "release: ${before##*/} does not answer either: check 'journalctl -u cover-web'" >&2
  elif [ -f "$RELEASES/cover-web.service.before" ]; then  # the first release: the old service
    sudo cp "$RELEASES/cover-web.service.before" /etc/systemd/system/cover-web.service
    sudo systemctl daemon-reload
    sudo systemctl restart cover-web
    rm -f "$RELEASES/current"
  fi
  echo "$(date '+%F %T') $1 FAILED, back to ${before##*/}" >> "$RELEASES/history.log"
  exit 1
}

if [ "${1:-}" = "--switch" ]; then
  switch "${2:?which release, e.g. v1.0.0}"
  exit 0
fi

ver=${1:?version, e.g. v1.0.0}
note=${2:?one line: what is new}
[[ $ver =~ ^v[0-9]+\.[0-9]+\.[0-9]+$ ]] || die "a version looks like v1.2.3"
mkdir -p "$RELEASES"
cd "$REPO"
[ "$(git branch --show-current)" = main ] || die "releases come from main"
[ -z "$(git status --porcelain --untracked-files=no)" ] || die "commit the changes first"
! git rev-parse -q --verify "refs/tags/$ver" >/dev/null || die "$ver exists already"
[ ! -e "$RELEASES/$ver" ] || die "$RELEASES/$ver exists already"

make test
git tag -a "$ver" -m "$note"
git push origin main "$ver"

dir=$RELEASES/$ver
git worktree add --detach "$dir" "$ver"
cd "$dir"
# the data and the secrets stay outside the release
ln -s "$REPO/models" models
ln -s "$REPO/out" out
ln -s "$REPO/deploy/.env" deploy/.env
uv sync --all-packages --all-extras --frozen
(cd apps/web && npm ci --no-audit --no-fund && npm run build)
switch "$ver"
