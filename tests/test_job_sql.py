"""The rendered Databricks Job SQL (scripts/render_job_sql.py, D54) runs in DuckDB on the fixture.

Each job task file and its gate run in job order on a fresh connection. The result must equal the
build of the pipeline files (the con fixture), every gate must pass, and a wrong row count must
stop the job at the gate of the task that built the table.
"""

from __future__ import annotations

import re

import pytest

import duckdb_pipeline
import render_job_sql
from conftest import FIXTURES
from run_databricks import full_rebuild_overrides
from sql_split import split_statements


def fixture_overrides(expected_rows: dict[str, int]) -> dict:
    """Fixture row counts, and every year loaded: the job builds a fresh connection from scratch."""
    overrides: dict = {f"quality.expected_rows.{table}": n for table, n in expected_rows.items()}
    overrides.update(full_rebuild_overrides())
    return overrides


def run_job(rendered: dict[str, str]):
    """Run every task and gate in order; returns (connection, tasks finished, error or None)."""
    con = duckdb_pipeline.connect()
    done = []
    for task, _, _ in render_job_sql.JOB_TASKS:
        for name in (f"{task}.sql", f"{task}_gate.sql"):
            try:
                duckdb_pipeline.run_statements(con, split_statements(rendered[name]), FIXTURES, name)
            except RuntimeError as e:
                return con, done, e
            done.append(name)
    return con, done, None


@pytest.fixture(scope="module")
def job(expected_rows):
    rendered = render_job_sql.render(fixture_overrides(expected_rows))
    con, done, error = run_job(rendered)
    yield rendered, con, done, error
    con.close()


def test_job_tasks_run_the_pipeline_files_in_order():
    files = [f for _, _, fs in render_job_sql.JOB_TASKS for f in fs]
    assert files == render_job_sql.SQL_FILES
    assert [t for t, _, _ in render_job_sql.JOB_TASKS] == [
        "bronze", "silver", "gold_events", "gold_storm_match", "gold_reliability"]


def test_every_check_runs_once_and_every_gate_has_checks(job):
    rendered, *_ = job
    counts = render_job_sql.gate_check_counts(rendered)
    assert all(n >= 1 for n in counts.values())
    # 18 statements of 90_quality_checks.sql plus one task row-count statement per gate.
    assert sum(counts.values()) == 18 + len(render_job_sql.JOB_TASKS)


def test_the_configured_job_loads_only_the_new_year():
    """D56: with incremental.load_years = [2025] the Bronze task builds only bronze_eaglei_2025,
    Silver replaces only that partition, and every gate ends with the D55 retention delete."""
    rendered = render_job_sql.render()
    built = re.findall(r"CREATE OR REPLACE TABLE (bronze_eaglei_\d{4})\b", rendered["bronze.sql"])
    assert built == ["bronze_eaglei_2025"]
    assert "INSERT INTO silver_outages REPLACE WHERE year IN (2025)" in rendered["silver.sql"]
    for task, _, _ in render_job_sql.JOB_TASKS:
        assert re.search(r"DELETE FROM gold_quality_results WHERE run_ts < CURRENT_TIMESTAMP - INTERVAL 90 DAYS",
                         rendered[f"{task}_gate.sql"]), task


def test_rendered_sql_has_no_placeholders(job):
    rendered, *_ = job
    assert not any("${" in sql for sql in rendered.values())


def test_job_build_passes_every_gate(job):
    _, con, done, error = job
    assert error is None
    assert len(done) == 2 * len(render_job_sql.JOB_TASKS)
    failed = con.execute("SELECT check_name FROM gold_quality_results WHERE NOT passed").fetchall()
    assert failed == []
    # The 123 checks (D52; D56: the 2025 Bronze count, two Gold counts, event numbering; D64: the
    # empty-readings count, its two key checks and the new event columns; D67: four coverage counts)
    # plus one row per table in the task row counts.
    task_counts = con.execute(
        "SELECT COUNT(*) FROM gold_quality_results WHERE check_name LIKE 'task row count: %'").fetchone()[0]
    total = con.execute("SELECT COUNT(*) FROM gold_quality_results").fetchone()[0]
    assert total - task_counts == 123


def test_job_build_equals_the_pipeline_build(job, con):
    _, job_con, _, _ = job
    skip = {"gold_quality_results", render_job_sql.GATE_TABLE}
    tables = [r[0] for r in con.execute("SHOW TABLES").fetchall()]
    job_tables = [r[0] for r in job_con.execute("SHOW TABLES").fetchall() if r[0] not in skip]
    assert sorted(job_tables) == sorted(tables)
    for t in tables:
        cols = [r[0] for r in con.execute(f"DESCRIBE {t}").fetchall() if r[0] not in ("loaded_at",)]
        sel = ", ".join(f'"{c}"' for c in cols)
        a = con.execute(f"SELECT {sel} FROM {t}").fetchall()
        b = job_con.execute(f"SELECT {sel} FROM {t}").fetchall()
        assert sorted(map(repr, a)) == sorted(map(repr, b)), t


def test_a_wrong_row_count_stops_the_job_at_its_gate(expected_rows):
    overrides = fixture_overrides(expected_rows)
    overrides["quality.expected_rows.gold_event_storm_match"] += 1
    _, done, error = run_job(render_job_sql.render(overrides))
    assert error is not None
    assert "Quality gate gold_storm_match failed" in str(error)
    assert done[-1] == "gold_storm_match.sql"
    assert "gold_reliability.sql" not in done
