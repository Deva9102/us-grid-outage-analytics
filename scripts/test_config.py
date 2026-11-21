"""Test config/pipeline.yml and the SQL placeholders (D47). Runs in seconds, reads no data.

Checks:
    1. The configuration loads and validates.
    2. Every SQL file in sql/databricks/ renders with no placeholder left.
    3. No pipeline SQL file still holds a literal that the configuration owns (catalog, schema,
       volume path), so values cannot drift from the config.
    4. Every table with an expected row count is created by a SQL file, and the quality checks
       count exactly the tables listed in quality.expected_rows.
    5. Invalid values are rejected before any SQL runs.

Usage:
    uv run python scripts/test_config.py
"""

from __future__ import annotations

import copy
import re
import sys
from pathlib import Path

import yaml

import pipeline_config

REPO_ROOT = Path(__file__).resolve().parent.parent
SQL_DIR = REPO_ROOT / "sql" / "databricks"
FAILURES: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(f"  [{'ok' if ok else 'FAIL'}] {label}{'' if ok or not detail else ': ' + detail}")
    if not ok:
        FAILURES.append(label)


def rejects(label: str, path: str, value) -> None:
    raw = yaml.safe_load(pipeline_config.CONFIG_PATH.read_text())
    bad = copy.deepcopy(raw)
    node = bad
    *parents, leaf = path.split(".")
    for p in parents:
        node = node[p]
    node[leaf] = value
    try:
        pipeline_config.validate(bad)
        check(label, False, f"{path} = {value!r} was accepted")
    except pipeline_config.ConfigError:
        check(label, True)


def main() -> int:
    print("Configuration:")
    cfg = pipeline_config.load()
    check("config/pipeline.yml loads and validates", True)

    print("SQL placeholders:")
    created: set[str] = set()
    for path in sorted(SQL_DIR.glob("*.sql")):
        text = pipeline_config.render(path.read_text())
        left = pipeline_config.PLACEHOLDER.findall(text) + re.findall(r"\$\{[^}]*\}", text)
        check(f"{path.name} renders completely", not left, str(left[:3]))
        code = re.sub(r"--[^\n]*", "", path.read_text())
        owned = [s for s in ("workspace.outages", "/Volumes/workspace", "USE CATALOG workspace") if s in code]
        check(f"{path.name} has no hard-coded catalog, schema or volume", not owned, str(owned))
        created |= set(re.findall(r"^CREATE OR REPLACE TABLE (\w+)", text, re.M))

    print("Expected row counts:")
    expected = set(cfg["quality"]["expected_rows"])
    check("every expected table is created by a SQL file", expected <= created, str(sorted(expected - created)))
    counted = set(re.findall(r"'(\w+)'(?: AS table_name)?, COUNT\(\*\)",
                             (SQL_DIR / "90_quality_checks.sql").read_text()))
    check("quality checks count exactly the expected tables", counted == expected,
          f"missing {sorted(expected - counted)}, extra {sorted(counted - expected)}")

    print("Derived values:")
    check("gap rule is 4 runs for 1 hour", cfg["events"]["max_gap_runs"] == cfg["events"]["max_gap_hours"] * 4)
    check("volume path built from project names",
          cfg["project"]["volume_path"] == f"/Volumes/{cfg['project']['catalog']}/{cfg['project']['schema']}/{cfg['project']['volume']}")
    share = pipeline_config.render("${events.threshold_share}", {"events.threshold_share": 0.001})
    check("a one-run override replaces the configured value", share == "0.001")

    print("Invalid values are rejected:")
    rejects("threshold share above 1", "events.threshold_share", 1.5)
    rejects("gap not a multiple of 15 minutes", "events.max_gap_hours", 0.3)
    rejects("dropout recovery beyond the 5 LEAD columns", "dropouts.recovery_max_runs", 6)
    rejects("calibration ratio at or below 1", "calibration.state_ratio", 1.0)
    rejects("unsorted years", "years", [2024, 2022])
    rejects("schema that is not an identifier", "project.schema", "outages; DROP")
    rejects("utility numbers not quoted", "utilities.eversource_ids", [4176])

    print("\n" + ("ALL CHECKS PASSED" if not FAILURES else f"FAILED: {FAILURES}"))
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
