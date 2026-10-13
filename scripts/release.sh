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
# If the restart fails, or the app does not answer as that release within a minute, it is switched
# back to the release before at once, restarted, and the script says so (ADR-053, ADR-129).
#
# sudo: only `sudo systemctl restart cover-web` is allowed without a password on the server.
# The first install of the service file (cp + daemon-reload) needs a person: the script sees
# that before it changes anything and prints the commands instead of failing half-way.
set -euo pipefail

REPO=${COVER_REPO:-$HOME/cover-pattern-engine}
RELEASES=${COVER_RELEASES:-$HOME/releases}
HEALTH=${COVER_HEALTH_URL:-http://127.0.0.1:8080/api/health}
HEALTH_TRIES=${COVER_HEALTH_TRIES:-60}  # seconds to wait for the app to answer
UNIT=/etc/systemd/system/cover-web.service

die() { echo "release: $*" >&2; exit 1; }

healthy() {  # the app answers as release $1 within HEALTH_TRIES seconds
  local body
  for _ in $(seq "$HEALTH_TRIES"); do
    if body=$(curl -fsS -m 2 "$HEALTH" 2>/dev/null) &&
      { [ -z "${1:-}" ] || grep -q "\"release\": *\"$1\"" <<<"$body"; }; then
      return 0
    fi
    sleep 1
  done
  return 1
}

restart() {  # the one password-free sudo command; its failure is reported, not fatal here
  sudo -n systemctl restart cover-web
}

point() {  # ~/releases/current -> $1, atomically
  ln -sfn "$1" "$RELEASES/current.new"
  mv -T "$RELEASES/current.new" "$RELEASES/current"
}

needs_person() {  # the service does not run from ~/releases/current yet: print what a person runs
  local target=$1
  if [ "$(systemctl show -p WorkingDirectory --value cover-web)" != "$RELEASES/current" ]; then
    # the first release: the service must run from ~/releases/current. Installing the service
    # file needs sudo with a password: a person does it, nothing is changed here
    cat >&2 <<EOF
release: the service cover-web does not run from $RELEASES/current yet. Installing its
service file needs a person (sudo with a password). ${target##*/} is built; nothing was switched. Run:

  cp $UNIT $RELEASES/cover-web.service.before
  ln -sfn $target $RELEASES/current
  sudo cp $target/deploy/cover-web.service $UNIT
  sudo systemctl daemon-reload
  sudo systemctl restart cover-web
  curl -fsS $HEALTH

and, if it does not answer: sudo cp $RELEASES/cover-web.service.before $UNIT &&
sudo systemctl daemon-reload && sudo systemctl restart cover-web
EOF
    exit 2
  fi
}

switch() {  # point ~/releases/current at $1 and restart the app; back to the one before if it fails
  local target=$RELEASES/$1 before prev
  [ -d "$target/.venv" ] || die "$1 is not built in $RELEASES"
  before=$(readlink "$RELEASES/current" 2>/dev/null || true)
  prev=${before##*/}
  needs_person "$target"
  point "$target"
  local why=""
  if ! restart; then
    why="the restart failed"
  elif ! healthy "$1"; then
    why="it does not answer as $1 within ${HEALTH_TRIES} s"
  fi
  if [ -z "$why" ]; then
    echo "$(date '+%F %T') $1 live (before: $prev)" >> "$RELEASES/history.log"
    echo "release: $1 is live"
    return 0
  fi
  echo "release: $1 FAILED: $why" >&2
  if [ -z "$before" ] || [ "$before" = "$target" ]; then
    echo "release: no release before $1 to go back to; check 'journalctl -u cover-web'" >&2
    echo "$(date '+%F %T') $1 FAILED ($why), nothing to go back to" >> "$RELEASES/history.log"
    exit 1
  fi
  point "$before"
  if restart && healthy "$prev"; then
    echo "release: switched back to $prev automatically; $prev is live again" >&2
    echo "$(date '+%F %T') $1 FAILED ($why), switched back to $prev" >> "$RELEASES/history.log"
  else
    echo "release: switched back to $prev, but $prev does not answer either: check" \
      "'journalctl -u cover-web' (sudo systemctl restart cover-web)" >&2
    echo "$(date '+%F %T') $1 FAILED ($why), back to $prev which does not answer" \
      >> "$RELEASES/history.log"
  fi
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
