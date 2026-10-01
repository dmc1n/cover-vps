#!/usr/bin/env bash
# End-to-end browser test of the web app (make e2e). Starts the app on port 18181 with an
# empty data directory, runs apps/web/e2e/flow.py in the Playwright Docker image, stops the app.
set -euo pipefail
cd "$(dirname "$0")/.."
DATA=$(mktemp -d)
trap 'kill $APP 2>/dev/null || true; rm -rf "$DATA"' EXIT
[ -f testdata/generated/chair.stl ] || uv run python testdata/generate.py
(cd apps/web && npm run build >/dev/null)
# a user for the browser test (logins are on, as in production)
COVER_DATA_DIR=$DATA uv run python -c "
from pathlib import Path; import os
from coverapi.auth import Auth
a = Auth(Path(os.environ['COVER_DATA_DIR']) / 'app.db')
u = a.add_user('tester', 'Tester', 'admin', None, True)
a.set_password(a.invite(u.id), 'browser-test-password')"
COVER_DATA_DIR=$DATA COVER_PORT=18181 uv run cover-web >"$DATA/web.log" 2>&1 &
APP=$!
for _ in $(seq 1 60); do curl -sf http://127.0.0.1:18181/api/health >/dev/null && break; sleep 1; done
docker run --rm --network host -v "$PWD:/repo:ro" mcr.microsoft.com/playwright/python:v1.63.0-noble \
  bash -c "pip install -q playwright==1.63.0 >/dev/null 2>&1 && python /repo/apps/web/e2e/flow.py"
