"""Build tests/fixtures/ from the raw downloads: a small real sample for the pytest suite (D51).

Every fixture row is copied unchanged from a raw file in data/raw/. The sample is chosen so the
pipeline's rules can be checked with exact expected values:

    EAGLE-I   14 counties in 5 windows (UTC) plus two single readings:
                W1 2022-10-25 00:00-20:00   Harris event matched by OE-417 incident (D40)
                W2 2023-03-22 18:00-24:00   off-grid 20:31 run floored to 20:30 (D7)
                W3 2024-05-23 18:00-05-24 12:00  nationwide feed gap 00:15-09:00 (D3, D10)
                W4 2024-06-15 20:00-06-16 03:00  Rich UT readings above its customers (D4, D45)
                W5 2024-07-08 00:00-07-12 00:00  Harris Beryl dropout (D19), Harris overcount (D4),
                                                 Kauai peak that sets its D35 floor
              Kalawao HI: its first 2024 reading, so Hawaii's D21 state total is complete.
              Norton city VA: one reading; it has no denominator (D9).
    MCC       the 14 counties and the Grand Total row (D5)
    NOAA      storms whose match window (begin - 12 h to end + 1 h) overlaps a window in a
              fixture county, plus one water-area event (D30); NWS zone rows for their zones
    EIA-861   Sales rows for HI, UT, MA, TX, CA and VA 2024 (state totals, D21, D22) and the utilities
              ranked below; Reliability rows for HI, UT, MA 2024, the 2023 CT/MA pair behind the
              D39 source-error flag and National Grid RI 2022; the first 3 rows of each sheet
    OE-417    the header rows and four incidents: matched, not matched, no county, no time

Harris County (48201) reports in every collected 15-minute slot of every window, so the only
empty slots inside a window are the real nationwide feed gaps.

Usage:
    uv run python scripts/build_test_fixture.py
"""

from __future__ import annotations

import shutil
from pathlib import Path

import duckdb

import pipeline_config
import sql_dialect
import test_silver_duckdb as silver

REPO_ROOT = Path(__file__).resolve().parent.parent
RAW = REPO_ROOT / "data" / "raw"
OUT = REPO_ROOT / "tests" / "fixtures"

WINDOWS = [
    ("2022-10-25 00:00", "2022-10-25 20:00"),
    ("2023-03-22 18:00", "2023-03-23 00:00"),
    ("2024-05-23 18:00", "2024-05-24 12:00"),
    ("2024-06-15 20:00", "2024-06-16 03:00"),
    ("2024-07-08 00:00", "2024-07-12 00:00"),
]
COUNTIES = [
    "48201", "48157",                                # Harris, Fort Bend TX
    "06037",                                         # Los Angeles CA
    "15001", "15003", "15005", "15007", "15009",     # all of Hawaii (D21, D35)
    "49035", "49049", "49011", "49057", "49033",     # Salt Lake, Utah, Davis, Weber, Rich UT
]
KALAWAO, NORTON = "15005", "51720"
WATER_EVENT_TYPES = ("Marine Thunderstorm Wind", "Marine Strong Wind", "Marine High Wind", "Waterspout")
SALES_STATES_2024 = ("HI", "UT", "MA", "TX", "CA", "VA")
RELIABILITY_2024 = ("HI", "UT", "MA")
RELIABILITY_EXTRA = [(2023, "4176", "CT"), (2023, "54913", "MA"), (2022, "13214", "RI")]
OE417_INCIDENTS = ["2022-0309", "2022-0312", "2022-0040", "2023-0204"]


def sql_list(values) -> str:
    return ", ".join(f"'{v}'" for v in values)


def window_sql(col: str) -> str:
    return " OR ".join(f"({col} >= TIMESTAMP '{a}' AND {col} < TIMESTAMP '{b}')" for a, b in WINDOWS)


def copy_csv(con, query: str, path: Path) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    con.execute(f"COPY ({query}) TO '{path.as_posix()}' (HEADER, DELIMITER ',')")
    return con.execute(f"SELECT COUNT(*) FROM ({query})").fetchone()[0]


def eaglei(con) -> None:
    measure = {2022: "customers_out", 2023: '"sum"', 2024: "customers_out"}
    last_window_start = WINDOWS[-1][0]
    for year in pipeline_config.load()["years"]["list"]:
        src = (RAW / "eaglei_parquet" / str(year) / f"eaglei_outages_{year}.parquet").as_posix()
        extra = ""
        if year == 2024:
            # One real reading each for Kalawao (first of the year) and Norton (last before W5).
            extra = f"""
                OR run_start_time = (SELECT MIN(run_start_time) FROM read_parquet('{src}') WHERE fips_code = '{KALAWAO}')
                   AND fips_code = '{KALAWAO}'
                OR run_start_time = (SELECT MAX(run_start_time) FROM read_parquet('{src}')
                                     WHERE fips_code = '{NORTON}' AND run_start_time < '{last_window_start}')
                   AND fips_code = '{NORTON}'"""
        query = f"""
            SELECT * FROM read_parquet('{src}')
            WHERE (fips_code IN ({sql_list(COUNTIES)}) AND ({window_sql('CAST(run_start_time AS TIMESTAMP)')})) {extra}
            ORDER BY run_start_time, fips_code
        """
        n = copy_csv(con, query, OUT / "eaglei" / str(year) / f"eaglei_outages_{year}.csv")
        print(f"  eaglei {year}: {n} rows ({measure[year]})")
    mcc = (RAW / "eaglei" / "metadata" / "MCC.csv").as_posix()
    keys = sql_list([c.lstrip("0") for c in COUNTIES])
    n = copy_csv(con, f"""
        SELECT * FROM read_csv('{mcc}', all_varchar = true)
        WHERE County_FIPS IN ({keys}) OR County_FIPS = 'Grand Total'
    """, OUT / "eaglei" / "metadata" / "MCC.csv")
    print(f"  MCC: {n} rows")


def noaa_and_zones(con) -> None:
    stmts = dict(sql_dialect.table_statements(REPO_ROOT / "sql" / "databricks" / "02_silver_sources.sql"))
    for name in ("silver_nws_zone_versions", "silver_nws_zone_county", "silver_storm_event_details", "silver_storm_events"):
        con.execute(f"CREATE OR REPLACE TABLE {name} AS {stmts[name]}")
    before = pipeline_config.get("storm_match.window_before_hours")
    after = pipeline_config.get("storm_match.window_after_hours")
    overlaps = " OR ".join(
        f"(s.begin_utc - INTERVAL {before} HOUR < TIMESTAMP '{b}' AND s.end_utc + INTERVAL {after} HOUR > TIMESTAMP '{a}')"
        for a, b in WINDOWS)
    con.execute(f"""
        CREATE OR REPLACE TABLE fixture_storms AS
        SELECT DISTINCT s.event_id FROM silver_storm_events s
        WHERE s.fips_code IN ({sql_list(COUNTIES)}) AND ({overlaps})
        UNION
        SELECT MIN(event_id) FROM silver_storm_event_details
        WHERE area_type = 'water' AND event_type IN ({sql_list(WATER_EVENT_TYPES)})
          AND state_abbr IS NULL AND noaa_state = 'GULF OF MEXICO' AND ({window_sql('begin_utc')})
    """)
    for year in pipeline_config.load()["years"]["list"]:
        n = copy_csv(con, f"""
            SELECT * EXCLUDE (source_file) FROM bronze_noaa_storm_events
            WHERE CAST(EVENT_ID AS BIGINT) IN (SELECT event_id FROM fixture_storms) AND source_file LIKE '%d{year}_%'
            ORDER BY CAST(EVENT_ID AS BIGINT)
        """, OUT / "noaa_storm_events" / str(year) / f"storm_events_details_{year}.csv")
        print(f"  NOAA {year}: {n} events")
    zones = {r[0] for r in con.execute("""
        SELECT DISTINCT zone_key FROM silver_storm_events
        WHERE event_id IN (SELECT event_id FROM fixture_storms) AND zone_key IS NOT NULL
    """).fetchall()}
    for path in sorted((RAW / "nws_zone_county").rglob("bp*.dbx")):
        lines = [line for line in path.read_text(encoding="latin-1").splitlines()
                 if (p := line.split("|")) and len(p) > 2 and p[0].strip().upper() + p[1].strip().zfill(3) in zones]
        dest = OUT / "nws_zone_county" / path.parent.name / path.name
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text("\n".join(lines) + "\n", encoding="latin-1")
        print(f"  NWS {path.name}: {len(lines)} rows")


def eia(con) -> None:
    sales_keys = " OR ".join(
        f"(col_01 = '{y}' AND TRIM(col_02) = '{u}' AND TRIM(col_07) = '{s}')" for y, u, s in RELIABILITY_EXTRA)
    rel_keys = " OR ".join(
        f"(col_01 = '{y}' AND TRIM(col_02) = '{u}' AND TRIM(col_04) = '{s}')" for y, u, s in RELIABILITY_EXTRA)
    for year in pipeline_config.load()["years"]["list"]:
        base = RAW / "eia861_parquet" / str(year)
        files = {
            "sales": f"""(sheet_name IN ('States', 'Territories') AND (
                            (col_01 = '2024' AND TRIM(col_07) IN ({sql_list(SALES_STATES_2024)})) OR {sales_keys}))""",
            "reliability": f"""(sheet_name IN ('Reliability_States', 'Reliability_Territories') AND (
                            (col_01 = '2024' AND TRIM(col_04) IN ({sql_list(RELIABILITY_2024)})) OR {rel_keys}))""",
            "service_territory": f"(col_01 = '{year}' AND TRIM(col_04) = 'HI')",
        }
        for kind, where in files.items():
            src = (base / f"{kind}_{year}.parquet").as_posix()
            n = copy_csv(con, f"""
                SELECT * FROM read_parquet('{src}')
                WHERE CAST(row_number AS INT) <= 3 OR {where}
                ORDER BY sheet_name, CAST(row_number AS INT)
            """, OUT / "eia861" / str(year) / f"{kind}_{year}.csv")
            print(f"  EIA {kind} {year}: {n} rows")


def oe417(con) -> None:
    stmts = dict(sql_dialect.table_statements(REPO_ROOT / "sql" / "databricks" / "02_silver_sources.sql"))
    con.execute(f"CREATE OR REPLACE TABLE silver_oe417_rows AS {stmts['silver_oe417_rows']}")
    picks = con.execute(f"""
        SELECT report_year, sheet_row FROM silver_oe417_rows WHERE incident_id IN ({sql_list(OE417_INCIDENTS)})
    """).fetchall()
    for year in (2022, 2023):
        rows = [r for y, r in picks if y == year]
        src = (RAW / "oe417_parquet" / str(year) / f"oe417_{year}.parquet").as_posix()
        n = copy_csv(con, f"""
            WITH header AS (SELECT MIN(CAST(row_number AS INT)) AS h FROM read_parquet('{src}') WHERE TRIM(col_02) = 'Date Event Began')
            SELECT * FROM read_parquet('{src}')
            WHERE CAST(row_number AS INT) <= (SELECT h FROM header) OR CAST(row_number AS INT) IN ({', '.join(map(str, rows)) or 'NULL'})
            ORDER BY CAST(row_number AS INT)
        """, OUT / "oe417" / str(year) / f"oe417_{year}.csv")
        print(f"  OE-417 {year}: {n} rows ({len(rows)} incidents)")


def main() -> None:
    for sub in ("eaglei", "noaa_storm_events", "nws_zone_county", "eia861", "oe417"):
        shutil.rmtree(OUT / sub, ignore_errors=True)
    con = duckdb.connect()
    con.execute("SET TimeZone = 'UTC'")
    silver.bronze(con, month_filter="0000")  # views only; EAGLE-I is read from Parquet below
    print("Writing tests/fixtures/ from data/raw/:")
    eaglei(con)
    noaa_and_zones(con)
    eia(con)
    oe417(con)
    total = sum(p.stat().st_size for p in OUT.rglob("*") if p.is_file())
    print(f"Fixture size: {total / 1024:.0f} KB")


if __name__ == "__main__":
    main()
