"""Check that the dbt marts match the Gold tables exactly (D66).

Compares row counts, events and customer-hours per year, the top 10 events and the rank 1 state
per year between each mart and the Gold table it is built from. Any difference stops with exit 1.

Usage:
    uv run python scripts/reconcile_marts.py --engine duckdb --duckdb-file build/duckdb/fixture.duckdb
    uv run python scripts/reconcile_marts.py --engine databricks
"""

from __future__ import annotations

import argparse
import sys

# (label, SQL on the marts, SQL on Gold). Both sides return rows of strings after formatting.
PAIRS = [
    ("rows: events", "SELECT COUNT(*) FROM fct_outage_events", "SELECT COUNT(*) FROM gold_outage_events"),
    ("rows: county reliability", "SELECT COUNT(*) FROM fct_county_reliability", "SELECT COUNT(*) FROM gold_county_reliability"),
    ("rows: state reliability", "SELECT COUNT(*) FROM fct_state_reliability", "SELECT COUNT(*) FROM gold_state_reliability"),
    ("rows: territory reliability", "SELECT COUNT(*) FROM fct_territory_reliability",
     "SELECT COUNT(*) FROM gold_territory_reliability"),
    ("rows: utility reliability", "SELECT COUNT(*) FROM fct_utility_reliability",
     "SELECT (SELECT COUNT(*) FROM gold_utility_reliability) + (SELECT COUNT(*) FROM gold_utility_reliability_other)"),
    ("rows: counties", "SELECT COUNT(*) FROM dim_county", "SELECT COUNT(*) FROM dim_county_customers"),
    ("events and customer-hours per year",
     "SELECT event_year, COUNT(*), ROUND(SUM(customer_hours_lost), 2) FROM fct_outage_events GROUP BY 1 ORDER BY 1",
     "SELECT event_year, COUNT(*), ROUND(SUM(customer_hours_lost), 2) FROM gold_outage_events GROUP BY 1 ORDER BY 1"),
    ("top 10 events",
     "SELECT event_id, ROUND(customer_hours_lost, 2), storm_type FROM fct_outage_events "
     "ORDER BY customer_hours_lost DESC, event_id LIMIT 10",
     "SELECT e.event_id, ROUND(e.customer_hours_lost, 2), m.storm_type FROM gold_outage_events AS e "
     "JOIN gold_event_storm_match AS m ON m.event_id = e.event_id ORDER BY e.customer_hours_lost DESC, e.event_id LIMIT 10"),
    ("rank 1 state per year",
     "SELECT year, state_abbr, ROUND(outage_hours_per_1000_customers, 4) FROM fct_state_reliability "
     "WHERE national_rank = 1 ORDER BY 1",
     "SELECT year, state_abbr, ROUND(outage_hours_per_1000_customers, 4) FROM gold_state_reliability "
     "WHERE national_rank = 1 ORDER BY 1"),
    ("rank 1 county per year",
     "SELECT year, fips_code FROM fct_county_reliability WHERE national_rank = 1 ORDER BY 1",
     "SELECT year, fips_code FROM gold_county_reliability WHERE national_rank = 1 ORDER BY 1"),
    ("ranked counties and states per year",
     "SELECT year, COUNT(*) FROM fct_county_reliability WHERE is_ranked GROUP BY 1 ORDER BY 1",
     "SELECT year, COUNT(*) FROM gold_county_reliability WHERE national_rank IS NOT NULL GROUP BY 1 ORDER BY 1"),
]


def fmt(rows) -> list[tuple[str, ...]]:
    out = []
    for row in rows:
        cells = []
        for v in row:
            try:
                f = float(v)
                cells.append(f"{f:.2f}" if f != int(f) else str(int(f)))
            except (TypeError, ValueError):
                cells.append(str(v))
        out.append(tuple(cells))
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--engine", choices=["duckdb", "databricks"], required=True)
    parser.add_argument("--duckdb-file", default="build/duckdb/fixture.duckdb")
    args = parser.parse_args()
    if args.engine == "duckdb":
        import duckdb

        con = duckdb.connect(args.duckdb_file, read_only=True)
        run = lambda sql: con.execute(sql).fetchall()  # noqa: E731
    else:
        import run_databricks

        w, wh = run_databricks.connect()
        run = lambda sql: run_databricks.run_sql(w, wh, sql)  # noqa: E731
    problems = 0
    for label, mart_sql, gold_sql in PAIRS:
        mart, gold = fmt(run(mart_sql)), fmt(run(gold_sql))
        ok = mart == gold
        problems += not ok
        shown = gold if len(gold) <= 4 else f"{len(gold)} rows"
        print(f"  {label:<38} {'match' if ok else 'DIFFERS'}  {shown}")
        if not ok:
            print(f"      mart: {mart}\n      gold: {gold}")
    print("All marts match Gold." if not problems else f"{problems} difference(s).")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
