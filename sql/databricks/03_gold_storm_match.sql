-- =============================================================================
-- 03_gold_storm_match.sql
-- Gold layer: the NOAA storm behind each outage event (D37). Runs after
-- 03_gold_events.sql (D26).
--
--   gold_event_storm_match   one row per outage event: best matching storm, or 'unmatched'
--
-- scripts/test_gold_analysis_duckdb.py runs this statement in DuckDB. Keep it in the form
-- CREATE OR REPLACE TABLE <name> COMMENT '...' AS <query>;
-- =============================================================================

SET TIME ZONE 'UTC';

USE CATALOG workspace;
USE SCHEMA outages;


CREATE OR REPLACE TABLE gold_event_storm_match
COMMENT 'Best NOAA storm per outage event: same county, storm window 12 h before begin to end overlapping the outage (D37)'
AS
WITH
-- Only storm types that can cause outages are candidates; severity breaks ties (D37).
severity AS (
    SELECT event_type, CAST(severity_rank AS INT) AS severity_rank, severity_tier
    FROM bronze_storm_event_severity
    WHERE can_cause_outage = 'Y'
),
-- A storm's window opens 12 hours before NOAA's begin time and closes at its end (D37).
storms AS (
    SELECT
        s.event_id                         AS storm_event_id,
        s.episode_id                       AS storm_episode_id,
        s.fips_code,
        s.event_type,
        s.begin_utc,
        s.end_utc,
        s.begin_utc - INTERVAL 12 HOURS    AS window_start,
        s.end_utc                          AS window_end,
        v.severity_rank,
        v.severity_tier
    FROM silver_storm_events AS s
    INNER JOIN severity AS v ON v.event_type = s.event_type
),
-- Every storm in the same county whose window overlaps the outage, with the overlap in hours.
candidates AS (
    SELECT
        o.event_id,
        s.*,
        (unix_seconds(LEAST(o.event_end, s.window_end))
            - unix_seconds(GREATEST(o.event_start, s.window_start))) / 3600.0 AS overlap_hours
    FROM gold_outage_events AS o
    INNER JOIN storms AS s
        ON  s.fips_code    = o.fips_code
        AND s.window_start < o.event_end
        AND s.window_end   > o.event_start
),
-- Best match: largest overlap; ties to the more severe type, then the lower NOAA event id.
best AS (
    SELECT *
    FROM candidates
    QUALIFY ROW_NUMBER() OVER (PARTITION BY event_id ORDER BY overlap_hours DESC, severity_rank, storm_event_id) = 1
),
-- The most severe overlapping storm is kept alongside, so a long flood record cannot hide a
-- tropical storm in the same window (D37).
most_severe AS (
    SELECT
        event_id,
        event_type AS most_severe_storm_type,
        COUNT(*) OVER (PARTITION BY event_id) AS candidate_storms
    FROM candidates
    QUALIFY ROW_NUMBER() OVER (PARTITION BY event_id ORDER BY severity_rank, overlap_hours DESC, storm_event_id) = 1
)
SELECT
    o.event_id,
    o.fips_code,
    o.county,
    o.state_abbr,
    o.event_year,
    o.event_start,
    o.event_end,
    o.duration_hours,
    o.peak_customers_out,
    o.customer_hours_lost,
    COALESCE(b.event_type, 'unmatched')   AS storm_type,
    b.severity_tier                       AS storm_tier,
    b.storm_event_id,
    b.storm_episode_id,
    b.begin_utc                           AS storm_begin_utc,
    b.end_utc                             AS storm_end_utc,
    b.overlap_hours,
    m.most_severe_storm_type,
    COALESCE(m.candidate_storms, 0)       AS candidate_storms
FROM gold_outage_events AS o
LEFT JOIN best        AS b ON b.event_id = o.event_id
LEFT JOIN most_severe AS m ON m.event_id = o.event_id;


-- -----------------------------------------------------------------------------
-- Check: matched share of events and customer-hours per year
-- -----------------------------------------------------------------------------

SELECT event_year, COUNT(*) AS events, COUNT_IF(storm_type <> 'unmatched') AS matched,
       ROUND(SUM(CASE WHEN storm_type <> 'unmatched' THEN customer_hours_lost END) / SUM(customer_hours_lost), 3) AS matched_customer_hours_share
FROM gold_event_storm_match
GROUP BY event_year
ORDER BY event_year;
