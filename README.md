# US Power Outages & Storm Impact

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
| `make test` | Config test, then the DuckDB tests that run the real Databricks SQL on local samples. No Databricks needed. |
| `make pipeline` | Converts and uploads the raw files, runs all SQL on Databricks, runs the quality gate after Bronze, Silver and Gold (a failed check stops the run), then verifies row counts and the top 10 events. |
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

## Next Steps
