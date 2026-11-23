"""Test the analysis Gold tables in DuckDB: storm match, reliability rankings, OE-417 check.

Builds the whole pipeline from the local raw files (Bronze views, 02_silver_sources.sql, the
calibrated denominators, silver_outages, 03_gold_events.sql, 03_gold_coverage.sql), then runs
03_gold_storm_match.sql, 03_gold_reliability.sql and 03_gold_oe417_check.sql exactly as written
(translated by scripts/sql_dialect.py), prints the reports and checks, and the expected values
for scripts/run_databricks.py.

Raw files are only read. Nothing is written.

Usage:
    uv run python scripts/test_gold_analysis_duckdb.py
"""

from __future__ import annotations

import time
from pathlib import Path

import duckdb

import sql_dialect
import test_gold_events_duckdb as gold
import test_silver_duckdb as silver

REPO_ROOT = Path(__file__).resolve().parent.parent
SQL = REPO_ROOT / "sql" / "databricks"
FAILURES: list[str] = []


def show(con, sql: str) -> None:
    print(con.execute(sql).fetchdf().to_string(index=False))


def one(con, sql: str):
    return con.execute(sql).fetchall()[0][0]


def check(label: str, ok: bool) -> None:
    print(f"  [{'ok' if ok else 'FAIL'}] {label}")
    if not ok:
        FAILURES.append(label)


def run_file(con, name: str) -> None:
    for table, query in sql_dialect.table_statements(SQL / name):
        started = time.time()
        con.execute(f"CREATE OR REPLACE TABLE {table} AS {query}")
        print(f"  {table:<34} {one(con, f'SELECT COUNT(*) FROM {table}'):>10,} rows  {time.time() - started:5.1f}s")


def build(con) -> None:
    print("Building the pipeline in DuckDB ...", flush=True)
    silver.bronze(con, month_filter=None)
    silver.build_dim(con)
    run_file(con, "02_silver_sources.sql")
    for name, _, sql in silver.SILVER_STEPS:
        con.execute(f"CREATE OR REPLACE TABLE {name} AS {sql}")
    for name, _, _ in silver.SILVER_STEPS[:-1]:
        con.execute(f"DROP TABLE {name}")
    gold.build_gold(con)
    run_file(con, "03_gold_coverage.sql")
    print("\nAnalysis Gold tables:")
    for name in ("03_gold_storm_match.sql", "03_gold_reliability.sql", "03_gold_oe417_check.sql"):
        run_file(con, name)


def report_storm_match(con) -> None:
    print("\n=== Storm match (D37) ===")
    print("Matched share per year:")
    show(con, """SELECT event_year, COUNT(*) AS events, COUNT_IF(storm_type <> 'unmatched') AS matched,
                        ROUND(COUNT_IF(storm_type <> 'unmatched') / COUNT(*), 3) AS share_of_events,
                        ROUND(SUM(customer_hours_lost) / 1e6, 1) AS customer_hours_m,
                        ROUND(SUM(CASE WHEN storm_type <> 'unmatched'
                            THEN customer_hours_lost END) / SUM(customer_hours_lost), 3) AS share_of_customer_hours
                 FROM gold_event_storm_match GROUP BY 1 ORDER BY 1""")
    print("\nBy matched storm type (all years):")
    show(con, """SELECT storm_type, COUNT(*) AS events, ROUND(SUM(customer_hours_lost) / 1e6, 1) AS customer_hours_m,
                        ROUND(SUM(customer_hours_lost) / (SELECT SUM(customer_hours_lost)
                            FROM gold_event_storm_match), 3) AS share_of_customer_hours,
                        ROUND(MEDIAN(duration_hours), 1) AS median_outage_hours
                 FROM gold_event_storm_match GROUP BY 1 ORDER BY customer_hours_m DESC LIMIT 20""")
    print("\nLargest-overlap type vs most severe overlapping type (matched events):")
    show(con, """SELECT COUNT_IF(storm_type <> 'unmatched') AS matched,
                        COUNT_IF(storm_type <> 'unmatched' AND storm_type <> most_severe_storm_type) AS best_is_not_most_severe,
                        ROUND(SUM(CASE WHEN storm_type <> most_severe_storm_type
                            THEN customer_hours_lost END) / 1e6, 1) AS their_customer_hours_m
                 FROM gold_event_storm_match""")
    print("\nAttribution rule (D41):")
    show(con, """SELECT COALESCE(attribution_rule, 'unmatched') AS rule, COUNT(*) AS events,
                        ROUND(SUM(customer_hours_lost) / 1e6, 1) AS customer_hours_m
                 FROM gold_event_storm_match GROUP BY 1 ORDER BY 2 DESC""")
    (_, query), = sql_dialect.table_statements(SQL / "03_gold_storm_match.sql")
    line = "s.end_utc + INTERVAL 1 HOUR        AS window_end"
    con.execute("CREATE OR REPLACE TABLE storm_match_no_d42 AS " + query.replace(line, "s.end_utc AS window_end"))
    print("\nD42 effect (window closes at NOAA end vs 1 hour later):")
    show(con, """SELECT a.event_year, COUNT_IF(b.storm_type <> 'unmatched') AS without_d42,
                        COUNT_IF(a.storm_type <> 'unmatched') AS with_d42,
                        COUNT_IF(a.storm_type <> 'unmatched') - COUNT_IF(b.storm_type <> 'unmatched') AS added
                 FROM gold_event_storm_match a JOIN storm_match_no_d42 b USING (event_id) GROUP BY 1 ORDER BY 1""")
    for name in ("storm_match_no_d42", "gold_event_storm_match"):
        print(f"  top-100 matched ({name}):",
              one(con, f"SELECT COUNT_IF(storm_type <> 'unmatched') FROM (SELECT * FROM {name} ORDER BY customer_hours_lost DESC "
                       "LIMIT 100)"))
    print("\nTop 10 events and their match:")
    show(con, """SELECT ROW_NUMBER() OVER (ORDER BY customer_hours_lost DESC) AS rk, event_id, county, state_abbr AS st,
                        strftime(event_start, '%Y-%m-%d') AS start_utc, ROUND(customer_hours_lost / 1e6, 1) AS ch_m,
                        storm_type, most_severe_storm_type, ROUND(overlap_hours) AS overlap_h, candidate_storms
                 FROM gold_event_storm_match ORDER BY customer_hours_lost DESC LIMIT 10""")
    check("Helene top-10 events attributed to Tropical Storm, not Flood (D41)", con.execute(
        """SELECT storm_type FROM (SELECT * FROM gold_event_storm_match ORDER BY customer_hours_lost DESC LIMIT 10)
           WHERE fips_code IN ('45045', '45083', '37021') ORDER BY fips_code""").fetchall() == [("Tropical Storm",)] * 3)
    check("one storm-match row per outage event", one(con, "SELECT COUNT(*) FROM "
                                                           "gold_event_storm_match") == one(con, "SELECT COUNT(*) FROM gold_outage_events")
          and one(con, "SELECT COUNT(*) - COUNT(DISTINCT event_id) FROM gold_event_storm_match") == 0)
    check("no non-causal storm type is ever matched", one(con, """SELECT COUNT(*) FROM gold_event_storm_match m
          JOIN bronze_storm_event_severity s ON s.event_type = m.storm_type WHERE s.can_cause_outage <> 'Y'""") == 0)
    check("every NOAA event type has a severity entry", one(con, """SELECT COUNT(DISTINCT event_type) FROM silver_storm_event_details
          WHERE event_type NOT IN (SELECT event_type FROM bronze_storm_event_severity)""") == 0)


def report_q3(con) -> None:
    print("\n=== Q3: why top-100 events miss NOAA ===")
    con.execute("""CREATE OR REPLACE TABLE top100 AS
        SELECT *, ROW_NUMBER() OVER (ORDER BY customer_hours_lost DESC) AS rk FROM gold_event_storm_match QUALIFY rk <= 100""")
    old = one(con, """SELECT COUNT(DISTINCT t.event_id) FROM top100 t JOIN silver_storm_events s ON s.fips_code = t.fips_code
                      AND s.begin_utc <= t.event_start + INTERVAL 2 HOUR AND s.end_utc >= t.event_start - INTERVAL 24 HOUR""")
    any_type = one(con, """SELECT COUNT(DISTINCT t.event_id) FROM top100 t JOIN silver_storm_events s ON s.fips_code = t.fips_code
                           AND s.begin_utc - INTERVAL 12 HOUR < t.event_end AND s.end_utc > t.event_start""")
    new = one(con, "SELECT COUNT(*) FROM top100 WHERE storm_type <> 'unmatched'")
    print(f"  profile rule (any NOAA event active 24 h before to 2 h after the start): {old} of 100")
    print(f"  D37 window, any type:                                                  {any_type} of 100")
    print(f"  D37/D42 window, outage-causing types only (gold_event_storm_match):    {new} of 100")
    print("\nUnmatched top-100 events by cause:")
    show(con, """
        WITH um AS (SELECT * FROM top100 WHERE storm_type = 'unmatched'),
        c AS (
            SELECT um.rk, um.event_id, um.county, um.state_abbr AS st, strftime(um.event_start, '%Y-%m-%d') AS start_utc,
                   ROUND(um.customer_hours_lost / 1e6, 2) AS ch_m,
                   EXISTS (SELECT 1 FROM silver_storm_events s WHERE s.fips_code = um.fips_code
                           AND s.begin_utc - INTERVAL 12 HOUR < um.event_end AND s.end_utc > um.event_start) AS non_causal_overlap,
                   (SELECT MIN(ROUND(epoch(um.event_start - s.end_utc) / 3600, 1)) FROM silver_storm_events s
                     WHERE s.fips_code = um.fips_code AND s.end_utc <= um.event_start
                         AND s.end_utc > um.event_start - INTERVAL 3 DAY) AS hours_after_storm_end,
                   (SELECT MIN(ROUND(epoch(s.begin_utc - um.event_end) / 3600, 1)) FROM silver_storm_events s
                     WHERE s.fips_code = um.fips_code AND s.begin_utc - INTERVAL 12 HOUR >= um.event_end
                         AND s.begin_utc < um.event_end + INTERVAL 3 DAY) AS hours_before_storm_begin,
                   EXISTS (SELECT 1 FROM silver_storm_events s WHERE s.fips_code = um.fips_code
                           AND s.begin_utc BETWEEN um.event_start - INTERVAL 7 DAY AND um.event_end + INTERVAL 7 DAY) AS storm_within_7_days
            FROM um
        )
        SELECT rk, event_id, county, st, start_utc, ch_m,
               CASE
                   WHEN non_causal_overlap THEN 'labels: only non-causal types overlap'
                   WHEN hours_after_storm_end IS NOT NULL
                       THEN 'time window: storm ended ' || CAST(hours_after_storm_end AS VARCHAR) || ' h before the outage'
                   WHEN hours_before_storm_begin IS NOT NULL THEN 'time window: storm began after the outage ended'
                   WHEN storm_within_7_days THEN 'time window: storm within 7 days only'
                   WHEN st = 'PR' THEN 'geography: PREPA region, NOAA records other municipios'
                   ELSE 'coverage: no NOAA record in this county'
               END AS cause
        FROM c ORDER BY rk
    """)


def report_reliability(con) -> None:
    print("\n=== State reliability (D38, D43: 50 states and DC) ===")
    show(con, """SELECT year, national_rank AS rk, state_abbr AS st, ROUND(outage_hours_per_1000_customers) AS hours_per_1000,
                        ROUND(customer_hours_lost / 1e6, 1) AS ch_m, ROUND(customer_coverage, 3) AS coverage
                 FROM gold_state_reliability WHERE national_rank <= 5 ORDER BY year, rk""")
    print("\nTerritories (D43, unranked):")
    show(con, """SELECT year, state_abbr AS st, ROUND(outage_hours_per_1000_customers) AS hours_per_1000,
                        ROUND(customer_hours_lost / 1e6, 1) AS ch_m, reporting_units, geography_note
                 FROM gold_territory_reliability ORDER BY st, year""")
    check("state ranking holds the 50 states and DC only (153 rows)",
          one(con, "SELECT COUNT(*) FROM gold_state_reliability") == 153
          and one(con, "SELECT COUNT(*) FROM gold_state_reliability WHERE state_abbr IN ('PR', 'VI')") == 0)
    check("territories table holds PR and VI for 3 years", con.execute(
        "SELECT state_abbr, COUNT(*) FROM gold_territory_reliability GROUP BY 1 ORDER BY 1").fetchall() == [("PR", 3), ("VI", 3)])
    print("\nPer region, 2024 (region rank 1):")
    show(con, """SELECT year, census_region, state_abbr AS st, ROUND(outage_hours_per_1000_customers) AS hours_per_1000
                 FROM gold_state_reliability WHERE region_rank = 1 ORDER BY year, census_region""")
    check("state ranks run 1..n per year without gaps at the top",
          con.execute("SELECT year, MIN(national_rank) FROM gold_state_reliability GROUP BY 1 ORDER BY "
                      "1").fetchall() == [(2022, 1), (2023, 1), (2024, 1)])
    print("\n=== County reliability (D38, D44: 50 states and DC), top 5 per year ===")
    show(con, """SELECT year, national_rank AS rk, fips_code, county, state_abbr AS st, customers,
                        ROUND(outage_hours_per_1000_customers) AS hours_per_1000
                 FROM gold_county_reliability WHERE national_rank <= 5 ORDER BY year, rk""")
    print("\nTerritory reporting units (D44, unranked), 2022:")
    show(con, """SELECT year, reporting_unit, state_abbr AS st, customers, ROUND(outage_hours_per_1000_customers) AS hours_per_1000,
                        geography_note
                 FROM gold_territory_unit_reliability WHERE year = 2022 ORDER BY hours_per_1000 DESC""")
    check("county ranking holds the 50 states and DC only; 30 territory unit rows moved (D44)",
          one(con, "SELECT COUNT(*) FROM gold_county_reliability WHERE state_abbr IN ('PR', 'VI')") == 0
          and one(con, "SELECT COUNT(*) FROM gold_territory_unit_reliability") == 30
          and one(con, "SELECT COUNT(*) FROM gold_county_reliability") + 30 == one(con, "SELECT COUNT(*) FROM gold_unit_reliability"))
    show(con, """SELECT year, COUNT(*) AS counties, COUNT_IF(ranking_eligible) AS ranked,
                        COUNT_IF(customers IS NULL) AS no_denominator, COUNT_IF(customers < 1000) AS under_1000
                 FROM gold_county_reliability GROUP BY 1 ORDER BY 1""")
    print("\nCounty ranking footnotes (D45, D46; plus D9 and D11):")
    show(con, "SELECT footnote_reason, COUNT(*) AS county_years FROM gold_county_ranking_footnotes GROUP BY 1 ORDER BY 2 DESC")
    show(con, """SELECT year, would_have_rank, county, state_abbr AS st, ROUND(outage_hours_per_1000_customers) AS hours_per_1000,
                        footnote_evidence FROM gold_county_ranking_footnotes
                 WHERE footnote_reason NOT LIKE '%D11%' AND footnote_reason NOT LIKE '%D9%' ORDER BY year, would_have_rank""")
    check("D45 footnotes Austin TX and Waller TX 2024 (ranks 7 and 8 without footnotes)", con.execute(
        """SELECT fips_code, would_have_rank FROM gold_county_ranking_footnotes
           WHERE year = 2024 AND footnote_reason LIKE '%D45%' AND fips_code IN ('48015', '48473') ORDER BY 1""").fetchall()
          == [("48015", 7), ("48473", 8)])
    check("D46 exclusions file is empty, so no reviewed exclusions apply",
          one(con, "SELECT COUNT(*) FROM gold_county_ranking_footnotes WHERE footnote_reason LIKE '%D46%'") == 0)
    check("Austin TX 2023 stays ranked #1", one(con, "SELECT national_rank FROM gold_county_reliability WHERE fips_code = '48015' AND "
                                                     "year = 2023") == 1)
    check("every unranked county-year is in the footnote list", one(con, "SELECT COUNT(*) FROM gold_county_reliability WHERE NOT "
                                                                         "ranking_eligible")
          == one(con, "SELECT COUNT(*) FROM gold_county_ranking_footnotes"))
    check("reporting-unit outage hours add up to Gold event customer-hours",
          abs(one(con, "SELECT SUM(customer_hours_lost) FROM gold_unit_reliability")
              - one(con, "SELECT SUM(customer_hours_lost) FROM gold_outage_events WHERE fips_code IN (SELECT fips_code FROM "
                         "dim_county_customers)")) < 1)

    print("\n=== Utility reliability (D39) ===")
    show(con, """SELECT data_year, size_band, COUNT(*) AS utilities, COUNT(rank_saidi_without_med) AS ranked_saidi_without_med
                 FROM gold_utility_reliability GROUP BY 1, 2 ORDER BY 1, 2""")
    print("\nEversource and National Grid companies:")
    show(con, """SELECT data_year, utility_name, state_abbr AS st, parent_company, size_band, customers,
                        saidi_without_med, rank_saidi_without_med AS rk_without, saidi_with_med, rank_saidi_with_med AS rk_with,
                        utilities_in_band AS band_size
                 FROM gold_utility_reliability WHERE is_eversource_or_national_grid ORDER BY utility_name, data_year""")
    check("only IEEE 1366 reporters are ranked",
          one(con, "SELECT COUNT(*) FROM gold_utility_reliability u JOIN silver_utility_reliability s USING (data_year, "
                   "utility_number, state_abbr) WHERE s.reporting_standard <> 'IEEE 1366'") == 0)
    check("other-standard utilities are listed separately (921 rows with 2025, D59)",
          one(con, "SELECT COUNT(*) FROM gold_utility_reliability_other") == 921)
    print("\nRows flagged as source errors (not ranked):")
    show(con, """SELECT data_year, utility_number, utility_name, customers, saidi_with_med, saidi_without_med, data_quality_flag,
                        rank_saidi_without_med FROM gold_utility_reliability WHERE data_quality_flag IS NOT NULL""")
    check("only NSTAR 2023 and utility 19162 in 2025 are flagged, and neither has a rank (D59)", con.execute(
        "SELECT data_year, utility_number, rank_saidi_without_med, rank_saidi_with_med FROM gold_utility_reliability WHERE "
        "data_quality_flag IS NOT NULL ORDER BY data_year"
    ).fetchall() == [(2023, "54913", None, None), (2025, "19162", None, None)])


def report_oe417(con) -> None:
    print("\n=== OE-417 vs EAGLE-I (D24, D40) ===")
    show(con, "SELECT match_status, COUNT(*) AS incidents FROM gold_oe417_check GROUP BY 1 ORDER BY 2 DESC")
    print("\nBy customers-affected band (checkable = has a time and a county):")
    show(con, """SELECT customers_band, COUNT(*) AS incidents, COUNT_IF(match_status IN ('matched', 'not matched')) AS checkable,
                        COUNT_IF(match_status = 'matched') AS matched,
                        ROUND(COUNT_IF(match_status = 'matched') / NULLIF(COUNT_IF(match_status IN ('matched', 'not matched')), 0),
                            3) AS agreement
                 FROM gold_oe417_check GROUP BY 1 ORDER BY 1""")
    print("\nBy cause category:")
    show(con, """SELECT event_category, COUNT(*) AS incidents, COUNT_IF(match_status IN ('matched', 'not matched')) AS checkable,
                        COUNT_IF(match_status = 'matched') AS matched,
                        ROUND(COUNT_IF(match_status = 'matched') / NULLIF(COUNT_IF(match_status IN ('matched', 'not matched')), 0),
                            3) AS agreement
                 FROM gold_oe417_check GROUP BY 1 ORDER BY 2 DESC""")
    print("\nMatched incidents with 1,000+ customers: OE-417 customers vs EAGLE-I summed county peaks:")
    show(con, """SELECT COUNT(*) AS incidents, ROUND(MEDIAN(eaglei_peak_customers_out / customers_affected), 2) AS median_ratio,
                        ROUND(MEDIAN(closest_start_offset_hours), 1) AS median_start_offset_h
                 FROM gold_oe417_check WHERE match_status = 'matched' AND customers_affected >= 1000""")
    check("one row per OE-417 incident", one(con, "SELECT COUNT(*) - COUNT(DISTINCT incident_id) FROM gold_oe417_check") == 0
          and one(con, "SELECT COUNT(*) FROM gold_oe417_check") == 738)


def expected(con) -> None:
    print("\n=== Expected values for run_databricks.py ===")
    show(con, """SELECT 'gold_event_storm_match' t, COUNT(*) n FROM gold_event_storm_match
                 UNION ALL SELECT 'gold_unit_reliability', COUNT(*) FROM gold_unit_reliability
                 UNION ALL SELECT 'gold_county_reliability', COUNT(*) FROM gold_county_reliability
                 UNION ALL SELECT 'gold_territory_unit_reliability', COUNT(*) FROM gold_territory_unit_reliability
                 UNION ALL SELECT 'gold_county_ranking_footnotes', COUNT(*) FROM gold_county_ranking_footnotes
                 UNION ALL SELECT 'gold_state_reliability', COUNT(*) FROM gold_state_reliability
                 UNION ALL SELECT 'gold_territory_reliability', COUNT(*) FROM gold_territory_reliability
                 UNION ALL SELECT 'gold_utility_reliability', COUNT(*) FROM gold_utility_reliability
                 UNION ALL SELECT 'gold_utility_reliability_other', COUNT(*) FROM gold_utility_reliability_other
                 UNION ALL SELECT 'gold_oe417_check', COUNT(*) FROM gold_oe417_check""")
    show(con, "SELECT CAST(event_year AS VARCHAR), CAST(COUNT_IF(storm_type <> 'unmatched') AS VARCHAR) FROM gold_event_storm_match "
              "GROUP BY 1 ORDER BY 1")
    show(con, "SELECT CAST(year AS VARCHAR), state_abbr FROM gold_state_reliability WHERE national_rank = 1 ORDER BY 1")
    show(con, "SELECT match_status, CAST(COUNT(*) AS VARCHAR) FROM gold_oe417_check GROUP BY 1 ORDER BY 1")
    show(con, "SELECT CAST(year AS VARCHAR), CAST(COUNT_IF(ranking_eligible) AS VARCHAR) FROM gold_county_reliability GROUP BY 1 "
              "ORDER BY 1")


def main() -> None:
    con = duckdb.connect()
    con.execute("SET TimeZone = 'UTC'")
    build(con)
    report_storm_match(con)
    report_q3(con)
    report_reliability(con)
    report_oe417(con)
    expected(con)
    print("\n" + ("ALL CHECKS PASSED" if not FAILURES else f"FAILED: {FAILURES}"))
    if FAILURES:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
