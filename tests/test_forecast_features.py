"""Restoration-forecast features (D71): no feature may use information from after the prediction moment.

The synthetic tests build the few tables 04_gold_forecast_features.sql reads, run the real SQL,
then add information that only exists after the prediction moment (later readings, a dropout that
recovers later, a storm that begins later, a feed gap later, a longer event, history from the
event's own year or still running on Jan 1) and require every feature to stay identical. Each
case also has a twin just inside the prediction moment that must change the feature, so the
test cannot pass by the feature ignoring its input altogether.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

import duckdb_pipeline
import forecast_baseline
import pipeline_config
from conftest import FIXTURES

REPO_ROOT = Path(__file__).resolve().parent.parent
FILE = "04_gold_forecast_features.sql"
EVENT = "01001-00010"
TARGET = "duration_hours"

# The event under test: county 01001 (Alabama, America/Chicago), 2024-01-03 12:00 to 20:00 UTC.
# Prediction moment 14:00 (2 hours). Readings every 15 minutes; the midpoint (13:00) reads 800,
# the prediction moment 900; the peak so far is 950 at 13:30.
BASE_SQL = """
CREATE TABLE gold_collection_runs AS
SELECT slot_time, TRUE AS is_collected, CAST(ROW_NUMBER() OVER (ORDER BY slot_time) AS INT) AS run_index
FROM (SELECT UNNEST(generate_series(TIMESTAMP '2022-01-01', TIMESTAMP '2024-01-05', INTERVAL 15 MINUTE)) AS slot_time);

CREATE TABLE gold_outage_events AS SELECT * FROM (VALUES
    -- prior years: 2022 (4 h, not eligible: no reading at +2 h) and 2023 (3 h, eligible)
    ('01001-00001', '01001', 'A', 'AL', 'South', 2022, TIMESTAMP '2022-06-01 10:00', TIMESTAMP '2022-06-01 14:00',
        100.0::DOUBLE, 10000, TRUE, FALSE, 4.0::DECIMAL(27, 6)),
    ('01001-00002', '01001', 'A', 'AL', 'South', 2023, TIMESTAMP '2023-05-01 10:00', TIMESTAMP '2023-05-01 13:00',
        100.0, 10000, TRUE, FALSE, 3.0),
    -- the event under test
    ('01001-00010', '01001', 'A', 'AL', 'South', 2024, TIMESTAMP '2024-01-03 12:00', TIMESTAMP '2024-01-03 20:00',
        100.0, 10000, TRUE, FALSE, 8.0)
) AS t(event_id, fips_code, county, state_abbr, census_region, event_year, event_start, event_end, event_threshold, customers,
       has_denominator, spans_empty_gap, duration_hours);

CREATE TABLE silver_outages AS
SELECT '01001' AS fips_code, reading_time, customers_out FROM (VALUES
    (TIMESTAMP '2023-05-01 12:00', 300),
    (TIMESTAMP '2024-01-03 12:00', 500), (TIMESTAMP '2024-01-03 12:15', 550), (TIMESTAMP '2024-01-03 12:30', 600),
    (TIMESTAMP '2024-01-03 12:45', 700), (TIMESTAMP '2024-01-03 13:00', 800), (TIMESTAMP '2024-01-03 13:15', 850),
    (TIMESTAMP '2024-01-03 13:30', 950), (TIMESTAMP '2024-01-03 13:45', 920), (TIMESTAMP '2024-01-03 14:00', 900),
    (TIMESTAMP '2024-01-03 14:15', 880), (TIMESTAMP '2024-01-03 18:00', 400), (TIMESTAMP '2024-01-03 19:45', 150)
) AS t(reading_time, customers_out);

CREATE TABLE gold_feed_dropouts (fips_code VARCHAR, dropout_start TIMESTAMP, dropout_end TIMESTAMP);

CREATE TABLE silver_storm_events (event_id BIGINT, fips_code VARCHAR, event_type VARCHAR, begin_utc TIMESTAMP, end_utc TIMESTAMP);
"""

# (name, SQL that adds information after the prediction moment, SQL that adds the same just before it,
#  the feature the twin must change)
FUTURE_CASES = [
    ("later_readings",
     "UPDATE silver_outages SET customers_out = 99999 WHERE reading_time > TIMESTAMP '2024-01-03 14:00'",
     "UPDATE silver_outages SET customers_out = 99999 WHERE reading_time = TIMESTAMP '2024-01-03 13:45'",
     "peak_customers_out_so_far"),
    ("dropout_recovering_later",
     "INSERT INTO gold_feed_dropouts VALUES ('01001', TIMESTAMP '2024-01-03 13:00', TIMESTAMP '2024-01-03 14:15')",
     "INSERT INTO gold_feed_dropouts VALUES ('01001', TIMESTAMP '2024-01-03 13:00', TIMESTAMP '2024-01-03 14:00')",
     "dropout_so_far"),
    ("storm_beginning_later",
     "INSERT INTO silver_storm_events VALUES (1, '01001', 'Tornado', TIMESTAMP '2024-01-03 14:15', TIMESTAMP '2024-01-03 15:00')",
     "INSERT INTO silver_storm_events VALUES (1, '01001', 'Tornado', TIMESTAMP '2024-01-03 14:00', TIMESTAMP '2024-01-03 15:00')",
     "storm_family_at_start"),
    ("feed_gap_later",
     "UPDATE gold_collection_runs SET is_collected = FALSE WHERE slot_time = TIMESTAMP '2024-01-03 14:15'",
     "UPDATE gold_collection_runs SET is_collected = FALSE WHERE slot_time = TIMESTAMP '2024-01-03 13:45'",
     "feed_gap_so_far"),
    ("history_from_own_year",
     "INSERT INTO gold_outage_events SELECT '01001-00009', '01001', 'A', 'AL', 'South', 2024, TIMESTAMP '2024-01-02 01:00', "
     "TIMESTAMP '2024-01-02 09:00', 100.0, 10000, TRUE, FALSE, 8.0",
     "INSERT INTO gold_outage_events SELECT '01001-00009', '01001', 'A', 'AL', 'South', 2023, TIMESTAMP '2023-12-30 01:00', "
     "TIMESTAMP '2023-12-30 09:00', 100.0, 10000, TRUE, FALSE, 8.0",
     "prior_event_count"),
    ("history_still_running_on_jan_1",
     "INSERT INTO gold_outage_events SELECT '01001-00009', '01001', 'A', 'AL', 'South', 2023, TIMESTAMP '2023-12-31 22:00', "
     "TIMESTAMP '2024-01-01 00:15', 100.0, 10000, TRUE, FALSE, 2.25",
     "INSERT INTO gold_outage_events SELECT '01001-00009', '01001', 'A', 'AL', 'South', 2023, TIMESTAMP '2023-12-31 22:00', "
     "TIMESTAMP '2024-01-01 00:00', 100.0, 10000, TRUE, FALSE, 2.0",
     "prior_event_count"),
    ("longer_event",
     "UPDATE gold_outage_events SET event_end = TIMESTAMP '2024-01-04 20:00', duration_hours = 32.0 WHERE event_id = '01001-00010'",
     None, None),
]


def build(extra: str | None = None):
    con = duckdb_pipeline.connect()
    duckdb_pipeline.run_file(con, "01_bronze_sources.sql", FIXTURES,
                             only={"bronze_storm_event_severity", "bronze_state_time_zones"})
    for stmt in filter(str.strip, BASE_SQL.split(";")):
        con.execute(stmt)
    if extra:
        con.execute(extra)
    duckdb_pipeline.run_file(con, FILE, FIXTURES)
    return con


def features(con, event_id: str = EVENT) -> dict:
    cur = con.execute("SELECT * FROM gold_restoration_features WHERE event_id = ?", [event_id])
    names = [d[0] for d in cur.description]
    row = cur.fetchone()
    assert row is not None, f"{event_id} is not eligible"
    return dict(zip(names, row, strict=True))


@pytest.fixture(scope="module")
def base():
    return features(build())


def test_base_features(base):
    """The values the SQL must produce for the synthetic event, one per feature group."""
    expected = {
        "split": "train", "storm_type_at_start": "unmatched", "storm_family_at_start": "No storm matched",
        "start_month_local": 1, "start_hour_local": 6, "start_weekday_local": 2,   # 06:00 CST, Wednesday
        "customers": 10000, "customers_out_at_start": 500, "customers_out_at_mid": 800, "customers_out_at_prediction": 900,
        "growth_customers": 400, "growth_ratio": 1.8, "peak_customers_out_so_far": 950, "peak_share_so_far": 0.095,
        "feed_gap_so_far": False, "dropout_so_far": False,
        "history_years": 2, "prior_event_count": 2, "prior_eligible_event_count": 1, "prior_events_per_year": 1.0,
        "prior_median_duration_hours": 3.5, "prior_eligible_median_duration_hours": 3.0, TARGET: 8.0,
    }
    assert {k: base[k] for k in expected} == expected
    assert str(base["prediction_time"]) == "2024-01-03 14:00:00"


@pytest.mark.parametrize("name,future,inside,feature", FUTURE_CASES, ids=[c[0] for c in FUTURE_CASES])
def test_future_information_changes_no_feature(base, name, future, inside, feature):
    """Information after the prediction moment (or from the event's own year) leaves every feature as it was."""
    after = features(build(future))
    changed = {k for k in base if k != TARGET and base[k] != after[k]}
    assert not changed, f"{name}: features changed by future information: {sorted(changed)}"
    if inside is not None:
        twin = features(build(inside))
        assert twin[feature] != base[feature], f"{name}: the twin inside the prediction moment must change {feature}"


def test_event_not_ongoing_at_prediction_is_not_eligible():
    """Below the threshold at the prediction moment: not eligible, even though the event runs on (D71)."""
    con = build("UPDATE silver_outages SET customers_out = 50 WHERE reading_time = TIMESTAMP '2024-01-03 14:00'")
    assert con.execute("SELECT COUNT(*) FROM gold_restoration_features WHERE event_id = ?", [EVENT]).fetchone()[0] == 0


def test_prediction_slot_reading_must_belong_to_the_event():
    """A qualifying reading at the prediction moment that belongs to a later event does not make an ended event eligible."""
    con = build("UPDATE gold_outage_events SET event_end = TIMESTAMP '2024-01-03 13:00', duration_hours = 1.0 "
                "WHERE event_id = '01001-00010'")
    assert con.execute("SELECT COUNT(*) FROM gold_restoration_features WHERE event_id = ?", [EVENT]).fetchone()[0] == 0


def test_sql_reads_no_slot_past_the_prediction_moment():
    """The only reading path is the slot grid, and it stops at prediction_time (static check of the SQL)."""
    sql = (duckdb_pipeline.SQL_DIR / FILE).read_text()
    assert re.search(r"SEQUENCE\(c\.event_start, c\.prediction_time, INTERVAL 15 MINUTES\)", sql)
    assert len(re.findall(r"JOIN silver_outages", sql)) == 1  # readings enter through the slot join only
    assert "d.dropout_end   <= c.prediction_time" in sql
    assert "s.begin_utc    <= g.prediction_time" in sql
    assert "p.event_year < y.event_year" in sql


# --- Fixture: contract on real rows -------------------------------------------

@pytest.fixture(scope="module")
def fx():
    """The fixture pipeline plus the forecast stage, in its own connection (the session one stays read-only)."""
    connection = duckdb_pipeline.connect()
    duckdb_pipeline.run_all(connection, FIXTURES)
    duckdb_pipeline.run_file(connection, FILE, FIXTURES)
    yield lambda sql: connection.execute(sql).fetchall()
    connection.close()


def test_fixture_contract(fx):
    """Every eligible row: prediction 2 h after start, still above threshold then, longer than 2 h, split by year."""
    fc = pipeline_config.get("forecast")
    bad = fx(f"""
        SELECT event_id FROM gold_restoration_features
        WHERE prediction_time <> event_start + INTERVAL {fc['prediction_minutes']} MINUTE
           OR customers_out_at_prediction < event_threshold
           OR duration_hours <= {fc['prediction_hours']}
           OR (event_year IN ({', '.join(map(str, fc['train_years']))}) AND split <> 'train')
           OR (event_year IN ({', '.join(map(str, fc['test_years']))}) AND split <> 'test')
           OR (event_year = {pipeline_config.get('years.first')} AND prior_event_count IS NOT NULL)
    """)
    assert bad == []
    assert fx("SELECT COUNT(*), COUNT(DISTINCT event_id) FROM gold_restoration_features") == [(14, 14)]


def test_storm_family_matches_dbt_mart(fx):
    """gold_storm_family repeats the D68 CASE of dbt/models/marts/dim_storm_type.sql; the two must agree."""
    dbt_sql = (REPO_ROOT / "dbt" / "models" / "marts" / "dim_storm_type.sql").read_text()
    dbt_sql = re.sub(r"\{\{\s*source\('outages',\s*'(\w+)'\)\s*\}\}", r"\1", dbt_sql)
    dbt_sql = dbt_sql.replace("{{ dbt.type_int() }}", "INTEGER")
    mart = set(fx(f"SELECT storm_type, storm_group FROM ({dbt_sql})"))
    ours = set(fx("SELECT storm_type, storm_family FROM gold_storm_family"))
    assert ours == mart and len(ours) > 50


# --- Baseline metrics ------------------------------------------------------------

def test_pinball_loss():
    import numpy as np
    y = np.array([1.0, 10.0])
    # under-prediction by 9 costs 0.9 x 9; over-prediction by 1 costs 0.1 x 1
    assert forecast_baseline.pinball(y, np.array([2.0, 1.0]), 0.9) == pytest.approx((0.1 * 1 + 0.9 * 9) / 2)


def test_baseline_falls_back_to_family_then_global():
    import pandas as pd
    train = pd.DataFrame({
        "storm_family_at_start": ["A"] * 4 + ["B"] * 2,
        "census_region": ["South"] * 3 + ["West"] + ["South"] * 2,
        "duration_hours": [2.0, 4.0, 6.0, 100.0, 8.0, 10.0],
    })
    test = pd.DataFrame({"storm_family_at_start": ["A", "A", "B", "C"], "census_region": ["South", "West", "South", "South"]})
    pred = forecast_baseline.predict(train, test, ["storm_family_at_start", "census_region"], [0.5, 0.9], min_events=3)
    # A/South has 3 events -> its own median 4; A/West has 1 -> family A median 5;
    # B has 2 (< 3) at both levels -> global median 7; C is unseen -> global.
    assert pred["q0.5"].tolist() == [4.0, 5.0, 7.0, 7.0]
