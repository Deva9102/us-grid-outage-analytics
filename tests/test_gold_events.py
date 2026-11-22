"""Gold events (03_gold_events.sql): thresholds, feed gaps, dropouts and gaps-and-islands events.

Real fixture rows first; every event that lies fully inside a fixture window equals the event of
the full-data build (times, readings, customer-hours). A synthetic set then pins each rule at its
boundary (D3, D4, D10, D17, D18, D19).
"""

from __future__ import annotations

import math
from datetime import datetime

import duckdb_pipeline
import pipeline_config
from conftest import FIXTURES


def test_thresholds_scale_with_county_size(rows):
    """D18: GREATEST(100, 0.25% of customers); counties without a denominator stay at 100."""
    assert rows("SELECT fips_code, ROUND(event_threshold, 4) FROM gold_event_thresholds ORDER BY 1") == [
        ("06037", 9499.375), ("15001", 334.7275), ("15003", 583.7025), ("15005", 100.0), ("15007", 100.0),
        ("15009", 279.265), ("48157", 1736.95), ("48201", 3362.325), ("49011", 330.995), ("49033", 100.0),
        ("49035", 1265.08), ("49049", 821.5375), ("49057", 265.2875), ("51720", 100.0)]


def test_nationwide_feed_gap_is_found(rows):
    """D3: the 2024-05-24 00:15-09:00 slots have no reading from any county (36 slots, 9 hours)."""
    assert rows("""
        SELECT MIN(slot_time), MAX(slot_time), COUNT(*) FROM gold_collection_runs
        WHERE NOT is_collected AND slot_time >= TIMESTAMP '2024-05-23 18:00' AND slot_time < TIMESTAMP '2024-05-24 12:00'
    """) == [(datetime(2024, 5, 24, 0, 15), datetime(2024, 5, 24, 9, 0), 36)]


def test_harris_beryl_dropouts(rows):
    """D19: Harris falls from 1,095,633 to 2,323 at 2024-07-10 00:45 and is back at 1,050,184 at 02:00:
    one 5-run dropout. Fort Bend fails at the same times (one utility feed)."""
    assert rows("""
        SELECT fips_code, dropout_start, dropout_end, dropout_runs, pre_drop_customers_out, dropped_customers_out,
               recovery_customers_out
        FROM gold_feed_dropouts ORDER BY fips_code, dropout_start
    """) == [
        ("15007", datetime(2024, 7, 11, 6, 0), datetime(2024, 7, 11, 6, 15), 1, 25364, 0, 26386),
        ("48157", datetime(2024, 7, 9, 15, 30), datetime(2024, 7, 9, 15, 45), 1, 182381, 0, 177175),
        ("48157", datetime(2024, 7, 9, 16, 0), datetime(2024, 7, 9, 16, 15), 1, 177175, 0, 177765),
        ("48157", datetime(2024, 7, 10, 0, 45), datetime(2024, 7, 10, 2, 0), 5, 145194, 0, 136096),
        ("48157", datetime(2024, 7, 10, 3, 0), datetime(2024, 7, 10, 3, 15), 1, 135459, 0, 138093),
        ("48157", datetime(2024, 7, 10, 3, 30), datetime(2024, 7, 10, 3, 45), 1, 138093, 0, 135950),
        ("48157", datetime(2024, 7, 10, 5, 30), datetime(2024, 7, 10, 5, 45), 1, 136330, 0, 136346),
        ("48201", datetime(2024, 7, 9, 15, 30), datetime(2024, 7, 9, 15, 45), 1, 1338147, 3161, 1328310),
        ("48201", datetime(2024, 7, 9, 16, 0), datetime(2024, 7, 9, 16, 15), 1, 1328310, 3161, 1315776),
        ("48201", datetime(2024, 7, 10, 0, 45), datetime(2024, 7, 10, 2, 0), 5, 1095633, 2323, 1050184),
        ("48201", datetime(2024, 7, 10, 3, 0), datetime(2024, 7, 10, 3, 15), 1, 1041416, 2339, 1036922),
        ("48201", datetime(2024, 7, 10, 3, 30), datetime(2024, 7, 10, 3, 45), 1, 1036922, 2339, 1036231),
        ("48201", datetime(2024, 7, 10, 5, 30), datetime(2024, 7, 10, 5, 45), 1, 1026513, 2339, 1029798),
    ]


EVENTS = [
    # event_id, start, end, readings, peak, customer-hours (capped), raw, exceeds, feed gap h, dropout h
    ("15001-00001", "2024-07-08 08:00", "2024-07-08 09:30", 6, 1491, 2237, 2237, False, 0.0, 0.0),
    ("15001-00002", "2024-07-08 12:30", "2024-07-08 14:30", 8, 1597, 2996, 2996, False, 0.0, 0.0),
    ("15001-00003", "2024-07-10 06:15", "2024-07-10 07:00", 3, 866, 624, 624, False, 0.0, 0.0),
    ("15001-00004", "2024-07-10 14:30", "2024-07-10 17:45", 13, 1597, 5190, 5190, False, 0.0, 0.0),
    ("15001-00005", "2024-07-10 19:45", "2024-07-11 03:45", 32, 2107, 16768, 16768, False, 0.0, 0.0),
    ("15001-00006", "2024-07-11 14:00", "2024-07-11 16:30", 8, 2105, 3757, 3757, False, 0.0, 0.0),
    ("15003-00001", "2024-06-16 00:00", "2024-06-16 01:30", 6, 608, 911, 911, False, 0.0, 0.0),
    ("15003-00002", "2024-07-09 22:30", "2024-07-10 00:00", 6, 1860, 2784, 2784, False, 0.0, 0.0),
    ("15003-00003", "2024-07-10 13:00", "2024-07-10 14:45", 7, 947, 1623, 1623, False, 0.0, 0.0),
    ("15003-00004", "2024-07-10 20:30", "2024-07-10 21:15", 3, 732, 548, 548, False, 0.0, 0.0),
    # Starts at the first fixture reading; the full-data event starts at 2022-10-24 22:45.
    ("15007-00001", "2022-10-25 00:00", "2022-10-25 01:00", 4, 525, 292, 292, False, 0.0, 0.0),
    ("15007-00002", "2024-07-11 05:45", "2024-07-11 18:15", 49, 27853, 92627, 92627, False, 0.0, 0.25),
    ("15009-00001", "2024-07-11 04:45", "2024-07-11 06:30", 7, 1891, 3307, 3307, False, 0.0, 0.0),
    ("15009-00002", "2024-07-11 13:00", "2024-07-11 16:30", 14, 2431, 8506, 8506, False, 0.0, 0.0),
    ("48157-00001", "2022-10-25 05:30", "2022-10-25 15:30", 40, 12035, 80282, 80282, False, 0.0, 0.0),
    # Beryl events are cut at the end of the fixture (2024-07-12 00:00); 2 dropouts of 5 runs each counted.
    ("48157-00002", "2024-07-08 14:15", "2024-07-12 00:00", 317, 236443, 11394117, 11394117, False, 0.0, 2.5),
    ("48201-00001", "2022-10-25 05:15", "2022-10-25 16:00", 42, 28722, 183674, 183674, False, 0.0, 0.0),
    # One event across the 9-hour nationwide feed gap (D10), cut at both ends of window W3.
    ("48201-00002", "2024-05-23 18:00", "2024-05-24 12:00", 36, 19859, 105155, 105155, False, 9.0, 0.0),
    ("48201-00003", "2024-07-08 14:15", "2024-07-12 00:00", 317, 1660703, 85152728, 87051815, True, 0.0, 2.5),
    ("49011-00001", "2024-07-10 23:45", "2024-07-11 00:30", 3, 348, 261, 261, False, 0.0, 0.0),
    ("49033-00001", "2024-06-15 23:00", "2024-06-15 23:45", 3, 3935, 754, 2374, True, 0.0, 0.0),
    ("49033-00002", "2024-06-16 00:45", "2024-06-16 01:00", 1, 168, 42, 42, False, 0.0, 0.0),
    ("49035-00001", "2024-07-11 23:30", "2024-07-12 00:00", 2, 2561, 1202, 1202, False, 0.0, 0.0),
    ("49057-00001", "2022-10-25 04:00", "2022-10-25 10:00", 24, 5071, 29922, 29922, False, 0.0, 0.0),
    ("49057-00002", "2024-07-10 12:45", "2024-07-10 14:15", 6, 384, 572, 572, False, 0.0, 0.0),
    ("49057-00003", "2024-07-10 21:00", "2024-07-11 02:30", 22, 5706, 13678, 13678, False, 0.0, 0.0),
    ("49057-00004", "2024-07-11 06:15", "2024-07-11 07:00", 3, 2895, 903, 903, False, 0.0, 0.0),
]


def test_outage_events(rows):
    """D17: an event is a run of readings at or above the threshold; a gap above 1 hour of collected
    runs starts a new one. D10: Harris 2024-05-23/24 spans the 9-hour feed gap as one event.
    D4: customer-hours are capped at the denominator (Harris in Beryl, Rich UT); raw is kept."""
    got = rows("""
        SELECT event_id, strftime(event_start, '%Y-%m-%d %H:%M'), strftime(event_end, '%Y-%m-%d %H:%M'), reading_count,
               peak_customers_out, CAST(ROUND(customer_hours_lost) AS BIGINT), CAST(ROUND(customer_hours_lost_raw) AS BIGINT),
               exceeds_customers, CAST(feed_gap_hours AS DOUBLE), CAST(dropout_hours AS DOUBLE)
        FROM gold_outage_events ORDER BY event_id
    """)
    assert got == EVENTS


def test_event_flags(rows):
    assert rows("""
        SELECT COUNT_IF(spans_feed_gap), COUNT_IF(spans_dropout), COUNT_IF(NOT has_denominator), COUNT_IF(NOT ranking_eligible)
        FROM gold_outage_events
    """) == [(1, 3, 0, 0)]


def synthetic_silver(share: float) -> tuple:
    """Hand-built Silver rows with known answers (2024-01-01 UTC), as in scripts/test_gold_events_duckdb.py.

    A 01001 (10,000): 200 at 00:00, 00:15, feed gap 00:30-01:45, 200 at 02:00, 02:15 -> one event over the gap.
    B 01003 (120): 150 at 03:00, 04:15, 05:00, 06:00 -> 5 runs apart splits, 3 and 4 do not; capped at 120.
    C 01005: 50 in every collected slot; never qualifies.
    D 01007 (1,000,000): threshold T; T-1 at 03:00, 03:30 and T at 03:15, 03:45 -> one event 03:15-04:00.
    E 01009 (10,000): 5,000, 5,000, five readings of 50, 4,000 -> a 5-run dropout inside one event.
    F 01011 (10,000): 5,000, six readings of 50, 5,000 -> recovery after 6 runs: two events.
    """
    t = int(math.ceil(max(pipeline_config.get("events.min_customers_out"), share * 1_000_000)))
    con = duckdb_pipeline.connect()
    con.execute("""
        CREATE TABLE dim_county_customers AS SELECT * FROM (VALUES
            ('01001', 10000::BIGINT, 'total_customers_2024'), ('01003', 120::BIGINT, 'total_customers_2024'),
            ('01005', 5000::BIGINT, 'total_customers_2024'), ('01007', 1000000::BIGINT, 'total_customers_2024'),
            ('01009', 10000::BIGINT, 'total_customers_2024'), ('01011', 10000::BIGINT, 'total_customers_2024')
        ) AS t(fips_code, customers, denominator_source)
    """)
    con.execute(f"""
        CREATE TABLE silver_outages AS
        WITH slots AS (
            SELECT UNNEST(generate_series(TIMESTAMP '2024-01-01 00:00', TIMESTAMP '2024-01-01 12:00', INTERVAL 15 MINUTES)) AS reading_time
        ),
        hm AS (SELECT reading_time, strftime(reading_time, '%H:%M') AS hhmm FROM slots),
        r AS (
            SELECT '01001' AS fips_code, reading_time, 200::BIGINT AS customers_out FROM hm
                WHERE hhmm IN ('00:00', '00:15', '02:00', '02:15')
            UNION ALL SELECT '01003', reading_time, 150 FROM hm WHERE hhmm IN ('03:00', '04:15', '05:00', '06:00')
            UNION ALL SELECT '01005', reading_time, 50 FROM hm WHERE hhmm NOT BETWEEN '00:30' AND '01:45'
            UNION ALL SELECT '01007', reading_time, CASE WHEN hhmm IN ('03:15', '03:45') THEN {t} ELSE {t - 1} END
                      FROM hm WHERE hhmm IN ('03:00', '03:15', '03:30', '03:45')
            UNION ALL SELECT '01009', reading_time, CASE WHEN hhmm IN ('08:00', '08:15') THEN 5000 WHEN hhmm = '09:45' THEN 4000 ELSE 50 END
                      FROM hm WHERE hhmm BETWEEN '08:00' AND '09:45'
            UNION ALL SELECT '01011', reading_time, CASE WHEN hhmm IN ('10:00', '11:45') THEN 5000 ELSE 50 END
                      FROM hm WHERE hhmm BETWEEN '10:00' AND '11:45'
        )
        SELECT r.fips_code, 'Test' AS county, 'Alabama' AS state, 'AL' AS state_abbr, 'South' AS census_region,
               r.reading_time, r.customers_out, r.customers_out > k.customers AS exceeds_customers
        FROM r JOIN dim_county_customers k USING (fips_code)
    """)
    duckdb_pipeline.run_file(con, "03_gold_events.sql", FIXTURES)
    return con, t


def test_event_rules_at_their_boundaries():
    con, t = synthetic_silver(pipeline_config.get("events.threshold_share"))
    got = con.execute("""
        SELECT event_id, strftime(event_start, '%H:%M'), strftime(event_end, '%H:%M'), duration_hours, reading_count,
               customer_hours_lost, customer_hours_lost_raw, spans_feed_gap, feed_gap_hours, spans_dropout, dropout_hours
        FROM gold_outage_events ORDER BY event_id
    """).fetchall()
    assert got == [
        ("01001-00001", "00:00", "02:30", 2.5, 4, 200.0, 200.0, True, 1.5, False, 0.0),
        ("01003-00001", "03:00", "03:15", 0.25, 1, 30.0, 37.5, False, 0.0, False, 0.0),
        ("01003-00002", "04:15", "06:15", 2.0, 3, 90.0, 112.5, False, 0.0, False, 0.0),
        ("01007-00001", "03:15", "04:00", 0.75, 2, t * 0.5, t * 0.5, False, 0.0, False, 0.0),
        ("01009-00001", "08:00", "10:00", 2.0, 3, 3500.0, 3500.0, False, 0.0, True, 1.25),
        ("01011-00001", "10:00", "10:15", 0.25, 1, 1250.0, 1250.0, False, 0.0, False, 0.0),
        ("01011-00002", "11:45", "12:00", 0.25, 1, 1250.0, 1250.0, False, 0.0, False, 0.0),
    ]
    assert con.execute("""
        SELECT fips_code, strftime(dropout_start, '%H:%M'), strftime(dropout_end, '%H:%M'), dropout_runs FROM gold_feed_dropouts
    """).fetchall() == [("01009", "08:30", "09:45", 5)]
    assert con.execute("SELECT COUNT(*) FROM gold_collection_runs WHERE NOT is_collected").fetchone()[0] == 6
