"""Run the Databricks pipeline: convert, upload, execute SQL, verify.

Steps (run all, or pick with --steps):
    check    connect to the SQL warehouse and confirm the session time zone is UTC (D1)
    convert  EAGLE-I yearly CSVs -> Parquet with DuckDB, every column as STRING (D14, D20),
             into data/raw/eaglei_parquet/<year>/
    upload   Parquet files, EAGLE-I metadata files and data/reference/state_regions.csv to
             /Volumes/workspace/outages/raw/ with the Databricks SDK, keeping the folder structure
    sql      sql/databricks/01_bronze.sql, 02_silver.sql, 03_gold_events.sql, statement by statement
    verify   row counts for every table in workspace.outages, compared with the DuckDB results

Credentials come from .env (DATABRICKS_SERVER_HOSTNAME, DATABRICKS_HTTP_PATH, DATABRICKS_TOKEN).
The token is never printed.

Safety: statements run with catalog workspace and schema outages. A statement is refused before
it is sent if it contains DROP, ALTER, TRUNCATE, DELETE, GRANT or REVOKE, or a three-part name
outside workspace.outages. Any failure or count mismatch stops the run.

The Statement Execution API runs each statement in its own session, so USE and SET statements in
the .sql files are skipped: catalog and schema are passed with every statement, and the check step
requires the warehouse's session time zone to be UTC.

Usage:
    uv run python scripts/run_databricks.py
    uv run python scripts/run_databricks.py --steps check,convert
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import time
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

REPO_ROOT = Path(__file__).resolve().parent.parent
RAW = REPO_ROOT / "data" / "raw"
SQL_DIR = REPO_ROOT / "sql" / "databricks"
# Run order (D26): files are numbered by layer; within a layer, sources before dependants.
SQL_FILES = ["01_bronze.sql", "01_bronze_sources.sql", "02_silver_sources.sql", "02_silver.sql",
             "03_gold_events.sql", "03_gold_coverage.sql", "03_gold_storm_match.sql", "03_gold_reliability.sql",
             "03_gold_oe417_check.sql"]
CATALOG, SCHEMA = "workspace", "outages"
VOLUME = "/Volumes/workspace/outages/raw"
YEARS = (2022, 2023, 2024)

# Expected values from the DuckDB tests (docs/decisions.md).
EXPECTED_COUNTS = {
    "bronze_eaglei_2022": 25_796_465,
    "bronze_eaglei_2023": 26_101_051,
    "bronze_eaglei_2024": 27_701_334,
    "bronze_eaglei_mcc": 3_234,
    "bronze_state_regions": 53,
    "bronze_noaa_storm_events": 215_282,
    "bronze_nws_zone_county": 28_391,
    "bronze_eia861_reliability": 3_042,
    "bronze_eia861_sales": 8_791,
    "bronze_eia861_service_territory": 35_616,
    "bronze_oe417": 742,
    "bronze_noaa_state_codes": 69,
    "bronze_oe417_event_types": 43,
    "bronze_state_time_zones": 53,
    "silver_eia_state_customers": 168,
    "silver_utility_reliability": 2_908,
    "silver_nws_zone_versions": 6,
    "silver_nws_zone_county": 28_209,
    "silver_storm_event_details": 215_282,
    "silver_storm_events": 232_414,
    "silver_storm_events_unplaced": 8_756,
    "silver_oe417_rows": 738,
    "silver_oe417_locations": 1_972,
    "silver_oe417": 738,
    "dim_county_customers": 3_063,
    "silver_outages": 79_598_850,
    "gold_collection_runs": 105_216,
    "gold_event_thresholds": 3_063,
    "gold_feed_dropouts": 19_190,
    "gold_outage_events": 446_261,
    "gold_state_coverage": 53,
    "bronze_storm_event_severity": 54,
    "gold_event_storm_match": 446_261,
    "gold_county_reliability": 9_189,
    "gold_state_reliability": 159,
    "gold_utility_reliability": 2_204,
    "gold_utility_reliability_other": 704,
    "gold_oe417_check": 738,
}
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
    "feed gaps per year (D3)": [("2022", "3"), ("2023", "16"), ("2024", "41")],
    "events per year": [("2022", "149695"), ("2023", "144747"), ("2024", "151819")],
    "dropouts per year (D19)": [("2022", "6793"), ("2023", "5782"), ("2024", "6615")],
    "exceeds_customers rows per year (D4, D21, D35, D36)": [("2022", "1841"), ("2023", "365"), ("2024", "8437")],
    "denominator sources (D13)": [("NULL", "2"), ("max_mcc_2024", "372"), ("mcc", "2"),
                                  ("total_customers_2024", "2687")],
    "calibrated states and counties (D21)": [("5", "246")],
    "counties held at their peak (D35)": [("11",)],
    "counties with the floor skipped (D36)": [("46063",)],
    "storm events unplaced by reason (D30)": [("territory_not_tracked", "180"), ("water", "8544"),
                                              ("zone_not_in_file", "32")],
    "reliability rows by standard (D32)": [("IEEE 1366", "2204"), ("other", "704")],
    "OE-417 incidents per year (D33)": [("2022", "390"), ("2023", "348")],
    "states below 70% coverage (D22)": [("0",)],
    "storm-matched events per year (D37)": [("2022", "14566"), ("2023", "15631"), ("2024", "15262")],
    "rank 1 state per year (D38)": [("2022", "PR"), ("2023", "VI"), ("2024", "VI")],
    "ranked counties per year (D38)": [("2022", "3020"), ("2023", "3020"), ("2024", "3020")],
    "utility rows flagged as source errors (D39)": [("2023", "54913")],
    "OE-417 check status (D40)": [("matched", "180"), ("no county", "185"), ("no time", "70"), ("not matched", "303")],
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
    "storm-matched events per year (D37)":
        "SELECT CAST(event_year AS STRING), CAST(COUNT_IF(storm_type <> 'unmatched') AS STRING) "
        "FROM gold_event_storm_match GROUP BY 1 ORDER BY 1",
    "rank 1 state per year (D38)":
        "SELECT CAST(year AS STRING), state_abbr FROM gold_state_reliability WHERE national_rank = 1 ORDER BY 1",
    "ranked counties per year (D38)":
        "SELECT CAST(year AS STRING), CAST(COUNT_IF(ranking_eligible) AS STRING) FROM gold_county_reliability GROUP BY 1 ORDER BY 1",
    "utility rows flagged as source errors (D39)":
        "SELECT CAST(data_year AS STRING), utility_number FROM gold_utility_reliability WHERE data_quality_flag IS NOT NULL ORDER BY 1",
    "OE-417 check status (D40)":
        "SELECT match_status, CAST(COUNT(*) AS STRING) FROM gold_oe417_check GROUP BY 1 ORDER BY 1",
}

FORBIDDEN = re.compile(r"\b(DROP|ALTER|TRUNCATE|DELETE|GRANT|REVOKE)\b", re.I)
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


def split_statements(text: str) -> list[str]:
    """Split SQL on semicolons outside string literals, backticks and -- comments."""
    statements, buf = [], []
    i, n = 0, len(text)
    quote = None
    while i < n:
        ch = text[i]
        if quote:
            buf.append(ch)
            if ch == quote:
                if quote == "'" and i + 1 < n and text[i + 1] == "'":
                    buf.append("'")
                    i += 1
                else:
                    quote = None
        elif ch in ("'", "`", '"'):
            quote = ch
            buf.append(ch)
        elif ch == "-" and text.startswith("--", i):
            j = text.find("\n", i)
            j = n if j == -1 else j
            buf.append(text[i:j])
            i = j
            continue
        elif ch == ";":
            stmt = "".join(buf).strip()
            if strip_comments(stmt):
                statements.append(stmt)
            buf = []
        else:
            buf.append(ch)
        i += 1
    tail = "".join(buf).strip()
    if strip_comments(tail):
        statements.append(tail)
    return statements


def strip_comments(stmt: str) -> str:
    return "\n".join(line for line in stmt.splitlines() if not line.strip().startswith("--")).strip()


def without_literals(stmt: str) -> str:
    """The statement with string literals and comments removed, for safety checks."""
    s = re.sub(r"'(?:[^']|'')*'", "''", stmt)
    return re.sub(r"--[^\n]*", "", s)


def check_safe(stmt: str) -> None:
    code = without_literals(stmt)
    if FORBIDDEN.search(code):
        raise Stop(f"Refused (forbidden keyword {FORBIDDEN.search(code).group(1)}):\n{summary(stmt)}")
    for cat, sch, _ in THREE_PART.findall(code):
        if (cat.lower(), sch.lower()) != (CATALOG, SCHEMA):
            raise Stop(f"Refused (object outside {CATALOG}.{SCHEMA}: {cat}.{sch}):\n{summary(stmt)}")
    m = re.search(r"\bCREATE\s+SCHEMA\s+(?:IF\s+NOT\s+EXISTS\s+)?([\w.]+)", code, re.I)
    if m and m.group(1).lower() != f"{CATALOG}.{SCHEMA}":
        raise Stop(f"Refused (schema {m.group(1)} is not {CATALOG}.{SCHEMA})")


def summary(stmt: str) -> str:
    lines = [l.strip() for l in strip_comments(stmt).splitlines() if l.strip()]
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


def step_convert() -> None:
    con = duckdb.connect()
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
    print("Excel sources to raw-row Parquet (D27):")
    import raw_convert

    for out in raw_convert.ensure_converted():
        print(f"  {out.relative_to(REPO_ROOT)}")


def upload_list() -> list[tuple[Path, str]]:
    items = [(RAW / "eaglei_parquet" / str(y) / f"eaglei_outages_{y}.parquet",
              f"{VOLUME}/eaglei_parquet/{y}/eaglei_outages_{y}.parquet") for y in YEARS]
    for name in ("MCC.csv", "coverage_history.csv", "DQI.csv"):
        items.append((RAW / "eaglei" / "metadata" / name, f"{VOLUME}/eaglei/metadata/{name}"))
    ref = REPO_ROOT / "data" / "reference"
    for name in ("state_regions.csv", "noaa_state_codes.csv", "oe417_event_types.csv", "state_time_zones.csv",
                 "storm_event_severity.csv"):
        items.append((ref / name, f"{VOLUME}/reference/{name}"))
    for p in sorted((RAW / "noaa_storm_events").rglob("StormEvents_details-*.csv.gz")):
        items.append((p, f"{VOLUME}/noaa_storm_events/{p.parent.name}/{p.name}"))
    for p in sorted((RAW / "nws_zone_county").rglob("bp*.dbx")):
        items.append((p, f"{VOLUME}/nws_zone_county/{p.parent.name}/{p.name}"))
    for folder in ("eia861_parquet", "oe417_parquet"):
        for p in sorted((RAW / folder).rglob("*.parquet")):
            items.append((p, f"{VOLUME}/{folder}/{p.parent.name}/{p.name}"))
    return items


def step_upload(w: WorkspaceClient, warehouse_id: str) -> None:
    # The schema and volume must exist first: run the setup statements of 01_bronze.sql.
    for stmt in split_statements((SQL_DIR / "01_bronze.sql").read_text()):
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


def step_sql(w: WorkspaceClient, warehouse_id: str) -> None:
    for name in SQL_FILES:
        statements = split_statements((SQL_DIR / name).read_text())
        print(f"\n{name}: {len(statements)} statements")
        for k, stmt in enumerate(statements, 1):
            head = summary(stmt)
            if SKIPPED.match(strip_comments(stmt)):
                print(f"  [{k:>2}] skip (session statement): {head}")
                continue
            started = time.time()
            rows = run_sql(w, warehouse_id, stmt)
            print(f"  [{k:>2}] ok {time.time() - started:6.1f}s  {head}")
            if re.match(r"^\s*SELECT\b", strip_comments(stmt), re.I):
                for row in rows[:12]:
                    print(f"         {row}")


def step_verify(w: WorkspaceClient, warehouse_id: str) -> None:
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
        print(f"  {table:<24} {n:>14,} {exp if exp is None else format(exp, ','):>14}{flag}")

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
    for k, (row, (exp_id, exp_hours)) in enumerate(zip(rows, EXPECTED_TOP10), 1):
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


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--steps", default="check,convert,upload,sql,verify")
    args = parser.parse_args()
    steps = [s.strip() for s in args.steps.split(",")]
    try:
        w = warehouse_id = None
        if any(s != "convert" for s in steps):
            w, warehouse_id = connect()
        for step in steps:
            print(f"\n=== {step} ===")
            if step == "check":
                step_check(w, warehouse_id)
            elif step == "convert":
                step_convert()
            elif step == "upload":
                step_upload(w, warehouse_id)
            elif step == "sql":
                step_sql(w, warehouse_id)
            elif step == "verify":
                step_verify(w, warehouse_id)
            else:
                raise Stop(f"Unknown step {step}")
    except Stop as e:
        print(f"\nSTOPPED: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
