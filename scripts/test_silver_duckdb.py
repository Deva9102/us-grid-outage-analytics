"""Test the Silver logic of sql/databricks/02_silver.sql locally in DuckDB.

Each step below has the same name as a CTE in 02_silver.sql and applies the same rule.
Dialect differences (Databricks -> DuckDB):
    read_files(... schema => all STRING)   -> read_csv(all_varchar = true)
    RLIKE '^...$'                          -> regexp_full_match
    try_to_timestamp(x, 'yyyy-MM-dd ...')  -> TRY_STRPTIME(x, '%Y-%m-%d ...')
    timestamp_seconds(FLOOR(unix_seconds(t) / 900) * 900) -> time_bucket(INTERVAL 15 MINUTE, t)
    COUNT_IF(x)                            -> COUNT(*) FILTER (WHERE x)

What runs:
    1. dim_county_customers on the full raw files (it is county-level, D13).
    2. silver_outages steps on one month of 2024 (--month, default 2024-07),
       printing row counts before and after each rule.
    3. A synthetic check of D7 (floor and dedupe), which real 2024 data does not exercise.
    4. D4 exceeds_customers recount on all three full years with the final denominators.

Raw files are only read. Nothing is written.

Usage:
    uv run python scripts/census_regions.py     # builds the region lookup first
    uv run python scripts/test_silver_duckdb.py [--month 2024-07 | --month all]
"""

from __future__ import annotations

import argparse
from pathlib import Path

import duckdb

import pipeline_config

REPO_ROOT = Path(__file__).resolve().parent.parent
RAW = REPO_ROOT / "data" / "raw"
REGIONS_CSV = REPO_ROOT / "data" / "reference" / "state_regions.csv"
YEARS = tuple(pipeline_config.load()["years"]["list"])


def bronze(con: duckdb.DuckDBPyConnection, month_filter: str | None) -> None:
    """Bronze views: all text columns, as in 01_bronze.sql."""
    for year in YEARS:
        path = (RAW / "eaglei" / str(year) / f"eaglei_outages_{year}.csv").as_posix()
        where = f"WHERE run_start_time LIKE '{month_filter}%'" if month_filter else ""
        con.execute(f"""
            CREATE OR REPLACE VIEW bronze_eaglei_{year} AS
            SELECT *, '{path}' AS source_file
            FROM read_csv('{path}', all_varchar = true) {where}
        """)
    mcc = (RAW / "eaglei" / "metadata" / "MCC.csv").as_posix()
    con.execute(f"CREATE OR REPLACE VIEW bronze_eaglei_mcc AS SELECT * FROM read_csv('{mcc}', all_varchar = true)")
    # The coverage metadata files (D67), read by 02_silver_sources.sql.
    for name, file in (("bronze_eaglei_coverage_history", "coverage_history.csv"), ("bronze_eaglei_dqi", "DQI.csv")):
        path = (RAW / "eaglei" / "metadata" / file).as_posix()
        con.execute(f"CREATE OR REPLACE VIEW {name} AS SELECT *, '{path}' AS source_file "
                    f"FROM read_csv('{path}', all_varchar = true)")
    con.execute(f"""
        CREATE OR REPLACE VIEW bronze_state_regions AS
        SELECT * FROM read_csv('{REGIONS_CSV.as_posix()}', all_varchar = true)
    """)
    bronze_sources(con)


def bronze_sources(con: duckdb.DuckDBPyConnection) -> None:
    """Bronze views for the added sources, as in 01_bronze_sources.sql (all text, D14, D27)."""
    import raw_convert

    raw_convert.ensure_converted(verbose=False)
    ref = REPO_ROOT / "data" / "reference"
    noaa = sorted((RAW / "noaa_storm_events").rglob("StormEvents_details-*.csv.gz"))
    zones = sorted((RAW / "nws_zone_county").rglob("bp*.dbx"))

    def lst(paths: list[Path]) -> str:
        return "[" + ", ".join(f"'{p.as_posix()}'" for p in paths) + "]"

    con.execute(f"""
        CREATE OR REPLACE VIEW bronze_noaa_storm_events AS
        SELECT * EXCLUDE (filename), filename AS source_file
        FROM read_csv({lst(noaa)}, all_varchar = true, union_by_name = true, filename = true)
    """)
    con.execute(f"""
        CREATE OR REPLACE VIEW bronze_nws_zone_county AS
        SELECT * EXCLUDE (filename), filename AS source_file
        FROM read_csv({lst(zones)}, delim = '|', header = false, encoding = 'latin-1', filename = true,
            columns = {{'state': 'VARCHAR', 'zone': 'VARCHAR', 'cwa': 'VARCHAR', 'name': 'VARCHAR',
                        'state_zone': 'VARCHAR', 'county': 'VARCHAR', 'fips': 'VARCHAR', 'time_zone': 'VARCHAR',
                        'fe_area': 'VARCHAR', 'lat': 'VARCHAR', 'lon': 'VARCHAR'}})
    """)
    for name, pattern in (("bronze_eia861_reliability", "eia861_parquet/*/reliability_*.parquet"),
                          ("bronze_eia861_sales", "eia861_parquet/*/sales_*.parquet"),
                          ("bronze_eia861_service_territory", "eia861_parquet/*/service_territory_*.parquet"),
                          ("bronze_oe417", "oe417_parquet/*/oe417_*.parquet")):
        con.execute(f"""
            CREATE OR REPLACE VIEW {name} AS
            SELECT * EXCLUDE (filename), filename AS source_file
            FROM read_parquet('{(RAW / pattern).as_posix()}', filename = true)
        """)
    for name, file in (("bronze_noaa_state_codes", "noaa_state_codes.csv"),
                       ("bronze_oe417_event_types", "oe417_event_types.csv"),
                       ("bronze_state_time_zones", "state_time_zones.csv"),
                       ("bronze_storm_event_severity", "storm_event_severity.csv"),
                       ("bronze_ranking_exclusions", "ranking_exclusions.csv")):
        con.execute(f"CREATE OR REPLACE VIEW {name} AS SELECT * FROM read_csv('{(ref / file).as_posix()}', all_varchar = true, header "
                    "= true)")


D21_SCALING = "CASE WHEN s.d13_customers > ${calibration.state_ratio} * e.customers THEN s.d13_customers / e.customers ELSE 1.0 END"
D35_FLOOR = "COALESCE(p.peak_customers_out, 0)"


def dim_sql(mode: str = "d35") -> str:
    """dim_county_customers exactly as in 02_silver.sql, translated to DuckDB.

    mode:
        d35  the pipeline: D21 state calibration with the D35 peak floor
        d21  D21 uniform scaling only (every floor set to 0)
        d13  no calibration (every state factor set to 1.0)
    """
    import re

    import sql_dialect

    text = (REPO_ROOT / "sql" / "databricks" / "02_silver.sql").read_text()
    query = re.search(r"^INSERT OVERWRITE dim_county_customers\n(.*?);\s*$", text, re.S | re.M).group(1)
    if mode == "d13":
        assert query.count(D21_SCALING) == 1
        query = query.replace(D21_SCALING, "1.0")
    elif mode == "d21":
        assert query.count(D35_FLOOR) == 3
        query = query.replace(D35_FLOOR, "0")
    elif mode != "d35":
        raise ValueError(mode)
    return "CREATE OR REPLACE TABLE dim_county_customers AS " + sql_dialect.to_duckdb(pipeline_config.render(query))


def build_dim(con: duckdb.DuckDBPyConnection, mode: str = "d35") -> None:
    """dim_county_customers as in 02_silver.sql. Needs silver_eia_state_customers (D21)."""
    import sql_dialect

    stmts = dict(sql_dialect.table_statements(REPO_ROOT / "sql" / "databricks" / "02_silver_sources.sql"))
    con.execute(f"CREATE OR REPLACE TABLE silver_eia_state_customers AS {stmts['silver_eia_state_customers']}")
    con.execute(dim_sql(mode))

SILVER_STEPS = [
    ("unioned", "D2 rename sum -> customers_out, union years", """
        SELECT fips_code, county, state, customers_out, CAST(NULL AS VARCHAR) AS total_customers,
               run_start_time, source_file FROM bronze_eaglei_2022
        UNION ALL
        SELECT fips_code, county, state, "sum" AS customers_out, CAST(NULL AS VARCHAR),
               run_start_time, source_file FROM bronze_eaglei_2023
        UNION ALL
        SELECT fips_code, county, state, customers_out, total_customers,
               run_start_time, source_file FROM bronze_eaglei_2024
    """),
    ("typed", "D1/D14 pad FIPS, cast counts, parse UTC timestamps", """
        SELECT LPAD(TRIM(fips_code), 5, '0') AS fips_code,
               TRIM(county) AS county,
               state AS state_raw,
               TRY_CAST(customers_out AS BIGINT) AS customers_out,
               TRY_CAST(total_customers AS BIGINT) AS total_customers,
               TRY_STRPTIME(run_start_time, '%Y-%m-%d %H:%M:%S') AS run_start_time,
               source_file
        FROM unioned
    """),
    ("valid", "D15 drop rows that cannot be parsed", """
        SELECT * FROM typed
        WHERE regexp_full_match(fips_code, '[0-9]{5}')
          AND run_start_time IS NOT NULL
          AND customers_out IS NOT NULL
    """),
    ("floored", "D7 floor to the 15-minute mark", """
        SELECT *, time_bucket(INTERVAL 15 MINUTE, run_start_time) AS reading_time FROM valid
    """),
    ("deduped", "D7 dedupe (fips_code, reading_time), keep max", """
        SELECT * FROM floored
        QUALIFY ROW_NUMBER() OVER (PARTITION BY fips_code, reading_time
                                   ORDER BY customers_out DESC, source_file) = 1
    """),
    ("silver_outages", "D8/D16 region join on state FIPS; D4 overcount flag", """
        SELECT d.fips_code, d.county, r.state_name AS state, r.state_abbr,
               r.census_region, r.census_division, r.fema_region,
               d.reading_time, d.customers_out, d.total_customers,
               COALESCE(d.customers_out > k.customers, FALSE) AS exceeds_customers,
               CAST(YEAR(d.reading_time) AS INTEGER) AS year,
               d.source_file
        FROM deduped AS d
        INNER JOIN bronze_state_regions AS r ON r.state_fips = LEFT(d.fips_code, 2)
        LEFT JOIN  dim_county_customers AS k ON k.fips_code  = d.fips_code
    """),
]


def count(con, table: str) -> int:
    return con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


def show(con, sql: str) -> None:
    print(con.execute(sql).fetchdf().to_string(index=False))


def run_silver(con) -> None:
    print("\nSilver steps (row counts before -> after each rule)")
    print(f"  {'step':<16} {'rule':<56} {'before':>12} {'after':>12} {'change':>10}")
    before = None
    for name, rule, sql in SILVER_STEPS:
        con.execute(f"CREATE OR REPLACE TABLE {name} AS {sql}")
        after = count(con, name)
        b = before if before is not None else after
        print(f"  {name:<16} {rule:<56} {b:>12,} {after:>12,} {after - b:>+10,}")
        before = after

    print("\nRule detail on the sample:")
    detail = con.execute("""
        SELECT
            (SELECT COUNT(*) FROM unioned WHERE LENGTH(TRIM(fips_code)) <> 5)              AS fips_padded,
            (SELECT COUNT(*) FROM typed WHERE customers_out IS NULL)                        AS bad_customers_out,
            (SELECT COUNT(*) FROM typed WHERE run_start_time IS NULL)                       AS bad_timestamp,
            (SELECT COUNT(*) FROM typed WHERE NOT regexp_full_match(fips_code, '[0-9]{5}')) AS bad_fips,
            (SELECT COUNT(*) FROM floored WHERE reading_time <> run_start_time)             AS rows_floored,
            (SELECT COUNT(*) FROM deduped d
               LEFT JOIN bronze_state_regions r ON r.state_fips = LEFT(d.fips_code, 2)
               WHERE r.state_fips IS NULL)                                                  AS no_region_match,
            (SELECT COUNT(*) FROM deduped d
               JOIN bronze_state_regions r ON r.state_fips = LEFT(d.fips_code, 2)
               WHERE r.state_name <> d.state_raw)                                           AS state_name_differs,
            (SELECT COUNT(*) FROM silver_outages s
               LEFT JOIN dim_county_customers k USING (fips_code)
               WHERE k.customers IS NULL)                                                   AS no_denominator_rows,
            (SELECT COUNT(*) FROM silver_outages WHERE exceeds_customers)                   AS exceeds_rows,
            (SELECT COUNT(*) FROM silver_outages WHERE census_region = 'Territory')         AS territory_rows
    """).fetchdf()
    for col in detail.columns:
        print(f"  {col:<22} {int(detail[col][0]):>12,}")

    print("\nsilver_outages schema:")
    show(con, "SELECT column_name, column_type FROM (DESCRIBE silver_outages)")
    print("\nRows by Census region:")
    show(con, "SELECT census_region, COUNT(*) AS row_count, COUNT(DISTINCT fips_code) AS counties FROM silver_outages GROUP BY 1 "
              "ORDER BY 2 DESC")
    print("\nLargest overcounts in the sample:")
    show(con, """
        SELECT s.fips_code, s.county, s.state_abbr, MAX(s.customers_out) AS max_out, k.customers,
               k.denominator_source, COUNT(*) FILTER (WHERE s.exceeds_customers) AS flagged_rows
        FROM silver_outages s JOIN dim_county_customers k USING (fips_code)
        GROUP BY ALL HAVING COUNT(*) FILTER (WHERE s.exceeds_customers) > 0
        ORDER BY flagged_rows DESC LIMIT 5
    """)


def run_d7_synthetic(con) -> None:
    """Off-grid run at 20:31 next to a regular 20:30 row for the same county."""
    con.execute("""
        CREATE OR REPLACE TABLE valid AS
        SELECT * FROM (VALUES
            ('01001', 'Autauga', 'Alabama', 120::BIGINT, NULL::BIGINT, TIMESTAMP '2023-03-22 20:30:00', 'a'),
            ('01001', 'Autauga', 'Alabama', 150::BIGINT, NULL::BIGINT, TIMESTAMP '2023-03-22 20:31:00', 'a'),
            ('01003', 'Baldwin', 'Alabama',  90::BIGINT, NULL::BIGINT, TIMESTAMP '2023-03-22 20:31:00', 'a')
        ) AS t(fips_code, county, state_raw, customers_out, total_customers, run_start_time, source_file)
    """)
    for name, _, sql in SILVER_STEPS[3:5]:
        con.execute(f"CREATE OR REPLACE TABLE {name} AS {sql}")
    got = con.execute("SELECT fips_code, reading_time, customers_out FROM deduped ORDER BY 1").fetchall()
    expected = [("01001", "2023-03-22 20:30:00", 150), ("01003", "2023-03-22 20:30:00", 90)]
    ok = [(f, str(t), c) for f, t, c in got] == expected
    print(f"\nD7 synthetic check (floor 20:31 -> 20:30, keep max of duplicates): {'PASS' if ok else 'FAIL'}")
    for row in got:
        print(f"  {row[0]}  {row[1]}  {row[2]}")
    if not ok:
        raise SystemExit("D7 synthetic check failed")


def run_d4_recount(con) -> None:
    """exceeds_customers on all full years, using dim_county_customers (D13)."""
    print("\nD4 recount on full years with final denominators (D13):")
    rows = []
    for year in YEARS:
        path = (RAW / "eaglei" / str(year) / f"eaglei_outages_{year}.csv").as_posix()
        measure = '"sum"' if year == 2023 else "customers_out"
        rows.append(con.execute(f"""
            SELECT {year} AS year,
                   COUNT(*) AS row_count,
                   COUNT(*) FILTER (WHERE TRY_CAST(r.{measure} AS BIGINT) > k.customers) AS exceeds_rows,
                   COUNT(DISTINCT r.fips_code) FILTER (WHERE TRY_CAST(r.{measure} AS BIGINT) > k.customers) AS exceeds_counties,
                   COUNT(*) FILTER (WHERE k.customers IS NULL) AS no_denominator_rows
            FROM read_csv('{path}', all_varchar = true) AS r
            LEFT JOIN dim_county_customers AS k ON k.fips_code = LPAD(TRIM(r.fips_code), 5, '0')
        """).fetchone())
    print(f"  {'year':<6} {'rows':>12} {'exceeds_rows':>14} {'counties':>10} {'no_denom_rows':>14}")
    for y, n, e, c, nd in rows:
        print(f"  {y:<6} {n:>12,} {e:>14,} {c:>10,} {nd:>14,}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--month", default="2024-07", help="YYYY-MM sample for the Silver steps, or 'all'")
    args = parser.parse_args()
    if not REGIONS_CSV.exists():
        raise SystemExit("Missing region lookup. Run: uv run python scripts/census_regions.py")

    con = duckdb.connect()

    # 1. Denominator table from full data.
    bronze(con, month_filter=None)
    build_dim(con)
    print("dim_county_customers (full data):")
    show(con, """
        SELECT COALESCE(denominator_source, '(none)') AS denominator_source, COUNT(*) AS counties,
               COUNT(*) FILTER (WHERE denominator_mismatch) AS mismatch, SUM(customers) AS customers
        FROM dim_county_customers GROUP BY 1 ORDER BY 2 DESC
    """)
    dupes = con.execute("SELECT COUNT(*) - COUNT(DISTINCT fips_code) FROM dim_county_customers").fetchone()[0]
    print(f"  duplicate fips_code rows: {dupes}")

    # 4. D4 recount on full years (uses the full-data dim).
    run_d4_recount(con)

    # 2. Silver steps on a one-month sample.
    print(f"\nSample month: {args.month}")
    bronze(con, month_filter=None if args.month == "all" else args.month)
    run_silver(con)
    if args.month == "all":
        print("\nRows by year:")
        show(con, "SELECT year, COUNT(*) AS row_count, COUNT(*) FILTER (WHERE exceeds_customers) AS exceeds_rows FROM silver_outages "
                  "GROUP BY 1 ORDER BY 1")

    # 3. D7 synthetic check.
    run_d7_synthetic(con)


if __name__ == "__main__":
    main()
