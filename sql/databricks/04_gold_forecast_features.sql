-- =============================================================================
-- 04_gold_forecast_features.sql
-- Gold layer: features for the restoration-time forecast (D71). Runs after 03_gold_*.sql.
--
--   gold_storm_family            NOAA event type -> storm family, the D68 groups of dim_storm_type
--   gold_restoration_features    one row per eligible outage event: what is known at the
--                                prediction moment, and the target duration_hours
--
-- Prediction moment: event_start + ${forecast.prediction_hours} hours. Eligible: the county's reading at that
-- moment still meets the event threshold (D18) and belongs to the same event, so the outage is
-- visibly ongoing; events with spans_empty_gap (D64) are left out because their length is unknown.
--
-- No-leakage contract (tests/test_forecast_features.py):
--   * reading features use only 15-minute slots from event_start to the prediction moment;
--   * a feed dropout (D19) counts only when its recovery reading is at or before that moment;
--   * a storm counts only when its match window covers event_start and NOAA's begin time is at
--     or before that moment;
--   * county history uses only events of earlier years that had ended before the event's year
--     began.
-- The target, duration_hours, is the only column that looks past the prediction moment.
-- Split: train years ${forecast.train_years}, test years ${forecast.test_years} (time-based, never random).
-- =============================================================================

SET TIME ZONE 'UTC';

USE CATALOG ${project.catalog};
USE SCHEMA ${project.schema};


CREATE OR REPLACE TABLE gold_storm_family
COMMENT 'NOAA event type to storm family: the D68 groups of the dbt mart dim_storm_type (D71)'
AS
WITH
-- Every NOAA event type in the severity list, plus 'unmatched' for no storm (D37).
types AS (
    SELECT event_type AS storm_type, severity_tier AS storm_tier
    FROM bronze_storm_event_severity
    UNION ALL
    SELECT 'unmatched' AS storm_type, 'unmatched' AS storm_tier
)
-- Same CASE as dbt/models/marts/dim_storm_type.sql; a test keeps the two equal.
SELECT
    storm_type,
    storm_tier,
    CASE
        WHEN storm_tier = 'tropical_cyclone'                          THEN 'Hurricane / tropical'
        WHEN storm_tier = 'ice_snow'
          OR storm_type IN ('Winter Weather', 'Cold/Wind Chill',
                            'Extreme Cold/Wind Chill')                THEN 'Winter weather'
        WHEN storm_type = 'Thunderstorm Wind'                         THEN 'Thunderstorm wind'
        WHEN storm_tier = 'wind'                                      THEN 'Other wind'
        WHEN storm_tier = 'tornado'                                   THEN 'Tornado'
        WHEN storm_tier = 'wildfire'                                  THEN 'Wildfire'
        WHEN storm_type IN ('Excessive Heat', 'Heat')                 THEN 'Heat'
        WHEN storm_tier = 'flood'                                     THEN 'Flood'
        WHEN storm_tier = 'unmatched'                                 THEN 'No storm matched'
        ELSE 'Other'
    END AS storm_family
FROM types;


CREATE OR REPLACE TABLE gold_restoration_features
COMMENT 'Restoration forecast features known at event_start + ${forecast.prediction_hours} h, with target duration_hours (D71)'
AS
WITH
-- Events that run past the prediction moment are the only ones that can be eligible; filtering
-- here keeps the slot join below small.
candidates AS (
    SELECT
        e.event_id,
        e.fips_code,
        e.county,
        e.state_abbr,
        e.census_region,
        e.event_year,
        e.event_start,
        e.event_end,
        e.event_start + INTERVAL ${forecast.mid_minutes} MINUTES          AS mid_time,
        e.event_start + INTERVAL ${forecast.prediction_minutes} MINUTES   AS prediction_time,
        e.event_threshold,
        e.customers,
        e.has_denominator,
        e.spans_empty_gap,
        CAST(e.duration_hours AS DOUBLE)                                 AS duration_hours
    FROM gold_outage_events AS e
    WHERE e.event_end > e.event_start + INTERVAL ${forecast.prediction_minutes} MINUTES
),
-- Feed dropouts (D19) are only known once the feed recovers, so a dropout counts only when its
-- recovery reading is at or before the prediction moment.
known_dropouts AS (
    SELECT c.event_id, d.dropout_start, d.dropout_end
    FROM candidates AS c
    INNER JOIN gold_feed_dropouts AS d
        ON  d.fips_code     = c.fips_code
        AND d.dropout_start >= c.event_start
        AND d.dropout_end   <= c.prediction_time
),
-- One row per 15-minute slot from event_start to the prediction moment, both included. This
-- grid is the only path by which readings reach the features.
slots AS (
    SELECT
        c.event_id,
        c.fips_code,
        EXPLODE(SEQUENCE(c.event_start, c.prediction_time, INTERVAL 15 MINUTES)) AS slot_time
    FROM candidates AS c
),
-- The county's reading in each slot. A collected slot without a row is zero (D3); a nationwide
-- feed gap, a slot past the last collected run, or a known dropout reading is unknown (NULL).
slot_readings AS (
    SELECT
        s.event_id,
        s.slot_time,
        COALESCE(NOT r.is_collected, TRUE)                               AS is_feed_gap,
        k.event_id IS NOT NULL                                           AS is_known_dropout,
        CASE
            WHEN r.is_collected IS NULL OR NOT r.is_collected THEN NULL
            WHEN k.event_id IS NOT NULL THEN NULL
            ELSE COALESCE(o.customers_out, 0)
        END                                                              AS customers_out
    FROM slots AS s
    LEFT JOIN gold_collection_runs AS r ON r.slot_time = s.slot_time
    LEFT JOIN silver_outages AS o
        ON  o.fips_code    = s.fips_code
        AND o.reading_time = s.slot_time
    LEFT JOIN known_dropouts AS k
        ON  k.event_id      = s.event_id
        AND s.slot_time     >= k.dropout_start
        AND s.slot_time     <  k.dropout_end
),
-- Readings at the start, the midpoint and the prediction moment, the peak so far and the flags.
-- Overlapping dropouts can match a slot twice; MAX and COUNT_IF are unaffected by duplicates.
window_stats AS (
    SELECT
        c.event_id,
        MAX(CASE WHEN w.slot_time = c.event_start     THEN w.customers_out END) AS customers_out_at_start,
        MAX(CASE WHEN w.slot_time = c.mid_time        THEN w.customers_out END) AS customers_out_at_mid,
        MAX(CASE WHEN w.slot_time = c.prediction_time THEN w.customers_out END) AS customers_out_at_prediction,
        MAX(w.customers_out)                                                     AS peak_customers_out_so_far,
        COUNT_IF(w.is_feed_gap) > 0                                              AS feed_gap_so_far,
        COUNT_IF(w.is_known_dropout) > 0                                         AS dropout_so_far
    FROM candidates AS c
    INNER JOIN slot_readings AS w ON w.event_id = c.event_id
    GROUP BY c.event_id
),
-- Eligible: the reading at the prediction moment meets the county threshold (D18). The event
-- runs past that moment (candidates), so the reading belongs to this event, not a later one.
eligible AS (
    SELECT
        c.*,
        w.customers_out_at_start,
        w.customers_out_at_mid,
        w.customers_out_at_prediction,
        w.peak_customers_out_so_far,
        w.feed_gap_so_far,
        w.dropout_so_far
    FROM candidates AS c
    INNER JOIN window_stats AS w ON w.event_id = c.event_id
    WHERE w.customers_out_at_prediction >= c.event_threshold
      AND NOT c.spans_empty_gap
),
-- Storms that could cause outages (D37), with the match window of D37 and D42.
storms AS (
    SELECT
        s.event_id                                                  AS storm_event_id,
        s.fips_code,
        s.event_type,
        s.begin_utc,
        s.begin_utc - INTERVAL ${storm_match.window_before_hours} HOURS     AS window_start,
        s.end_utc + INTERVAL ${storm_match.window_after_hours} HOUR         AS window_end,
        CAST(v.severity_rank AS INT)                                AS severity_rank
    FROM silver_storm_events AS s
    INNER JOIN bronze_storm_event_severity AS v ON v.event_type = s.event_type
    WHERE v.can_cause_outage = 'Y'
),
-- The storm at the start: its window covers event_start and it had begun by the prediction
-- moment (a storm beginning later is future information). Most severe first (D41).
storm_at_start AS (
    SELECT g.event_id, s.event_type AS storm_type_at_start
    FROM eligible AS g
    INNER JOIN storms AS s
        ON  s.fips_code    = g.fips_code
        AND s.window_start <= g.event_start
        AND s.window_end   >  g.event_start
        AND s.begin_utc    <= g.prediction_time
    QUALIFY ROW_NUMBER() OVER (
        PARTITION BY g.event_id
        ORDER BY s.severity_rank ASC, s.begin_utc ASC, s.storm_event_id ASC
    ) = 1
),
-- Counties and years that need history.
county_years AS (
    SELECT DISTINCT fips_code, event_year
    FROM eligible
),
-- Every event with its eligibility, for the history of later years.
past_events AS (
    SELECT
        e.fips_code,
        e.event_year,
        e.event_end,
        CAST(e.duration_hours AS DOUBLE)          AS duration_hours,
        g.event_id IS NOT NULL                    AS was_eligible
    FROM gold_outage_events AS e
    LEFT JOIN eligible AS g ON g.event_id = e.event_id
),
-- County history from earlier years only, and only events that had ended before the year began:
-- a Dec 31 outage still running on Jan 1 is not yet history.
history AS (
    SELECT
        y.fips_code,
        y.event_year,
        COUNT(p.event_year)                                                                   AS prior_event_count,
        COUNT_IF(p.was_eligible)                                                              AS prior_eligible_event_count,
        PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY p.duration_hours)                         AS prior_median_duration_hours,
        PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY CASE WHEN p.was_eligible THEN p.duration_hours END)
                                                                                              AS prior_eligible_median_duration_hours
    FROM county_years AS y
    LEFT JOIN past_events AS p
        ON  p.fips_code  = y.fips_code
        AND p.event_year < y.event_year
        AND p.event_end  <= MAKE_TIMESTAMP(y.event_year, 1, 1, 0, 0, 0)
    GROUP BY y.fips_code, y.event_year
),
-- Start time in the state's primary time zone, for month, hour and weekday.
local_start AS (
    SELECT g.event_id, FROM_UTC_TIMESTAMP(g.event_start, z.primary_time_zone) AS start_local
    FROM eligible AS g
    LEFT JOIN bronze_state_time_zones AS z ON z.state_abbr = g.state_abbr
)
SELECT
    g.event_id,
    g.fips_code,
    g.county,
    g.state_abbr,
    g.census_region,
    g.event_year,
    CASE
        WHEN g.event_year IN (${forecast.train_years}) THEN 'train'
        WHEN g.event_year IN (${forecast.test_years}) THEN 'test'
    END                                                                       AS split,
    g.event_start,
    g.prediction_time,
    -- Storm known at the prediction moment
    COALESCE(a.storm_type_at_start, 'unmatched')                              AS storm_type_at_start,
    f.storm_family                                                            AS storm_family_at_start,
    -- Calendar, local time of the state (weekday 0 = Monday)
    MONTH(l.start_local)                                                      AS start_month_local,
    HOUR(l.start_local)                                                       AS start_hour_local,
    WEEKDAY(l.start_local)                                                    AS start_weekday_local,
    -- County size (D13) and threshold (D18)
    g.customers,
    g.has_denominator,
    g.event_threshold,
    -- Readings up to the prediction moment
    g.customers_out_at_start,
    g.customers_out_at_mid,
    g.customers_out_at_prediction,
    g.customers_out_at_prediction - g.customers_out_at_start                  AS growth_customers,
    CAST(g.customers_out_at_prediction AS DOUBLE) / g.customers_out_at_start  AS growth_ratio,
    g.peak_customers_out_so_far,
    CAST(LEAST(g.peak_customers_out_so_far, g.customers) AS DOUBLE) / NULLIF(g.customers, 0)
                                                                              AS peak_share_so_far,
    g.feed_gap_so_far,
    g.dropout_so_far,
    -- County history from earlier years; NULL when the event is in the first year of data
    g.event_year - ${years.first}                                                      AS history_years,
    CASE WHEN g.event_year > ${years.first} THEN h.prior_event_count END               AS prior_event_count,
    CASE WHEN g.event_year > ${years.first} THEN h.prior_eligible_event_count END      AS prior_eligible_event_count,
    CASE WHEN g.event_year > ${years.first}
         THEN CAST(h.prior_event_count AS DOUBLE) / (g.event_year - ${years.first}) END AS prior_events_per_year,
    h.prior_median_duration_hours,
    h.prior_eligible_median_duration_hours,
    -- Target
    g.duration_hours
FROM eligible AS g
LEFT JOIN storm_at_start AS a ON a.event_id = g.event_id
LEFT JOIN gold_storm_family AS f ON f.storm_type = COALESCE(a.storm_type_at_start, 'unmatched')
LEFT JOIN local_start AS l ON l.event_id = g.event_id
LEFT JOIN history AS h
    ON  h.fips_code  = g.fips_code
    AND h.event_year = g.event_year;


-- -----------------------------------------------------------------------------
-- Check: eligible events and the target per year (D71)
-- -----------------------------------------------------------------------------

SELECT event_year, split, COUNT(*) AS events,
       PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY duration_hours) AS median_hours,
       PERCENTILE_CONT(0.9) WITHIN GROUP (ORDER BY duration_hours) AS p90_hours
FROM gold_restoration_features
GROUP BY event_year, split
ORDER BY event_year;
