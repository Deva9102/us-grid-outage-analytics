"""Test sql/databricks/03_gold_events.sql in DuckDB.

The Gold queries are read straight from the .sql file, so the test runs the same logic that
Databricks will run, translated to DuckDB by scripts/sql_dialect.py.

Steps:
    1. Synthetic check of the event rules: 1-hour boundary, nationwide feed gap (D3, D10),
       capping (D4), scaled threshold (D18) and feed dropouts (D19).
    2. Build dim_county_customers (full data) and silver_outages (sample or all years) with the
       Silver test logic, then the Gold tables, and print checks, dropouts and the 10 largest events.

Raw files are only read. Nothing is written.

Usage:
    uv run python scripts/test_gold_events_duckdb.py [--month 2024-07 | --month all]
"""

from __future__ import annotations

import argparse
import math
from pathlib import Path

import duckdb

import pipeline_config
import test_silver_duckdb as silver

REPO_ROOT = Path(__file__).resolve().parent.parent
GOLD_SQL = REPO_ROOT / "sql" / "databricks" / "03_gold_events.sql"
GOLD_TABLES = ["gold_collection_runs", "gold_event_thresholds", "gold_feed_dropouts", "gold_outage_events"]

def current_share() -> float:
    return float(pipeline_config.get("events.threshold_share"))


def gold_statements(share: float | None = None) -> list[tuple[str, str]]:
    """(table name, query) for each CREATE OR REPLACE TABLE ... AS <query>; in the file.

    With share given, events.threshold_share is overridden for this run (used by the sensitivity test).
    """
    overrides = {"events.threshold_share": float(share)} if share is not None else None
    text = pipeline_config.render(GOLD_SQL.read_text(), overrides)
    import sql_split

    found = sql_split.table_statements(text)  # D53
    if [name for name, _ in found] != GOLD_TABLES:
        raise SystemExit(f"Unexpected statements in {GOLD_SQL.name}: {[n for n, _ in found]}")
    import sql_dialect

    return [(name, sql_dialect.to_duckdb(query)) for name, query in found]


def build_gold(con, share: float | None = None, skip: tuple[str, ...] = ()) -> None:
    for name, query in gold_statements(share):
        if name not in skip:
            con.execute(f"CREATE OR REPLACE TABLE {name} AS {query}")


def show(con, sql: str) -> None:
    print(con.execute(sql).fetchdf().to_string(index=False))


def synthetic_check() -> None:
    """Hand-built Silver rows with known answers (2024-01-01, UTC).

    A 01001 (10,000 customers): 200 at 00:00, 00:15, nationwide feed gap 00:30-01:45 (1.5 h),
        200 at 02:00, 02:15. Expect ONE event 00:00-02:30, spans_feed_gap, 1.5 gap hours.
    B 01003 (120 customers): 150 at 03:00, 04:15, 05:00, 06:00. 04:15 is 5 runs after 03:00:
        new event. 3 and 4 runs apart stay together. 150 is capped to 120 for customer-hours.
        The missing rows between 03:00 and 04:15 are zeros, not a dropout.
    C 01005: 50 in every collected slot; never qualifies, keeps the non-gap slots collected.
    D 01007 (1,000,000 customers): threshold T = GREATEST(100, share x 1,000,000) (D18).
        T-1 at 03:00 and 03:30, T at 03:15 and 03:45. Expect ONE event 03:15-04:00, 2 readings.
    E 01009 (10,000 customers): 5,000 at 08:00, 08:15; 50 for five readings 08:30-09:30;
        4,000 at 09:45. The drop is below 10% and recovers above 50% 5 runs later: a dropout
        (D19). Expect ONE event 08:00-10:00, 3 readings, spans_dropout, 1.25 dropout hours.
    F 01011 (10,000 customers): 5,000 at 10:00; 50 for six readings 10:15-11:30; 5,000 at
        11:45. Recovery comes 6 runs after the drop: not a dropout. Expect TWO events.
    """
    share = current_share()
    t = int(math.ceil(max(pipeline_config.get("events.min_customers_out"), share * 1_000_000)))
    print(f"Event share (config events.threshold_share): {share:g} (threshold for 1,000,000 customers: {t:,})")
    con = duckdb.connect()
    con.execute("""
        CREATE TABLE dim_county_customers AS SELECT * FROM (VALUES
            ('01001',   10000::BIGINT, 'total_customers_2024', FALSE),
            ('01003',     120::BIGINT, 'total_customers_2024', FALSE),
            ('01005',    5000::BIGINT, 'total_customers_2024', FALSE),
            ('01007', 1000000::BIGINT, 'total_customers_2024', FALSE),
            ('01009',   10000::BIGINT, 'total_customers_2024', FALSE),
            ('01011',   10000::BIGINT, 'total_customers_2024', FALSE)
        ) AS t(fips_code, customers, denominator_source, denominator_mismatch)
    """)
    con.execute(f"""
        CREATE TABLE silver_outages AS
        WITH
        slots AS (
            SELECT unnest(generate_series(TIMESTAMP '2024-01-01 00:00', TIMESTAMP '2024-01-01 12:00',
                                          INTERVAL 15 MINUTES)) AS reading_time
        ),
        gap AS (
            SELECT * FROM slots WHERE reading_time BETWEEN TIMESTAMP '2024-01-01 00:30' AND TIMESTAMP '2024-01-01 01:45'
        ),
        hm AS (SELECT reading_time, strftime(reading_time, '%H:%M') AS hhmm FROM slots),
        a AS (SELECT '01001' AS fips_code, reading_time, 200::BIGINT AS customers_out FROM hm
              WHERE hhmm IN ('00:00', '00:15', '02:00', '02:15')),
        b AS (SELECT '01003', reading_time, 150::BIGINT FROM hm
              WHERE hhmm IN ('03:00', '04:15', '05:00', '06:00')),
        c AS (SELECT '01005', reading_time, 50::BIGINT FROM slots
              WHERE reading_time NOT IN (SELECT reading_time FROM gap)),
        d AS (SELECT '01007', reading_time,
                     CASE WHEN hhmm IN ('03:15', '03:45') THEN {t} ELSE {t - 1} END::BIGINT FROM hm
              WHERE hhmm IN ('03:00', '03:15', '03:30', '03:45')),
        e AS (SELECT '01009', reading_time,
                     CASE WHEN hhmm IN ('08:00', '08:15') THEN 5000 WHEN hhmm = '09:45' THEN 4000 ELSE 50 END::BIGINT
              FROM hm WHERE hhmm BETWEEN '08:00' AND '09:45'),
        f AS (SELECT '01011', reading_time,
                     CASE WHEN hhmm IN ('10:00', '11:45') THEN 5000 ELSE 50 END::BIGINT
              FROM hm WHERE hhmm BETWEEN '10:00' AND '11:45'),
        rows AS (SELECT * FROM a UNION ALL SELECT * FROM b UNION ALL SELECT * FROM c
                 UNION ALL SELECT * FROM d UNION ALL SELECT * FROM e UNION ALL SELECT * FROM f)
        SELECT r.fips_code, 'Test' AS county, 'Alabama' AS state, 'AL' AS state_abbr,
               'South' AS census_region, r.reading_time, r.customers_out,
               r.customers_out > k.customers AS exceeds_customers
        FROM rows r JOIN dim_county_customers k USING (fips_code)
    """)
    build_gold(con)

    got = con.execute("""
        SELECT event_id, strftime(event_start, '%H:%M'), strftime(event_end, '%H:%M'), duration_hours,
               reading_count, customer_hours_lost, customer_hours_lost_raw, spans_feed_gap, feed_gap_hours,
               spans_dropout, dropout_hours
        FROM gold_outage_events ORDER BY event_id
    """).fetchall()
    expected = [
        ("01001-00001", "00:00", "02:30", 2.5, 4, 200.0, 200.0, True, 1.5, False, 0.0),
        ("01003-00001", "03:00", "03:15", 0.25, 1, 30.0, 37.5, False, 0.0, False, 0.0),
        ("01003-00002", "04:15", "06:15", 2.0, 3, 90.0, 112.5, False, 0.0, False, 0.0),
        ("01007-00001", "03:15", "04:00", 0.75, 2, t * 0.5, t * 0.5, False, 0.0, False, 0.0),
        ("01009-00001", "08:00", "10:00", 2.0, 3, 3500.0, 3500.0, False, 0.0, True, 1.25),
        ("01011-00001", "10:00", "10:15", 0.25, 1, 1250.0, 1250.0, False, 0.0, False, 0.0),
        ("01011-00002", "11:45", "12:00", 0.25, 1, 1250.0, 1250.0, False, 0.0, False, 0.0),
    ]
    got_norm = [(r[0], r[1], r[2], float(r[3]), int(r[4]), float(r[5]), float(r[6]), bool(r[7]), float(r[8]),
                 bool(r[9]), float(r[10])) for r in got]
    ok = got_norm == expected
    print(f"Synthetic event check (1-hour boundary, feed gap, D4 cap, D18 threshold, D19 dropout): "
          f"{'PASS' if ok else 'FAIL'}")
    print("  event_id     start  end    hours  readings  cust_hours  raw  gap  gap_h  dropout  dropout_h")
    for row in got:
        print("  " + "  ".join(str(v) for v in row))
    if not ok:
        for g, e in zip(got_norm, expected, strict=False):
            if g != e:
                print(f"  got      {g}\n  expected {e}")

    dropouts = con.execute("""
        SELECT fips_code, strftime(dropout_start, '%H:%M'), strftime(dropout_end, '%H:%M'), dropout_runs
        FROM gold_feed_dropouts ORDER BY 1
    """).fetchall()
    dropouts_ok = dropouts == [("01009", "08:30", "09:45", 5)]
    print(f"  dropouts found: {dropouts} (expected [('01009', '08:30', '09:45', 5)])")
    gaps = con.execute("SELECT COUNT(*) FROM gold_collection_runs WHERE NOT is_collected").fetchone()[0]
    print(f"  feed gap slots found: {gaps} (expected 6)")
    if not ok or gaps != 6 or not dropouts_ok:
        raise SystemExit("Synthetic event check failed")


def consistency_checks(con) -> None:
    print("\nConsistency checks:")
    checks = con.execute("""
        SELECT
            (SELECT COUNT(*) FROM silver_outages s
               JOIN gold_collection_runs r ON r.slot_time = s.reading_time
               LEFT JOIN gold_event_thresholds t USING (fips_code)
               WHERE s.customers_out >= COALESCE(t.event_threshold, 100)
                 AND NOT EXISTS (
                     SELECT 1 FROM gold_feed_dropouts d
                     WHERE d.fips_code = s.fips_code
                       AND r.run_index >= d.drop_start_run AND r.run_index < d.recovery_run))
                                                                                      AS qualifying_readings,
            (SELECT SUM(reading_count) FROM gold_outage_events)                       AS readings_in_events,
            (SELECT COUNT(*) - COUNT(DISTINCT event_id) FROM gold_outage_events)      AS duplicate_event_ids,
            (SELECT COUNT(*) FROM (
                SELECT event_start, LAG(event_end) OVER (PARTITION BY fips_code ORDER BY event_start) AS prev_end
                FROM gold_outage_events) WHERE event_start < prev_end)                AS overlapping_events,
            (SELECT COUNT(*) FROM gold_outage_events WHERE duration_hours < 0.25)     AS shorter_than_one_run,
            (SELECT COUNT(*) FROM gold_outage_events
               WHERE customer_hours_lost > customer_hours_lost_raw + 1e-6)            AS capped_above_raw,
            (SELECT COUNT(*) FROM gold_outage_events WHERE peak_out_per_1000 > 1000)  AS rate_above_1000,
            (SELECT COUNT(*) FROM gold_outage_events WHERE dropout_hours < 0)         AS negative_dropout_hours
    """).fetchdf()
    for col in checks.columns:
        print(f"  {col:<24} {int(checks[col][0]):>14,}")
    c = checks.iloc[0]
    if c.qualifying_readings != c.readings_in_events or c.duplicate_event_ids or c.overlapping_events \
            or c.shorter_than_one_run or c.capped_above_raw or c.rate_above_1000 or c.negative_dropout_hours:
        raise SystemExit("Consistency check failed")


def real_data(month: str) -> None:
    con = duckdb.connect()

    # Denominators from full data, as in the Silver test.
    silver.bronze(con, month_filter=None)
    silver.build_dim(con)

    # Silver on the sample (or all years), then drop the intermediate steps to save memory.
    silver.bronze(con, month_filter=None if month == "all" else month)
    for name, _, sql in silver.SILVER_STEPS:
        con.execute(f"CREATE OR REPLACE TABLE {name} AS {sql}")
    for name, _, _ in silver.SILVER_STEPS[:-1]:
        con.execute(f"DROP TABLE {name}")

    build_gold(con)

    print(f"\nData: {'all three years' if month == 'all' else month}, event share {current_share():g}")
    print("\nFeed gaps found (D3):")
    show(con, """
        SELECT YEAR(slot_time) AS year, COUNT(*) FILTER (WHERE NOT is_collected) AS feed_gap_slots,
               COUNT(*) AS slots
        FROM gold_collection_runs GROUP BY 1 ORDER BY 1
    """)

    print("\nFeed dropouts (D19):")
    show(con, """
        SELECT dropout_year, COUNT(*) AS dropouts, COUNT(DISTINCT fips_code) AS counties,
               SUM(dropout_runs) AS dropout_runs,
               COUNT(*) FILTER (WHERE pre_drop_customers_out >= 10000) AS pre_drop_10k_plus
        FROM gold_feed_dropouts GROUP BY 1 ORDER BY 1
    """)
    print("\n10 largest dropouts by pre-drop customers out:")
    show(con, """
        SELECT d.fips_code, t.county, t.state_abbr AS st,
               strftime(d.dropout_start, '%Y-%m-%d %H:%M') AS start_utc,
               strftime(d.dropout_end, '%Y-%m-%d %H:%M') AS recovered_utc,
               d.dropout_runs AS runs, d.pre_drop_customers_out AS before,
               d.dropped_customers_out AS dropped_to, d.recovery_customers_out AS recovered_to
        FROM gold_feed_dropouts d
        LEFT JOIN (SELECT fips_code, ANY_VALUE(county) AS county, ANY_VALUE(state_abbr) AS state_abbr
                   FROM silver_outages GROUP BY 1) t USING (fips_code)
        ORDER BY d.pre_drop_customers_out DESC LIMIT 10
    """)
    print("\nHouston-area dropouts on 2024-07-10 (Harris 48201, Fort Bend 48157):")
    show(con, """
        SELECT fips_code, strftime(dropout_start, '%Y-%m-%d %H:%M') AS start_utc,
               strftime(dropout_end, '%Y-%m-%d %H:%M') AS recovered_utc, dropout_runs AS runs,
               pre_drop_customers_out AS before, dropped_customers_out AS dropped_to,
               recovery_customers_out AS recovered_to
        FROM gold_feed_dropouts
        WHERE fips_code IN ('48201', '48157') AND CAST(dropout_start AS DATE) = DATE '2024-07-10'
        ORDER BY 1, 2
    """)

    print("\nEvents per year:")
    show(con, """
        SELECT event_year, COUNT(*) AS events,
               COUNT(*) FILTER (WHERE spans_feed_gap) AS spans_feed_gap,
               COUNT(*) FILTER (WHERE spans_dropout) AS spans_dropout,
               COUNT(*) FILTER (WHERE exceeds_customers) AS has_overcount,
               COUNT(*) FILTER (WHERE NOT has_denominator) AS no_denominator,
               COUNT(*) FILTER (WHERE NOT ranking_eligible) AS not_ranking_eligible,
               ROUND(MEDIAN(duration_hours), 2) AS median_hours,
               ROUND(QUANTILE_CONT(duration_hours, 0.95), 2) AS p95_hours,
               ROUND(SUM(customer_hours_lost) / 1e6, 1) AS customer_hours_m
        FROM gold_outage_events GROUP BY 1 ORDER BY 1
    """)

    consistency_checks(con)

    print("\n10 largest events by customer_hours_lost:")
    show(con, """
        SELECT event_id, county, state_abbr AS st,
               strftime(event_start, '%Y-%m-%d %H:%M') AS start_utc,
               strftime(event_end, '%Y-%m-%d %H:%M') AS end_utc,
               ROUND(duration_hours, 1) AS hours,
               peak_customers_out AS peak_out,
               ROUND(customer_hours_lost) AS customer_hours,
               spans_feed_gap AS gap, spans_dropout AS dropout, exceeds_customers AS over
        FROM gold_outage_events
        ORDER BY customer_hours_lost DESC
        LIMIT 10
    """)

    if month == "all":
        n = con.execute("""
            SELECT COUNT(*) FROM gold_outage_events
            WHERE spans_feed_gap AND event_start < TIMESTAMP '2024-05-24 00:15' AND event_end > TIMESTAMP '2024-05-24 09:00'
        """).fetchone()[0]
        print(f"\nEvents spanning the whole 2024-05-24 9-hour feed gap (D10): {n:,}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--month", default="2024-07", help="YYYY-MM sample, or 'all'")
    args = parser.parse_args()
    if not silver.REGIONS_CSV.exists():
        raise SystemExit("Missing region lookup. Run: uv run python scripts/census_regions.py")
    synthetic_check()
    real_data(args.month)


if __name__ == "__main__":
    main()
