"""The quality gates of sql/databricks/90_quality_checks.sql run against the fixture build (D48, D51).

The row-count checks compare against tests/fixtures/expected_rows.yml instead of the full-data
counts in config/pipeline.yml; every other check runs unchanged.
"""

from __future__ import annotations

import pytest

import quality_checks
import sql_dialect


def fixture_overrides(expected_rows: dict[str, int]) -> dict[str, int]:
    return {f"quality.expected_rows.{table}": n for table, n in expected_rows.items()}


def run(con, overrides):
    return quality_checks.run_layers(lambda sql: con.execute(sql_dialect.to_duckdb(sql)).fetchall(),
                                     quality_checks.LAYERS, overrides=overrides)


def test_every_quality_gate_passes_on_the_fixture(con, expected_rows):
    results = run(con, fixture_overrides(expected_rows))
    failed = [(r[0], r[1], r[2], r[3]) for r in results if not r[4]]
    assert failed == []
    assert len(results) == 109
    quality_checks.raise_on_failure(results)


def test_a_wrong_row_count_stops_the_run(con, expected_rows):
    overrides = fixture_overrides(expected_rows)
    overrides["quality.expected_rows.gold_outage_events"] += 1
    results = run(con, overrides)
    assert [r[1] for r in results if not r[4]] == ["row count: gold_outage_events"]
    with pytest.raises(quality_checks.QualityFailed):
        quality_checks.raise_on_failure(results)
