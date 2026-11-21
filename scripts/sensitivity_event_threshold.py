"""Sensitivity test for the event threshold share (D18), with feed-dropout handling (D19).

Builds Silver once on all three years in DuckDB, then runs the Gold queries from
sql/databricks/03_gold_events.sql (thresholds, dropouts, events) with different values of
event_share. Share 0 (flat 100, with D19) is the baseline whose top 10 storms are tracked.

For each share it reports events per year with median and 95th percentile duration, feed
dropouts, Pinellas FL (Helene and Milton must split), Wayne MI (ice storm and the March 3 storm
must split), Los Angeles CA May-June 2024 (background chain must break), Harris TX (Beryl must
stay whole), the baseline top 10, and the margin between each county's threshold and its exact
split point.

Split points. An event breaks when 4 consecutive active runs (collected runs minus the county's
dropout runs, D3/D19) are all below the threshold; missing rows count as 0. For a time window,
the critical threshold T* is the smallest 4-run maximum in the window: the event splits there
exactly when threshold > T*. The critical share is T* / customers.

Raw files are only read. Nothing is written.

Usage:
    uv run python scripts/sensitivity_event_threshold.py
"""

from __future__ import annotations

from datetime import datetime

import duckdb

import test_gold_events_duckdb as gold
import test_silver_duckdb as silver

SHARES = [0.0, 0.001, 0.0015, 0.0025, 0.005]

PINELLAS, WAYNE, LOS_ANGELES, HARRIS, FORT_BEND = "12103", "26163", "06037", "48201", "48157"


def label(share: float) -> str:
    return "flat 100" if share == 0 else f"{share * 100:g}%"


def tag(share: float) -> str:
    return "s" + f"{share:.4f}".replace(".", "_")


def show(con, sql: str) -> None:
    print(con.execute(sql).fetchdf().to_string(index=False))


def peak(con, fips: str, start: str, end: str):
    return con.execute(f"""
        SELECT arg_max(reading_time, customers_out), MAX(customers_out) FROM silver_outages
        WHERE fips_code = '{fips}' AND reading_time BETWEEN TIMESTAMP '{start}' AND TIMESTAMP '{end}'
    """).fetchone()


def critical_threshold(con, fips: str, start, end, dropouts: str) -> tuple[float, str]:
    """Smallest max over 4 consecutive active runs between start and end, and where it is."""
    return con.execute(f"""
        WITH
        runs AS (
            SELECT run_index, slot_time FROM gold_collection_runs
            WHERE is_collected AND slot_time > TIMESTAMP '{start}' AND slot_time < TIMESTAMP '{end}'
        ),
        drop_runs AS (
            SELECT DISTINCT unnest(generate_series(drop_start_run, recovery_run - 1)) AS run_index
            FROM {dropouts} WHERE fips_code = '{fips}'
        ),
        active AS (
            SELECT r.run_index, r.slot_time, COALESCE(s.customers_out, 0) AS c
            FROM runs r
            LEFT JOIN silver_outages s ON s.fips_code = '{fips}' AND s.reading_time = r.slot_time
            WHERE r.run_index NOT IN (SELECT run_index FROM drop_runs)
        ),
        windows AS (
            SELECT slot_time,
                   MAX(c) OVER (ORDER BY run_index ROWS BETWEEN 3 PRECEDING AND CURRENT ROW) AS wmax,
                   COUNT(*) OVER (ORDER BY run_index ROWS BETWEEN 3 PRECEDING AND CURRENT ROW) AS n
            FROM active
        )
        SELECT MIN(wmax), strftime(arg_min(slot_time, wmax), '%Y-%m-%d %H:%M') FROM windows WHERE n = 4
    """).fetchone()


def main() -> None:
    con = duckdb.connect()

    print("Building dim_county_customers and silver_outages (all years) ...", flush=True)
    silver.bronze(con, month_filter=None)
    con.execute(silver.DIM_SQL)
    for name, _, sql in silver.SILVER_STEPS:
        con.execute(f"CREATE OR REPLACE TABLE {name} AS {sql}")
    for name, _, _ in silver.SILVER_STEPS[:-1]:
        con.execute(f"DROP TABLE {name}")

    customers = dict(con.execute(f"""
        SELECT fips_code, customers FROM dim_county_customers
        WHERE fips_code IN ('{PINELLAS}', '{WAYNE}', '{LOS_ANGELES}', '{HARRIS}', '{FORT_BEND}')
    """).fetchall())

    for i, share in enumerate(SHARES):
        print(f"Building thresholds, dropouts and events for share {label(share)} ...", flush=True)
        gold.build_gold(con, share, skip=("gold_collection_runs",) if i else ())
        con.execute(f"CREATE OR REPLACE TABLE ev_{tag(share)} AS SELECT * FROM gold_outage_events")
        con.execute(f"CREATE OR REPLACE TABLE dr_{tag(share)} AS SELECT * FROM gold_feed_dropouts")

    # Fixed reference points: the time of the highest reading in each storm window.
    helene_t, helene_out = peak(con, PINELLAS, "2024-09-25", "2024-10-05")
    milton_t, milton_out = peak(con, PINELLAS, "2024-10-08", "2024-10-20")
    ice_t, ice_out = peak(con, WAYNE, "2023-02-22", "2023-03-01")
    march_t, march_out = peak(con, WAYNE, "2023-03-03", "2023-03-08")
    beryl_t, beryl_out = peak(con, HARRIS, "2024-07-07", "2024-07-12")
    # Beryl's main restoration: the week after the peak. A date is used, not "first reading below
    # x% of peak", because single dropout readings (D19) would end such a window too early.
    beryl_end = datetime(2024, 7, 16)
    print("\nReference peaks (UTC):")
    print(f"  Pinellas Helene {helene_t} ({helene_out:,}), Milton {milton_t} ({milton_out:,})")
    print(f"  Wayne ice storm {ice_t} ({ice_out:,}), March storm {march_t} ({march_out:,})")
    print(f"  Harris Beryl {beryl_t} ({beryl_out:,}); must stay one event through {beryl_end}")
    print(f"  Customers: {customers}")

    base = f"ev_{tag(0.0)}"
    con.execute(f"""
        CREATE TABLE base_top AS
        WITH top AS (
            SELECT *, ROW_NUMBER() OVER (ORDER BY customer_hours_lost DESC) AS base_rank
            FROM {base} QUALIFY base_rank <= 10
        )
        SELECT t.base_rank, t.event_id, t.fips_code, t.county, t.state_abbr, t.customer_hours_lost,
               arg_max(s.reading_time, s.customers_out) AS peak_time
        FROM top t JOIN silver_outages s
          ON s.fips_code = t.fips_code AND s.reading_time >= t.event_start AND s.reading_time < t.event_end
        GROUP BY ALL
    """)

    # Large baseline events (peak >= 10,000 customers out) and the time of each one's peak. A share
    # that leaves no event at that time has stopped counting a real outage.
    con.execute(f"""
        CREATE TABLE base_large AS
        SELECT e.event_id, e.fips_code, e.peak_customers_out, e.customer_hours_lost,
               arg_max(s.reading_time, s.customers_out) AS peak_time
        FROM {base} e JOIN silver_outages s
          ON s.fips_code = e.fips_code AND s.reading_time >= e.event_start AND s.reading_time < e.event_end
        WHERE e.peak_customers_out >= 10000
        GROUP BY ALL
    """)

    def event_at(ev: str, fips: str, ts) -> str | None:
        row = con.execute(f"""
            SELECT event_id FROM {ev} WHERE fips_code = '{fips}'
              AND TIMESTAMP '{ts}' >= event_start AND TIMESTAMP '{ts}' < event_end
        """).fetchone()
        return row[0] if row else None

    summary = []
    for share in SHARES:
        ev, dr = f"ev_{tag(share)}", f"dr_{tag(share)}"
        print("\n" + "=" * 100)
        print(f"SHARE {label(share)}  (with D19 dropout handling)")
        print("=" * 100)

        print("\nEvents and duration by year:")
        show(con, f"""
            SELECT event_year, COUNT(*) AS events,
                   ROUND(MEDIAN(duration_hours), 2) AS median_hours,
                   ROUND(QUANTILE_CONT(duration_hours, 0.95), 2) AS p95_hours,
                   ROUND(MAX(duration_hours), 1) AS max_hours,
                   COUNT(*) FILTER (WHERE spans_dropout) AS spans_dropout,
                   ROUND(SUM(customer_hours_lost) / 1e6, 1) AS customer_hours_m
            FROM {ev} GROUP BY 1 ORDER BY 1
        """)
        print("\nFeed dropouts by year:")
        show(con, f"SELECT dropout_year, COUNT(*) AS dropouts, SUM(dropout_runs) AS runs FROM {dr} GROUP BY 1 ORDER BY 1")
        hou = con.execute(f"""
            SELECT string_agg(fips_code || ' ' || strftime(dropout_start, '%H:%M') || '-' ||
                              strftime(dropout_end - INTERVAL 15 MINUTE, '%H:%M'), ', ' ORDER BY fips_code, dropout_start)
            FROM {dr} WHERE fips_code IN ('{HARRIS}', '{FORT_BEND}')
              AND dropout_start BETWEEN TIMESTAMP '2024-07-10 00:00' AND TIMESTAMP '2024-07-10 06:00'
        """).fetchone()[0]
        print(f"  Harris / Fort Bend dropouts 2024-07-10 00:00-06:00 UTC: {hou}")

        print("\n5 longest events:")
        show(con, f"""
            SELECT event_id, county, state_abbr AS st, ROUND(event_threshold) AS threshold,
                   strftime(event_start, '%Y-%m-%d') AS start_utc, strftime(event_end, '%Y-%m-%d') AS end_utc,
                   ROUND(duration_hours, 1) AS hours, ROUND(customer_hours_lost / 1e6, 2) AS cust_hours_m
            FROM {ev} ORDER BY duration_hours DESC LIMIT 5
        """)

        h, m = event_at(ev, PINELLAS, helene_t), event_at(ev, PINELLAS, milton_t)
        w1, w2 = event_at(ev, WAYNE, ice_t), event_at(ev, WAYNE, march_t)
        b1, b2 = event_at(ev, HARRIS, beryl_t), event_at(ev, HARRIS, beryl_end)
        pinellas_split = h is not None and m is not None and h != m
        wayne_split = w1 is not None and w2 is not None and w1 != w2
        # Beryl is whole when the event at the peak lasts at least until the main body ends.
        beryl_end_of_event = con.execute(f"SELECT event_end FROM {ev} WHERE event_id = '{b1}'").fetchone()[0]
        beryl_whole = beryl_end_of_event >= beryl_end
        print(f"\nPinellas: Helene in {h}, Milton in {m} -> {'SPLIT' if pinellas_split else 'MERGED'}")
        print(f"Wayne:    ice storm in {w1}, March storm in {w2} -> {'SPLIT' if wayne_split else 'MERGED'}")
        print(f"Harris:   Beryl peak event {b1} ends {beryl_end_of_event} -> {'WHOLE' if beryl_whole else 'BROKEN'}")
        show(con, f"""
            SELECT event_id, county, strftime(event_start, '%Y-%m-%d %H:%M') AS start_utc,
                   strftime(event_end, '%Y-%m-%d %H:%M') AS end_utc, ROUND(duration_hours, 1) AS hours,
                   peak_customers_out AS peak_out, ROUND(customer_hours_lost / 1e6, 2) AS cust_hours_m,
                   dropout_hours
            FROM {ev} WHERE event_id IN ('{h}', '{m}', '{w1}', '{w2}', '{b1}') ORDER BY event_id
        """)

        la = con.execute(f"""
            SELECT COUNT(*), MAX(duration_hours), SUM(duration_hours), SUM(customer_hours_lost), MAX(event_threshold)
            FROM {ev} WHERE fips_code = '{LOS_ANGELES}'
              AND event_end > TIMESTAMP '2024-05-19' AND event_start < TIMESTAMP '2024-06-20'
        """).fetchone()
        print(f"Los Angeles 2024-05-19 to 2024-06-19: {la[0]} events, longest {la[1] or 0:.1f} h, "
              f"total {la[2] or 0:.1f} h, customer-hours {(la[3] or 0) / 1e6:.2f} M")

        # Exact split points with this share's dropouts.
        crit = {
            "Pinellas (must split)": (PINELLAS, helene_t, milton_t, "split"),
            "Wayne (must split)": (WAYNE, ice_t, march_t, "split"),
            "Los Angeles (must break)": (LOS_ANGELES, "2024-05-19 07:45", "2024-06-19 12:00", "split"),
            "Harris Beryl (must stay whole)": (HARRIS, beryl_t, beryl_end, "whole"),
        }
        print("\nSplit points and margins:")
        print(f"  {'county':<32} {'T*':>9} {'at (UTC)':>17} {'critical share':>15} {'threshold':>10} {'margin':>8}")
        margins = {}
        for name, (fips, a, b, kind) in crit.items():
            t_star, at = critical_threshold(con, fips, a, b, dr)
            c_share = t_star / customers[fips]
            threshold = max(100.0, share * customers[fips])
            margin = (threshold / t_star - 1) if kind == "split" else (t_star / threshold - 1)
            margins[name] = margin
            print(f"  {name:<32} {t_star:>9,} {at:>17} {c_share * 100:>14.4f}% {threshold:>10,.0f} {margin * 100:>+7.1f}%")
        safe = min(margins.values())
        print(f"  smallest margin: {safe * 100:+.1f}%  ({'all conditions met' if safe > 0 else 'a condition fails'})")

        print("\nBaseline top 10 under this share (event containing each baseline event's peak):")
        top = con.execute(f"""
            WITH ranked AS (
                SELECT *, ROW_NUMBER() OVER (ORDER BY customer_hours_lost DESC) AS new_rank FROM {ev}
            )
            SELECT b.base_rank, b.county, b.state_abbr, strftime(b.peak_time, '%Y-%m-%d') AS peak_day,
                   ROUND(b.customer_hours_lost / 1e6, 1) AS base_m,
                   r.new_rank, ROUND(r.customer_hours_lost / 1e6, 1) AS new_m,
                   ROUND(r.customer_hours_lost / b.customer_hours_lost * 100, 1) AS kept_pct,
                   ROUND(r.duration_hours, 0) AS new_hours
            FROM base_top b
            LEFT JOIN ranked r
              ON r.fips_code = b.fips_code AND b.peak_time >= r.event_start AND b.peak_time < r.event_end
            ORDER BY b.base_rank
        """).fetchdf()
        print(top.to_string(index=False))
        in_top10 = int((top["new_rank"] <= 10).sum())
        print(f"  baseline top-10 storms still in the top 10: {in_top10} / 10")
        newcomers = con.execute(f"""
            WITH ranked AS (
                SELECT *, ROW_NUMBER() OVER (ORDER BY customer_hours_lost DESC) AS new_rank FROM {ev}
                QUALIFY new_rank <= 10
            )
            SELECT r.new_rank, r.county, r.state_abbr, strftime(r.event_start, '%Y-%m-%d') AS start_day,
                   ROUND(r.customer_hours_lost / 1e6, 1) AS cust_hours_m
            FROM ranked r
            WHERE NOT EXISTS (SELECT 1 FROM base_top b WHERE b.fips_code = r.fips_code
                              AND b.peak_time >= r.event_start AND b.peak_time < r.event_end)
            ORDER BY r.new_rank
        """).fetchdf()
        if len(newcomers):
            print("  new entries in the top 10:")
            print(newcomers.to_string(index=False))

        lost = con.execute(f"""
            SELECT COUNT(*), COUNT(DISTINCT b.fips_code), MAX(b.peak_customers_out),
                   SUM(b.customer_hours_lost)
            FROM base_large b
            WHERE NOT EXISTS (SELECT 1 FROM {ev} e WHERE e.fips_code = b.fips_code
                              AND b.peak_time >= e.event_start AND b.peak_time < e.event_end)
        """).fetchone()
        n_large = con.execute("SELECT COUNT(*) FROM base_large").fetchone()[0]
        print(f"\nLarge baseline events (peak >= 10,000) no longer counted at all: {lost[0]:,} of {n_large:,} "
              f"in {lost[1] or 0} counties, largest peak {lost[2] or 0:,}, "
              f"baseline customer-hours {(lost[3] or 0) / 1e6:.2f} M")
        if lost[0]:
            show(con, f"""
                SELECT b.event_id, t.county, t.state_abbr AS st, b.peak_customers_out AS peak_out,
                       ROUND(GREATEST(100, {share!r} * k.customers)) AS threshold,
                       strftime(b.peak_time, '%Y-%m-%d') AS peak_day
                FROM base_large b
                JOIN dim_county_customers k USING (fips_code)
                LEFT JOIN (SELECT fips_code, ANY_VALUE(county) AS county, ANY_VALUE(state_abbr) AS state_abbr
                           FROM silver_outages GROUP BY 1) t USING (fips_code)
                WHERE NOT EXISTS (SELECT 1 FROM {ev} e WHERE e.fips_code = b.fips_code
                                  AND b.peak_time >= e.event_start AND b.peak_time < e.event_end)
                ORDER BY b.peak_customers_out DESC LIMIT 5
            """)

        totals = con.execute(f"""
            SELECT COUNT(*), MEDIAN(duration_hours), QUANTILE_CONT(duration_hours, 0.95),
                   SUM(customer_hours_lost), (SELECT COUNT(*) FROM {dr})
            FROM {ev}
        """).fetchone()
        summary.append((label(share), totals[0], totals[1], totals[2], totals[3], totals[4],
                        pinellas_split, wayne_split, beryl_whole, la[0], la[1] or 0, in_top10, margins,
                        lost[0]))

    print("\n" + "=" * 100)
    print("SUMMARY (all years, D19 applied)")
    print("=" * 100)
    print(f"{'share':<9} {'events':>9} {'med_h':>6} {'p95_h':>6} {'cust_h_M':>9} {'dropouts':>9} "
          f"{'Pinellas':>9} {'Wayne':>7} {'Beryl':>7} {'LA_ev':>6} {'LA_max':>7} {'top10':>6} "
          f"{'m_Pin':>7} {'m_Way':>7} {'m_LA':>7} {'m_Har':>7} {'min_m':>7} {'lost10k':>8}")
    for s, n, med, p95, ch, nd, pin, way, ber, la_n, la_max, t10, mg, lost_n in summary:
        mv = list(mg.values())
        print(f"{s:<9} {n:>9,} {med:>6.2f} {p95:>6.2f} {ch / 1e6:>9.1f} {nd:>9,} "
              f"{'split' if pin else 'merged':>9} {'split' if way else 'merged':>7} "
              f"{'whole' if ber else 'broken':>7} {la_n:>6,} {la_max:>7.1f} {t10:>6} "
              + " ".join(f"{v * 100:>+6.0f}%" for v in mv) + f" {min(mv) * 100:>+6.0f}% {lost_n:>8,}")


if __name__ == "__main__":
    main()
