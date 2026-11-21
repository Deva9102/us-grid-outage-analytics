"""Run the data quality gates in sql/databricks/90_quality_checks.sql (D48).

Each statement in the file returns rows of (layer, check_name, observed, expected, passed). The
checks of a layer run after that layer is built (scripts/run_databricks.py calls run_layers after
Bronze, Silver and Gold) or all at once with this script. Every result row is written to
gold_quality_results with the run timestamp; any failed check stops the run with a clear error.

Engines:
    databricks  runs on the SQL warehouse against workspace.outages and appends to
                workspace.outages.gold_quality_results
    duckdb      builds the whole pipeline locally from data/raw (as scripts/test_gold_analysis_duckdb.py
                does), runs the same SQL translated by scripts/sql_dialect.py, keeps the results in a
                DuckDB table and writes them to logs/quality_results_<timestamp>.csv

Usage:
    uv run python scripts/quality_checks.py --engine databricks
    uv run python scripts/quality_checks.py --engine duckdb [--duckdb-file logs/pipeline.duckdb]
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

import pipeline_config
from pipeline_log import LOG_DIR, RunLog

REPO_ROOT = Path(__file__).resolve().parent.parent
CHECKS_SQL = REPO_ROOT / "sql" / "databricks" / "90_quality_checks.sql"
LAYERS = ("bronze", "silver", "gold")
LAYER_MARK = re.compile(r"^-- @layer (\w+)\s*$", re.M)

Row = tuple[str, str, float, str, bool]


class QualityFailed(Exception):
    """One or more quality checks failed."""


def statements_by_layer() -> dict[str, list[str]]:
    """Rendered statements of 90_quality_checks.sql grouped by their -- @layer section."""
    from run_databricks import split_statements

    text = CHECKS_SQL.read_text()
    marks = list(LAYER_MARK.finditer(text))
    found = [m.group(1) for m in marks]
    if found != list(LAYERS):
        raise QualityFailed(f"{CHECKS_SQL.name}: expected sections {list(LAYERS)}, found {found}")
    out: dict[str, list[str]] = {}
    for k, m in enumerate(marks):
        end = marks[k + 1].start() if k + 1 < len(marks) else len(text)
        out[m.group(1)] = split_statements(pipeline_config.render(text[m.end():end]))
    return out


def _to_row(raw) -> Row:
    layer, name, observed, expected, passed = raw
    if isinstance(passed, str):
        passed = passed.strip().lower() == "true"
    return (str(layer), str(name), float(observed) if observed is not None else float("nan"),
            str(expected), bool(passed))


def run_layers(execute: Callable[[str], list], layers, log: RunLog | None = None) -> list[Row]:
    """Run the checks of the given layers; execute(sql) returns result rows."""
    sections = statements_by_layer()
    rows: list[Row] = []
    for layer in layers:
        layer_rows: list[Row] = []
        for stmt in sections[layer]:
            layer_rows.extend(_to_row(r) for r in execute(stmt))
        failed = [r for r in layer_rows if not r[4]]
        print(f"  quality {layer}: {len(layer_rows) - len(failed)}/{len(layer_rows)} checks passed")
        if log:
            log.info("quality %s: %d checks, %d failed", layer, len(layer_rows), len(failed))
            for r in layer_rows:
                log.info("check %-6s %-4s %s observed=%s expected=%s", r[0], "ok" if r[4] else "FAIL", r[1], r[2], r[3])
        rows.extend(layer_rows)
    return rows


def raise_on_failure(rows: list[Row]) -> None:
    failed = [r for r in rows if not r[4]]
    if failed:
        lines = [f"{r[0]}: {r[1]} (observed {r[2]:g}, expected {r[3]})" for r in failed]
        raise QualityFailed(f"{len(failed)} quality check(s) failed:\n  " + "\n  ".join(lines))


def _sql_str(s: str) -> str:
    return "'" + s.replace("'", "''") + "'"


def results_table_sql() -> str:
    table = pipeline_config.get("quality.results_table")
    return f"""CREATE TABLE IF NOT EXISTS {table} (
    run_ts      TIMESTAMP COMMENT 'Start of the quality run, UTC',
    engine      STRING    COMMENT 'databricks or duckdb',
    layer       STRING    COMMENT 'bronze, silver or gold',
    check_name  STRING    COMMENT 'What the check asserts',
    observed    DOUBLE    COMMENT 'Measured value: bad rows for most checks, the row count for count checks',
    expected    STRING    COMMENT 'Value or range that passes',
    passed      BOOLEAN   COMMENT 'True when the check passed'
)
COMMENT 'Data quality gate results, one row per check per run (D48)'"""


def insert_sql(run_ts: datetime, engine: str, rows: list[Row]) -> str:
    table = pipeline_config.get("quality.results_table")
    ts = f"TIMESTAMP '{run_ts:%Y-%m-%d %H:%M:%S}'"
    values = ",\n".join(
        f"({ts}, {_sql_str(engine)}, {_sql_str(r[0])}, {_sql_str(r[1])}, "
        f"{'NULL' if r[2] != r[2] else repr(r[2])}, {_sql_str(r[3])}, {'TRUE' if r[4] else 'FALSE'})"
        for r in rows
    )
    return f"INSERT INTO {table} VALUES\n{values}"


def write_csv(run_ts: datetime, engine: str, rows: list[Row]) -> Path:
    LOG_DIR.mkdir(exist_ok=True)
    path = LOG_DIR / f"quality_results_{run_ts:%Y%m%d_%H%M%S}.csv"
    with path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["run_ts", "engine", "layer", "check_name", "observed", "expected", "passed"])
        for r in rows:
            w.writerow([f"{run_ts:%Y-%m-%d %H:%M:%S}", engine, *r])
    return path


# -----------------------------------------------------------------------------
# Engines
# -----------------------------------------------------------------------------

def databricks_gate(w, warehouse_id: str, layers, log: RunLog | None, run_ts: datetime) -> list[Row]:
    """Run checks on Databricks, append the results, raise QualityFailed on any failure."""
    from run_databricks import run_sql

    rows = run_layers(lambda sql: run_sql(w, warehouse_id, sql), layers, log)
    run_sql(w, warehouse_id, results_table_sql())
    run_sql(w, warehouse_id, insert_sql(run_ts, "databricks", rows))
    raise_on_failure(rows)
    return rows


def duckdb_connection(db_file: Path | None, log: RunLog):
    """A DuckDB connection with the pipeline built; reuses db_file when it already holds Gold."""
    import duckdb

    con = duckdb.connect(str(db_file) if db_file else ":memory:")
    con.execute("SET TimeZone = 'UTC'")
    built = con.execute(
        "SELECT COUNT(*) FROM information_schema.tables WHERE table_name = 'gold_oe417_check'").fetchone()[0]
    if built:
        print(f"Reusing the pipeline built in {db_file}")
        return con
    import test_gold_analysis_duckdb as analysis

    with log.step("duckdb build") as s:
        analysis.build(con)
        s.rows = con.execute("SELECT COUNT(*) FROM gold_outage_events").fetchone()[0]
    return con


def duckdb_gate(con, layers, log: RunLog, run_ts: datetime) -> list[Row]:
    import sql_dialect

    rows = run_layers(lambda sql: con.execute(sql_dialect.to_duckdb(sql)).fetchall(), layers, log)
    con.execute(_duckdb_results_table())
    con.execute(insert_sql(run_ts, "duckdb", rows))
    path = write_csv(run_ts, "duckdb", rows)
    print(f"  results: {path.relative_to(REPO_ROOT)}")
    raise_on_failure(rows)
    return rows


def _duckdb_results_table() -> str:
    """The results table without column comments, which DuckDB does not accept inline."""
    return re.sub(r"\s+COMMENT '(?:[^']|'')*'", "", results_table_sql())


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--engine", choices=("databricks", "duckdb"), default="databricks")
    parser.add_argument("--layers", default=",".join(LAYERS))
    parser.add_argument("--duckdb-file", type=Path, help="persist (or reuse) the local DuckDB build")
    args = parser.parse_args()
    layers = [x.strip() for x in args.layers.split(",")]
    if any(x not in LAYERS for x in layers):
        print(f"--layers must be from {LAYERS}", file=sys.stderr)
        return 2
    log = RunLog(f"quality_{args.engine}")
    run_ts = datetime.now(timezone.utc).replace(microsecond=0, tzinfo=None)
    try:
        if args.engine == "duckdb":
            con = duckdb_connection(args.duckdb_file, log)
            with log.step("quality checks (duckdb)") as s:
                rows = duckdb_gate(con, layers, log, run_ts)
                s.rows = len(rows)
        else:
            from run_databricks import connect

            w, warehouse_id = connect()
            with log.step("quality checks (databricks)") as s:
                rows = databricks_gate(w, warehouse_id, layers, log, run_ts)
                s.rows = len(rows)
        print(f"All {len(rows)} quality checks passed.")
        return 0
    except QualityFailed as e:
        print(f"\nQUALITY GATE FAILED: {e}", file=sys.stderr)
        return 1
    except Exception as e:  # connection or SQL errors: stop with the message, never a credential
        print(f"\nSTOPPED: {e}", file=sys.stderr)
        return 1
    finally:
        log.summary()


if __name__ == "__main__":
    sys.exit(main())
