"""config/pipeline.yml, the SQL placeholders and the sqlfluff settings (D47, D51). Reads no data."""

from __future__ import annotations

import copy
import re
from pathlib import Path

import pytest
import yaml

import pipeline_config
import sqlfluff_config
from forecast_features import FORECAST_FILES

REPO_ROOT = Path(__file__).resolve().parent.parent
SQL_DIR = REPO_ROOT / "sql" / "databricks"
SQL_FILES = sorted(SQL_DIR.glob("*.sql"))


def test_config_loads_and_validates():
    cfg = pipeline_config.load()
    assert cfg["years"]["list"] == [2022, 2023, 2024, 2025]
    assert cfg["incremental"]["load_years"] == [2025] and not cfg["incremental"]["full_rebuild"]
    assert (cfg["project"]["catalog"], cfg["project"]["schema"]) == ("workspace", "outages")


@pytest.mark.parametrize("path", SQL_FILES, ids=lambda p: p.name)
def test_sql_renders_completely(path):
    text = pipeline_config.render(path.read_text())
    assert not re.findall(r"\$\{[^}]*\}", text)


@pytest.mark.parametrize("path", SQL_FILES, ids=lambda p: p.name)
def test_sql_has_no_hard_coded_project_names(path):
    code = re.sub(r"--[^\n]*", "", path.read_text())
    for owned in ("workspace.outages", "/Volumes/workspace", "USE CATALOG workspace"):
        assert owned not in code


def test_expected_tables_are_created_and_counted():
    expected = set(pipeline_config.load()["quality"]["expected_rows"])
    run_tables = {"gold_outage_events_rebuilt"}  # describes the run; no expected count (D56)
    created: set[str] = set()
    # The forecast stage runs outside the pipeline and its quality gates (scripts/forecast_features.py, D71).
    for path in (p for p in SQL_FILES if p.name not in FORECAST_FILES):
        created |= set(re.findall(r"^CREATE (?:OR REPLACE TABLE|TABLE IF NOT EXISTS) (\w+)", path.read_text(), re.M))
    assert expected <= created
    assert created - expected == run_tables
    counted = set(re.findall(r"'(\w+)'(?: AS table_name)?, COUNT\(\*\)", (SQL_DIR / "90_quality_checks.sql").read_text()))
    assert counted == expected


def test_denominator_base_years_match_the_dim_sql():
    """D58: the D21 totals and D35 floors in 02_silver.sql read exactly the base years' Bronze tables."""
    text = (SQL_DIR / "02_silver.sql").read_text()
    for cte in ("base_counties", "peaks"):
        body = text.split(f"{cte} AS (", 1)[1].split("\n),", 1)[0]
        years = sorted(int(y) for y in re.findall(r"bronze_eaglei_(\d{4})", body))
        assert years == pipeline_config.load()["denominator"]["base_years"], cte


def test_derived_values():
    cfg = pipeline_config.load()
    assert cfg["events"]["max_gap_runs"] == cfg["events"]["max_gap_hours"] * 4
    assert cfg["project"]["volume_path"] == "/Volumes/workspace/outages/raw"
    assert pipeline_config.render("${events.threshold_share}", {"events.threshold_share": 0.001}) == "0.001"
    assert pipeline_config.render("year IN (${incremental.load_years})", {"incremental.load_years": [2024, 2025]}) \
        == "year IN (2024, 2025)"


@pytest.mark.parametrize("path, value", [
    ("events.threshold_share", 1.5),
    ("events.max_gap_hours", 0.3),
    ("dropouts.recovery_max_runs", 6),
    ("calibration.state_ratio", 1.0),
    ("years", [2024, 2022]),
    ("project.schema", "outages; DROP"),
    ("utilities.eversource_ids", [4176]),
    ("incremental.load_years", [2026]),
    ("incremental.load_years", []),
    ("incremental.lookback_days", 0),
    ("quality.results_retention_days", 0.5),
])
def test_invalid_values_are_rejected(path, value):
    bad = copy.deepcopy(yaml.safe_load(pipeline_config.CONFIG_PATH.read_text()))
    node = bad
    *parents, leaf = path.split(".")
    for p in parents:
        node = node[p]
    node[leaf] = value
    with pytest.raises(pipeline_config.ConfigError):
        pipeline_config.validate(bad)


def test_sqlfluff_config_is_up_to_date():
    """.sqlfluff holds the placeholder values from config/pipeline.yml (scripts/sqlfluff_config.py)."""
    assert (REPO_ROOT / ".sqlfluff").read_text() == sqlfluff_config.render()
