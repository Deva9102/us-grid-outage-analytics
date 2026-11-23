# US Power Outages & Storm Impact

[![CI](https://github.com/Deva9102/us-grid-outage-analytics/actions/workflows/ci.yml/badge.svg)](https://github.com/Deva9102/us-grid-outage-analytics/actions/workflows/ci.yml)

## Overview

## Questions I Answer

## Data Sources

## Architecture

## Repository Structure

## Setup

I run everything through `make`. Copy `.env.example` to `.env` and fill in the Databricks
connection first. Every tunable value (years, event and dropout rules, calibration and ranking
thresholds, storm windows, catalog and schema) lives in `config/pipeline.yml`; the SQL and scripts
read it, so I change values there and nowhere else.

| Target | What it does |
|---|---|
| `make setup` | Installs the uv environment and validates `config/pipeline.yml`. |
| `make download` | Downloads every raw source into `data/raw/<source>/<year>/` (folders are created by the scripts). |
| `make profile` | Profiles the raw files; the results feed `docs/data_profile.md`. |
| `make test` | Fast pytest suite (about 1 second): the real Databricks SQL, rendered from `config/pipeline.yml`, runs in DuckDB on the small real sample in `tests/fixtures/` and is checked against exact expected values, including all quality gates. No Databricks or downloads needed. |
| `make test-slow` | The full-data DuckDB checks on `data/raw/` (several minutes). |
| `make lint` | ruff on the Python, sqlfluff (Databricks dialect) on `sql/databricks/`. |
| `make ci` | `lint` then `test`: the same checks GitHub Actions runs on every push and pull request. |
| `make fixture` | Rebuilds `tests/fixtures/` from `data/raw/` (`scripts/build_test_fixture.py`). |
| `make pipeline` | Converts and uploads the raw files, runs all SQL on Databricks, runs the quality gate after Bronze, Silver and Gold (a failed check stops the run), then verifies row counts and the top 10 events. It loads only the years in `incremental.load_years` and leaves the others untouched (D56); `--full` rebuilds every year. |
| `make cli` | Installs the pinned Databricks CLI into `.tools/` (checksum verified, no global install). |
| `make job-deploy` | Renders the job SQL from `config/pipeline.yml` into `build/databricks/` and deploys the Databricks Job in `databricks.yml` (D54). |
| `make job-run` | Runs the deployed job once and prints each task's result and duration. Deploying, repairs and failed gates are in `docs/runbook.md`. |
| `make quality` | Runs every check in `sql/databricks/90_quality_checks.sql` and appends the results to `gold_quality_results`. `make quality ENGINE=duckdb` builds the pipeline locally and runs the same checks. |
| `make export` | Writes the Gold tables to `data/gold_exports/` as CSV for Power BI, split by year when a file would exceed 50 MB. The CSVs are gitignored (D50). |
| `make all` | `setup`, `download`, `test`, `pipeline`, `quality`, `export` in order. |
| `make clean` | Removes `logs/` and Python caches; raw data is kept. |

Each run logs its steps (start time, duration, row counts) to `logs/` and prints a summary table.

## Pipeline

### Bronze

### Silver

### Gold

## Snowflake Star Schema

## Power BI Dashboard

## Key Findings

## Known Limitations

- EAGLE-I misses outages shorter than its 15-minute collection run and is less reliable for small
  and rural utilities. Earlier years have lower coverage, so I never report coverage growth as
  outage growth.
- EAGLE-I is county-level. Utility comparisons come only from EIA-861 SAIDI and SAIFI.
- 2025 (loaded incrementally, D56-D60): Connecticut reports in its nine planning regions instead of
  its eight counties from 2025-05-29. The planning regions have no customer denominator, so
  Connecticut's 2025 state and county rates are footnoted, not ranked (D60). 6.5% of the 2025
  readings have an empty customers-out value and are dropped (D15). OE-417 reports for 2024 and
  2025 are not loaded (the official host is unreachable from my network, D25, D59), so the OE-417
  cross-check covers 2022-2023 only.

## Next Steps
