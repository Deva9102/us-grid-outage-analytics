"""Bronze and Silver rules on the real fixture rows, plus synthetic rows where real data has no case.

Expected values were checked against the full-data DuckDB build: every denominator below is the
value the full pipeline produces (D51).
"""

from __future__ import annotations

from datetime import datetime

import pytest

import duckdb_pipeline
from conftest import FIXTURES


def test_every_table_has_the_expected_row_count(con, expected_rows):
    got = {t: con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in expected_rows}
    assert got == expected_rows


# --- Bronze ------------------------------------------------------------------

def test_bronze_is_all_text_with_lineage(con):
    """D14: every Bronze column is text; source_file and loaded_at are added."""
    types = dict(con.execute(
        "SELECT column_name, data_type FROM information_schema.columns WHERE table_name = 'bronze_eaglei_2023'").fetchall())
    assert types == {"fips_code": "VARCHAR", "county": "VARCHAR", "state": "VARCHAR", "sum": "VARCHAR",
                     "run_start_time": "VARCHAR", "source_file": "VARCHAR", "loaded_at": "TIMESTAMP WITH TIME ZONE"}


# --- dim_county_customers -----------------------------------------------------

DIM = [
    # fips, customers, source, mismatch (D12), state factor (D21), floored (D35), skipped (D36)
    ("06037", 3799750, "total_customers_2024", False, 1.0, False, False),
    ("15001", 133891, "max_mcc_2024", True, 1.317739, False, False),
    ("15003", 233481, "total_customers_2024", False, 1.317739, False, False),
    ("15005", 58, "max_mcc_2024", True, 1.317739, False, False),
    ("15007", 27853, "total_customers_2024", False, 1.317739, True, False),
    ("15009", 111706, "max_mcc_2024", True, 1.317739, False, False),
    ("48157", 694780, "max_mcc_2024", True, 1.0, False, False),
    ("48201", 1344930, "total_customers_2024", False, 1.0, False, False),
    ("49011", 132398, "total_customers_2024", False, 1.0, False, False),
    ("49033", 1005, "total_customers_2024", False, 1.0, False, False),
    ("49035", 506032, "total_customers_2024", False, 1.0, False, False),
    ("49049", 328615, "total_customers_2024", False, 1.0, False, False),
    ("49057", 106115, "total_customers_2024", False, 1.0, False, False),
    ("51720", None, None, False, 1.0, False, False),
]


def test_denominators(rows):
    """D5 MCC padding and Grand Total, D9 none, D12 mismatch, D13 fallback, D21 and D35 calibration."""
    got = rows("""
        SELECT fips_code, customers, denominator_source, denominator_mismatch, ROUND(state_calibration_factor, 6),
               peak_floor_applied, peak_floor_skipped
        FROM dim_county_customers ORDER BY fips_code
    """)
    assert got == DIM


def test_hawaii_calibrated_to_eia_with_kauai_held_at_its_peak(one, rows):
    """D21: Hawaii's D13 total (668,078) is above 1.25x EIA 2024 (506,988), so it is scaled to EIA.
    D35: Kauai's peak of 27,853 (2024-07-11 07:00) is above its scaled value, so it is held there."""
    assert one("SELECT customers FROM silver_eia_state_customers WHERE state_abbr = 'HI' AND data_year = 2024") == 506988
    assert one("SELECT SUM(ROUND(customers * calibration_factor)) FROM dim_county_customers WHERE fips_code LIKE '15%'") == 668078
    assert one("SELECT SUM(customers) FROM dim_county_customers WHERE fips_code LIKE '15%'") == 506989  # rounding
    assert rows("SELECT reading_time, customers_out FROM silver_outages WHERE fips_code = '15007' "
                "ORDER BY customers_out DESC LIMIT 1") == [(datetime(2024, 7, 11, 7, 0), 27853)]


def test_peak_skip_ratio_drops_the_floor(tmp_path):
    """D36: a peak above calibration.peak_skip_ratio x the D13 denominator gives no floor. Kauai's peak is
    0.795x its D13 value (27,853 / 35,024); at a ratio of 0.79 its floor is skipped and it takes the
    common rescaling, which also changes the other Hawaii counties."""
    con = duckdb_pipeline.connect()
    overrides = {"calibration.peak_skip_ratio": 0.79}
    for name in ("01_bronze.sql", "01_bronze_sources.sql", "02_silver_sources.sql"):
        duckdb_pipeline.run_file(con, name, FIXTURES, overrides)
    duckdb_pipeline.run_file(con, "02_silver.sql", FIXTURES, overrides, only={"dim_county_customers"})
    got = con.execute("""
        SELECT fips_code, customers, peak_floor_applied, peak_floor_skipped FROM dim_county_customers
        WHERE fips_code LIKE '15%' ORDER BY fips_code
    """).fetchall()
    # 26,579 is Kauai's "D21 only" value in docs/decisions.md D35.
    assert got == [("15001", 134247, False, False), ("15003", 234102, False, False), ("15005", 58, False, False),
                   ("15007", 26579, False, True), ("15009", 112003, False, False)]


# --- silver_outages -----------------------------------------------------------

def test_silver_rows_per_year_and_overcounts(rows):
    """D4: readings above the county's customers are flagged, never changed (Harris in Beryl, Rich UT)."""
    assert rows("""
        SELECT year, COUNT(*), COUNT_IF(exceeds_customers) FROM silver_outages GROUP BY year ORDER BY year
    """) == [(2022, 624, 0), (2023, 195, 0), (2024, 3965, 84)]
    assert rows("""
        SELECT fips_code, COUNT(*), MAX(customers_out) FROM silver_outages WHERE exceeds_customers
        GROUP BY fips_code ORDER BY fips_code
    """) == [("48201", 81, 1660703), ("49033", 3, 3935)]


def test_fips_padding_and_region_from_state_fips(rows):
    """D1/D8/D16: 5-digit FIPS, state and region from the state FIPS prefix, never from names."""
    assert rows("""
        SELECT DISTINCT fips_code, state, state_abbr, census_region FROM silver_outages
        WHERE fips_code IN ('06037', '15007', '51720') ORDER BY 1
    """) == [("06037", "California", "CA", "West"), ("15007", "Hawaii", "HI", "West"),
             ("51720", "Virginia", "VA", "South")]


def test_off_grid_run_is_floored(rows, one):
    """D7: the 2023-03-22 20:31 run fills the 20:30 slot; no off-grid time is left."""
    assert one("SELECT COUNT(*) FROM bronze_eaglei_2023 WHERE run_start_time = '2023-03-22 20:31:00'") == 8
    assert rows("""
        SELECT reading_time, COUNT(*) FROM silver_outages
        WHERE reading_time BETWEEN TIMESTAMP '2023-03-22 20:15' AND TIMESTAMP '2023-03-22 20:45'
        GROUP BY 1 ORDER BY 1
    """) == [(datetime(2023, 3, 22, 20, 15), 8), (datetime(2023, 3, 22, 20, 30), 8), (datetime(2023, 3, 22, 20, 45), 8)]
    assert one("SELECT COUNT(*) FROM silver_outages WHERE MINUTE(reading_time) % 15 <> 0 OR SECOND(reading_time) <> 0") == 0


@pytest.fixture()
def synthetic_silver():
    """A connection with synthetic Bronze rows, built by the real 02_silver.sql."""
    con = duckdb_pipeline.connect()
    duckdb_pipeline.run_file(con, "01_bronze.sql", FIXTURES)
    duckdb_pipeline.run_file(con, "01_bronze_sources.sql", FIXTURES)
    duckdb_pipeline.run_file(con, "02_silver_sources.sql", FIXTURES)
    return con


def test_floor_and_dedupe_keep_the_highest_reading(synthetic_silver):
    """D7: an off-grid 20:31 run next to a regular 20:30 run of the same county keeps the max.
    D15: rows that cannot be parsed are dropped. Real data has neither case, so rows are synthetic."""
    con = synthetic_silver
    con.execute("DELETE FROM bronze_eaglei_2022")
    con.execute("DELETE FROM bronze_eaglei_2024")
    con.execute("DELETE FROM bronze_eaglei_2023")
    con.execute("""
        INSERT INTO bronze_eaglei_2023 (fips_code, county, state, "sum", run_start_time, source_file) VALUES
            ('1001', 'Autauga', 'Alabama', '120', '2023-03-22 20:30:00', 'a'),
            ('1001', 'Autauga', 'Alabama', '150', '2023-03-22 20:31:00', 'a'),
            ('01003', 'Baldwin', 'Alabama', '90', '2023-03-22 20:31:00', 'a'),
            ('01003', 'Baldwin', 'Alabama', 'n/a', '2023-03-22 20:45:00', 'a'),
            ('01003', 'Baldwin', 'Alabama', '80', 'not a time', 'a'),
            ('ABCDE', 'Bad', 'Alabama', '10', '2023-03-22 20:45:00', 'a')
    """)
    duckdb_pipeline.run_file(con, "02_silver.sql", FIXTURES)
    assert con.execute("SELECT fips_code, reading_time, customers_out FROM silver_outages ORDER BY 1").fetchall() == [
        ("01001", datetime(2023, 3, 22, 20, 30), 150), ("01003", datetime(2023, 3, 22, 20, 30), 90)]


# --- Added sources ------------------------------------------------------------

def test_eia_state_customers_use_parts_a_c_d(rows):
    """D23: state customers sum Sales Parts A, C and D (never B); the totals equal the full data."""
    assert rows("SELECT data_year, state_abbr, customers, utilities FROM silver_eia_state_customers ORDER BY 1, 2") == [
        (2022, "RI", 503017, 1), (2023, "CT", 1281655, 1), (2023, "MA", 1515653, 1),
        (2024, "CA", 16140825, 49), (2024, "HI", 506988, 13), (2024, "MA", 3372904, 33),
        (2024, "TX", 14481051, 172), (2024, "UT", 1429521, 23), (2024, "VA", 4104032, 22)]


def test_storm_events_placed_in_counties(rows, one):
    """D28-D31: NOAA events in UTC, county and zone events placed in counties, water events unplaced."""
    assert rows("SELECT location_type, COUNT(DISTINCT event_id), COUNT(*) FROM silver_storm_events GROUP BY 1 ORDER BY 1") \
        == [("C", 7, 7), ("Z", 44, 60)]
    assert rows("SELECT event_type, reason FROM silver_storm_events_unplaced") == [("Marine Thunderstorm Wind", "water")]
    assert one("SELECT COUNT(*) FROM (SELECT event_id, SUM(event_weight) AS w FROM silver_storm_events "
               "GROUP BY 1 HAVING ABS(w - 1) > 1e-9)") == 0
    assert rows("SELECT version, effective_from FROM silver_nws_zone_versions ORDER BY 2 DESC LIMIT 1") \
        == [("bp05mr24", datetime(2024, 3, 5).date())]


def test_oe417_incidents_parsed_and_located(rows):
    """D24, D33, D34: header row found, local times to UTC, county names matched to EAGLE-I FIPS."""
    assert rows("""
        SELECT incident_id, primary_state, begin_utc, counties_affected, event_category, customers_affected
        FROM silver_oe417 ORDER BY incident_id
    """) == [
        ("2022-0001", "TX", datetime(2022, 2, 5, 0, 21), None, "transmission_interruption", None),
        ("2022-0002", "TX", datetime(2022, 10, 25, 6, 45), ["48201"], "system_operations", 109865),
        ("2022-0003", "CA", datetime(2022, 10, 28, 21, 16), ["06037"], "vandalism_theft", 0),
        ("2023-0001", "CA", None, None, "vandalism_theft", 0),
    ]
    assert rows("SELECT state_abbr, county_name_raw, match_type FROM silver_oe417_locations "
                "WHERE location_level = 'county' ORDER BY incident_id") == [
        ("TX", "Harris County", "exact"), ("CA", "Los Angeles County", "exact"), ("CA", "San Diego County", "unmatched")]
