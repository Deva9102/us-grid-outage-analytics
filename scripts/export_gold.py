"""Export Gold tables to CSV for Power BI (D49).

Writes each table in export.tables (config/pipeline.yml) to data/gold_exports/<table>.csv. A table
whose CSV would exceed export.max_file_mb is written as one file per year instead
(<table>_<year>.csv), using its year column. Every file must end up under the limit, or the export
stops. Older files of the same table are replaced.

Engines:
    databricks  reads workspace.outages through the SQL warehouse (credentials from .env)
    duckdb      reads a local build made by scripts/quality_checks.py --duckdb-file

Usage:
    uv run python scripts/export_gold.py
    uv run python scripts/export_gold.py --engine duckdb --duckdb-file logs/pipeline.duckdb
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

import pipeline_config
from pipeline_log import RunLog

REPO_ROOT = Path(__file__).resolve().parent.parent
YEAR_COLUMNS = ("year", "event_year", "data_year", "report_year")


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
    cfg = pipeline_config.load()["project"]

    def read(table: str) -> pd.DataFrame:
        with conn.cursor() as cur:
            cur.execute(f"SELECT * FROM {cfg['catalog']}.{cfg['schema']}.{table}")
            return cur.fetchall_arrow().to_pandas()

    return read


def duckdb_reader(db_file: Path):
    import duckdb

    if not db_file.exists():
        raise SystemExit(f"{db_file} not found: build it with scripts/quality_checks.py --engine duckdb --duckdb-file")
    con = duckdb.connect(str(db_file), read_only=True)
    return lambda table: con.execute(f"SELECT * FROM {table}").fetchdf()


def write_table(df: pd.DataFrame, table: str, folder: Path, limit_bytes: int) -> list[tuple[Path, int, int]]:
    for old in list(folder.glob(f"{table}.csv")) + list(folder.glob(f"{table}_[0-9][0-9][0-9][0-9].csv")):
        old.unlink()
    text = df.to_csv(index=False)
    if len(text.encode()) <= limit_bytes:
        path = folder / f"{table}.csv"
        path.write_text(text)
        return [(path, len(df), path.stat().st_size)]
    year_col = next((c for c in YEAR_COLUMNS if c in df.columns), None)
    if year_col is None:
        raise SystemExit(f"{table}: CSV exceeds the limit and has no year column to split on")
    written = []
    for year, part in df.groupby(year_col, sort=True):
        path = folder / f"{table}_{int(year)}.csv"
        part.to_csv(path, index=False)
        size = path.stat().st_size
        if size > limit_bytes:
            raise SystemExit(f"{path.name}: {size / 1e6:.1f} MB is over the export limit even after splitting by year")
        written.append((path, len(part), size))
    return written


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--engine", choices=("databricks", "duckdb"), default="databricks")
    parser.add_argument("--duckdb-file", type=Path)
    args = parser.parse_args()
    cfg = pipeline_config.load()["export"]
    folder = REPO_ROOT / cfg["folder"]
    folder.mkdir(parents=True, exist_ok=True)
    limit = int(cfg["max_file_mb"] * 1024 * 1024)
    if args.engine == "duckdb" and not args.duckdb_file:
        parser.error("--duckdb-file is required with --engine duckdb")
    read = databricks_reader() if args.engine == "databricks" else duckdb_reader(args.duckdb_file)
    log = RunLog("export")
    try:
        for table in cfg["tables"]:
            with log.step(f"export {table}") as s:
                files = write_table(read(table), table, folder, limit)
                s.rows = sum(n for _, n, _ in files)
                s.note = ", ".join(f"{p.name} {size / 1e6:.1f} MB" for p, _, size in files)
                log.info("%s: %s", table, s.note)
    finally:
        log.summary()
    return 0


if __name__ == "__main__":
    sys.exit(main())
