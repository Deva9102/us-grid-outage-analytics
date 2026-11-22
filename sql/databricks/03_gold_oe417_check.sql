-- =============================================================================
-- 03_gold_oe417_check.sql
-- Gold layer: OE-417 incidents compared with EAGLE-I events (D24, D40). Runs after
-- 03_gold_events.sql (D26).
--
--   gold_oe417_check   one row per OE-417 incident: whether an EAGLE-I event in its counties
--                      started within +/-12 hours of the incident's begin time
--
-- scripts/test_gold_analysis_duckdb.py runs this statement in DuckDB. Keep it in the form
-- CREATE OR REPLACE TABLE <name> COMMENT '...' AS <query>;
-- =============================================================================

SET TIME ZONE 'UTC';

USE CATALOG ${project.catalog};
USE SCHEMA ${project.schema};


CREATE OR REPLACE TABLE gold_oe417_check
COMMENT 'OE-417 incidents vs EAGLE-I events in the same counties, start within +/-${oe417_check.start_window_hours} hours (D24, D40)'
AS
WITH
-- Matched counties per incident (D34).
incident_counties AS (
    SELECT DISTINCT incident_id, fips_code
    FROM silver_oe417_locations
    WHERE fips_code IS NOT NULL
),
-- EAGLE-I events in those counties that start within oe417_check.start_window_hours of the incident (D24).
candidates AS (
    SELECT
        i.incident_id,
        e.event_id,
        e.fips_code,
        e.peak_customers_out,
        (UNIX_SECONDS(e.event_start) - UNIX_SECONDS(o.begin_utc)) / 3600.0 AS start_offset_hours
    FROM incident_counties AS i
    INNER JOIN silver_oe417 AS o ON o.incident_id = i.incident_id
    INNER JOIN gold_outage_events AS e
        ON  e.fips_code = i.fips_code
        AND e.event_start >= o.begin_utc - INTERVAL ${oe417_check.start_window_hours} HOURS
        AND e.event_start <= o.begin_utc + INTERVAL ${oe417_check.start_window_hours} HOURS
    WHERE o.begin_utc IS NOT NULL
),
-- Per incident: how many events and counties agree, and the summed peaks (one event per county).
summary AS (
    SELECT
        incident_id,
        COUNT(*)                   AS matched_events,
        COUNT(DISTINCT fips_code)  AS matched_counties
    FROM candidates
    GROUP BY incident_id
),
county_peaks AS (
    SELECT incident_id, SUM(peak) AS eaglei_peak_customers_out
    FROM (
        SELECT incident_id, fips_code, MAX(peak_customers_out) AS peak
        FROM candidates
        GROUP BY incident_id, fips_code
    ) AS per_county
    GROUP BY incident_id
),
-- The event starting closest to the incident.
closest AS (
    SELECT *
    FROM candidates
    QUALIFY ROW_NUMBER() OVER (PARTITION BY incident_id ORDER BY ABS(start_offset_hours), event_id) = 1
)
SELECT
    o.incident_id,
    o.report_year,
    o.event_category,
    o.primary_state,
    o.county_count,
    o.begin_utc,
    o.customers_affected,
    CASE
        WHEN o.customers_affected IS NULL    THEN 'unknown'
        WHEN o.customers_affected = 0        THEN '0'
        WHEN o.customers_affected < ${oe417_check.band_low}     THEN '${oe417_check.band_low_label}'
        WHEN o.customers_affected < ${oe417_check.band_high}    THEN '${oe417_check.band_mid_label}'
        ELSE '${oe417_check.band_high_label}'
    END AS customers_band,
    -- Only incidents with a time and at least one matched county can be checked (D40).
    CASE
        WHEN o.begin_utc IS NULL     THEN 'no time'
        WHEN o.county_count = 0      THEN 'no county'
        WHEN s.incident_id IS NULL   THEN 'not matched'
        ELSE 'matched'
    END AS match_status,
    COALESCE(s.matched_events, 0)   AS matched_events,
    COALESCE(s.matched_counties, 0) AS matched_counties,
    c.event_id                      AS closest_event_id,
    c.start_offset_hours            AS closest_start_offset_hours,
    p.eaglei_peak_customers_out
FROM silver_oe417 AS o
LEFT JOIN summary      AS s ON s.incident_id = o.incident_id
LEFT JOIN closest      AS c ON c.incident_id = o.incident_id
LEFT JOIN county_peaks AS p ON p.incident_id = o.incident_id;


-- -----------------------------------------------------------------------------
-- Check: agreement by customers-affected band
-- -----------------------------------------------------------------------------

SELECT customers_band, COUNT(*) AS incidents,
       COUNT_IF(match_status IN ('matched', 'not matched')) AS checkable,
       COUNT_IF(match_status = 'matched') AS matched
FROM gold_oe417_check
GROUP BY customers_band
ORDER BY customers_band;
