"""Build the restoration-forecast feature tables (D71) on DuckDB or Databricks.

Runs sql/databricks/04_gold_forecast_features.sql, rendered from config/pipeline.yml like every
pipeline file, after the Gold tables exist. It is a separate stage from the main pipeline
(run_databricks.SQL_FILES) until the forecast model is settled, so a change here can never stop
the reliability pipeline. Every statement passes the runner's safety check before it is sent.

After the build it prints a checksum of gold_restoration_features (rows and column sums), the
same query on both engines, so a DuckDB build and a Databricks build can be compared.

Usage:
    uv run python scripts/forecast_features.py                                  # build/duckdb/full.duckdb
    uv run python scripts/forecast_features.py --duckdb-file build/duckdb/fixture.duckdb
    uv run python scripts/forecast_features.py --engine databricks
"""

from __future__ import annotations

import argparse
from pathlib import Path

import duckdb_pipeline
import pipeline_config
from sql_split import split_statements, strip_comments

REPO_ROOT = Path(__file__).resolve().parent.parent
FORECAST_FILES = ["04_gold_forecast_features.sql"]

# Rows and rounded column sums: equal on both engines when the features are equal.
CHECKSUM_SQL = """
SELECT
    split,
    COUNT(*)                                                   AS events,
    ROUND(CAST(SUM(duration_hours) AS DECIMAL(38, 6)), 2)      AS duration_hours,
    SUM(customers_out_at_start)                                AS out_start,
    SUM(customers_out_at_mid)                                  AS out_mid,
    SUM(customers_out_at_prediction)                           AS out_prediction,
    SUM(peak_customers_out_so_far)                             AS peak_so_far,
    COUNT_IF(feed_gap_so_far)                                  AS feed_gap,
    COUNT_IF(dropout_so_far)                                   AS dropout,
    COUNT_IF(storm_family_at_start <> 'No storm matched')      AS with_storm,
    SUM(start_hour_local * 10 + start_weekday_local)           AS local_time,
    SUM(prior_event_count)                                     AS prior_events,
    ROUND(CAST(SUM(prior_eligible_median_duration_hours) AS DECIMAL(38, 6)), 2) AS prior_median
FROM gold_restoration_features
GROUP BY split
ORDER BY split
"""


def statements() -> list[str]:
    out = []
    for name in FORECAST_FILES:
        out += split_statements(pipeline_config.render((duckdb_pipeline.SQL_DIR / name).read_text()))
    return out


def build_duckdb(path: Path) -> list[tuple]:
    con = duckdb_pipeline.connect(str(path))
    for name in FORECAST_FILES:
        print(f"{name}: {duckdb_pipeline.run_file(con, name, REPO_ROOT / 'tests' / 'fixtures')}")
    rows = con.execute(CHECKSUM_SQL).fetchall()
    con.close()
    return rows


def build_databricks() -> list[list[str]]:
    import run_databricks  # needs .env only for this engine

    w, warehouse_id = run_databricks.connect()
    for stmt in statements():
        if run_databricks.SKIPPED.match(strip_comments(stmt)):
            continue  # catalog and schema go with every statement (run_databricks.run_sql)
        print(f"  {run_databricks.summary(stmt)}")
        run_databricks.run_sql(w, warehouse_id, stmt)
    return run_databricks.run_sql(w, warehouse_id, CHECKSUM_SQL)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--engine", choices=["duckdb", "databricks"], default="duckdb")
    parser.add_argument("--duckdb-file", default="build/duckdb/full.duckdb", help="DuckDB file with the Gold tables")
    args = parser.parse_args()
    if args.engine == "duckdb":
        path = REPO_ROOT / args.duckdb_file
        if not path.exists():
            raise SystemExit(f"{args.duckdb_file} not found: run scripts/build_duckdb.py first")
        rows = build_duckdb(path)
    else:
        rows = build_databricks()
    print("checksum (split, events, duration, out_start, out_mid, out_prediction, peak, feed_gap, dropout, "
          "with_storm, local_time, prior_events, prior_median):")
    for row in rows:
        print("  " + ", ".join(str(v) for v in row))


if __name__ == "__main__":
    main()
