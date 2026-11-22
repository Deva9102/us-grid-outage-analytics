-- =============================================================================
-- 03_gold_events.sql
-- Gold layer: county outage events built from silver_outages (gaps and islands).
--
--   gold_collection_runs   every 15-minute slot, collected or a nationwide feed gap (D3)
--   gold_event_thresholds  one event threshold per county (D18)
--   gold_feed_dropouts     county-level reporting dropouts (D19)
--   gold_outage_events     one row per county outage event (D3, D4, D10, D11, D13, D17-D19)
--
-- Event rule: a reading belongs to an event when customers_out >= the county's threshold,
-- GREATEST(${events.min_customers_out}, share x customers) (D18). A gap of more than ${events.max_gap_hours} hour(s) since the county's
-- previous qualifying reading starts a new event. The gap is measured in collected runs,
-- excluding nationwide feed gaps (D3) and the county's own feed dropouts (D19), so
-- neither can split an event.
--
-- scripts/test_gold_events_duckdb.py runs the queries in this file in DuckDB. Keep each
-- statement in the form CREATE OR REPLACE TABLE <name> COMMENT '...' AS <query>;
-- =============================================================================

SET TIME ZONE 'UTC';

USE CATALOG ${project.catalog};
USE SCHEMA ${project.schema};


-- -----------------------------------------------------------------------------
-- gold_collection_runs (D3)
-- One row per 15-minute slot between the first and last reading. Collected slots get a
-- consecutive run_index; slots with no rows nationwide are feed gaps and get NULL.
-- -----------------------------------------------------------------------------

CREATE OR REPLACE TABLE gold_collection_runs
COMMENT 'Every 15-minute slot; is_collected = false marks a nationwide feed gap (D3)'
AS
WITH
-- The expected grid runs from the first to the last reading in Silver.
bounds AS (
    SELECT MIN(reading_time) AS first_time, MAX(reading_time) AS last_time
    FROM silver_outages
),
-- One row per 15-minute slot on that grid.
grid AS (
    SELECT EXPLODE(SEQUENCE(first_time, last_time, INTERVAL 15 MINUTES)) AS slot_time
    FROM bounds
),
-- A slot is collected when at least one county reported in it.
collected AS (
    SELECT DISTINCT reading_time
    FROM silver_outages
)
-- run_index counts collected slots only, so the distance between two readings in runs
-- excludes any feed gap between them.
SELECT
    g.slot_time,
    c.reading_time IS NOT NULL AS is_collected,
    CASE
        WHEN c.reading_time IS NOT NULL
        THEN ROW_NUMBER() OVER (PARTITION BY c.reading_time IS NOT NULL ORDER BY g.slot_time)
    END AS run_index
FROM grid AS g
LEFT JOIN collected AS c ON c.reading_time = g.slot_time;


-- -----------------------------------------------------------------------------
-- gold_event_thresholds (D18)
-- -----------------------------------------------------------------------------

CREATE OR REPLACE TABLE gold_event_thresholds
COMMENT 'Event threshold per county: GREATEST(${events.min_customers_out}, event_share x customers) (D18)'
AS
WITH
-- Share of county customers that sets the threshold in large counties. Chosen by the
-- sensitivity test in scripts/sensitivity_event_threshold.py (D18); set in config/pipeline.yml
-- (events.threshold_share, D47).
params AS (
    SELECT CAST(${events.threshold_share} AS DOUBLE) AS event_share
)
-- A fixed floor is background noise in a county with a million customers, so the threshold
-- scales with the D13 denominator. Counties without one stay at the floor.
SELECT
    k.fips_code,
    k.customers,
    k.denominator_source,
    p.event_share,
    GREATEST(${events.min_customers_out}, COALESCE(p.event_share * k.customers, 0)) AS event_threshold
FROM dim_county_customers AS k
CROSS JOIN params AS p;


-- -----------------------------------------------------------------------------
-- gold_feed_dropouts (D19)
-- A dropout starts at a reported reading that is below dropouts.drop_below_share of the county's
-- previous reading, where the previous reading was inside an event (at or above the threshold).
-- It ends at the first later reading back at dropouts.recovery_share or more of that previous level,
-- if that comes within dropouts.recovery_max_runs runs (config/pipeline.yml, D47).
-- -----------------------------------------------------------------------------

CREATE OR REPLACE TABLE gold_feed_dropouts
COMMENT 'Feed dropouts: under ${dropouts.drop_below_pct}% of the prior reading, back to ${dropouts.recovery_pct}% in ${dropouts.recovery_max_minutes} min (D19)'
AS
WITH
-- Every reading with its collected-run position and its county threshold.
readings AS (
    SELECT
        s.fips_code,
        s.customers_out,
        r.run_index,
        COALESCE(t.event_threshold, ${events.min_customers_out}) AS event_threshold
    FROM silver_outages AS s
    INNER JOIN gold_collection_runs AS r ON r.slot_time = s.reading_time
    LEFT JOIN  gold_event_thresholds AS t ON t.fips_code = s.fips_code
),
-- The previous reading and the next five readings of the same county. Recovery must come
-- within dropouts.recovery_max_runs (at most 5) runs, and runs are distinct per county, so five
-- LEADs always cover it.
neighbours AS (
    SELECT
        *,
        LAG(run_index)          OVER w AS prev_run,
        LAG(customers_out)      OVER w AS prev_out,
        LEAD(run_index, 1)      OVER w AS run_1,
        LEAD(customers_out, 1)  OVER w AS out_1,
        LEAD(run_index, 2)      OVER w AS run_2,
        LEAD(customers_out, 2)  OVER w AS out_2,
        LEAD(run_index, 3)      OVER w AS run_3,
        LEAD(customers_out, 3)  OVER w AS out_3,
        LEAD(run_index, 4)      OVER w AS run_4,
        LEAD(customers_out, 4)  OVER w AS out_4,
        LEAD(run_index, 5)      OVER w AS run_5,
        LEAD(customers_out, 5)  OVER w AS out_5
    FROM readings
    WINDOW w AS (PARTITION BY fips_code ORDER BY run_index)
),
-- A drop is a reported reading in the very next run below dropouts.drop_below_share. Missing
-- rows are zeros under D3 and are not treated as drops.
drops AS (
    SELECT *
    FROM neighbours
    WHERE run_index = prev_run + 1
      AND prev_out >= event_threshold
      AND customers_out < ${dropouts.drop_below_share} * prev_out
),
-- The earliest of the next five readings that is back at dropouts.recovery_share of the pre-drop
-- level, no more than dropouts.recovery_max_runs runs after the drop started.
recovered AS (
    SELECT
        *,
        CASE
            WHEN run_1 <= run_index + ${dropouts.recovery_max_runs} AND out_1 >= ${dropouts.recovery_share} * prev_out THEN run_1
            WHEN run_2 <= run_index + ${dropouts.recovery_max_runs} AND out_2 >= ${dropouts.recovery_share} * prev_out THEN run_2
            WHEN run_3 <= run_index + ${dropouts.recovery_max_runs} AND out_3 >= ${dropouts.recovery_share} * prev_out THEN run_3
            WHEN run_4 <= run_index + ${dropouts.recovery_max_runs} AND out_4 >= ${dropouts.recovery_share} * prev_out THEN run_4
            WHEN run_5 <= run_index + ${dropouts.recovery_max_runs} AND out_5 >= ${dropouts.recovery_share} * prev_out THEN run_5
        END AS recovery_run,
        CASE
            WHEN run_1 <= run_index + ${dropouts.recovery_max_runs} AND out_1 >= ${dropouts.recovery_share} * prev_out THEN out_1
            WHEN run_2 <= run_index + ${dropouts.recovery_max_runs} AND out_2 >= ${dropouts.recovery_share} * prev_out THEN out_2
            WHEN run_3 <= run_index + ${dropouts.recovery_max_runs} AND out_3 >= ${dropouts.recovery_share} * prev_out THEN out_3
            WHEN run_4 <= run_index + ${dropouts.recovery_max_runs} AND out_4 >= ${dropouts.recovery_share} * prev_out THEN out_4
            WHEN run_5 <= run_index + ${dropouts.recovery_max_runs} AND out_5 >= ${dropouts.recovery_share} * prev_out THEN out_5
        END AS recovery_out
    FROM drops
)
-- Only drops that recover are dropouts. The dropped runs are drop_start_run to recovery_run - 1.
SELECT
    d.fips_code,
    s1.slot_time                        AS dropout_start,
    s2.slot_time                        AS dropout_end,
    d.run_index                         AS drop_start_run,
    d.recovery_run,
    d.recovery_run - d.run_index        AS dropout_runs,
    d.prev_out                          AS pre_drop_customers_out,
    d.customers_out                     AS dropped_customers_out,
    d.recovery_out                      AS recovery_customers_out,
    YEAR(s1.slot_time)                  AS dropout_year
FROM recovered AS d
INNER JOIN gold_collection_runs AS s1 ON s1.run_index = d.run_index
INNER JOIN gold_collection_runs AS s2 ON s2.run_index = d.recovery_run
WHERE d.recovery_run IS NOT NULL;


-- -----------------------------------------------------------------------------
-- gold_outage_events
-- -----------------------------------------------------------------------------

CREATE OR REPLACE TABLE gold_outage_events
COMMENT 'County outage events: readings at or above the county threshold, a gap over ${events.max_gap_hours} hour(s) of active runs starts a new event'
AS
WITH
-- Each dropout covers its dropped runs, drop_start_run to recovery_run - 1.
dropout_runs_all AS (
    SELECT fips_code, EXPLODE(SEQUENCE(drop_start_run, recovery_run - 1)) AS run_index
    FROM gold_feed_dropouts
),
-- Dropouts of the same county can overlap; each run counts once.
dropout_runs AS (
    SELECT DISTINCT fips_code, run_index
    FROM dropout_runs_all
),
-- Only readings at or above the county's threshold can belong to an event (D18). The raw
-- value is used: D4 keeps customers_out uncapped, the cap applies to metrics only. Dropout
-- readings were not really measured, so they are left out like feed gaps (D19).
qualifying AS (
    SELECT
        s.fips_code,
        s.county,
        s.state,
        s.state_abbr,
        s.census_region,
        s.reading_time,
        s.customers_out,
        s.exceeds_customers,
        r.run_index,
        t.customers,
        t.denominator_source,
        COALESCE(t.event_threshold, ${events.min_customers_out}) AS event_threshold
    FROM silver_outages AS s
    INNER JOIN gold_collection_runs AS r ON r.slot_time = s.reading_time
    LEFT JOIN  gold_event_thresholds AS t ON t.fips_code = s.fips_code
    WHERE s.customers_out >= COALESCE(t.event_threshold, ${events.min_customers_out})
      AND NOT EXISTS (
          SELECT 1 FROM dropout_runs AS d
          WHERE d.fips_code = s.fips_code AND d.run_index = r.run_index
      )
),
-- Qualifying readings and dropout runs in one ordered list per county, so the number of
-- dropout runs before each reading can be counted.
run_keys AS (
    SELECT fips_code, run_index, 0 AS is_dropout FROM qualifying
    UNION ALL
    SELECT fips_code, run_index, 1 AS is_dropout FROM dropout_runs
),
-- active_index = run_index minus the county's dropout runs so far. Distances in active runs
-- skip both nationwide feed gaps (not in run_index) and county dropouts (D3, D19).
active_positions AS (
    SELECT
        fips_code,
        run_index,
        is_dropout,
        run_index - SUM(is_dropout) OVER (
            PARTITION BY fips_code
            ORDER BY run_index, is_dropout
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ) AS active_index
    FROM run_keys
),
-- Attach the active position to each qualifying reading.
positioned AS (
    SELECT q.*, a.active_index
    FROM qualifying AS q
    INNER JOIN active_positions AS a
        ON  a.fips_code  = q.fips_code
        AND a.run_index  = q.run_index
        AND a.is_dropout = 0
),
-- LAG finds the county's previous qualifying reading; the distance is in active runs.
with_previous AS (
    SELECT
        *,
        active_index - LAG(active_index) OVER (PARTITION BY fips_code ORDER BY reading_time) AS runs_since_previous
    FROM positioned
),
-- A new event starts at the county's first qualifying reading, or when more than
-- events.max_gap_runs active runs (events.max_gap_hours) have passed since the previous one.
-- A gap of exactly that length stays in the same event.
flagged AS (
    SELECT
        *,
        CASE
            WHEN runs_since_previous IS NULL OR runs_since_previous > ${events.max_gap_runs} THEN 1
            ELSE 0
        END AS is_new_event
    FROM with_previous
),
-- The running SUM of the new-event flags numbers the events within each county: every
-- reading until the next flag carries the same number.
numbered AS (
    SELECT
        *,
        SUM(is_new_event) OVER (
            PARTITION BY fips_code
            ORDER BY reading_time
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ) AS event_seq
    FROM flagged
),
-- The one-per-county denominator (D13) caps each reading for customer-hours (D4).
-- Counties without a denominator keep the raw value in raw totals (D9).
capped AS (
    SELECT
        *,
        CASE
            WHEN customers IS NULL THEN customers_out
            ELSE LEAST(customers_out, customers)
        END AS customers_out_capped
    FROM numbered
),
-- One row per event. Each reading stands for one 15-minute run, hence * 0.25 hours.
events AS (
    SELECT
        fips_code,
        event_seq,
        MAX(county)                                      AS county,
        MAX(state)                                       AS state,
        MAX(state_abbr)                                  AS state_abbr,
        MAX(census_region)                               AS census_region,
        MIN(reading_time)                                AS event_start,
        MAX(reading_time)                                AS last_reading_time,
        COUNT(*)                                         AS reading_count,
        MAX(customers_out)                               AS peak_customers_out,
        MAX(customers_out_capped)                        AS peak_customers_out_capped,
        SUM(CAST(customers_out_capped AS DOUBLE) * 0.25) AS customer_hours_lost,
        SUM(CAST(customers_out AS DOUBLE) * 0.25)        AS customer_hours_lost_raw,
        COUNT_IF(exceeds_customers) > 0                  AS exceeds_customers,
        MAX(customers)                                   AS customers,
        MAX(denominator_source)                          AS denominator_source,
        MAX(event_threshold)                             AS event_threshold,
        -- Collected runs minus active runs between the first and last reading = dropout runs inside.
        (MAX(run_index) - MIN(run_index)) - (MAX(active_index) - MIN(active_index)) AS dropout_slots
    FROM capped
    GROUP BY fips_code, event_seq
),
-- Only the nationwide gaps are needed for the overlap check.
feed_gaps AS (
    SELECT slot_time
    FROM gold_collection_runs
    WHERE NOT is_collected
),
-- An event spans a feed gap when a gap slot falls between its first and last reading:
-- nothing was measured there, so the duration is uncertain (D10).
gap_overlap AS (
    SELECT
        e.fips_code,
        e.event_seq,
        COUNT(g.slot_time) AS gap_slots
    FROM events AS e
    LEFT JOIN feed_gaps AS g
        ON  g.slot_time > e.event_start
        AND g.slot_time < e.last_reading_time
    GROUP BY e.fips_code, e.event_seq
)
-- event_end is the end of the last qualifying run, so a single reading lasts 0.25 hours (D17).
SELECT
    CONCAT(e.fips_code, '-', LPAD(CAST(e.event_seq AS STRING), 5, '0'))  AS event_id,
    e.fips_code,
    e.county,
    e.state,
    e.state_abbr,
    e.census_region,
    e.event_start,
    e.last_reading_time + INTERVAL 15 MINUTES                             AS event_end,
    (UNIX_SECONDS(e.last_reading_time + INTERVAL 15 MINUTES)
        - UNIX_SECONDS(e.event_start)) / 3600.0                           AS duration_hours,
    e.reading_count,
    e.peak_customers_out,
    e.event_threshold,
    e.customer_hours_lost,
    e.customer_hours_lost_raw,
    e.exceeds_customers,
    o.gap_slots > 0                                                       AS spans_feed_gap,
    o.gap_slots * 0.25                                                    AS feed_gap_hours,
    e.dropout_slots > 0                                                   AS spans_dropout,
    e.dropout_slots * 0.25                                                AS dropout_hours,
    e.customers,
    e.denominator_source,
    e.customers IS NOT NULL                                               AS has_denominator,
    COALESCE(e.customers >= ${ranking.min_customers}, FALSE)                                  AS ranking_eligible,
    e.peak_customers_out_capped * 1000.0 / NULLIF(e.customers, 0)         AS peak_out_per_1000,
    e.customer_hours_lost * 1000.0 / NULLIF(e.customers, 0)               AS customer_hours_per_1000,
    YEAR(e.event_start)                                                   AS event_year
FROM events AS e
INNER JOIN gap_overlap AS o
    ON  o.fips_code = e.fips_code
    AND o.event_seq = e.event_seq;


-- -----------------------------------------------------------------------------
-- Checks (expected values from the DuckDB test, see docs/decisions.md D17-D19)
-- -----------------------------------------------------------------------------

-- Feed gaps per year: 3 / 16 / 41 (D3)
SELECT YEAR(slot_time) AS year, COUNT_IF(NOT is_collected) AS feed_gaps
FROM gold_collection_runs
GROUP BY YEAR(slot_time)
ORDER BY year;

-- Feed dropouts per year (D19)
SELECT dropout_year, COUNT(*) AS dropouts, SUM(dropout_runs) AS dropout_runs
FROM gold_feed_dropouts
GROUP BY dropout_year
ORDER BY dropout_year;

-- Events per year, and how many span a feed gap (D10) or a dropout (D19)
SELECT event_year, COUNT(*) AS events, COUNT_IF(spans_feed_gap) AS spans_feed_gap,
       COUNT_IF(spans_dropout) AS spans_dropout
FROM gold_outage_events
GROUP BY event_year
ORDER BY event_year;
