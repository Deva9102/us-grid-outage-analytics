"""Export the dbt marts for Power BI (D70).

Small tables (mart_export.summary_tables in config/pipeline.yml) go to data/gold_exports/summary/
as CSV and are committed. Large tables (mart_export.release_tables) go to
data/gold_exports/release/ as Parquet; they are gitignored and published as assets of a GitHub
Release by scripts/publish_release.py. Rows are sorted on each table's key, so an unchanged mart
writes an identical file. data/gold_exports/summary/manifest.json lists every file with its rows,
columns, size and SHA-256, so a downloaded Parquet file can be checked.

CSV conventions: comma separated, UTF-8, header row, empty field for NULL, true/false for
booleans, timestamps as YYYY-MM-DD HH:MM:SS in UTC. Parquet keeps the warehouse types
(timestamps in UTC without a zone, Snappy compression, which Power BI Desktop reads).

Engines:
    databricks  the marts in workspace.outages, through the SQL warehouse (credentials from .env)
    duckdb      the marts in a local DuckDB file built by make dbt-test-local

Usage:
    uv run python scripts/export_marts.py                     # or: make export
    uv run python scripts/export_marts.py --engine duckdb --duckdb-file build/duckdb/fixture.duckdb
"""

from __future__ import annotations

import argparse
import atexit
import hashlib
import json
import os
import sys
from pathlib import Path

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.csv as pacsv
import pyarrow.parquet as pq
from dotenv import load_dotenv

import pipeline_config

REPO_ROOT = Path(__file__).resolve().parent.parent


def databricks_reader():
    from databricks import sql

    load_dotenv(REPO_ROOT / ".env")
    missing = [k for k in ("DATABRICKS_SERVER_HOSTNAME", "DATABRICKS_HTTP_PATH", "DATABRICKS_TOKEN")
               if not os.environ.get(k)]
    if missing:
        raise SystemExit(f"Missing in .env: {', '.join(missing)}")
    conn = sql.connect(
        server_hostname=os.environ["DATABRICKS_SERVER_HOSTNAME"].strip().removeprefix("https://").rstrip("/"),
        http_path=os.environ["DATABRICKS_HTTP_PATH"].strip(),
        access_token=os.environ["DATABRICKS_TOKEN"].strip(),
    )
    atexit.register(conn.close)
    project = pipeline_config.load()["project"]

    def read(table: str, key: str) -> pa.Table:
        with conn.cursor() as cur:
            cur.execute(f"SELECT * FROM {project['catalog']}.{project['schema']}.{table} ORDER BY {key}")
            return cur.fetchall_arrow()

    return read


def duckdb_reader(db_file: Path):
    import duckdb

    if not db_file.exists():
        raise SystemExit(f"{db_file} not found: build it with make dbt-test-local")
    con = duckdb.connect(str(db_file), read_only=True)
    con.execute("SET TimeZone = 'UTC'")
    return lambda table, key: con.sql(f"SELECT * FROM {table} ORDER BY {key}").to_arrow_table()


def utc_naive(table: pa.Table) -> pa.Table:
    """Timestamps as UTC wall-clock values without a zone: Power BI reads them as plain datetimes."""
    for i, field in enumerate(table.schema):
        if pa.types.is_timestamp(field.type):
            col = table.column(i)
            if field.type.tz:
                col = pc.cast(col, pa.timestamp(field.type.unit, tz="UTC")).cast(pa.timestamp(field.type.unit))
            table = table.set_column(i, field.name, pc.cast(col, pa.timestamp("us")))
    return table


def write_csv(table: pa.Table, path: Path) -> None:
    cols = []
    for field, col in zip(table.schema, table.columns, strict=True):
        if pa.types.is_timestamp(field.type):
            col = pc.strftime(pc.cast(col, pa.timestamp("s"), safe=False), format="%Y-%m-%d %H:%M:%S")
        elif pa.types.is_boolean(field.type):
            col = pc.if_else(col, "true", "false")
        cols.append(col)
    out = pa.table(cols, names=table.column_names)
    pacsv.write_csv(out, path, pacsv.WriteOptions(quoting_style="needed"))


def describe(path: Path, table: pa.Table) -> dict:
    return {
        "file": path.relative_to(REPO_ROOT).as_posix(),
        "rows": table.num_rows,
        "bytes": path.stat().st_size,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "columns": {f.name: str(f.type) for f in table.schema},
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--engine", choices=("databricks", "duckdb"), default="databricks")
    parser.add_argument("--duckdb-file", type=Path)
    args = parser.parse_args()
    if args.engine == "duckdb" and not args.duckdb_file:
        parser.error("--duckdb-file is required with --engine duckdb")
    cfg = pipeline_config.load()["mart_export"]
    summary_dir = REPO_ROOT / cfg["summary_folder"]
    release_dir = REPO_ROOT / cfg["release_folder"]
    for folder in (summary_dir, release_dir):
        folder.mkdir(parents=True, exist_ok=True)
    read = databricks_reader() if args.engine == "databricks" else duckdb_reader(args.duckdb_file)
    limit = cfg["max_summary_mb"] * 1024 * 1024

    manifest = {"engine": args.engine, "summary": {}, "release": {}}
    for table, key in cfg["summary_tables"].items():
        data = utc_naive(read(table, key))
        path = summary_dir / f"{table}.csv"
        write_csv(data, path)
        if path.stat().st_size > limit:
            raise SystemExit(f"{path.name}: {path.stat().st_size / 1e6:.1f} MB is over mart_export.max_summary_mb; "
                             "move the table to release_tables")
        manifest["summary"][table] = describe(path, data)
        print(f"  summary  {table:<28} {data.num_rows:>8,} rows  {path.stat().st_size / 1e6:6.2f} MB")
    for table, key in cfg["release_tables"].items():
        data = utc_naive(read(table, key))
        path = release_dir / f"{table}.parquet"
        pq.write_table(data, path, compression="snappy")
        manifest["release"][table] = describe(path, data)
        print(f"  release  {table:<28} {data.num_rows:>8,} rows  {path.stat().st_size / 1e6:6.2f} MB")
    (summary_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"  {cfg['summary_folder']}/manifest.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
