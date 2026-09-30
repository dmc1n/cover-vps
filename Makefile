# Cover pattern engine — see CLAUDE.md "Commands".
.PHONY: setup test lint shapes testsheets golden demo api-dev web-dev deploy backup

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

api-dev:
	@echo "make api-dev arrives in M6"; exit 2

web-dev:
	@echo "make web-dev arrives in M6"; exit 2

deploy:
	@echo "make deploy arrives in M6"; exit 2

backup:
	@echo "make backup arrives in M6"; exit 2
