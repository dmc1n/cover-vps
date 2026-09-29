# Cover pattern engine — see CLAUDE.md "Commands".
.PHONY: setup test lint shapes testsheets demo api-dev web-dev deploy backup

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

demo:
	@echo "make demo arrives in M4 (full pipeline on the procedural chair)"; exit 2

api-dev:
	@echo "make api-dev arrives in M6"; exit 2

web-dev:
	@echo "make web-dev arrives in M6"; exit 2

deploy:
	@echo "make deploy arrives in M6"; exit 2

backup:
	@echo "make backup arrives in M6"; exit 2
