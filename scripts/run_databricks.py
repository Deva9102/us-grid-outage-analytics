"""Run the Databricks pipeline: convert, upload, execute SQL, verify.

Steps (run all, or pick with --steps):
    check    connect to the SQL warehouse and confirm the session time zone is UTC (D1)
    convert  EAGLE-I yearly CSVs -> Parquet with DuckDB, every column as STRING (D14, D20),
             into data/raw/eaglei_parquet/<year>/
    migrate  add the columns listed in scripts/schema_migrations.py to tables an earlier run created
             (D64), and fill them for the rows already there
    upload   Parquet files, EAGLE-I metadata files and data/reference/state_regions.csv to
             /Volumes/workspace/outages/raw/ with the Databricks SDK, keeping the folder structure
    sql      sql/databricks/01_bronze.sql, 02_silver.sql, 03_gold_events.sql, statement by statement
             with the quality gate of each layer (sql/databricks/90_quality_checks.sql) after
             Bronze, Silver and Gold; a failed check stops the run (D48). Incremental (D56): only the
             years in incremental.load_years are loaded into Bronze and Silver; --full loads all
    verify   row counts for every table in workspace.outages, compared with the DuckDB results
    quality  all quality checks on demand, results appended to gold_quality_results

Configuration (catalog, schema, years, every rule threshold) comes from config/pipeline.yml and is
substituted into the SQL before it is sent (D47). Each step is logged with its start time,
duration and row count to logs/pipeline_<timestamp>.log, and a summary table is printed (D49).

Credentials come from .env (DATABRICKS_SERVER_HOSTNAME, DATABRICKS_HTTP_PATH, DATABRICKS_TOKEN).
The token is never printed.

Safety: statements run with catalog workspace and schema outages. A statement is refused before
it is sent if it contains DROP, ALTER, TRUNCATE, DELETE, GRANT or REVOKE, or a three-part name
outside workspace.outages. The exceptions are the retention statement of the quality results
table (D55) and the ALTER TABLE ... ADD COLUMNS statements of the migrate step (D64). Any failure or count mismatch stops the run.

The Statement Execution API runs each statement in its own session, so USE and SET statements in
the .sql files are skipped: catalog and schema are passed with every statement, and the check step
requires the warehouse's session time zone to be UTC.

Usage:
    uv run python scripts/run_databricks.py
    uv run python scripts/run_databricks.py --steps check,convert
    uv run python scripts/run_databricks.py --full      # every year, not only incremental.load_years
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import duckdb
from databricks.sdk import WorkspaceClient
from databricks.sdk.errors import NotFound
from databricks.sdk.service.sql import (
    Disposition,
    ExecuteStatementRequestOnWaitTimeout,
    Format,
    StatementState,
)
from dotenv import load_dotenv

import pipeline_config
import schema_migrations
from pipeline_log import RunLog
from sql_split import split_statements, strip_comments, without_literals

REPO_ROOT = Path(__file__).resolve().parent.parent
RAW = REPO_ROOT / "data" / "raw"
SQL_DIR = REPO_ROOT / "sql" / "databricks"
# Run order (D26): files are numbered by layer; within a layer, sources before dependants.
SQL_FILES = ["01_bronze.sql", "01_bronze_sources.sql", "02_silver_sources.sql", "02_silver.sql",
             "03_gold_events.sql", "03_gold_coverage.sql", "03_gold_storm_match.sql", "03_gold_reliability.sql",
             "03_gold_oe417_check.sql"]
# The quality gate of a layer runs after its last file (D48).
LAYER_OF_PREFIX = {"01": "bronze", "02": "silver", "03": "gold"}
CFG = pipeline_config.load()
CATALOG, SCHEMA = CFG["project"]["catalog"], CFG["project"]["schema"]
VOLUME = CFG["project"]["volume_path"]
YEARS = tuple(CFG["years"]["list"])

# Expected row counts of the verified run live in config/pipeline.yml (quality.expected_rows, D47).
EXPECTED_COUNTS = dict(CFG["quality"]["expected_rows"])
# Regression fixtures from the DuckDB tests (docs/decisions.md): the top 10 and detail checks.
EXPECTED_TOP10 = [
    ("48201-00250", 135_547_967),
    ("72097-00360", 69_989_855),
    ("12071-00096", 66_586_074),
    ("72113-00314", 60_274_807),
    ("72025-00354", 51_591_410),
    ("72013-00311", 39_747_345),
    ("12103-00430", 39_189_773),
    ("45045-00330", 33_811_120),
    ("45083-00354", 25_642_003),
    ("37021-00329", 23_641_092),
]
EXPECTED_DETAIL = {
    "feed gaps per year (D3)": [("2022", "3"), ("2023", "16"), ("2024", "41"), ("2025", "12")],
    "events per year": [("2022", "149695"), ("2023", "144747"), ("2024", "151819"), ("2025", "156094")],
    "dropouts per year (D19)": [("2022", "6793"), ("2023", "5782"), ("2024", "6615"), ("2025", "4869")],
    "exceeds_customers rows per year (D4, D21, D35, D36)": [("2022", "1841"), ("2023", "365"), ("2024", "8437"),
                                                            ("2025", "3415")],
    # D58: 7 counties first reported in 2025 take MCC; the 9 Connecticut planning regions have none.
    "denominator sources (D13)": [("NULL", "11"), ("max_mcc_2024", "372"), ("mcc", "9"),
                                  ("total_customers_2024", "2687")],
    "calibrated states and counties (D21)": [("5", "246")],
    "counties held at their peak (D35)": [("11",)],
    "counties with the floor skipped (D36)": [("46063",)],
    "storm events unplaced by reason (D30)": [("territory_not_tracked", "306"), ("water", "10962"),
                                              ("zone_not_in_file", "39")],
    "reliability rows by standard (D32)": [("IEEE 1366", "2963"), ("not reported", "3"), ("other", "921")],
    "OE-417 incidents per year (D33)": [("2022", "390"), ("2023", "348")],
    "states below 70% coverage (D22)": [("0",)],
    "storm-matched events per year (D37, D42)": [("2022", "17823"), ("2023", "19332"), ("2024", "18449"),
                                                 ("2025", "17724")],
    # D64: 928 events bridge 871 hours of empty readings; 20 touch a longer empty run.
    "events with bridged empty readings (D64)": [("928", "871", "20")],
    "Puerto Rico blackout of 2025-04-16 (D64)": [("72013-01668", "2454656", "15.00"), ("72021-01755", "2307430", "15.00"),
                                                 ("72025-01779", "2099312", "15.00"), ("72097-01588", "3157675", "15.00"),
                                                 ("72113-01541", "4060494", "15.00"), ("72127-01830", "2621865", "15.00")],
    "rank 1 state per year (D38, D43)": [("2022", "ME"), ("2023", "ME"), ("2024", "SC"), ("2025", "WV")],
    # D61: a county is in the reliability tables from its first reported year only.
    "ranked counties per year (D38, D44, D45)": [("2022", "3004"), ("2023", "3006"), ("2024", "3006"),
                                                 ("2025", "3006")],
    "utility rows flagged as source errors (D39)": [("2023", "54913"), ("2025", "19162")],
    "OE-417 check status (D40)": [("matched", "180"), ("no county", "185"), ("no time", "70"), ("not matched", "303")],
    "Helene top-10 attribution (D41)": [("37021", "Tropical Storm"), ("45045", "Tropical Storm"), ("45083", "Tropical Storm")],
    "rank 1 county per year (D44)": [("2022", "12015"), ("2023", "48015"), ("2024", "37199"), ("2025", "26119")],
    "D45 footnoted county-years": [("2022", "49033"), ("2023", "49033"), ("2024", "04003"), ("2024", "48015"),
                                   ("2024", "48473"), ("2024", "49033"), ("2025", "49033")],
}
DETAIL_SQL = {
    "feed gaps per year (D3)":
        "SELECT CAST(YEAR(slot_time) AS STRING), CAST(COUNT_IF(NOT is_collected) AS STRING) "
        "FROM gold_collection_runs GROUP BY 1 ORDER BY 1",
    "events per year":
        "SELECT CAST(event_year AS STRING), CAST(COUNT(*) AS STRING) FROM gold_outage_events GROUP BY 1 ORDER BY 1",
    "dropouts per year (D19)":
        "SELECT CAST(dropout_year AS STRING), CAST(COUNT(*) AS STRING) FROM gold_feed_dropouts GROUP BY 1 ORDER BY 1",
    "exceeds_customers rows per year (D4, D21, D35, D36)":
        "SELECT CAST(year AS STRING), CAST(COUNT_IF(exceeds_customers) AS STRING) "
        "FROM silver_outages GROUP BY 1 ORDER BY 1",
    "denominator sources (D13)":
        "SELECT COALESCE(denominator_source, 'NULL'), CAST(COUNT(*) AS STRING) "
        "FROM dim_county_customers GROUP BY 1 ORDER BY 1",
    "calibrated states and counties (D21)":
        "SELECT CAST(COUNT(DISTINCT LEFT(fips_code, 2)) AS STRING), CAST(COUNT(*) AS STRING) "
        "FROM dim_county_customers WHERE state_calibration_factor > 1",
    "counties held at their peak (D35)":
        "SELECT CAST(COUNT_IF(peak_floor_applied) AS STRING) FROM dim_county_customers",
    "counties with the floor skipped (D36)":
        "SELECT fips_code FROM dim_county_customers WHERE peak_floor_skipped ORDER BY 1",
    "storm events unplaced by reason (D30)":
        "SELECT reason, CAST(COUNT(*) AS STRING) FROM silver_storm_events_unplaced GROUP BY 1 ORDER BY 1",
    "reliability rows by standard (D32)":
        "SELECT reporting_standard, CAST(COUNT(*) AS STRING) FROM silver_utility_reliability GROUP BY 1 ORDER BY 1",
    "OE-417 incidents per year (D33)":
        "SELECT CAST(report_year AS STRING), CAST(COUNT(*) AS STRING) FROM silver_oe417 GROUP BY 1 ORDER BY 1",
    "states below 70% coverage (D22)":
        "SELECT CAST(COUNT_IF(NOT ranking_eligible) AS STRING) FROM gold_state_coverage",
    "storm-matched events per year (D37, D42)":
        "SELECT CAST(event_year AS STRING), CAST(COUNT_IF(storm_type <> 'unmatched') AS STRING) "
        "FROM gold_event_storm_match GROUP BY 1 ORDER BY 1",
    "events with bridged empty readings (D64)":
        "SELECT CAST(COUNT_IF(bridged_empty_hours > 0) AS STRING), CAST(CAST(SUM(bridged_empty_hours) AS INT) AS STRING), "
        "CAST(COUNT_IF(spans_empty_gap) AS STRING) FROM gold_outage_events",
    "Puerto Rico blackout of 2025-04-16 (D64)":
        "SELECT event_id, CAST(CAST(ROUND(customer_hours_lost) AS BIGINT) AS STRING), CAST(bridged_empty_hours AS STRING) "
        "FROM gold_outage_events WHERE fips_code IN ('72013', '72021', '72025', '72097', '72113', '72127') "
        "AND event_start < TIMESTAMP '2025-04-17 00:00:00' AND event_end > TIMESTAMP '2025-04-17 00:00:00' ORDER BY 1",
    "rank 1 state per year (D38, D43)":
        "SELECT CAST(year AS STRING), state_abbr FROM gold_state_reliability WHERE national_rank = 1 ORDER BY 1",
    "ranked counties per year (D38, D44, D45)":
        "SELECT CAST(year AS STRING), CAST(COUNT_IF(ranking_eligible) AS STRING) FROM gold_county_reliability GROUP BY 1 ORDER BY 1",
    "utility rows flagged as source errors (D39)":
        "SELECT CAST(data_year AS STRING), utility_number FROM gold_utility_reliability WHERE data_quality_flag IS NOT NULL ORDER BY 1",
    "OE-417 check status (D40)":
        "SELECT match_status, CAST(COUNT(*) AS STRING) FROM gold_oe417_check GROUP BY 1 ORDER BY 1",
    "Helene top-10 attribution (D41)":
        "SELECT fips_code, storm_type FROM (SELECT * FROM gold_event_storm_match ORDER BY customer_hours_lost DESC LIMIT 10) "
        "WHERE fips_code IN ('45045', '45083', '37021') ORDER BY fips_code",
    "rank 1 county per year (D44)":
        "SELECT CAST(year AS STRING), fips_code FROM gold_county_reliability WHERE national_rank = 1 ORDER BY 1",
    "D45 footnoted county-years":
        "SELECT CAST(year AS STRING), fips_code FROM gold_county_ranking_footnotes WHERE footnote_reason LIKE '%D45%' ORDER BY 1, 2",
}

FORBIDDEN = re.compile(r"\b(DROP|ALTER|TRUNCATE|DELETE|GRANT|REVOKE)\b", re.I)
# The only DELETE allowed: quality results older than the retention period (D55).
RETENTION = re.compile(rf"^\s*DELETE\s+FROM\s+{CFG['quality']['results_table']}\s+WHERE\s+run_ts\s*<\s*"
                       r"CURRENT_TIMESTAMP(?:\(\))?\s*-\s*INTERVAL\s+\d+\s+DAYS\s*$", re.I)
# The only ALTER allowed: adding columns listed in scripts/schema_migrations.py (D64).
MIGRATION = re.compile(r"^\s*ALTER\s+TABLE\s+(\w+)\s+ADD\s+COLUMNS\s*\(\s*(\w+)\s", re.I)
THREE_PART = re.compile(r"\b([A-Za-z_]\w*)\.([A-Za-z_]\w*)\.([A-Za-z_]\w*)\b")
SKIPPED = re.compile(r"^\s*(USE|SET)\b", re.I)


class Stop(Exception):
    """A failure that ends the run with a message."""


def human(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


# -----------------------------------------------------------------------------
# Connection and SQL execution
# -----------------------------------------------------------------------------

def connect() -> tuple[WorkspaceClient, str]:
    load_dotenv(REPO_ROOT / ".env")
    missing = [k for k in ("DATABRICKS_SERVER_HOSTNAME", "DATABRICKS_HTTP_PATH", "DATABRICKS_TOKEN")
               if not os.environ.get(k)]
    if missing:
        raise Stop(f"Missing in .env: {', '.join(missing)}")
    host = os.environ["DATABRICKS_SERVER_HOSTNAME"].strip().removeprefix("https://").rstrip("/")
    warehouse_id = os.environ["DATABRICKS_HTTP_PATH"].strip().rstrip("/").split("/")[-1]
    w = WorkspaceClient(host=f"https://{host}", token=os.environ["DATABRICKS_TOKEN"].strip())
    return w, warehouse_id


def allowed_migration(stmt: str) -> bool:
    """True for exactly an ADD COLUMNS statement that schema_migrations.py generates."""
    m = MIGRATION.match(strip_comments(stmt))
    if not m:
        return False
    listed = schema_migrations.statements(
        [c for c in schema_migrations.ADDED_COLUMNS if (c.table, c.column) == (m.group(1), m.group(2))], "databricks")
    return strip_comments(stmt).strip() in listed


def check_safe(stmt: str) -> None:
    code = without_literals(stmt)
    if FORBIDDEN.search(code) and not RETENTION.match(strip_comments(stmt)) and not allowed_migration(stmt):
        raise Stop(f"Refused (forbidden keyword {FORBIDDEN.search(code).group(1)}):\n{summary(stmt)}")
    for cat, sch, _ in THREE_PART.findall(code):
        if (cat.lower(), sch.lower()) != (CATALOG, SCHEMA):
            raise Stop(f"Refused (object outside {CATALOG}.{SCHEMA}: {cat}.{sch}):\n{summary(stmt)}")
    m = re.search(r"\bCREATE\s+SCHEMA\s+(?:IF\s+NOT\s+EXISTS\s+)?([\w.]+)", code, re.I)
    if m and m.group(1).lower() != f"{CATALOG}.{SCHEMA}":
        raise Stop(f"Refused (schema {m.group(1)} is not {CATALOG}.{SCHEMA})")


def summary(stmt: str) -> str:
    lines = [line.strip() for line in strip_comments(stmt).splitlines() if line.strip()]
    return " ".join(lines)[:110] + ("..." if len(" ".join(lines)) > 110 else "")


def run_sql(w: WorkspaceClient, warehouse_id: str, stmt: str) -> list[list[str]]:
    check_safe(stmt)
    resp = w.statement_execution.execute_statement(
        warehouse_id=warehouse_id,
        statement=stmt,
        catalog=CATALOG,
        schema=SCHEMA,
        wait_timeout="50s",
        on_wait_timeout=ExecuteStatementRequestOnWaitTimeout.CONTINUE,
        disposition=Disposition.INLINE,
        format=Format.JSON_ARRAY,
    )
    while resp.status.state in (StatementState.PENDING, StatementState.RUNNING):
        time.sleep(5)
        resp = w.statement_execution.get_statement(resp.statement_id)
    if resp.status.state != StatementState.SUCCEEDED:
        err = resp.status.error
        msg = f"{err.error_code}: {err.message}" if err else str(resp.status.state)
        raise Stop(f"Statement failed ({resp.status.state.value}):\n  {summary(stmt)}\n{msg}")
    if resp.result and resp.result.data_array:
        return resp.result.data_array
    return []


# -----------------------------------------------------------------------------
# Steps
# -----------------------------------------------------------------------------

def step_check(w: WorkspaceClient, warehouse_id: str) -> None:
    wh = w.warehouses.get(warehouse_id)
    print(f"Warehouse: {wh.name} ({wh.state.value if wh.state else 'unknown'})")
    rows = run_sql(w, warehouse_id, "SELECT current_user(), current_timezone(), current_catalog(), current_schema()")
    user, tz, cat, sch = rows[0]
    print(f"Connected as {user}; session time zone {tz}; default {cat}.{sch} (statements use {CATALOG}.{SCHEMA})")
    if tz not in ("UTC", "Etc/UTC", "Z", "+00:00", "GMT", "Etc/GMT"):
        raise Stop(
            f"Session time zone is {tz}, not UTC. D1 parsing and YEAR() depend on it.\n"
            "Fix: set the warehouse SQL configuration parameter TIMEZONE = UTC "
            "(SQL Warehouses > warehouse > Advanced options), then rerun."
        )


def step_convert() -> int:
    con = duckdb.connect()
    total = 0
    print(f"{'year':<6} {'csv':>10} {'parquet':>10} {'ratio':>6} {'rows':>14}")
    for year in YEARS:
        csv = RAW / "eaglei" / str(year) / f"eaglei_outages_{year}.csv"
        out = RAW / "eaglei_parquet" / str(year) / f"eaglei_outages_{year}.parquet"
        out.parent.mkdir(parents=True, exist_ok=True)
        if not out.exists() or out.stat().st_mtime < csv.stat().st_mtime:
            tmp = out.with_suffix(".parquet.part")
            con.execute(f"""
                COPY (SELECT * FROM read_csv('{csv.as_posix()}', header = true, all_varchar = true))
                TO '{tmp.as_posix()}' (FORMAT parquet, COMPRESSION zstd, ROW_GROUP_SIZE 1000000)
            """)
            tmp.rename(out)
        rows = con.execute(f"SELECT COUNT(*) FROM read_parquet('{out.as_posix()}')").fetchone()[0]
        types = {r[1] for r in con.execute(f"DESCRIBE SELECT * FROM read_parquet('{out.as_posix()}')").fetchall()}
        if types != {"VARCHAR"}:
            raise Stop(f"{out.name}: expected all STRING columns, got {types}")
        expected = EXPECTED_COUNTS[f"bronze_eaglei_{year}"]
        if rows != expected:
            raise Stop(f"{out.name}: {rows:,} rows, expected {expected:,}")
        c, p = csv.stat().st_size, out.stat().st_size
        print(f"{year:<6} {human(c):>10} {human(p):>10} {p / c:>6.1%} {rows:>14,}")
        total += rows
    print("Excel sources to raw-row Parquet (D27):")
    import raw_convert

    for out in raw_convert.ensure_converted():
        print(f"  {out.relative_to(REPO_ROOT)}")
    return total


def upload_list() -> list[tuple[Path, str]]:
    items = [(RAW / "eaglei_parquet" / str(y) / f"eaglei_outages_{y}.parquet",
              f"{VOLUME}/eaglei_parquet/{y}/eaglei_outages_{y}.parquet") for y in YEARS]
    for name in ("MCC.csv", "coverage_history.csv", "DQI.csv"):
        items.append((RAW / "eaglei" / "metadata" / name, f"{VOLUME}/eaglei/metadata/{name}"))
    ref = REPO_ROOT / "data" / "reference"
    for name in ("state_regions.csv", "noaa_state_codes.csv", "oe417_event_types.csv", "state_time_zones.csv",
                 "storm_event_severity.csv", "ranking_exclusions.csv"):
        items.append((ref / name, f"{VOLUME}/reference/{name}"))
    for p in sorted((RAW / "noaa_storm_events").rglob("StormEvents_details-*.csv.gz")):
        items.append((p, f"{VOLUME}/noaa_storm_events/{p.parent.name}/{p.name}"))
    for p in sorted((RAW / "nws_zone_county").rglob("bp*.dbx")):
        items.append((p, f"{VOLUME}/nws_zone_county/{p.parent.name}/{p.name}"))
    for folder in ("eia861_parquet", "oe417_parquet"):
        for p in sorted((RAW / folder).rglob("*.parquet")):
            items.append((p, f"{VOLUME}/{folder}/{p.parent.name}/{p.name}"))
    return items


def step_upload(w: WorkspaceClient, warehouse_id: str) -> int:
    # The schema and volume must exist first: run the setup statements of 01_bronze.sql.
    for stmt in split_statements(pipeline_config.render((SQL_DIR / "01_bronze.sql").read_text())):
        if re.match(r"^\s*CREATE\s+(SCHEMA|VOLUME)\b", strip_comments(stmt), re.I):
            print(f"  {summary(stmt)}")
            run_sql(w, warehouse_id, stmt)
    for local, remote in upload_list():
        if not local.exists():
            raise Stop(f"Missing local file {local.relative_to(REPO_ROOT)}")
        size = local.stat().st_size
        try:
            meta = w.files.get_metadata(remote)
            if meta.content_length == size:
                print(f"  {remote}: already uploaded ({human(size)}), skipping")
                continue
        except NotFound:
            pass
        w.files.create_directory(remote.rsplit("/", 1)[0])
        started = time.time()
        with local.open("rb") as f:
            w.files.upload(remote, f, overwrite=True)
        meta = w.files.get_metadata(remote)
        if meta.content_length != size:
            raise Stop(f"{remote}: uploaded {meta.content_length} bytes, expected {size}")
        print(f"  {remote}: {human(size)} in {time.time() - started:.0f}s")
    return len(upload_list())


# Statements that build a table: replace it, overwrite it, or replace some of its partitions (D56).
CREATED = re.compile(r"^\s*(?:CREATE\s+OR\s+REPLACE\s+TABLE|INSERT\s+OVERWRITE|INSERT\s+INTO(?=\s+\w+\s+REPLACE\s+WHERE))"
                     r"\s+(\w+)", re.I)
BRONZE_YEAR = re.compile(r"^\s*CREATE\s+OR\s+REPLACE\s+TABLE\s+bronze_eaglei_(\d{4})\b", re.I)
# Values replaced for this run only (--full sets incremental.load_years to every year).
RUN_OVERRIDES: dict = {}


def for_this_run(statements: list[str], overrides: dict | None = None) -> list[str]:
    """Drop the Bronze statements of EAGLE-I years outside incremental.load_years (D56).

    Those yearly tables were loaded by an earlier run and stay untouched.
    """
    years = set(pipeline_config.load_years(overrides))
    out = []
    for stmt in statements:
        m = BRONZE_YEAR.match(strip_comments(stmt))
        if m and int(m.group(1)) not in years:
            continue
        out.append(stmt)
    return out


def full_rebuild_overrides() -> dict:
    """Overrides that load every configured year: a full rebuild."""
    return {"incremental.load_years": list(YEARS)}


def check_years() -> None:
    """Every configured year needs its own Bronze statement: the column layout differs by year (D2, D47)."""
    text = (SQL_DIR / "01_bronze.sql").read_text()
    missing = [y for y in YEARS if f"CREATE OR REPLACE TABLE bronze_eaglei_{y}" not in text]
    if missing:
        raise Stop(f"config years {missing} have no Bronze statement in 01_bronze.sql; add one per year")


def step_sql(w: WorkspaceClient, warehouse_id: str, log: RunLog) -> None:
    import quality_checks

    check_years()
    run_ts = datetime.now(UTC).replace(microsecond=0, tzinfo=None)
    print(f"Loading years {pipeline_config.load_years(RUN_OVERRIDES)} of {list(YEARS)}")
    for i, name in enumerate(SQL_FILES):
        statements = for_this_run(split_statements(pipeline_config.render((SQL_DIR / name).read_text(), RUN_OVERRIDES)),
                                  RUN_OVERRIDES)
        print(f"\n{name}: {len(statements)} statements")
        with log.step(f"sql {name}") as step:
            step.rows = 0
            for k, stmt in enumerate(statements, 1):
                head = summary(stmt)
                code = strip_comments(stmt)
                if SKIPPED.match(code):
                    print(f"  [{k:>2}] skip (session statement): {head}")
                    continue
                started = time.time()
                rows = run_sql(w, warehouse_id, stmt)
                print(f"  [{k:>2}] ok {time.time() - started:6.1f}s  {head}")
                created = CREATED.match(code)
                if created:
                    n = int(run_sql(w, warehouse_id, f"SELECT COUNT(*) FROM {created.group(1)}")[0][0])
                    step.rows += n
                    log.info("table %s rows=%d (%.1fs)", created.group(1), n, time.time() - started)
                elif re.match(r"^\s*SELECT\b", code, re.I):
                    for row in rows[:12]:
                        print(f"         {row}")
        layer = LAYER_OF_PREFIX[name[:2]]
        is_last = i + 1 == len(SQL_FILES) or LAYER_OF_PREFIX[SQL_FILES[i + 1][:2]] != layer
        if is_last:
            with log.step(f"quality gate {layer}") as step:
                try:
                    step.rows = len(quality_checks.databricks_gate(w, warehouse_id, [layer], log, run_ts))
                except quality_checks.QualityFailed as e:
                    raise Stop(f"Quality gate after {layer} failed; later layers were not built.\n{e}") from e


def step_migrate(w: WorkspaceClient, warehouse_id: str) -> int:
    """Add the columns of schema_migrations.py that existing tables lack (D64); returns how many."""
    tables = {r[1] for r in run_sql(w, warehouse_id, f"SHOW TABLES IN {CATALOG}.{SCHEMA}")}
    existing = {}
    for table in sorted({c.table for c in schema_migrations.ADDED_COLUMNS} & tables):
        existing[table] = {r[0].lower() for r in run_sql(w, warehouse_id, f"SHOW COLUMNS IN {table}")}
    todo = schema_migrations.missing(existing)
    for stmt in schema_migrations.statements(todo, "databricks"):
        started = time.time()
        run_sql(w, warehouse_id, stmt)
        print(f"  ok {time.time() - started:6.1f}s  {summary(stmt)}")
    print(f"  {len(todo)} column(s) added" if todo else "  every table has its columns")
    return len(todo)


def step_quality(w: WorkspaceClient, warehouse_id: str, log: RunLog) -> int:
    import quality_checks

    run_ts = datetime.now(UTC).replace(microsecond=0, tzinfo=None)
    try:
        return len(quality_checks.databricks_gate(w, warehouse_id, quality_checks.LAYERS, log, run_ts))
    except quality_checks.QualityFailed as e:
        raise Stop(str(e)) from e


def step_verify(w: WorkspaceClient, warehouse_id: str) -> int:
    problems = []
    tables = [r[1] for r in run_sql(w, warehouse_id, f"SHOW TABLES IN {CATALOG}.{SCHEMA}")]
    print(f"\nRow counts in {CATALOG}.{SCHEMA}:")
    print(f"  {'table':<24} {'Databricks':>14} {'DuckDB':>14}")
    for table in sorted(set(tables) | set(EXPECTED_COUNTS)):
        if table not in tables:
            problems.append(f"{table}: missing")
            print(f"  {table:<24} {'missing':>14} {EXPECTED_COUNTS[table]:>14,}  <-- MISSING")
            continue
        n = int(run_sql(w, warehouse_id, f"SELECT COUNT(*) FROM {CATALOG}.{SCHEMA}.{table}")[0][0])
        exp = EXPECTED_COUNTS.get(table)
        flag = "" if exp is None or exp == n else "  <-- DIFFERS"
        if flag:
            problems.append(f"{table}: {n:,} vs DuckDB {exp:,}")
        print(f"  {table:<24} {n:>14,} {'-' if exp is None else format(exp, ','):>14}{flag}")

    print("\nDetail checks:")
    for label, sql in DETAIL_SQL.items():
        got = [tuple(r) for r in run_sql(w, warehouse_id, sql)]
        ok = got == EXPECTED_DETAIL[label]
        print(f"  {label:<38} {'match' if ok else 'DIFFERS'}  {got}")
        if not ok:
            problems.append(f"{label}: {got} vs DuckDB {EXPECTED_DETAIL[label]}")

    print("\nTop 10 events by customer_hours_lost:")
    rows = run_sql(w, warehouse_id, """
        SELECT event_id, county, state_abbr, CAST(event_start AS STRING), CAST(event_end AS STRING),
               CAST(ROUND(customer_hours_lost) AS BIGINT)
        FROM gold_outage_events ORDER BY customer_hours_lost DESC LIMIT 10
    """)
    for k, (row, (exp_id, exp_hours)) in enumerate(zip(rows, EXPECTED_TOP10, strict=False), 1):
        event_id, county, st, start, end, hours = row
        ok = event_id == exp_id and abs(int(hours) - exp_hours) <= 1
        print(f"  {k:>2} {event_id} {county:<12} {st} {start[:16]} -> {end[:16]} {int(hours):>13,}  "
              f"{'match' if ok else f'DIFFERS (DuckDB {exp_id} {exp_hours:,})'}")
        if not ok:
            problems.append(f"top 10 #{k}: {event_id} {hours} vs DuckDB {exp_id} {exp_hours}")
    if len(rows) != 10:
        problems.append(f"top 10 returned {len(rows)} rows")

    if problems:
        raise Stop("Differences from DuckDB:\n  " + "\n  ".join(problems))
    print("\nAll counts and the top 10 match DuckDB.")
    return len(tables)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--steps", default="check,convert,upload,migrate,sql,verify")
    parser.add_argument("--full", action="store_true", help="rebuild every year, not only incremental.load_years")
    args = parser.parse_args()
    if args.full:
        RUN_OVERRIDES.update(full_rebuild_overrides())
    steps = [s.strip() for s in args.steps.split(",")]
    log = RunLog("pipeline")
    log.info("steps %s; target %s.%s; years %s; loading %s", ",".join(steps), CATALOG, SCHEMA, list(YEARS),
             pipeline_config.load_years(RUN_OVERRIDES))
    try:
        w = warehouse_id = None
        if any(s != "convert" for s in steps):
            w, warehouse_id = connect()
        for step in steps:
            print(f"\n=== {step} ===")
            if step == "sql":
                step_sql(w, warehouse_id, log)  # logs one step per SQL file and per quality gate
                continue
            with log.step(step) as s:
                if step == "check":
                    step_check(w, warehouse_id)
                elif step == "convert":
                    s.rows = step_convert()
                elif step == "upload":
                    s.rows = step_upload(w, warehouse_id)
                elif step == "migrate":
                    s.rows = step_migrate(w, warehouse_id)
                elif step == "verify":
                    s.rows = step_verify(w, warehouse_id)
                elif step == "quality":
                    s.rows = step_quality(w, warehouse_id, log)
                else:
                    raise Stop(f"Unknown step {step}")
    except Stop as e:
        print(f"\nSTOPPED: {e}", file=sys.stderr)
        log.info("stopped: %s", str(e).splitlines()[0])
        return 1
    finally:
        log.summary()
    return 0


if __name__ == "__main__":
    sys.exit(main())
