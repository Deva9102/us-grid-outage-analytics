"""Test the added-source Silver SQL, the D21 calibration and the D22 coverage table in DuckDB.

Runs the real statements from sql/databricks/02_silver_sources.sql, 03_gold_events.sql and
03_gold_coverage.sql (translated by scripts/sql_dialect.py) on local Bronze views, and prints
row counts before and after each rule. Then measures the D21 calibration's effect by building
Gold twice, with uncalibrated (D13) and calibrated (D21) denominators.

Raw files are only read. Nothing is written except converted Excel Parquet (raw_convert.py).

Usage:
    uv run python scripts/test_sources_duckdb.py [--skip-gold]
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

import duckdb

import sql_dialect
import test_gold_events_duckdb as gold
import test_silver_duckdb as silver

REPO_ROOT = Path(__file__).resolve().parent.parent
SQL = REPO_ROOT / "sql" / "databricks"
CALIBRATED_STATES = ("MA", "SC", "HI", "MO", "SD")

FAILURES: list[str] = []


def show(con, sql: str) -> None:
    print(con.execute(sql).fetchdf().to_string(index=False))


def one(con, sql: str):
    return con.execute(sql).fetchall()[0][0]


def check(label: str, ok: bool) -> None:
    print(f"  [{'ok' if ok else 'FAIL'}] {label}")
    if not ok:
        FAILURES.append(label)


def run_file(con, path: Path) -> None:
    for name, query in sql_dialect.table_statements(path):
        started = time.time()
        con.execute(f"CREATE OR REPLACE TABLE {name} AS {query}")
        print(f"  {name:<32} {one(con, f'SELECT COUNT(*) FROM {name}'):>12,} rows  {time.time() - started:5.1f}s")


def rule(label: str, before: int, after: int) -> None:
    print(f"  {label:<70} {before:>10,} -> {after:>10,}  ({after - before:+,})")


# -----------------------------------------------------------------------------

def report_eia(con) -> None:
    print("\n=== EIA-861 ===")
    for table, sheets in (("bronze_eia861_reliability", "'Reliability_States', 'Reliability_Territories'"),
                          ("bronze_eia861_sales", "'States', 'Territories'")):
        total = one(con, f"SELECT COUNT(*) FROM {table}")
        in_sheets = one(con, f"SELECT COUNT(*) FROM {table} WHERE sheet_name IN ({sheets})")
        data = one(con, f"SELECT COUNT(*) FROM {table} WHERE sheet_name IN ({sheets}) AND regexp_matches(col_01, '^[0-9]{{4}}$')")
        rule(f"{table}: all rows -> sheets used (D32)", total, in_sheets)
        rule(f"{table}: sheets used -> data rows, 4-digit year (D32)", in_sheets, data)
    sales_data = one(con, "SELECT COUNT(*) FROM bronze_eia861_sales WHERE sheet_name IN ('States','Territories') AND "
                          "regexp_matches(col_01, '^[0-9]{4}$')")
    sales_acd = one(con, "SELECT COUNT(*) FROM bronze_eia861_sales WHERE sheet_name IN ('States','Territories') AND "
                         "regexp_matches(col_01, '^[0-9]{4}$') AND TRIM(col_04) IN ('A','C','D')")
    rule("sales data rows -> Parts A, C, D only (D23)", sales_data, sales_acd)
    print("\nsilver_utility_reliability by year and standard:")
    show(con, """SELECT data_year, reporting_standard, COUNT(*) AS rows, COUNT(customers) AS with_sales_customers
                 FROM silver_utility_reliability GROUP BY ALL ORDER BY 1, 2""")
    print("\nSize bands (D32), 2024:")
    show(con, """SELECT size_band, COUNT(*) AS utilities, MIN(customers) AS min_customers, MAX(customers) AS max_customers,
                        COUNT(*) FILTER (WHERE reporting_standard = 'IEEE 1366') AS ieee
                 FROM silver_utility_reliability WHERE data_year = 2024 GROUP BY 1 ORDER BY min_customers NULLS LAST""")
    print("\nEversource / National Grid, 2024:")
    show(con, """SELECT utility_name, state_abbr, reporting_standard, customers, size_band, saidi_with_med, saidi_without_med
                 FROM silver_utility_reliability
                 WHERE data_year = 2024 AND regexp_matches(utility_name,
                   '(?i)(nstar|connecticut light|public service co of nh|massachusetts electric|'
                   || 'nantucket electric|niagara mohawk|narragansett)')
                 ORDER BY utility_name""")
    check("silver_utility_reliability is unique per utility, state, year",
          one(con, "SELECT COUNT(*) - COUNT(DISTINCT (data_year, utility_number, state_abbr)) FROM silver_utility_reliability") == 0)
    check("silver_eia_state_customers 2024 total = 165,391,292 (profile)",
          one(con, "SELECT SUM(customers) FROM silver_eia_state_customers WHERE data_year = 2024") == 165_391_292)


def report_noaa(con) -> None:
    print("\n=== NOAA Storm Events ===")
    raw = one(con, "SELECT COUNT(*) FROM bronze_noaa_storm_events")
    det = one(con, "SELECT COUNT(*) FROM silver_storm_event_details")
    rule("bronze rows -> silver_storm_event_details (one per event)", raw, det)
    print("\nArea type from the NOAA state code crosswalk (D28):")
    show(con, """SELECT COALESCE(area_type, '(no match)') AS area_type, location_type, COUNT(*) AS events
                 FROM silver_storm_event_details GROUP BY ALL ORDER BY 1, 2""")
    land = one(con, "SELECT COUNT(*) FROM silver_storm_event_details WHERE area_type IN ('state', 'territory')")
    rule("events -> on land in a state or tracked territory (D30)", det, land)
    placed = one(con, "SELECT COUNT(DISTINCT event_id) FROM silver_storm_events")
    rule("land events -> placed in at least one county (D30)", land, placed)
    rows = one(con, "SELECT COUNT(*) FROM silver_storm_events")
    rule("placed events -> event x county rows (zones expand)", placed, rows)
    print("\nsilver_storm_events_unplaced by reason (D30):")
    show(con, "SELECT reason, COUNT(*) AS events FROM silver_storm_events_unplaced GROUP BY 1 ORDER BY 2 DESC")
    print("\nZone events not in the file in effect, by state (top 8):")
    show(con, """SELECT noaa_state, COUNT(*) AS events FROM silver_storm_events_unplaced WHERE reason = 'zone_not_in_file'
                 GROUP BY 1 ORDER BY 2 DESC LIMIT 8""")
    print("\nTime conversion (D29) and damage parsing (D31):")
    show(con, """SELECT COUNT(*) FILTER (WHERE begin_utc IS NULL) AS begin_utc_null,
                        COUNT(*) FILTER (WHERE end_utc < begin_utc) AS ends_before_begin,
                        COUNT(*) FILTER (WHERE damage_property_usd IS NOT NULL) AS property_parsed,
                        COUNT(*) FILTER (WHERE damage_property_usd IS NULL) AS property_null,
                        SUM(damage_property_usd) / 1e9 AS property_usd_bn,
                        SUM(damage_crops_usd) / 1e9 AS crops_usd_bn
                 FROM silver_storm_event_details""")
    bad = one(con, """SELECT COUNT(*) FROM bronze_noaa_storm_events
                      WHERE TRIM(COALESCE(DAMAGE_PROPERTY, '')) <> '' AND NOT regexp_matches(TRIM(DAMAGE_PROPERTY), '^[0-9.]+[KMB]?$')""")
    check(f"every non-empty DAMAGE_PROPERTY parses ({bad} do not)", bad == 0)
    print("\nCounties per event:")
    show(con, """SELECT location_type, COUNT(DISTINCT event_id) AS events, COUNT(*) AS county_rows,
                        ROUND(COUNT(*) / COUNT(DISTINCT event_id), 3) AS counties_per_event, MAX(county_count) AS max_counties
                 FROM silver_storm_events GROUP BY 1 ORDER BY 1""")
    check("silver_storm_events unique per event_id, fips_code",
          one(con, "SELECT COUNT(*) - COUNT(DISTINCT (event_id, fips_code)) FROM silver_storm_events") == 0)
    check("event_weight sums to 1 per event",
          one(con, "SELECT COUNT(*) FROM (SELECT event_id, SUM(event_weight) s FROM silver_storm_events GROUP BY 1) WHERE ABS(s - 1) "
                   "> 1e-9") == 0)
    check("every event is placed or unplaced, not both",
          one(con, "SELECT COUNT(*) FROM silver_storm_events_unplaced u JOIN silver_storm_events s USING (event_id)") == 0
          and placed + one(con, "SELECT COUNT(*) FROM silver_storm_events_unplaced") == det)
    print("\nCounty rows vs EAGLE-I counties:")
    show(con, """SELECT location_type, COUNT(*) AS county_rows,
                        COUNT(*) FILTER (WHERE fips_code IN (SELECT fips_code FROM dim_county_customers)) AS in_eaglei
                 FROM silver_storm_events GROUP BY 1 ORDER BY 1""")
    print("\nCounty FIPS (C events) not in any NWS zone file, top 8:")
    show(con, """SELECT fips_code, ANY_VALUE(d.cz_name) AS cz_name, COUNT(*) AS events
                 FROM silver_storm_events s JOIN silver_storm_event_details d USING (event_id)
                 WHERE s.location_type = 'C' AND s.fips_code NOT IN (SELECT fips_code FROM silver_nws_zone_county)
                 GROUP BY 1 ORDER BY 3 DESC LIMIT 8""")


def report_oe417(con) -> None:
    print("\n=== OE-417 ===")
    raw = one(con, "SELECT COUNT(*) FROM bronze_oe417")
    after_header = one(con, """SELECT COUNT(*) FROM bronze_oe417 b JOIN (SELECT source_name, MIN(CAST(row_number AS INT)) h
                               FROM bronze_oe417 WHERE TRIM(col_02) = 'Date Event Began' GROUP BY 1) x
                               ON x.source_name = b.source_name AND CAST(b.row_number AS INT) > x.h""")
    rows = one(con, "SELECT COUNT(*) FROM silver_oe417_rows")
    rule("bronze rows -> rows after the header row (D33)", raw, after_header)
    rule("rows after header -> non-blank incident rows (D33)", after_header, rows)
    show(con, """SELECT report_year, COUNT(*) AS incidents, COUNT(*) FILTER (WHERE begin_local IS NULL) AS no_begin_date,
                        COUNT(*) FILTER (WHERE NOT begin_time_reported) AS no_begin_time,
                        COUNT(*) FILTER (WHERE customers_affected IS NULL) AS customers_unknown
                 FROM silver_oe417_rows GROUP BY 1 ORDER BY 1""")
    print("\nRestoration status (D33):")
    show(con, "SELECT restoration_status, COUNT(*) AS incidents FROM silver_oe417_rows GROUP BY 1 ORDER BY 2 DESC")
    print("\nLocations (D33, D34):")
    show(con, """SELECT location_level, COALESCE(match_type, '-') AS match_type, COUNT(*) AS rows, COUNT(DISTINCT incident_id) AS incidents
                 FROM silver_oe417_locations GROUP BY ALL ORDER BY 1, 2""")
    names = con.execute("""SELECT COUNT(DISTINCT (incident_id, token_position)),
                                  COUNT(DISTINCT (incident_id, token_position)) FILTER (WHERE fips_code IS NOT NULL)
                           FROM silver_oe417_locations WHERE location_level = 'county'""").fetchall()[0]
    rule("county names listed -> matched to an EAGLE-I FIPS (D34)", names[0], names[1])
    print("\nUnmatched county names (top 8):")
    show(con, """SELECT state_abbr, county_name_raw, COUNT(*) AS n FROM silver_oe417_locations
                 WHERE match_type = 'unmatched' GROUP BY ALL ORDER BY 3 DESC LIMIT 8""")
    print("\nsilver_oe417: location and time conversion (D24):")
    show(con, """SELECT COUNT(*) AS incidents,
                        COUNT(*) FILTER (WHERE primary_state IS NULL) AS no_state,
                        COUNT(*) FILTER (WHERE county_count > 0) AS with_counties,
                        COUNT(*) FILTER (WHERE begin_utc IS NULL) AS begin_utc_null,
                        COUNT(*) FILTER (WHERE begin_local IS NOT NULL AND primary_state IS NOT NULL
                            AND begin_utc IS NULL) AS conversion_failed
                 FROM silver_oe417""")
    print("\nOffset applied (begin_utc - begin_local, hours):")
    show(con, """SELECT CAST(epoch(begin_utc - begin_local) / 3600 AS INT) AS offset_hours, COUNT(*) AS incidents
                 FROM silver_oe417 WHERE begin_utc IS NOT NULL GROUP BY 1 ORDER BY 1""")
    print("\nEvent categories (D24):")
    show(con, "SELECT event_category, COUNT(*) AS incidents FROM silver_oe417 GROUP BY 1 ORDER BY 2 DESC")
    check("every OE-417 event type maps to a category", one(con, "SELECT COUNT(*) FROM silver_oe417 WHERE event_category = "
                                                                 "'unmapped'") == 0)
    check("silver_oe417 has one row per incident", one(con, "SELECT COUNT(*) - COUNT(DISTINCT incident_id) FROM silver_oe417") == 0)
    check("OE-417 incidents 2022 = 390, 2023 = 348", con.execute(
        "SELECT report_year, COUNT(*) FROM silver_oe417 GROUP BY 1 ORDER BY 1").fetchall() == [(2022, 390), (2023, 348)])


# -----------------------------------------------------------------------------

READINGS_SQL = """
    SELECT LPAD(TRIM(fips_code), 5, '0') AS fips_code, CAST(run_start_time AS TIMESTAMP) AS reading_time,
           TRY_CAST(customers_out AS BIGINT) AS customers_out FROM bronze_eaglei_2022
    UNION ALL
    SELECT LPAD(TRIM(fips_code), 5, '0'), CAST(run_start_time AS TIMESTAMP), TRY_CAST("sum" AS BIGINT) FROM bronze_eaglei_2023
    UNION ALL
    SELECT LPAD(TRIM(fips_code), 5, '0'), CAST(run_start_time AS TIMESTAMP), TRY_CAST(customers_out AS BIGINT) FROM bronze_eaglei_2024
"""


def iterate_floors(con) -> dict[str, int]:
    """The D35/D36 rule as a literal loop: floor every county below its peak, rescale the rest, repeat.

    D36: a peak above 1.25x the D13 denominator gives no floor.
    """
    rows = con.execute(f"""
        SELECT r.state_abbr, u.fips_code, u.customers AS d13, COALESCE(p.peak, 0) AS peak, e.customers AS eia
        FROM dim_d13 u
        JOIN bronze_state_regions r ON r.state_fips = LEFT(u.fips_code, 2)
        JOIN silver_eia_state_customers e ON e.state_abbr = r.state_abbr AND e.data_year = 2024
        JOIN dim_d35 c USING (fips_code)
        LEFT JOIN (SELECT fips_code, MAX(customers_out) AS peak FROM ({READINGS_SQL}) GROUP BY 1) p USING (fips_code)
        WHERE c.state_calibration_factor > 1 AND u.customers IS NOT NULL
    """).fetchall()
    states: dict[str, list] = {}
    for st, f, d, pk, eia in rows:
        floor = 0 if pk > 1.25 * d else pk  # D36
        states.setdefault(st, []).append((f, d, floor, eia))
    out, rounds = {}, {}
    for st, counties in states.items():
        eia = counties[0][3]
        floored: set[str] = set()
        for n in range(1, len(counties) + 2):  # noqa: B007 (n is the number of rounds, read after the loop)
            rest = [(f, d) for f, d, pk, _ in counties if f not in floored]
            k = (eia - sum(pk for f, d, pk, _ in counties if f in floored)) / sum(d for _, d in rest)
            below = {f for f, d, pk, _ in counties if f not in floored and k * d < pk}
            if not below:
                break
            floored |= below
        rounds[st] = n
        for f, d, pk, _ in counties:
            out[f] = pk if f in floored else round(k * d)
    print("  iteration rounds per state:", rounds)
    return out


def calibration_effect(con) -> None:
    print("\n=== D21 / D35 calibration: denominators ===")
    for mode in ("d13", "d21", "d35"):
        silver.build_dim(con, mode=mode)
        con.execute(f"CREATE OR REPLACE TABLE dim_{mode} AS SELECT * FROM dim_county_customers")
    show(con, """SELECT r.state_abbr, COUNT(*) AS counties, ANY_VALUE(c.state_calibration_factor) AS state_factor,
                        COUNT_IF(c.peak_floor_applied) AS floored,
                        SUM(u.customers) AS d13, SUM(m.customers) AS d21, SUM(c.customers) AS d35, e.customers AS eia_2024
                 FROM dim_d35 c JOIN dim_d13 u USING (fips_code) JOIN dim_d21 m USING (fips_code)
                 JOIN bronze_state_regions r ON r.state_fips = LEFT(c.fips_code, 2)
                 LEFT JOIN silver_eia_state_customers e ON e.state_abbr = r.state_abbr AND e.data_year = 2024
                 WHERE c.state_calibration_factor > 1 GROUP BY r.state_abbr, e.customers ORDER BY 1""")
    check("5 states calibrated, 246 counties", con.execute(
        "SELECT COUNT(DISTINCT LEFT(fips_code, 2)), COUNT(*) FROM dim_d35 WHERE state_calibration_factor > 1").fetchall() == [(5, 246)])
    check("each calibrated state total equals EIA within 10 customers (rounding)", one(con, """
        SELECT COUNT(*) FROM (SELECT r.state_abbr, SUM(d.customers) s, ANY_VALUE(e.customers) e
            FROM dim_d35 d JOIN bronze_state_regions r ON r.state_fips = LEFT(d.fips_code, 2)
            JOIN silver_eia_state_customers e ON e.state_abbr = r.state_abbr AND e.data_year = 2024
            WHERE d.state_calibration_factor > 1 GROUP BY 1) WHERE ABS(s - e) > 10""") == 0)

    looped = iterate_floors(con)
    sql = dict(con.execute("SELECT fips_code, customers FROM dim_d35 WHERE state_calibration_factor > 1").fetchall())
    diffs = [f for f in looped if abs(looped[f] - sql[f]) > 1]
    check(f"SQL result equals the literal iteration for all {len(looped)} counties ({len(diffs)} differ)", not diffs)

    con.execute(f"""
        CREATE OR REPLACE TABLE floor_peaks AS
        WITH r AS (
            SELECT x.*, LAG(customers_out) OVER w AS prev_out, LEAD(customers_out) OVER w AS next_out,
                   LAG(reading_time) OVER w AS prev_time, LEAD(reading_time) OVER w AS next_time
            FROM ({READINGS_SQL}) x
            WHERE fips_code IN (SELECT fips_code FROM dim_d35 WHERE peak_floor_applied)
            WINDOW w AS (PARTITION BY fips_code ORDER BY reading_time)
        )
        SELECT fips_code, arg_max(reading_time, customers_out) AS peak_time, MAX(customers_out) AS peak,
               arg_max(CASE WHEN prev_time = reading_time - INTERVAL 15 MINUTE THEN prev_out ELSE 0 END, customers_out) AS prev_out,
               arg_max(CASE WHEN next_time = reading_time + INTERVAL 15 MINUTE THEN next_out ELSE 0 END, customers_out) AS next_out
        FROM r GROUP BY 1
    """)
    con.execute(f"""
        CREATE OR REPLACE TABLE floor_sustained AS
        SELECT x.fips_code, COUNT(*) AS readings_above_half_peak
        FROM ({READINGS_SQL}) x JOIN floor_peaks p USING (fips_code)
        WHERE x.customers_out >= 0.5 * p.peak GROUP BY 1
    """)
    print("\nCounties whose peak is above 1.25x the D13 denominator, so no floor applies (D36):")
    show(con, """
        SELECT c.fips_code, r.state_abbr AS st, u.customers AS d13, m.customers AS d21_only, c.customers AS d36,
               c.customers < 1000 AS below_d11_cutoff
        FROM dim_d35 c JOIN dim_d13 u USING (fips_code) JOIN dim_d21 m USING (fips_code)
        JOIN bronze_state_regions r ON r.state_fips = LEFT(c.fips_code, 2)
        WHERE c.peak_floor_skipped ORDER BY 1
    """)
    check("D36 skips the floor only for Harding SD (46063)", con.execute(
        "SELECT fips_code FROM dim_d35 WHERE peak_floor_skipped").fetchall() == [("46063",)])
    print("\nCounties held at their peak (D35):")
    show(con, """
        SELECT c.fips_code, n.county, r.state_abbr AS st, u.customers AS d13, m.customers AS d21_only, c.customers AS d35,
               p.peak, strftime(p.peak_time, '%Y-%m-%d %H:%M') AS peak_utc, ROUND(p.peak / u.customers, 2) AS peak_vs_d13,
               p.prev_out, p.next_out, s.readings_above_half_peak AS sustained,
               CASE WHEN p.peak > u.customers THEN 'peak above uncalibrated denominator; ' ELSE '' END
               || CASE WHEN p.peak > 2 * GREATEST(p.prev_out, p.next_out) THEN 'isolated spike' ELSE '' END AS flag
        FROM dim_d35 c JOIN dim_d13 u USING (fips_code) JOIN dim_d21 m USING (fips_code)
        JOIN floor_peaks p USING (fips_code) JOIN floor_sustained s USING (fips_code)
        JOIN bronze_state_regions r ON r.state_fips = LEFT(c.fips_code, 2)
        LEFT JOIN (SELECT DISTINCT fips_code, county FROM bronze_eaglei_2024) n USING (fips_code)
        WHERE c.peak_floor_applied ORDER BY r.state_abbr, p.peak DESC
    """)
    con.execute("CREATE OR REPLACE TABLE dim_county_customers AS SELECT * FROM dim_d35")


def gold_effect(con) -> None:
    print("\n=== Silver outages (all years, D35) ===")
    silver.bronze(con, month_filter=None)
    con.execute("CREATE OR REPLACE TABLE dim_county_customers AS SELECT * FROM dim_d35")
    for name, _, sql in silver.SILVER_STEPS:
        con.execute(f"CREATE OR REPLACE TABLE {name} AS {sql}")
    for name, _, _ in silver.SILVER_STEPS[:-1]:
        con.execute(f"DROP TABLE {name}")
    show(con, "SELECT year, COUNT(*) AS rows, COUNT(*) FILTER (WHERE exceeds_customers) AS exceeds FROM silver_outages GROUP BY 1 "
              "ORDER BY 1")

    print("\n=== Gold events for D13, D21 and D35 denominators ===")
    for i, mode in enumerate(("d13", "d21", "d35")):
        con.execute(f"CREATE OR REPLACE TABLE dim_county_customers AS SELECT * FROM dim_{mode}")
        gold.build_gold(con, skip=("gold_collection_runs",) if i else ())
        for t in ("gold_outage_events", "gold_event_thresholds", "gold_feed_dropouts"):
            con.execute(f"CREATE OR REPLACE TABLE {t}_{mode} AS SELECT * FROM {t}")

    states = ", ".join(f"'{s}'" for s in CALIBRATED_STATES)
    print("\nPer calibrated state (events, overcount rows in Silver, customer-hours in M):")
    show(con, f"""
        WITH st AS (SELECT state_fips, state_abbr FROM bronze_state_regions WHERE state_abbr IN ({states})),
        ev AS (
            SELECT LEFT(fips_code, 2) sf, 'd13' m, COUNT(*) n, SUM(customer_hours_lost) ch FROM gold_outage_events_d13 GROUP BY 1
            UNION ALL SELECT LEFT(fips_code, 2), 'd21', COUNT(*), SUM(customer_hours_lost) FROM gold_outage_events_d21 GROUP BY 1
            UNION ALL SELECT LEFT(fips_code, 2), 'd35', COUNT(*), SUM(customer_hours_lost) FROM gold_outage_events_d35 GROUP BY 1
        ),
        ex AS (
            SELECT LEFT(s.fips_code, 2) sf,
                   COUNT(*) FILTER (WHERE s.customers_out > a.customers) ex_d13,
                   COUNT(*) FILTER (WHERE s.customers_out > b.customers) ex_d21,
                   COUNT(*) FILTER (WHERE s.customers_out > c.customers) ex_d35
            FROM silver_outages s JOIN dim_d13 a USING (fips_code) JOIN dim_d21 b USING (fips_code) JOIN dim_d35 c USING (fips_code)
            WHERE LEFT(s.fips_code, 2) IN (SELECT state_fips FROM st) GROUP BY 1
        )
        SELECT st.state_abbr,
               MAX(n) FILTER (WHERE m = 'd13') AS events_d13, MAX(n) FILTER (WHERE m = 'd21') AS events_d21,
               MAX(n) FILTER (WHERE m = 'd35') AS events_d35,
               ANY_VALUE(ex.ex_d13) AS overcount_d13, ANY_VALUE(ex.ex_d21) AS overcount_d21, ANY_VALUE(ex.ex_d35) AS overcount_d35,
               ROUND(MAX(ch) FILTER (WHERE m = 'd13') / 1e6, 2) AS ch_d13, ROUND(MAX(ch) FILTER (WHERE m = 'd21') / 1e6, 2) AS ch_d21,
               ROUND(MAX(ch) FILTER (WHERE m = 'd35') / 1e6, 2) AS ch_d35
        FROM st JOIN ev ON ev.sf = st.state_fips JOIN ex ON ex.sf = st.state_fips
        GROUP BY st.state_abbr ORDER BY 1
    """)
    print("\nNational events per year:")
    show(con, """SELECT event_year, COUNT(*) FILTER (WHERE m = 'd13') AS d13, COUNT(*) FILTER (WHERE m = 'd21') AS d21,
                        COUNT(*) FILTER (WHERE m = 'd35') AS d35
                 FROM (SELECT event_year, 'd13' m FROM gold_outage_events_d13 UNION ALL SELECT event_year, 'd21' FROM gold_outage_events_d21
                       UNION ALL SELECT event_year, 'd35' FROM gold_outage_events_d35) GROUP BY 1 ORDER BY 1""")
    print("dropouts d13 / d21 / d35:", [one(con, f"SELECT COUNT(*) FROM gold_feed_dropouts_{m}") for m in ("d13", "d21", "d35")])

    print("\nTop 10 by customer-hours, D13 (uncalibrated) vs D21 vs D35, matched by county and the D13 event's peak:")
    top = con.execute("""
        WITH b AS (SELECT *, ROW_NUMBER() OVER (ORDER BY customer_hours_lost DESC) rk FROM gold_outage_events_d13 QUALIFY rk <= 10),
        peaks AS (SELECT b.rk, b.event_id, b.fips_code, b.county, b.state_abbr, b.customer_hours_lost,
                         arg_max(s.reading_time, s.customers_out) AS peak_time
                  FROM b JOIN silver_outages s ON s.fips_code = b.fips_code AND s.reading_time >= b.event_start
                      AND s.reading_time < b.event_end
                  GROUP BY ALL),
        m AS (SELECT *, ROW_NUMBER() OVER (ORDER BY customer_hours_lost DESC) rk FROM gold_outage_events_d21),
        a AS (SELECT *, ROW_NUMBER() OVER (ORDER BY customer_hours_lost DESC) rk FROM gold_outage_events_d35)
        SELECT p.rk AS rank_d13, p.county, p.state_abbr AS st, ROUND(p.customer_hours_lost) AS ch_d13,
               m.rk AS rank_d21, ROUND(m.customer_hours_lost) AS ch_d21,
               a.rk AS rank_d35, a.event_id AS id_d35, ROUND(a.customer_hours_lost) AS ch_d35
        FROM peaks p
        LEFT JOIN m ON m.fips_code = p.fips_code AND p.peak_time >= m.event_start AND p.peak_time < m.event_end
        LEFT JOIN a ON a.fips_code = p.fips_code AND p.peak_time >= a.event_start AND p.peak_time < a.event_end
        ORDER BY 1
    """).fetchdf()
    print(top.to_string(index=False))
    check("D35 top 10 has the same storms as the uncalibrated top 10", bool((top.rank_d35 <= 10).all()))
    print(f"  D35 vs uncalibrated: same order {bool((top.rank_d35 == top.rank_d13).all())}, "
          f"same customer-hours {bool((top.ch_d35 == top.ch_d13).all())}")

    con.execute("CREATE OR REPLACE TABLE dim_county_customers AS SELECT * FROM dim_d35")
    for t in ("gold_outage_events", "gold_event_thresholds", "gold_feed_dropouts"):
        con.execute(f"CREATE OR REPLACE TABLE {t} AS SELECT * FROM {t}_d35")
    print("\nExpected values for run_databricks.py (D35):")
    show(con, """SELECT 'gold_outage_events' t, COUNT(*) n FROM gold_outage_events
                 UNION ALL SELECT 'gold_feed_dropouts', COUNT(*) FROM gold_feed_dropouts""")
    show(con, "SELECT event_year, COUNT(*) FROM gold_outage_events GROUP BY 1 ORDER BY 1")
    show(con, "SELECT dropout_year, COUNT(*) FROM gold_feed_dropouts GROUP BY 1 ORDER BY 1")
    show(con, """SELECT event_id, CAST(ROUND(customer_hours_lost) AS BIGINT) ch FROM gold_outage_events
                 ORDER BY customer_hours_lost DESC LIMIT 10""")
    show(con, "SELECT COUNT_IF(peak_floor_applied) AS floored FROM dim_county_customers")

    print("\n=== Gold coverage (D22) ===")
    run_file(con, SQL / "03_gold_coverage.sql")
    show(con, """SELECT state_abbr, eaglei_counties, total_counties, ROUND(customer_coverage, 3) AS coverage,
                        ranking_eligible, ROUND(calibration_factor, 3) AS factor
                 FROM gold_state_coverage
                 WHERE customer_coverage < 0.95 OR calibration_factor > 1
                 ORDER BY customer_coverage""")
    check("53 states and territories in gold_state_coverage", one(con, "SELECT COUNT(*) FROM gold_state_coverage") == 53)
    print("  footnoted (below 70%):", con.execute("SELECT state_abbr FROM gold_state_coverage WHERE NOT ranking_eligible").fetchall())


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-gold", action="store_true", help="only the source Silver tables")
    args = parser.parse_args()

    con = duckdb.connect()
    con.execute("SET TimeZone = 'UTC'")
    print("Bronze views (local files) ...")
    silver.bronze(con, month_filter=None)
    silver.build_dim(con)  # dim needed for the EAGLE-I county checks below

    print("\n02_silver_sources.sql:")
    run_file(con, SQL / "02_silver_sources.sql")
    report_eia(con)
    report_noaa(con)
    report_oe417(con)
    calibration_effect(con)
    if not args.skip_gold:
        gold_effect(con)

    print("\n" + ("ALL CHECKS PASSED" if not FAILURES else f"FAILED: {FAILURES}"))
    if FAILURES:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
