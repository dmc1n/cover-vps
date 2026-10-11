#!/usr/bin/env bash
# Blender 4.2 (Cycles, CPU) in the Playwright image, which has the X libraries the host lacks
# (ADR-108, ADR-116). Gentle on the shared server: nice 19, at most CPUS cores and MEM memory,
# one render at a time. The container runs as you, so its files are yours; paths under /home/dev
# are the same inside and out.
#
#     scripts/film/blender.sh -P scripts/film/render_scroll.py -- --data DIR --out DIR ...
#     CPUS=6 MEM=9g NAME=film-scroll scripts/film/blender.sh ...
#
# The container is named NAME (default cover-film-render) and its id written to NAME.cid in
# ~/opt/film2/logs, so it can be stopped by name or id (`docker stop NAME`), never by a pattern.
set -euo pipefail
BLENDER=${BLENDER:-/home/dev/opt/blender-4.2.3-linux-x64/blender}
IMAGE=${IMAGE:-mcr.microsoft.com/playwright/python:v1.63.0-noble}
NAME=${NAME:-cover-film-render}
LOGS=${LOGS:-/home/dev/opt/film2/logs}
mkdir -p "$LOGS"
rm -f "$LOGS/$NAME.cid"
exec docker run --rm --name "$NAME" --cidfile "$LOGS/$NAME.cid" \
  --cpus="${CPUS:-6}" --memory="${MEM:-9g}" --memory-swap="${MEM:-9g}" \
  --user "$(id -u):$(id -g)" -e HOME=/tmp \
  -v /home/dev:/home/dev -w "$PWD" \
  "$IMAGE" nice -n 19 "$BLENDER" -b "$@"
