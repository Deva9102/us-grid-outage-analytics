"""Analysis Gold tables: storm attribution, coverage, rankings with footnotes, utilities, OE-417 check."""

from __future__ import annotations

from datetime import datetime

import duckdb_pipeline
from conftest import FIXTURES

# --- Storm attribution (03_gold_storm_match.sql) ------------------------------


def test_storm_match_on_fixture(rows):
    """D37: the two 2022-10-25 Houston events start while a Thunderstorm Wind warning window is open.
    Beryl is unmatched, as in the full data: NOAA places no Beryl event in Harris or Fort Bend."""
    assert rows("""
        SELECT event_id, storm_type, most_severe_storm_type, attribution_rule, candidate_storms
        FROM gold_event_storm_match WHERE storm_type <> 'unmatched' ORDER BY event_id
    """) == [("48157-00001", "Thunderstorm Wind", "Thunderstorm Wind", "active_at_start", 2),
             ("48201-00001", "Thunderstorm Wind", "Thunderstorm Wind", "active_at_start", 3)]
    assert rows("SELECT COUNT(*), COUNT(DISTINCT event_id) FROM gold_event_storm_match") == [(27, 27)]


def test_storm_attribution_rules():
    """D41: a storm active at the outage start wins over a longer overlap, the most severe first.
    D42: the window closes 1 hour after NOAA's end, so a storm that ended 30 minutes before the
    outage still matches; one that ended 2 hours before does not. Synthetic rows, real SQL."""
    con = duckdb_pipeline.connect()
    duckdb_pipeline.run_file(con, "01_bronze_sources.sql", FIXTURES, only={"bronze_storm_event_severity"})
    con.execute("""
        CREATE TABLE gold_outage_events AS SELECT * FROM (VALUES
            ('01001-00001', '01001', 'A', 'AL', 'Alabama', 'South', TIMESTAMP '2024-01-01 12:00', TIMESTAMP '2024-01-02 12:00',
                24.0, 500, 1000.0, 2024),
            ('01003-00001', '01003', 'B', 'AL', 'Alabama', 'South', TIMESTAMP '2024-01-01 12:00', TIMESTAMP '2024-01-01 14:00', 2.0,
                100, 10.0, 2024),
            ('01005-00001', '01005', 'C', 'AL', 'Alabama', 'South', TIMESTAMP '2024-01-01 12:00', TIMESTAMP '2024-01-01 14:00', 2.0,
                100, 10.0, 2024)
        ) AS t(event_id, fips_code, county, state_abbr, state, census_region, event_start, event_end, duration_hours,
               peak_customers_out, customer_hours_lost, event_year)
    """)
    con.execute("""
        CREATE TABLE silver_storm_events AS SELECT * FROM (VALUES
            -- 01001: a flood covering the whole outage, and a tornado active at its start for 1 hour
            (1::BIGINT, 10::BIGINT, '01001', 'Flood', TIMESTAMP '2024-01-01 00:00', TIMESTAMP '2024-01-03 00:00'),
            (2::BIGINT, 10::BIGINT, '01001', 'Tornado', TIMESTAMP '2024-01-01 12:00', TIMESTAMP '2024-01-01 12:30'),
            -- 01003: thunderstorm wind ended 30 minutes before the outage (inside the 1-hour tail)
            (3::BIGINT, 11::BIGINT, '01003', 'Thunderstorm Wind', TIMESTAMP '2024-01-01 10:00', TIMESTAMP '2024-01-01 11:30'),
            -- 01005: ended 2 hours before the outage
            (4::BIGINT, 12::BIGINT, '01005', 'Thunderstorm Wind', TIMESTAMP '2024-01-01 09:00', TIMESTAMP '2024-01-01 10:00')
        ) AS t(event_id, episode_id, fips_code, event_type, begin_utc, end_utc)
    """)
    duckdb_pipeline.run_file(con, "03_gold_storm_match.sql", FIXTURES)
    assert con.execute("""
        SELECT event_id, storm_type, most_severe_storm_type, attribution_rule, candidate_storms
        FROM gold_event_storm_match ORDER BY event_id
    """).fetchall() == [
        ("01001-00001", "Tornado", "Tornado", "active_at_start", 2),
        ("01003-00001", "Thunderstorm Wind", "Thunderstorm Wind", "active_at_start", 1),
        ("01005-00001", "unmatched", None, None, 0),
    ]


# --- Coverage and rankings (03_gold_coverage.sql, 03_gold_reliability.sql) ----

def test_state_coverage(rows):
    """D22: EAGLE-I customers / EIA-861 2024 customers, capped at 1; below 70% is footnoted.
    VA has a county but no denominator: LEAST skips the NULL ratio, so coverage reads 1.0."""
    assert rows("""
        SELECT state_abbr, eaglei_counties, eaglei_customers, eia_customers, ROUND(customer_coverage, 4), ranking_eligible,
               ROUND(calibration_factor, 6)
        FROM gold_state_coverage WHERE eaglei_counties > 0 ORDER BY 1
    """) == [("CA", 1, 3799750, 16140825, 0.2354, False, 1.0), ("HI", 5, 506989, 506988, 1.0, True, 1.317739),
             ("TX", 2, 2039710, 14481051, 0.1409, False, 1.0), ("UT", 5, 1074165, 1429521, 0.7514, True, 1.0),
             ("VA", 1, None, 4104032, 1.0, True, 1.0)]


def test_county_ranking_footnotes(rows):
    """The first reason that applies is kept: D9 no denominator, D11 under 1,000 customers, D22 state
    coverage, D45 capped readings (Rich UT: 94.7% of customer-hours capped, peak 3.9x customers)."""
    assert rows("""
        SELECT year, fips_code, would_have_rank, footnote_reason, footnote_evidence
        FROM gold_county_ranking_footnotes ORDER BY year, fips_code
    """) == [
        (2022, "06037", 5, "state below 70% customer coverage (D22)", None),
        (2022, "15005", 5, "denominator under 1,000 customers (D11)", None),
        (2022, "48157", 3, "state below 70% customer coverage (D22)", None),
        (2022, "48201", 2, "state below 70% customer coverage (D22)", None),
        (2022, "51720", None, "no denominator (D9)", None),
        (2024, "06037", 11, "state below 70% customer coverage (D22)", None),
        (2024, "15005", 11, "denominator under 1,000 customers (D11)", None),
        (2024, "48157", 2, "state below 70% customer coverage (D22)", None),
        (2024, "48201", 1, "state below 70% customer coverage (D22)", None),
        (2024, "49033", 4, "over 25% of customer-hours from capped readings and peak above 3x customers (D45)",
         "capped share 94.7%, peak 3.9x customers"),
        (2024, "51720", None, "no denominator (D9)", None),
    ]


def test_county_ranks(rows):
    """D38: RANK by outage hours per 1,000 customers, 1 = most; ties share a rank."""
    assert rows("""
        SELECT year, fips_code, ROUND(outage_hours_per_1000_customers, 3), national_rank, state_rank
        FROM gold_county_reliability WHERE ranking_eligible ORDER BY year, national_rank, fips_code
    """) == [
        (2022, "49057", 281.979, 1, 1), (2022, "15007", 10.484, 2, 1), (2022, "15001", 0.0, 3, 2),
        (2022, "15003", 0.0, 3, 2), (2022, "15009", 0.0, 3, 2), (2022, "49011", 0.0, 3, 2),
        (2022, "49033", 0.0, 3, 2), (2022, "49035", 0.0, 3, 2), (2022, "49049", 0.0, 3, 2),
        (2024, "15007", 3325.548, 1, 1), (2024, "15001", 235.798, 2, 2), (2024, "49057", 142.786, 3, 1),
        (2024, "15009", 105.753, 4, 3), (2024, "15003", 25.123, 5, 4), (2024, "49035", 2.376, 6, 2),
        (2024, "49011", 1.971, 7, 3), (2024, "49049", 0.0, 8, 4),
    ]


def test_state_ranks(rows):
    """D43: states with coverage are ranked; TX and CA are below 70% in the fixture and are not.
    VA is ranked with no rate (see test_state_coverage); docs/decisions.md D51 records this."""
    assert rows("""
        SELECT year, state_abbr, ROUND(outage_hours_per_1000_customers, 3), national_rank, region_rank
        FROM gold_state_reliability ORDER BY year, state_abbr
    """) == [
        (2022, "CA", 0.0, None, None), (2022, "HI", 0.576, 2, 2), (2022, "TX", 129.408, None, None),
        (2022, "UT", 27.856, 1, 1), (2022, "VA", None, 3, 1),
        (2024, "CA", 0.0, None, None), (2024, "HI", 279.842, 1, 1), (2024, "TX", 47385.167, None, None),
        (2024, "UT", 16.209, 2, 2), (2024, "VA", None, 3, 1),
    ]


def test_utility_ranking(rows):
    """D39: IEEE 1366 reporters ranked by SAIDI without major events within size band and year.
    Eversource and National Grid are labelled; NSTAR 2023 repeats Connecticut Light & Power's
    metric set with a customer count far off its own, so it is flagged and not ranked."""
    assert rows("""
        SELECT data_year, utility_number, size_band, parent_company, data_quality_flag, utilities_in_band,
               rank_saidi_without_med
        FROM gold_utility_reliability WHERE size_band = 'very_large' ORDER BY data_year, utility_number
    """) == [
        (2022, "13214", "very_large", "National Grid (sold to PPL in May 2022)", None, 1, 1),
        (2023, "4176", "very_large", "Eversource", None, 2, 1),
        (2023, "54913", "very_large", "Eversource", "source row repeats the values of another utility", 2, None),
        (2024, "11804", "very_large", "National Grid", None, 3, 2),
        (2024, "14354", "very_large", None, None, 3, 3),
        (2024, "54913", "very_large", "Eversource", None, 3, 1),
    ]
    assert rows("SELECT size_band, COUNT(*) FROM gold_utility_reliability GROUP BY 1 ORDER BY 1") == [
        ("medium", 19), ("small", 1), ("very_large", 6)]
    assert rows("SELECT COUNT(*) FROM gold_utility_reliability_other") == [(11,)]


def test_oe417_check(rows):
    """D40: an incident is checked only with a time and a matched county; Harris 2022-10-25 06:45 matches
    the EAGLE-I event that started 1.5 hours earlier."""
    assert rows("""
        SELECT incident_id, match_status, matched_events, closest_event_id, closest_start_offset_hours, customers_band
        FROM gold_oe417_check ORDER BY incident_id
    """) == [
        ("2022-0001", "no county", 0, None, None, "unknown"),
        ("2022-0002", "matched", 1, "48201-00001", -1.5, "10,000+"),
        ("2022-0003", "not matched", 0, None, None, "0"),
        ("2023-0001", "no time", 0, None, None, "0"),
    ]
    assert rows("SELECT begin_utc FROM silver_oe417 WHERE incident_id = '2022-0002'") == [(datetime(2022, 10, 25, 6, 45),)]
