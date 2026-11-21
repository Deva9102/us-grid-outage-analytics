"""Translate the Databricks SQL in sql/databricks/ to DuckDB for local tests.

The .sql files are written for Databricks. The tests run the same statements in DuckDB after a
small set of rewrites, so local tests exercise the real code:

    explode(sequence(a, b, ...))      -> unnest(generate_series(a, b, ...))
    explode(x)                        -> unnest(x)
    unix_seconds(x)                   -> epoch(x)
    timestamp_seconds(x)              -> make_timestamp(CAST((x) AS BIGINT) * 1000000)
    try_to_timestamp(x, 'yyyyMMdd..') -> try_strptime(x, '%Y%m%d..')
    regexp_like(x, p)                 -> regexp_matches(x, p)
    regexp_replace(x, p, r)           -> regexp_replace(x, p, r, 'g')   (Databricks replaces all)
    split(x, p)                       -> regexp_split_to_array(x, p)
    cardinality(x)                    -> len(x)
    element_at(x, i)                  -> list_extract(x, i)
    array_sort(x)                     -> list_sort(x)
    to_utc_timestamp(x, tz)           -> CAST(timezone(tz, x) AS TIMESTAMP)   (session TimeZone = UTC)

Statements must have the form  CREATE OR REPLACE TABLE <name> COMMENT '...' AS <query>;
"""

from __future__ import annotations

import re
from pathlib import Path

JAVA_TO_STRFTIME = [("yyyy", "%Y"), ("MM", "%m"), ("M", "%m"), ("dd", "%d"), ("d", "%d"),
                    ("HH", "%H"), ("mm", "%M"), ("ss", "%S")]


def _split_args(s: str) -> list[str]:
    args, depth, quote, cur = [], 0, None, []
    for ch in s:
        if quote:
            cur.append(ch)
            if ch == quote:
                quote = None
            continue
        if ch in ("'", '"'):
            quote = ch
        elif ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        elif ch == "," and depth == 0:
            args.append("".join(cur).strip())
            cur = []
            continue
        cur.append(ch)
    args.append("".join(cur).strip())
    return args


def _rewrite_calls(sql: str, name: str, fn) -> str:
    """Rewrite every call name(...) using fn(list_of_args) -> replacement text."""
    pattern = re.compile(rf"(?<![A-Za-z0-9_]){name}\s*\(", re.I)
    out, pos = [], 0
    while True:
        m = pattern.search(sql, pos)
        if not m:
            out.append(sql[pos:])
            return "".join(out)
        start, i, depth, quote = m.end(), m.end(), 1, None
        while depth:
            ch = sql[i]
            if quote:
                if ch == quote:
                    quote = None
            elif ch in ("'", '"'):
                quote = ch
            elif ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
            i += 1
        inner = sql[start:i - 1]
        out.append(sql[pos:m.start()])
        out.append(fn([_rewrite_all(a) for a in _split_args(inner)]))
        pos = i


def _java_fmt(lit: str) -> str:
    fmt = lit.strip("'")
    out, i = [], 0
    while i < len(fmt):
        for java, c in JAVA_TO_STRFTIME:
            if fmt.startswith(java, i):
                out.append(c)
                i += len(java)
                break
        else:
            out.append(fmt[i])
            i += 1
    return "'" + "".join(out) + "'"


REWRITES = [
    ("explode", lambda a: f"unnest({a[0].replace('sequence(', 'generate_series(', 1) if a[0].lower().startswith('sequence(') else a[0]})"),
    ("sequence", lambda a: f"generate_series({', '.join(a)})"),
    ("unix_seconds", lambda a: f"epoch({a[0]})"),
    ("timestamp_seconds", lambda a: f"make_timestamp(CAST(({a[0]}) AS BIGINT) * 1000000)"),
    ("try_to_timestamp", lambda a: f"try_strptime({a[0]}, {_java_fmt(a[1])})"),
    ("regexp_like", lambda a: f"regexp_matches({a[0]}, {a[1]})"),
    ("regexp_replace", lambda a: f"regexp_replace({', '.join(a[:3])}, 'g')"),
    ("split", lambda a: f"regexp_split_to_array({a[0]}, {a[1]})"),
    ("cardinality", lambda a: f"len({a[0]})"),
    ("element_at", lambda a: f"list_extract({a[0]}, {a[1]})"),
    ("array_sort", lambda a: f"list_sort({a[0]})"),
    ("to_utc_timestamp", lambda a: f"CAST(timezone({a[1]}, {a[0]}) AS TIMESTAMP)"),
]


def _rewrite_all(sql: str) -> str:
    for name, fn in REWRITES:
        sql = _rewrite_calls(sql, name, fn)
    return sql


def to_duckdb(sql: str) -> str:
    return _rewrite_all(sql)


def table_statements(path: Path) -> list[tuple[str, str]]:
    """(table name, DuckDB query) for each CREATE OR REPLACE TABLE ... AS <query>; in a file."""
    text = path.read_text()
    pattern = re.compile(r"^CREATE OR REPLACE TABLE (\w+)\s*\nCOMMENT '(?:[^']|'')*'\s*\nAS\s*\n(.*?);\s*$", re.S | re.M)
    return [(name, to_duckdb(query)) for name, query in pattern.findall(text)]
