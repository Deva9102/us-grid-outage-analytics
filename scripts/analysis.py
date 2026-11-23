"""Run the analysis queries, render the findings from their results, and check them (D68).

Every number in docs/findings.md and docs/case_study.md comes from a query in sql/analysis/:

    run     run every query (each "-- result: <name>" statement) on an engine and write
            docs/analysis_results/<name>.csv
    render  render docs/templates/*.md into docs/ from those CSV files
    check   rerun the queries, compare them with the committed CSV files, render the templates
            from the fresh results and compare with the committed docs; exit 1 on any difference

Template placeholders (docs/templates/):
    {{ name[0].column | fmt }}               a value of the first row (0-based)
    {{ name[col=value,col2=value].column | fmt }}   a value of the one row matching every filter
    {{ count(name) }}, {{ count(name[col=value]) }}  a row count
    {{ table name | cols=col:Header:fmt,... | rows=10 | where=col=value;col<=3 }}   a Markdown table
Filters compare text with = and numbers with <= or >=.
Formats: int (1,234), f0-f3 (fixed decimals with separators), m1 / m2 (millions, "21.2 M"),
pct0 / pct1 (a share as a percentage), dt (YYYY-MM-DD HH:MM), date (YYYY-MM-DD), raw (default).

Usage:
    uv run python scripts/analysis.py run --engine databricks
    uv run python scripts/analysis.py run --engine duckdb --duckdb-file build/duckdb/full.duckdb
    uv run python scripts/analysis.py render
    uv run python scripts/analysis.py check --engine databricks
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import decimal
import re
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SQL_DIR = REPO_ROOT / "sql" / "analysis"
RESULTS = REPO_ROOT / "docs" / "analysis_results"
TEMPLATES = REPO_ROOT / "docs" / "templates"
DOCS = REPO_ROOT / "docs"

RESULT_LINE = re.compile(r"^-- result: (\w+)\s*$", re.M)
FLOAT_TEXT = re.compile(r"^-?\d+\.\d*(?:[eE][-+]?\d+)?$|^-?\d+[eE][-+]?\d+$")
TS_TEXT = re.compile(r"^(\d{4}-\d{2}-\d{2})[T ](\d{2}:\d{2})(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]00:?00)?$")
PLACEHOLDER = re.compile(r"\{\{(.+?)\}\}", re.S)


# -----------------------------------------------------------------------------
# Queries
# -----------------------------------------------------------------------------

def statements() -> list[tuple[str, str]]:
    """(result name, SQL) for every "-- result:" statement, in file order."""
    out = []
    for path in sorted(SQL_DIR.glob("*.sql")):
        text = path.read_text()
        marks = list(RESULT_LINE.finditer(text))
        for i, m in enumerate(marks):
            end = marks[i + 1].start() if i + 1 < len(marks) else len(text)
            sql = text[m.end():end].strip().rstrip(";").strip()
            out.append((m.group(1), sql))
    names = [n for n, _ in out]
    if len(names) != len(set(names)):
        raise SystemExit("duplicate result names in sql/analysis/")
    return out


def normalise(v) -> str:
    """One text form per value on both engines: numbers without float noise, UTC minutes."""
    if v is None:
        return ""
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, int):
        return str(v)
    if isinstance(v, float | decimal.Decimal):
        return _num(float(v))
    if isinstance(v, dt.datetime):
        return v.strftime("%Y-%m-%d %H:%M")
    if isinstance(v, dt.date):
        return v.isoformat()
    s = str(v)
    if FLOAT_TEXT.match(s):
        return _num(float(s))
    if m := TS_TEXT.match(s):
        return f"{m.group(1)} {m.group(2)}"
    return s


def _num(x: float) -> str:
    text = f"{round(x, 6):.6f}".rstrip("0").rstrip(".")
    return "0" if text in ("-0", "") else text


def executor(engine: str, duckdb_file: str):
    """A function sql -> (column names, rows) for the engine."""
    if engine == "duckdb":
        import duckdb

        con = duckdb.connect(duckdb_file, read_only=True)
        con.execute("SET TimeZone = 'UTC'")

        def run(sql: str):
            cur = con.execute(sql)
            return [d[0] for d in cur.description], cur.fetchall()
        return run

    from databricks.sdk.service.sql import Disposition, ExecuteStatementRequestOnWaitTimeout, Format, StatementState

    import run_databricks

    w, warehouse_id = run_databricks.connect()

    def run(sql: str):
        run_databricks.check_safe(sql)
        resp = w.statement_execution.execute_statement(
            warehouse_id=warehouse_id, statement=sql, catalog=run_databricks.CATALOG, schema=run_databricks.SCHEMA,
            wait_timeout="50s", on_wait_timeout=ExecuteStatementRequestOnWaitTimeout.CONTINUE,
            disposition=Disposition.INLINE, format=Format.JSON_ARRAY)
        while resp.status.state in (StatementState.PENDING, StatementState.RUNNING):
            import time
            time.sleep(3)
            resp = w.statement_execution.get_statement(resp.statement_id)
        if resp.status.state != StatementState.SUCCEEDED:
            err = resp.status.error
            raise SystemExit(f"query failed: {err.message if err else resp.status.state}\n{sql[:300]}")
        cols = [c.name for c in resp.manifest.schema.columns]
        return cols, (resp.result.data_array or []) if resp.result else []
    return run


def run_all(engine: str, duckdb_file: str, out_dir: Path) -> dict[str, list[dict]]:
    run = executor(engine, duckdb_file)
    out_dir.mkdir(parents=True, exist_ok=True)
    results = {}
    for name, sql in statements():
        cols, rows = run(sql)
        table = [dict(zip(cols, (normalise(v) for v in row), strict=True)) for row in rows]
        with (out_dir / f"{name}.csv").open("w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=cols, lineterminator="\n")
            writer.writeheader()
            writer.writerows(table)
        results[name] = table
        print(f"  {name:<32} {len(table):>5} rows")
    return results


def load(results_dir: Path = RESULTS) -> dict[str, list[dict]]:
    out = {}
    for path in sorted(results_dir.glob("*.csv")):
        with path.open(newline="") as f:
            out[path.stem] = list(csv.DictReader(f))
    return out


# -----------------------------------------------------------------------------
# Templates
# -----------------------------------------------------------------------------

def fmt(value: str, spec: str) -> str:
    if value == "" and spec != "raw":
        return "–"
    match spec:
        case "raw" | "":
            return value
        case "int":
            return f"{round(float(value)):,}"
        case "f0" | "f1" | "f2" | "f3":
            return f"{float(value):,.{spec[1]}f}"
        case "m1" | "m2":
            return f"{float(value) / 1e6:,.{spec[1]}f} M"
        case "pct0" | "pct1":
            return f"{float(value) * 100:.{spec[3]}f}%"
        case "dt":
            return value[:16]
        case "date":
            return value[:10]
    raise ValueError(f"unknown format {spec!r}")


def select(results: dict, ref: str) -> list[dict]:
    """name or name[i] or name[col=value,...] -> the matching rows."""
    m = re.fullmatch(r"(\w+)(?:\[(.*)\])?", ref.strip())
    if not m or m.group(1) not in results:
        raise KeyError(f"unknown result in {ref!r}")
    rows = results[m.group(1)]
    sel = m.group(2)
    if sel is None:
        return rows
    if sel.strip().isdigit():
        return [rows[int(sel)]]
    return [r for r in rows if all(matches(r, cond) for cond in sel.split(","))]


def matches(row: dict, cond: str) -> bool:
    """col=value (text), or col<=number / col>=number."""
    m = re.fullmatch(r"\s*(\w+)\s*(<=|>=|=)\s*(.*?)\s*", cond)
    if not m:
        raise ValueError(f"bad filter {cond!r}")
    col, op, val = m.groups()
    if op == "=":
        return row[col] == val
    if row[col] == "":
        return False
    x, y = float(row[col]), float(val)
    return x <= y if op == "<=" else x >= y


def render_table(results: dict, spec: str) -> str:
    parts = [p.strip() for p in spec.split("|")]
    rows = select(results, parts[0])
    cols, limit, where = [], None, None
    for opt in parts[1:]:
        key, _, val = opt.partition("=")
        if key == "cols":
            cols = [c.split(":") + [""] * (3 - len(c.split(":"))) for c in val.split(",")]
        elif key == "rows":
            limit = int(val)
        elif key == "where":
            where = val.split(";")
    if where:
        rows = [r for r in rows if all(matches(r, c) for c in where)]
    rows = rows[:limit] if limit else rows
    head = "| " + " | ".join(h or c for c, h, _ in cols) + " |"
    align = "|" + "|".join("---:" if f and f not in ("raw", "dt", "date") else "---" for _, _, f in cols) + "|"
    body = ["| " + " | ".join(fmt(r[c], f or "raw") for c, _, f in cols) + " |" for r in rows]
    return "\n".join([head, align, *body])


def render_value(results: dict, expr: str) -> str:
    expr = expr.strip()
    if expr.startswith("table "):
        return render_table(results, expr[6:])
    if m := re.fullmatch(r"count\((.+)\)", expr):
        return f"{len(select(results, m.group(1))):,}"
    ref, _, spec = expr.partition("|")
    ref, _, column = ref.strip().rpartition(".")
    rows = select(results, ref)
    if len(rows) != 1:
        raise KeyError(f"{expr!r} matches {len(rows)} rows, not 1")
    return fmt(rows[0][column], spec.strip())


def render(results: dict) -> dict[str, str]:
    """{doc name: rendered text} for every template."""
    out = {}
    for path in sorted(TEMPLATES.glob("*.md")):
        text = path.read_text()
        out[path.name] = PLACEHOLDER.sub(lambda m, r=results: render_value(r, m.group(1)), text)
    return out


# -----------------------------------------------------------------------------
# Commands
# -----------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["run", "render", "check"])
    parser.add_argument("--engine", choices=["duckdb", "databricks"], default="databricks")
    parser.add_argument("--duckdb-file", default="build/duckdb/full.duckdb")
    args = parser.parse_args()

    if args.command == "run":
        run_all(args.engine, args.duckdb_file, RESULTS)
        return 0
    if args.command == "render":
        for name, text in render(load()).items():
            (DOCS / name).write_text(text)
            print(f"  docs/{name}")
        return 0

    problems = []
    with tempfile.TemporaryDirectory() as tmp:
        fresh = run_all(args.engine, args.duckdb_file, Path(tmp))
    committed = load()
    for name in sorted(set(fresh) | set(committed)):
        if fresh.get(name) != committed.get(name):
            problems.append(f"result {name}: the query no longer returns the committed rows")
    for name, text in render(fresh).items():
        if not (DOCS / name).exists() or (DOCS / name).read_text() != text:
            problems.append(f"docs/{name}: its numbers differ from the fresh query results")
    for p in problems:
        print(f"  DIFFERS  {p}")
    print("Every number in the docs matches the queries." if not problems else f"{len(problems)} difference(s).")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
