"""Run the real pipeline SQL files in DuckDB, statement by statement (D51).

Every file in scripts/run_databricks.py SQL_FILES is rendered from config/pipeline.yml and split
into statements exactly as on Databricks. Each statement is then run in DuckDB:

    CREATE SCHEMA / CREATE VOLUME / USE / SET   skipped (Databricks session setup)
    Bronze  ... FROM read_files('<volume path>', ...)
            reads the matching local files instead (read_csv, every column as text, D14):
            the path, header, separator, encoding and column names come from the statement;
            _metadata.file_path becomes the local file name
    CREATE OR REPLACE TABLE t (columns) ...     column definitions without COMMENT / PARTITIONED BY
    INSERT OVERWRITE t <query>                  DELETE FROM t, then INSERT INTO t <query>
    CREATE OR REPLACE TABLE t COMMENT '..' AS   the query, translated by scripts/sql_dialect.py
    SELECT ...                                  the check queries run too, results discarded

The local files sit under one root with the volume layout, except that Parquet and gzipped CSV
uploads are plain CSV (tests/fixtures/ holds the sample; see tests/fixtures/README.md) and
reference/ is data/reference/.

Usage from tests:
    import duckdb_pipeline
    con = duckdb_pipeline.connect()
    duckdb_pipeline.run_all(con, Path("tests/fixtures"))
"""

from __future__ import annotations

import re
from pathlib import Path

import duckdb

import pipeline_config
import sql_dialect
from run_databricks import SQL_FILES, split_statements, strip_comments

REPO_ROOT = Path(__file__).resolve().parent.parent
SQL_DIR = REPO_ROOT / "sql" / "databricks"
REFERENCE_DIR = REPO_ROOT / "data" / "reference"

SKIPPED = re.compile(r"^\s*(USE|SET|CREATE\s+SCHEMA|CREATE\s+VOLUME)\b", re.I)
COMMENT_CLAUSE = re.compile(r"\s+COMMENT\s+'(?:[^']|'')*'", re.I)
PARTITION_CLAUSE = re.compile(r"\s+PARTITIONED\s+BY\s*\([^)]*\)", re.I)
CTAS = re.compile(r"^CREATE OR REPLACE TABLE (\w+)\s+COMMENT\s+'(?:[^']|'')*'\s+AS\s+(.*)$", re.S | re.I)
DDL = re.compile(r"^CREATE OR REPLACE TABLE (\w+)\s*\(", re.I)
INSERT_OVERWRITE = re.compile(r"^INSERT OVERWRITE (\w+)\s+(.*)$", re.S | re.I)
READ_FILES = re.compile(r"\bREAD_FILES\s*\(", re.I)
OPTION = re.compile(r"(\w+)\s*=>\s*('(?:[^']|'')*'|\w+)", re.I)
# Volume layout -> local layout: Parquet and gzipped uploads are stored as plain CSV.
LOCAL_PATHS = [
    (re.compile(r"^eaglei_parquet/(\w+)/$"), r"eaglei/\1/*.csv"),
    (re.compile(r"^eia861_parquet/(.*)\.parquet$"), r"eia861/\1.csv"),
    (re.compile(r"^oe417_parquet/(.*)\.parquet$"), r"oe417/\1.csv"),
    (re.compile(r"^noaa_storm_events/(.*)\.csv\.gz$"), r"noaa_storm_events/\1.csv"),
]


def connect(path: str = ":memory:") -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(path)
    con.execute("SET TimeZone = 'UTC'")  # raw timestamps are UTC (D1)
    return con


def _sql_str(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def local_files(volume_path: str, root: Path) -> list[Path]:
    """The local files that stand in for a read_files() path on the volume."""
    prefix = pipeline_config.get("project.volume_path") + "/"
    if not volume_path.startswith(prefix):
        raise ValueError(f"read_files path outside the volume: {volume_path}")
    rel = volume_path[len(prefix):]
    if rel.startswith("reference/"):
        base, rel = REFERENCE_DIR, rel[len("reference/"):]
    else:
        base = root
        for pattern, repl in LOCAL_PATHS:
            if pattern.match(rel):
                rel = pattern.sub(repl, rel)
                break
    files = sorted(base.glob(rel))
    if not files:
        raise FileNotFoundError(f"no local files for {volume_path} (looked for {base / rel})")
    return files


def bronze_sql(table: str, stmt: str, root: Path) -> str:
    """A Bronze CREATE ... FROM read_files(...) statement as a DuckDB read_csv of local files."""
    call = READ_FILES.search(stmt)
    args = stmt[call.end():stmt.rindex(")")]
    path = re.match(r"\s*'((?:[^']|'')*)'", args).group(1)
    opts = {k.lower(): v.strip("'") for k, v in OPTION.findall(args)}
    fmt = opts.get("format", "csv").lower()
    header = fmt == "parquet" or opts.get("header", "false").lower() == "true"
    params = [
        "all_varchar = true",
        f"header = {'true' if header else 'false'}",
        "filename = true",
        f"delim = {_sql_str(opts.get('sep', ','))}",
    ]
    if opts.get("encoding", "").upper() in ("ISO-8859-1", "LATIN1", "LATIN-1"):
        params.append("encoding = 'latin-1'")
    if "schema" in opts:
        names = [c.split()[0].strip("`") for c in opts["schema"].split(",")]
        params.append("names = [" + ", ".join(_sql_str(n) for n in names) + "]")
    files = "[" + ", ".join(_sql_str(p.as_posix()) for p in local_files(path, root)) + "]"
    return (f"CREATE OR REPLACE TABLE {table} AS\n"
            f"SELECT * EXCLUDE (filename), filename AS source_file, current_timestamp AS loaded_at\n"
            f"FROM read_csv({files}, {', '.join(params)})")


def to_duckdb(stmt: str, root: Path) -> list[str]:
    """DuckDB statements for one rendered Databricks statement (empty when it is skipped)."""
    code = strip_comments(stmt)
    if SKIPPED.match(code):
        return []
    if m := CTAS.match(code):
        table, query = m.groups()
        if READ_FILES.search(query):
            return [bronze_sql(table, code, root)]
        return [f"CREATE OR REPLACE TABLE {table} AS\n{sql_dialect.to_duckdb(query)}"]
    if DDL.match(code):
        return [PARTITION_CLAUSE.sub("", COMMENT_CLAUSE.sub("", code))]
    if m := INSERT_OVERWRITE.match(code):
        table, query = m.groups()
        return [f"DELETE FROM {table}", f"INSERT INTO {table}\n{sql_dialect.to_duckdb(query)}"]
    return [sql_dialect.to_duckdb(code)]


def file_statements(name: str, overrides: dict | None = None) -> list[str]:
    return split_statements(pipeline_config.render((SQL_DIR / name).read_text(), overrides))


def run_file(con, name: str, root: Path, overrides: dict | None = None, only: set[str] | None = None) -> list[str]:
    """Run one SQL file; returns the tables it created. only limits it to some tables."""
    created = []
    for stmt in file_statements(name, overrides):
        target = re.match(r"^(?:CREATE OR REPLACE TABLE|INSERT OVERWRITE)\s+(\w+)", strip_comments(stmt), re.I)
        if only is not None and (target is None or target.group(1) not in only):
            continue
        for sql in to_duckdb(stmt, root):
            try:
                con.execute(sql).fetchall()
            except duckdb.Error as e:
                raise RuntimeError(f"{name}: {e}\n--- statement ---\n{sql[:2000]}") from e
        if target and target.group(1) not in created:
            created.append(target.group(1))
    return created


def run_all(con, root: Path, overrides: dict | None = None) -> list[str]:
    """Run every pipeline SQL file in order against the local files under root."""
    created: list[str] = []
    for name in SQL_FILES:
        created += run_file(con, name, root, overrides)
    return created
