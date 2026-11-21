"""Measure the D46 evidence for a reviewed ranking exclusion.

For a county-year and a candidate neighbouring county, uses the 15-minute runs where the county had
at least exclusions.min_county_customers_out customers out and the neighbour more than 0
(config/pipeline.yml), and reports:
    readings            number of such runs
    events              separate EAGLE-I events of the county containing them
    events_20plus       events with at least min_readings_per_event such runs
    median_ratio        median of county / neighbour
    cv_readings         coefficient of variation of the ratio over all runs
    cv_between_events   coefficient of variation of the per-event median ratio (events_20plus)
    meets_d46           readings, events_20plus, cv_between_events and neighbour size meet the
                        exclusions thresholds in config/pipeline.yml

Adjacency is not in the data: the reviewer chooses an adjacent neighbour and states it in the
exclusion's evidence.

Builds the pipeline in DuckDB from the local raw files (a few minutes). Nothing is written.

Usage:
    uv run python scripts/exclusion_evidence.py --county 48015 --year 2023 --neighbour 48157 [--neighbour 48201]
"""

from __future__ import annotations

import argparse

import duckdb

import pipeline_config
import test_gold_analysis_duckdb as analysis

# D46 entry criteria from config/pipeline.yml (exclusions).
_X = pipeline_config.load()["exclusions"]
MIN_OUT, MIN_READINGS, MIN_EVENTS = _X["min_county_customers_out"], _X["min_readings"], _X["min_events"]
MIN_PER_EVENT, MAX_CV, MIN_SIZE = _X["min_readings_per_event"], _X["max_cv_between_events"], _X["min_neighbour_size_ratio"]


def evidence(con, county: str, year: int, neighbour: str) -> dict:
    row = con.execute(f"""
        WITH x AS (
            SELECT s.customers_out * 1.0 / o.customers_out AS ratio,
                   (SELECT e.event_id FROM gold_outage_events e
                     WHERE e.fips_code = '{county}' AND s.reading_time >= e.event_start AND s.reading_time < e.event_end) AS event_id
            FROM silver_outages s
            JOIN silver_outages o ON o.fips_code = '{neighbour}' AND o.reading_time = s.reading_time AND o.customers_out > 0
            WHERE s.fips_code = '{county}' AND s.year = {year} AND s.customers_out >= {MIN_OUT}
        ),
        ev AS (SELECT event_id, MEDIAN(ratio) AS med FROM x WHERE event_id IS NOT NULL GROUP BY 1 HAVING COUNT(*) >= {MIN_PER_EVENT})
        SELECT COUNT(*), COUNT(DISTINCT event_id), MEDIAN(ratio), STDDEV_SAMP(ratio) / AVG(ratio),
               (SELECT COUNT(*) FROM ev), (SELECT STDDEV_SAMP(med) / AVG(med) FROM ev),
               (SELECT customers FROM dim_county_customers WHERE fips_code = '{county}'),
               (SELECT customers FROM dim_county_customers WHERE fips_code = '{neighbour}')
        FROM x
    """).fetchall()[0]
    n, events, med, cv, ev20, cv_ev, c_cust, n_cust = row
    meets = (n >= MIN_READINGS and ev20 >= MIN_EVENTS and cv_ev is not None and cv_ev <= MAX_CV
             and c_cust and n_cust and n_cust >= MIN_SIZE * c_cust)
    return {"county": county, "year": year, "neighbour": neighbour, "readings": n, "events": events,
            "events_20plus": ev20, "median_ratio": med, "cv_readings": cv, "cv_between_events": cv_ev,
            "county_customers": c_cust, "neighbour_customers": n_cust, "meets_d46": bool(meets)}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--county", required=True)
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--neighbour", action="append", required=True)
    args = parser.parse_args()
    con = duckdb.connect()
    con.execute("SET TimeZone = 'UTC'")
    analysis.build(con)
    for nb in args.neighbour:
        e = evidence(con, args.county, args.year, nb)
        print("\n" + "\n".join(f"  {k:<20} {v if not isinstance(v, float) else round(v, 3)}" for k, v in e.items()))


if __name__ == "__main__":
    main()
