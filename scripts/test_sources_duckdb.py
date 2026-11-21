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
    sales_data = one(con, "SELECT COUNT(*) FROM bronze_eia861_sales WHERE sheet_name IN ('States','Territories') AND regexp_matches(col_01, '^[0-9]{4}$')")
    sales_acd = one(con, "SELECT COUNT(*) FROM bronze_eia861_sales WHERE sheet_name IN ('States','Territories') AND regexp_matches(col_01, '^[0-9]{4}$') AND TRIM(col_04) IN ('A','C','D')")
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
                   '(?i)(nstar|connecticut light|public service co of nh|massachusetts electric|nantucket electric|niagara mohawk|narragansett)')
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
          one(con, "SELECT COUNT(*) FROM (SELECT event_id, SUM(event_weight) s FROM silver_storm_events GROUP BY 1) WHERE ABS(s - 1) > 1e-9") == 0)
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
                        COUNT(*) FILTER (WHERE begin_local IS NOT NULL AND primary_state IS NOT NULL AND begin_utc IS NULL) AS conversion_failed
                 FROM silver_oe417""")
    print("\nOffset applied (begin_utc - begin_local, hours):")
    show(con, """SELECT CAST(epoch(begin_utc - begin_local) / 3600 AS INT) AS offset_hours, COUNT(*) AS incidents
                 FROM silver_oe417 WHERE begin_utc IS NOT NULL GROUP BY 1 ORDER BY 1""")
    print("\nEvent categories (D24):")
    show(con, "SELECT event_category, COUNT(*) AS incidents FROM silver_oe417 GROUP BY 1 ORDER BY 2 DESC")
    check("every OE-417 event type maps to a category", one(con, "SELECT COUNT(*) FROM silver_oe417 WHERE event_category = 'unmapped'") == 0)
    check("silver_oe417 has one row per incident", one(con, "SELECT COUNT(*) - COUNT(DISTINCT incident_id) FROM silver_oe417") == 0)
    check("OE-417 incidents 2022 = 390, 2023 = 348", con.execute(
        "SELECT report_year, COUNT(*) FROM silver_oe417 GROUP BY 1 ORDER BY 1").fetchall() == [(2022, 390), (2023, 348)])


# -----------------------------------------------------------------------------

def calibration_effect(con) -> None:
    print("\n=== D21 calibration: denominators ===")
    silver.build_dim(con, calibrated=False)
    con.execute("CREATE OR REPLACE TABLE dim_uncal AS SELECT * FROM dim_county_customers")
    silver.build_dim(con, calibrated=True)
    con.execute("CREATE OR REPLACE TABLE dim_cal AS SELECT * FROM dim_county_customers")
    show(con, """SELECT r.state_abbr, COUNT(*) AS counties, ANY_VALUE(c.calibration_factor) AS factor,
                        SUM(u.customers) AS before, SUM(c.customers) AS after, e.customers AS eia_2024
                 FROM dim_cal c JOIN dim_uncal u USING (fips_code)
                 JOIN bronze_state_regions r ON r.state_fips = LEFT(c.fips_code, 2)
                 LEFT JOIN silver_eia_state_customers e ON e.state_abbr = r.state_abbr AND e.data_year = 2024
                 WHERE c.calibration_factor > 1 GROUP BY r.state_abbr, e.customers ORDER BY factor DESC""")
    print("Suffolk MA:", con.execute("SELECT u.customers, c.customers FROM dim_cal c JOIN dim_uncal u USING (fips_code) WHERE fips_code = '25025'").fetchall())
    check("5 states calibrated, 246 counties", con.execute(
        "SELECT COUNT(DISTINCT LEFT(fips_code, 2)), COUNT(*) FROM dim_cal WHERE calibration_factor > 1").fetchall() == [(5, 246)])


def gold_effect(con) -> None:
    print("\n=== Silver outages (all years, calibrated) ===")
    silver.bronze(con, month_filter=None)
    for name, _, sql in silver.SILVER_STEPS:
        con.execute(f"CREATE OR REPLACE TABLE {name} AS {sql}")
    for name, _, _ in silver.SILVER_STEPS[:-1]:
        con.execute(f"DROP TABLE {name}")
    show(con, "SELECT year, COUNT(*) AS rows, COUNT(*) FILTER (WHERE exceeds_customers) AS exceeds FROM silver_outages GROUP BY 1 ORDER BY 1")

    print("\n=== Gold events: uncalibrated vs calibrated ===")
    con.execute("CREATE OR REPLACE TABLE dim_county_customers AS SELECT * FROM dim_uncal")
    gold.build_gold(con)
    for t in ("gold_outage_events", "gold_event_thresholds", "gold_feed_dropouts"):
        con.execute(f"CREATE OR REPLACE TABLE {t}_uncal AS SELECT * FROM {t}")
    con.execute("CREATE OR REPLACE TABLE dim_county_customers AS SELECT * FROM dim_cal")
    gold.build_gold(con, skip=("gold_collection_runs",))

    states = ", ".join(f"'{s}'" for s in CALIBRATED_STATES)
    print("\nPer calibrated state:")
    show(con, f"""
        WITH st AS (SELECT state_fips, state_abbr FROM bronze_state_regions WHERE state_abbr IN ({states})),
        ev AS (SELECT LEFT(fips_code, 2) sf, COUNT(*) n, SUM(customer_hours_lost) ch FROM gold_outage_events GROUP BY 1),
        evu AS (SELECT LEFT(fips_code, 2) sf, COUNT(*) n, SUM(customer_hours_lost) ch FROM gold_outage_events_uncal GROUP BY 1),
        th AS (SELECT LEFT(c.fips_code, 2) sf, COUNT(*) FILTER (WHERE c.event_threshold <> u.event_threshold) changed,
                      MEDIAN(u.event_threshold) FILTER (WHERE c.event_threshold <> u.event_threshold) med_before,
                      MEDIAN(c.event_threshold) FILTER (WHERE c.event_threshold <> u.event_threshold) med_after
               FROM gold_event_thresholds c JOIN gold_event_thresholds_uncal u USING (fips_code) GROUP BY 1),
        ex AS (SELECT LEFT(s.fips_code, 2) sf,
                      COUNT(*) FILTER (WHERE s.customers_out > u.customers) ex_before,
                      COUNT(*) FILTER (WHERE s.customers_out > c.customers) ex_after
               FROM silver_outages s JOIN dim_uncal u USING (fips_code) JOIN dim_cal c USING (fips_code)
               WHERE LEFT(s.fips_code, 2) IN (SELECT state_fips FROM st) GROUP BY 1)
        SELECT st.state_abbr, evu.n AS events_before, ev.n AS events_after,
               th.changed AS thresholds_changed, ROUND(th.med_before) AS median_threshold_before, ROUND(th.med_after) AS median_threshold_after,
               ex.ex_before AS exceeds_before, ex.ex_after AS exceeds_after,
               ROUND(evu.ch / 1e6, 2) AS cust_hours_m_before, ROUND(ev.ch / 1e6, 2) AS cust_hours_m_after
        FROM st JOIN ev ON ev.sf = st.state_fips JOIN evu ON evu.sf = st.state_fips
        JOIN th ON th.sf = st.state_fips JOIN ex ON ex.sf = st.state_fips ORDER BY 1
    """)
    print("\nNational, per year:")
    show(con, """SELECT a.event_year, b.n AS events_before, a.n AS events_after FROM
                 (SELECT event_year, COUNT(*) n FROM gold_outage_events GROUP BY 1) a
                 JOIN (SELECT event_year, COUNT(*) n FROM gold_outage_events_uncal GROUP BY 1) b USING (event_year) ORDER BY 1""")
    print("dropouts before / after:", one(con, "SELECT COUNT(*) FROM gold_feed_dropouts_uncal"), "/", one(con, "SELECT COUNT(*) FROM gold_feed_dropouts"))

    print("\nTop 10 by customer-hours: before vs after (matched by county and the before event's peak time):")
    top = con.execute("""
        WITH b AS (SELECT *, ROW_NUMBER() OVER (ORDER BY customer_hours_lost DESC) rk FROM gold_outage_events_uncal QUALIFY rk <= 10),
        peaks AS (SELECT b.rk, b.event_id, b.fips_code, b.county, b.state_abbr, b.customer_hours_lost,
                         arg_max(s.reading_time, s.customers_out) AS peak_time
                  FROM b JOIN silver_outages s ON s.fips_code = b.fips_code AND s.reading_time >= b.event_start AND s.reading_time < b.event_end
                  GROUP BY ALL),
        a AS (SELECT *, ROW_NUMBER() OVER (ORDER BY customer_hours_lost DESC) rk_after FROM gold_outage_events)
        SELECT p.rk AS rank_before, p.event_id AS id_before, p.county, p.state_abbr AS st, ROUND(p.customer_hours_lost) AS before,
               a.rk_after AS rank_after, a.event_id AS id_after, ROUND(a.customer_hours_lost) AS after
        FROM peaks p LEFT JOIN a ON a.fips_code = p.fips_code AND p.peak_time >= a.event_start AND p.peak_time < a.event_end
        ORDER BY 1
    """).fetchdf()
    print(top.to_string(index=False))
    same_storms = bool((top.rank_after <= 10).all())
    check("national top 10 contains the same 10 storms", same_storms)
    print(f"  same order: {bool((top.rank_after == top.rank_before).all())}; "
          f"customer-hours identical: {bool((top.before == top.after).all())}; "
          f"event ids identical: {bool((top.id_before == top.id_after).all())}")
    changed = top[(top.rank_after != top.rank_before) | (top.before != top.after)]
    if len(changed):
        print("  changed entries:")
        print(changed.to_string(index=False))

    print("\nExpected values for run_databricks.py:")
    show(con, """SELECT 'gold_outage_events' t, COUNT(*) n FROM gold_outage_events
                 UNION ALL SELECT 'gold_feed_dropouts', COUNT(*) FROM gold_feed_dropouts
                 UNION ALL SELECT 'gold_event_thresholds', COUNT(*) FROM gold_event_thresholds""")
    show(con, "SELECT event_year, COUNT(*) FROM gold_outage_events GROUP BY 1 ORDER BY 1")
    show(con, "SELECT dropout_year, COUNT(*) FROM gold_feed_dropouts GROUP BY 1 ORDER BY 1")
    show(con, """SELECT event_id, CAST(ROUND(customer_hours_lost) AS BIGINT) ch FROM gold_outage_events
                 ORDER BY customer_hours_lost DESC LIMIT 10""")

    print("\n=== Gold coverage (D22) ===")
    run_file(con, SQL / "03_gold_coverage.sql")
    show(con, """SELECT state_abbr, eaglei_counties, total_counties, ROUND(customer_coverage, 3) AS coverage,
                        ranking_eligible, ROUND(calibration_factor, 3) AS factor, coverage_note
                 FROM gold_state_coverage
                 WHERE customer_coverage < 0.95 OR coverage_note IS NOT NULL OR calibration_factor > 1
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
