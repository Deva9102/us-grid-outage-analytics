"""Profile the raw EAGLE-I yearly files with DuckDB and write docs/data_profile.md.

Raw files are only read, never modified. fips_code is forced to VARCHAR so that
type inference cannot hide lost leading zeros; the auto-detected types are
reported separately so the difference is visible.

Usage:
    uv run python scripts/profile_eaglei.py
    uv run python scripts/profile_eaglei.py --years 2022 2023 2024
"""

from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path

import duckdb

import pipeline_config

REPO_ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = REPO_ROOT / "data" / "raw" / "eaglei"
OUT_PATH = REPO_ROOT / "docs" / "data_profile.md"
DEFAULT_YEARS = pipeline_config.load()["years"]["list"]

# The customers-out measure has a different name in some years.
CUSTOMERS_OUT_ALIASES = ["customers_out", "sum"]


def csv_path(year: int) -> Path:
    return RAW_DIR / str(year) / f"eaglei_outages_{year}.csv"


def fmt(n) -> str:
    if n is None:
        return "NULL"
    if isinstance(n, float):
        return f"{n:,.2f}"
    if isinstance(n, int):
        return f"{n:,}"
    return str(n)


def profile_year(con: duckdb.DuckDBPyConnection, year: int) -> dict:
    path = csv_path(year).as_posix()

    inferred = con.execute(f"DESCRIBE SELECT * FROM read_csv('{path}')").fetchall()
    inferred_types = {row[0]: row[1] for row in inferred}
    columns = list(inferred_types)

    con.execute(
        f"""
        CREATE OR REPLACE TEMP TABLE t AS
        SELECT * FROM read_csv('{path}', types = {{'fips_code': 'VARCHAR'}})
        """
    )
    types = {row[0]: row[1] for row in con.execute("DESCRIBE t").fetchall()}
    measure = next(c for c in CUSTOMERS_OUT_ALIASES if c in columns)

    null_sql = ", ".join(f'COUNT(*) - COUNT("{c}") AS "{c}"' for c in columns)
    nulls = dict(zip(columns, con.execute(f"SELECT {null_sql} FROM t").fetchone()))

    stats = con.execute(
        f"""
        SELECT
            COUNT(*)                                   AS row_count,
            COUNT(DISTINCT fips_code)                  AS distinct_fips,
            COUNT(DISTINCT state)                      AS distinct_states,
            MIN(run_start_time)                        AS min_ts,
            MAX(run_start_time)                        AS max_ts,
            COUNT(DISTINCT run_start_time)             AS distinct_ts,
            MAX("{measure}")                           AS max_out,
            MIN("{measure}")                           AS min_out,
            AVG("{measure}")                           AS avg_out,
            COUNT(*) FILTER (WHERE "{measure}" < 0)    AS negative_out,
            COUNT(*) FILTER (WHERE "{measure}" = 0)    AS zero_out
        FROM t
        """
    ).fetchone()
    keys = ["row_count", "distinct_fips", "distinct_states", "min_ts", "max_ts", "distinct_ts",
            "max_out", "min_out", "avg_out", "negative_out", "zero_out"]
    result = dict(zip(keys, stats))

    fips_lengths = con.execute(
        """
        SELECT LENGTH(fips_code) AS len, COUNT(DISTINCT fips_code) AS codes, COUNT(*) AS rows
        FROM t GROUP BY 1 ORDER BY 1
        """
    ).fetchall()
    fips_checks = con.execute(
        """
        SELECT
            COUNT(DISTINCT fips_code) FILTER (WHERE LENGTH(fips_code) = 5 AND fips_code LIKE '0%'),
            COUNT(DISTINCT fips_code) FILTER (WHERE NOT regexp_full_match(fips_code, '[0-9]+')),
            COUNT(DISTINCT fips_code) FILTER (WHERE LENGTH(fips_code) < 5)
        FROM t
        """
    ).fetchone()
    short_examples = [r[0] for r in con.execute(
        "SELECT DISTINCT fips_code FROM t WHERE LENGTH(fips_code) < 5 ORDER BY 1 LIMIT 5"
    ).fetchall()]

    duplicates = con.execute(
        """
        SELECT COUNT(*) FROM (
            SELECT fips_code, run_start_time FROM t GROUP BY ALL HAVING COUNT(*) > 1
        )
        """
    ).fetchone()[0]
    off_grid = con.execute(
        """
        SELECT COUNT(*) FROM t
        WHERE EXTRACT(minute FROM run_start_time) % 15 <> 0 OR EXTRACT(second FROM run_start_time) <> 0
        """
    ).fetchone()[0]

    expected_slots = con.execute(
        f"""
        SELECT COUNT(*) FROM generate_series(
            TIMESTAMP '{year}-01-01', TIMESTAMP '{year}-12-31 23:45:00', INTERVAL 15 MINUTE)
        """
    ).fetchone()[0]
    missing_slots = con.execute(
        f"""
        SELECT COUNT(*) FROM (
            SELECT UNNEST(generate_series(
                TIMESTAMP '{year}-01-01', TIMESTAMP '{year}-12-31 23:45:00', INTERVAL 15 MINUTE)) AS ts
        ) g ANTI JOIN (SELECT DISTINCT run_start_time AS ts FROM t) d USING (ts)
        """
    ).fetchone()[0]
    off_grid_detail = con.execute(
        """
        SELECT run_start_time, COUNT(*) FROM t
        WHERE EXTRACT(minute FROM run_start_time) % 15 <> 0 OR EXTRACT(second FROM run_start_time) <> 0
        GROUP BY 1 ORDER BY 1 LIMIT 5
        """
    ).fetchall()

    top = con.execute(
        f"""
        SELECT fips_code, county, state, "{measure}", run_start_time
        FROM t ORDER BY "{measure}" DESC NULLS LAST LIMIT 5
        """
    ).fetchall()

    extra = {}
    if "total_customers" in columns:
        extra["out_gt_total"] = con.execute(
            f'SELECT COUNT(*) FROM t WHERE "{measure}" > total_customers'
        ).fetchone()[0]
        extra["total_customers_sum"] = con.execute(
            "SELECT SUM(tc) FROM (SELECT fips_code, MAX(total_customers) AS tc FROM t GROUP BY 1)"
        ).fetchone()[0]

    result.update(
        year=year, columns=columns, inferred_types=inferred_types, types=types, measure=measure,
        nulls=nulls, fips_lengths=fips_lengths, fips_zero_led=fips_checks[0],
        fips_non_numeric=fips_checks[1], fips_short=fips_checks[2], short_examples=short_examples,
        duplicates=duplicates, off_grid=off_grid, off_grid_detail=off_grid_detail,
        expected_slots=expected_slots, missing_slots=missing_slots,
        panel_density=result["row_count"] / (result["distinct_fips"] * expected_slots), top=top, size=csv_path(year).stat().st_size,
        **extra,
    )
    return result


def profile_mcc(con: duckdb.DuckDBPyConnection) -> dict:
    path = (RAW_DIR / "metadata" / "MCC.csv").as_posix()
    con.execute(f"CREATE OR REPLACE TEMP TABLE mcc AS SELECT * FROM read_csv('{path}', all_varchar = true)")
    cols = [r[0] for r in con.execute("DESCRIBE mcc").fetchall()]
    fips_col = cols[0]
    row = con.execute(
        f"""
        SELECT
            COUNT(*) FILTER (WHERE regexp_full_match("{fips_col}", '[0-9]+')),
            COUNT(*) FILTER (WHERE regexp_full_match("{fips_col}", '[0-9]+') AND LENGTH("{fips_col}") < 5),
            SUM(TRY_CAST("{cols[1]}" AS BIGINT)) FILTER (WHERE regexp_full_match("{fips_col}", '[0-9]+')),
            string_agg("{fips_col}" || ' = ' || "{cols[1]}", '; ')
                FILTER (WHERE NOT regexp_full_match("{fips_col}", '[0-9]+'))
        FROM mcc
        """
    ).fetchone()
    return {"columns": cols, "rows": row[0], "short": row[1], "customers": row[2], "non_county": row[3]}


def section(p: dict) -> str:
    lines = [f"## {p['year']}", ""]
    lines += [
        f"File: `data/raw/eaglei/{p['year']}/eaglei_outages_{p['year']}.csv` ({p['size'] / 1e9:.2f} GB)",
        "",
        "| Metric | Value |",
        "|---|---|",
        f"| Rows | {fmt(p['row_count'])} |",
        f"| Distinct FIPS codes | {fmt(p['distinct_fips'])} |",
        f"| Distinct states | {fmt(p['distinct_states'])} |",
        f"| Min timestamp | {p['min_ts']} |",
        f"| Max timestamp | {p['max_ts']} |",
        f"| Distinct timestamps | {fmt(p['distinct_ts'])} |",
        f"| Customers-out column | `{p['measure']}` |",
        f"| Max customers out | {fmt(p['max_out'])} |",
        f"| Min customers out | {fmt(p['min_out'])} |",
        f"| Mean customers out | {fmt(p['avg_out'])} |",
        f"| Rows with 0 customers out | {fmt(p['zero_out'])} |",
        f"| Rows with negative customers out | {fmt(p['negative_out'])} |",
        f"| Duplicate (fips_code, run_start_time) keys | {fmt(p['duplicates'])} |",
        f"| Rows with timestamps off the 15-minute grid | {fmt(p['off_grid'])} |",
        f"| Expected 15-minute slots in year | {fmt(p['expected_slots'])} |",
        f"| 15-minute slots with no rows at all | {fmt(p['missing_slots'])} |",
        f"| Panel density (rows / counties x slots) | {p['panel_density']:.1%} |",
    ]
    for ts, n in p["off_grid_detail"]:
        lines.append(f"| Off-grid timestamp {ts} | {fmt(n)} rows |")
    if "out_gt_total" in p:
        lines += [
            f"| Rows where customers out > total_customers | {fmt(p['out_gt_total'])} |",
            f"| Sum of total_customers (max per county) | {fmt(p['total_customers_sum'])} |",
        ]

    lines += ["", "### Columns", "", "| Column | Auto-detected type | Type used | Nulls |", "|---|---|---|---|"]
    for c in p["columns"]:
        lines.append(f"| `{c}` | {p['inferred_types'][c]} | {p['types'][c]} | {fmt(p['nulls'][c])} |")

    lines += ["", "### FIPS code format", "", "| Length | Distinct codes | Rows |", "|---|---|---|"]
    for length, codes, rows in p["fips_lengths"]:
        lines.append(f"| {length} | {fmt(codes)} | {fmt(rows)} |")
    lost = "yes" if p["fips_short"] else "no"
    lines += [
        "",
        f"- Leading zeros lost in the raw text: **{lost}** "
        f"({fmt(p['fips_short'])} codes shorter than 5 characters"
        + (f", e.g. {', '.join(p['short_examples'])}" if p["short_examples"] else "") + ").",
        f"- 5-digit codes starting with 0 (states 01-09): {fmt(p['fips_zero_led'])}.",
        f"- Non-numeric codes: {fmt(p['fips_non_numeric'])}.",
        f"- Auto-detected type for `fips_code` is {p['inferred_types']['fips_code']}"
        + (", so reading without a type override would drop leading zeros."
           if p["inferred_types"]["fips_code"] != "VARCHAR" else "."),
    ]

    lines += ["", "### Largest single readings", "", "| FIPS | County | State | Customers out | Time |", "|---|---|---|---|---|"]
    for fips, county, state, out, ts in p["top"]:
        lines.append(f"| {fips} | {county} | {state} | {fmt(out)} | {ts} |")
    lines.append("")
    return "\n".join(lines)


def comparison(profiles: list[dict]) -> str:
    all_cols: list[str] = []
    for p in profiles:
        for c in p["columns"]:
            if c not in all_cols:
                all_cols.append(c)
    years = [str(p["year"]) for p in profiles]
    lines = ["## Column comparison across years", "",
             "| Column | " + " | ".join(years) + " |",
             "|---|" + "---|" * len(years)]
    for c in all_cols:
        cells = [p["types"].get(c, "-") for p in profiles]
        lines.append(f"| `{c}` | " + " | ".join(cells) + " |")

    lines += ["", "| Metric | " + " | ".join(years) + " |", "|---|" + "---|" * len(years)]
    for label, key in [("Rows", "row_count"), ("Distinct FIPS", "distinct_fips"),
                       ("Distinct states", "distinct_states"), ("Distinct timestamps", "distinct_ts"),
                       ("Max customers out", "max_out"), ("Duplicate keys", "duplicates"),
                       ("Missing 15-min slots", "missing_slots"),
                       ("Off-grid rows", "off_grid")]:
        lines.append(f"| {label} | " + " | ".join(fmt(p[key]) for p in profiles) + " |")
    lines.append("| Panel density | " + " | ".join(f"{p['panel_density']:.1%}" for p in profiles) + " |")
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--years", type=int, nargs="+", default=DEFAULT_YEARS)
    args = parser.parse_args()

    con = duckdb.connect()
    profiles = []
    for year in args.years:
        print(f"Profiling {year} ...", flush=True)
        profiles.append(profile_year(con, year))
    mcc = profile_mcc(con)

    doc = [
        "# EAGLE-I Data Profile",
        "",
        f"Profiled on {date.today().isoformat()} with DuckDB {duckdb.__version__}, using "
        "`scripts/profile_eaglei.py`. Raw files are read only. `fips_code` is read as text so "
        "leading zeros are preserved; the auto-detected type is shown next to it.",
        "",
        comparison(profiles),
    ]
    doc += [section(p) for p in profiles]
    doc += [
        "## Reference: MCC.csv (modeled customers per county)",
        "",
        f"- Columns: {', '.join(f'`{c}`' for c in mcc['columns'])}",
        f"- County rows: {fmt(mcc['rows'])}",
        f"- Non-county rows (exclude when loading): {mcc['non_county'] or 'none'}",
        f"- FIPS codes shorter than 5 characters: {fmt(mcc['short'])} (leading zeros lost; pad to 5 before joining)",
        f"- Total modeled customers (county rows only): {fmt(mcc['customers'])}",
        "",
    ]
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text("\n".join(doc))
    print(f"Wrote {OUT_PATH.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
