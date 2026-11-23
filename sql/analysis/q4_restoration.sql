-- =============================================================================
-- Q4. Which storm families take longest to restore power: median and 90th percentile event
-- duration (first to last qualifying reading, D17), by storm family and by Census region.
-- Most events are small and short, so each result also shows events with a peak of at least
-- 10,000 customers out, the outages a storm operations team staffs for.
-- =============================================================================

-- result: q4_duration_by_storm
WITH
-- Every event with its storm family.
events AS (
    SELECT t.storm_group, e.duration_hours, e.peak_customers_out
    FROM fct_outage_events AS e
    INNER JOIN dim_storm_type AS t ON t.storm_type = e.storm_type
),
-- All events.
all_events AS (
    SELECT
        storm_group,
        COUNT(*)                                                         AS events,
        PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY duration_hours)      AS median_hours,
        PERCENTILE_CONT(0.9) WITHIN GROUP (ORDER BY duration_hours)      AS p90_hours
    FROM events
    GROUP BY storm_group
),
-- Events with at least 10,000 customers out at the peak.
large_events AS (
    SELECT
        storm_group,
        COUNT(*)                                                         AS large_events,
        PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY duration_hours)      AS large_median_hours,
        PERCENTILE_CONT(0.9) WITHIN GROUP (ORDER BY duration_hours)      AS large_p90_hours
    FROM events
    WHERE peak_customers_out >= 10000
    GROUP BY storm_group
)
SELECT
    a.storm_group,
    a.events,
    ROUND(CAST(a.median_hours AS DECIMAL(38, 6)), 2)        AS median_hours,
    ROUND(CAST(a.p90_hours AS DECIMAL(38, 6)), 1)           AS p90_hours,
    COALESCE(l.large_events, 0)     AS large_events,
    ROUND(CAST(l.large_median_hours AS DECIMAL(38, 6)), 1)  AS large_median_hours,
    ROUND(CAST(l.large_p90_hours AS DECIMAL(38, 6)), 1)     AS large_p90_hours
FROM all_events AS a
LEFT JOIN large_events AS l ON l.storm_group = a.storm_group
ORDER BY l.large_median_hours DESC NULLS LAST, a.storm_group;

-- result: q4_duration_by_region
WITH
-- Every event with its Census region (Territory for Puerto Rico and the Virgin Islands).
events AS (
    SELECT d.census_region, e.duration_hours, e.peak_customers_out
    FROM fct_outage_events AS e
    INNER JOIN dim_state AS d ON d.state_abbr = e.state_abbr
),
-- All events.
all_events AS (
    SELECT
        census_region,
        COUNT(*)                                                         AS events,
        PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY duration_hours)      AS median_hours,
        PERCENTILE_CONT(0.9) WITHIN GROUP (ORDER BY duration_hours)      AS p90_hours
    FROM events
    GROUP BY census_region
),
-- Events with at least 10,000 customers out at the peak.
large_events AS (
    SELECT
        census_region,
        COUNT(*)                                                         AS large_events,
        PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY duration_hours)      AS large_median_hours,
        PERCENTILE_CONT(0.9) WITHIN GROUP (ORDER BY duration_hours)      AS large_p90_hours
    FROM events
    WHERE peak_customers_out >= 10000
    GROUP BY census_region
)
SELECT
    a.census_region,
    a.events,
    ROUND(CAST(a.median_hours AS DECIMAL(38, 6)), 2)        AS median_hours,
    ROUND(CAST(a.p90_hours AS DECIMAL(38, 6)), 1)           AS p90_hours,
    COALESCE(l.large_events, 0)     AS large_events,
    ROUND(CAST(l.large_median_hours AS DECIMAL(38, 6)), 1)  AS large_median_hours,
    ROUND(CAST(l.large_p90_hours AS DECIMAL(38, 6)), 1)     AS large_p90_hours
FROM all_events AS a
LEFT JOIN large_events AS l ON l.census_region = a.census_region
ORDER BY l.large_median_hours DESC NULLS LAST, a.census_region;
