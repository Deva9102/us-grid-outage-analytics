"""Incremental loading on the fixture (D56, D57).

The fixture is first built for 2022-2024 only, as the pipeline stood before 2025 was added. Then
2025 is loaded alone, exactly as config/pipeline.yml sets it (incremental.load_years = [2025]).
The result must equal the full 2022-2025 build (the con fixture), the 2022-2024 Silver rows and
Bronze tables must be untouched, and the Monongalia WV outage that runs from 2024-12-31 into
2025-01-01 must stay one event.
"""

from __future__ import annotations

from datetime import datetime

import pytest

import duckdb_pipeline
from conftest import FIXTURES

BEFORE = {"incremental.load_years": [2022, 2023, 2024]}
# Before 2025 is added its Bronze table is empty (same columns as the loaded table).
EMPTY_2025 = """CREATE TABLE bronze_eaglei_2025 (fips_code VARCHAR, county VARCHAR, state VARCHAR, customers_out VARCHAR,
    run_start_time VARCHAR, source_file VARCHAR, loaded_at TIMESTAMP WITH TIME ZONE)"""
SILVER_CHECKSUM = """
    SELECT year, COUNT(*), SUM(hash(fips_code, county, state, reading_time, customers_out, total_customers,
                                    exceeds_customers, source_file) % 1000000007)
    FROM silver_outages GROUP BY year ORDER BY year"""
BOUNDARY_EVENT = """
    SELECT event_id, event_start, event_end, reading_count, event_year FROM gold_outage_events
    WHERE fips_code = '54061' ORDER BY event_start"""
# Tables written by an incremental run; the window and rebuilt tables describe the run itself.
RUN_TABLES = {"gold_event_reprocess_window", "gold_outage_events_rebuilt"}


def snapshot(con) -> dict:
    return {
        "silver": con.execute(SILVER_CHECKSUM).fetchall(),
        "bronze_loaded_at": {y: con.execute(f"SELECT MIN(loaded_at) FROM bronze_eaglei_{y}").fetchone()[0]
                             for y in (2022, 2023, 2024)},
        "events": con.execute("SELECT * FROM gold_outage_events ORDER BY event_id").fetchall(),
        "boundary": con.execute(BOUNDARY_EVENT).fetchall(),
    }


def table_rows(con, table: str) -> list[str]:
    cols = [r[0] for r in con.execute(f"DESCRIBE {table}").fetchall() if r[0] != "loaded_at"]
    sel = ", ".join(f'"{c}"' for c in cols)
    return sorted(map(repr, con.execute(f"SELECT {sel} FROM {table}").fetchall()))


@pytest.fixture(scope="module")
def staged():
    """(connection after the incremental 2025 load, snapshot before it, snapshot after it)."""
    con = duckdb_pipeline.connect()
    con.execute(EMPTY_2025)
    duckdb_pipeline.run_all(con, FIXTURES, overrides=BEFORE)
    before = snapshot(con)
    duckdb_pipeline.run_all(con, FIXTURES, incremental=True)
    after = snapshot(con)
    yield con, before, after
    con.close()


def test_before_2025_the_outage_ends_at_the_last_reading_of_2024(staged):
    _, before, _ = staged
    assert before["boundary"] == [
        ("54061-00001", datetime(2024, 12, 31, 19, 30), datetime(2025, 1, 1, 0, 0), 18, 2024)]


def test_outage_across_the_year_boundary_stays_one_event(staged):
    """D57: the event is reopened (its window starts at its own start, before the 7-day cut) and
    rebuilt whole with the 2025 readings: one event, same number, now ending in 2025."""
    con, _, after = staged
    assert after["boundary"] == [
        ("54061-00001", datetime(2024, 12, 31, 19, 30), datetime(2025, 1, 2, 0, 0), 114, 2024)]
    assert con.execute("""
        SELECT reprocess_from, cut_time, last_kept_seq FROM gold_event_reprocess_window WHERE fips_code = '54061'
    """).fetchall() == [(datetime(2024, 12, 25, 0, 0), datetime(2024, 12, 25, 0, 0), 0)]


def test_old_years_are_untouched(staged):
    """D56: the 2022-2024 Silver rows are identical (count and checksum per year) and their Bronze
    tables were not reloaded (same loaded_at)."""
    _, before, after = staged
    assert after["silver"][:3] == before["silver"]
    assert [r[0] for r in after["silver"]] == [2022, 2023, 2024, 2025]
    assert after["bronze_loaded_at"] == before["bronze_loaded_at"]


def test_events_before_the_window_are_kept_unchanged(staged):
    con, before, _ = staged
    kept = con.execute("""
        SELECT e.* FROM gold_outage_events AS e
        INNER JOIN gold_event_reprocess_window AS w ON w.fips_code = e.fips_code
        WHERE e.event_start < w.reprocess_from ORDER BY e.event_id""").fetchall()
    assert kept == [e for e in before["events"] if e[0] in {k[0] for k in kept}]
    assert len(kept) == 27  # every event of windows W1-W5


def test_incremental_load_equals_the_full_build(staged, con):
    """Every Silver and Gold table after the incremental run equals the full 2022-2025 build."""
    inc, *_ = staged
    tables = [r[0] for r in con.execute("SHOW TABLES").fetchall()
              if not r[0].startswith("bronze_") and r[0] not in RUN_TABLES]
    for t in tables:
        assert table_rows(inc, t) == table_rows(con, t), t


def test_rerunning_the_load_changes_nothing(staged):
    """The window is computed from the events the previous run wrote, so a rerun (a job retry or the
    daily schedule) rebuilds the same rows."""
    inc, _, after = staged
    duckdb_pipeline.run_all(inc, FIXTURES, incremental=True)
    assert snapshot(inc)["events"] == after["events"]
    assert snapshot(inc)["silver"] == after["silver"]
