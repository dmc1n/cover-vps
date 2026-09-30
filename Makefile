# Cover pattern engine — see CLAUDE.md "Commands".
.PHONY: setup test lint shapes testsheets golden demo api-dev web-dev web-build e2e deploy backup

UV ?= uv
RUN := $(UV) run

setup:
	$(UV) sync --all-packages --all-extras
	@if [ -f apps/web/package.json ]; then cd apps/web && npm install; else echo "apps/web: nothing to install yet (M6)"; fi
	$(RUN) pre-commit install

test: lint
	$(RUN) pytest -q

lint:
	$(RUN) ruff check .
	$(RUN) ruff format --check .
	$(RUN) mypy

shapes:
	$(RUN) python testdata/generate.py

testsheets:
	$(RUN) cover testsheet --out testdata/machine

golden:
	COVER_UPDATE_GOLDEN=1 $(RUN) pytest -q engine/tests/test_golden_info.py
	COVER_UPDATE_GOLDEN=1 $(RUN) pytest -q engine/tests/test_hull.py -k golden
	COVER_UPDATE_GOLDEN=1 $(RUN) pytest -q engine/tests/test_flatten.py -k golden

demo: shapes
	$(RUN) cover run testdata/generated/chair.stl --out out/chair

# the web app: API and built pages on http://127.0.0.1:8080 (data in COVER_DATA_DIR)
COVER_DATA_DIR ?= $(HOME)/cover-data
api-dev: web-build
	COVER_DATA_DIR=$(COVER_DATA_DIR) $(RUN) cover-web

# live-reloading pages on http://127.0.0.1:5173, forwarding /api to api-dev
web-dev:
	cd apps/web && npm run dev

web-build:
	cd apps/web && npm install --no-audit --no-fund && npm run build

# the whole flow in a real browser (Playwright in Docker)
e2e:
	scripts/e2e.sh

deploy:
	docker compose -f deploy/docker-compose.yml up -d --build app

# the data directory to ~/backups (and to R2 when COVER_BACKUP_REMOTE is set); restore:
#   tar -xzf ~/backups/cover-data-<date>.tar.gz -C <new data dir>
backup:
	scripts/backup.sh
