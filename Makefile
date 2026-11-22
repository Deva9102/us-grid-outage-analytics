# One-command build for the US power outages pipeline (D49). Run "make help" for the targets.
# Every value the pipeline uses comes from config/pipeline.yml (D47).

PY      := uv run python
ENGINE  ?= databricks
DUCKDB_FILE ?=
DUCKDB_ARG := $(if $(DUCKDB_FILE),--duckdb-file $(DUCKDB_FILE),)

.PHONY: help setup download profile test test-slow lint ci fixture pipeline quality export all clean

help:
	@echo "make setup      install the uv environment and validate config/pipeline.yml"
	@echo "make download   download every raw source into data/raw/<source>/<year>/"
	@echo "make profile    profile the raw files (docs/data_profile*.md inputs)"
	@echo "make test       fast pytest suite: the real SQL on tests/fixtures/ in DuckDB (no Databricks)"
	@echo "make test-slow  full-data DuckDB checks on data/raw/ (minutes)"
	@echo "make lint       ruff on Python, sqlfluff on sql/databricks/"
	@echo "make ci         the GitHub Actions checks: lint, then the fast tests"
	@echo "make fixture    rebuild tests/fixtures/ from data/raw/"
	@echo "make pipeline   convert, upload, run all SQL on Databricks with quality gates, verify"
	@echo "make quality    run every quality check (ENGINE=databricks|duckdb, DUCKDB_FILE=path)"
	@echo "make export     write Gold tables to data/gold_exports/ as CSV for Power BI"
	@echo "make all        setup, download, test, pipeline, quality, export"
	@echo "make clean      remove logs and Python caches (raw data is kept)"

setup:
	uv sync
	@mkdir -p logs
	$(PY) scripts/pipeline_config.py
	@test -f .env || echo "Note: .env not found; copy .env.example and fill it in before make pipeline"

download:
	$(PY) scripts/download_eaglei.py
	$(PY) scripts/download_eia861.py
	$(PY) scripts/download_noaa_storm_events.py
	$(PY) scripts/download_nws_zone_county.py
	$(PY) scripts/download_oe417.py

profile:
	$(PY) scripts/profile_eaglei.py
	$(PY) scripts/profile_sources.py

test:
	uv run pytest -q

test-slow:
	uv run pytest -m slow -q

# --ignore-local-config --config .sqlfluff: read only the repo's sqlfluff config (D51).
lint:
	uv run ruff check scripts tests
	$(PY) scripts/sqlfluff_config.py --check
	uv run sqlfluff lint --ignore-local-config --config .sqlfluff sql/databricks

ci: lint test

fixture:
	$(PY) scripts/build_test_fixture.py

pipeline:
	$(PY) scripts/run_databricks.py

quality:
	$(PY) scripts/quality_checks.py --engine $(ENGINE) $(DUCKDB_ARG)

export:
	$(PY) scripts/export_gold.py --engine $(ENGINE) $(DUCKDB_ARG)

all: setup download test pipeline quality export

clean:
	rm -rf logs
	find scripts tests -name __pycache__ -type d -prune -exec rm -rf {} +
	rm -rf .pytest_cache .ruff_cache
