"""Build the whole pipeline into a DuckDB file, the source for the local dbt target (D66).

Runs every SQL file of sql/databricks/ with scripts/duckdb_pipeline.py, as a full rebuild, on the
test fixture (default) or on the full raw data, and leaves the Silver and Gold tables in the file.

Usage:
    uv run python scripts/build_duckdb.py                                   # tests/fixtures/
    uv run python scripts/build_duckdb.py --root data/raw --out build/duckdb/full.duckdb
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

import duckdb_pipeline

REPO_ROOT = Path(__file__).resolve().parent.parent


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default="tests/fixtures", help="local files with the volume layout")
    parser.add_argument("--out", default="build/duckdb/fixture.duckdb", help="DuckDB file to write")
    args = parser.parse_args()
    out = REPO_ROOT / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.unlink(missing_ok=True)  # a fresh build, never a mix with an earlier one
    started = time.time()
    con = duckdb_pipeline.connect(str(out))
    if args.root != "tests/fixtures":
        tmp = REPO_ROOT / ".tmp"
        tmp.mkdir(exist_ok=True)
        con.execute(f"SET temp_directory = '{tmp.as_posix()}'")
        con.execute("SET preserve_insertion_order = false")
    tables = duckdb_pipeline.run_all(con, REPO_ROOT / args.root)
    con.close()
    print(f"{out.relative_to(REPO_ROOT)}: {len(tables)} tables from {args.root} in {time.time() - started:.0f}s")


if __name__ == "__main__":
    main()
