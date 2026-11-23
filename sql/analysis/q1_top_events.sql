-- =============================================================================
-- Q1. The top 20 outage events by customer-hours lost, and their causes.
-- Reads only the dbt marts. Customer-hours are capped at the county denominator (D4). An event
-- counts in the year it starts (UTC). The storm is the most severe NOAA storm active when the
-- outage began, else the one overlapping it most (D41); 'unmatched' means no NOAA storm.
-- Each statement is one result, named by the "-- result:" line above it (scripts/analysis.py).
-- =============================================================================

-- result: q1_top20_all_years
WITH
-- Events with their county and state names, ranked by capped customer-hours.
ranked AS (
    SELECT
        ROW_NUMBER() OVER (ORDER BY e.customer_hours_lost DESC, e.event_id) AS event_rank,
        e.event_id,
        c.county,
        e.state_abbr,
        e.event_year,
        e.event_start,
        e.event_end,
        e.duration_hours,
        e.peak_customers_out,
        e.customer_hours_lost,
        e.storm_type,
        t.storm_group,
        e.attribution_rule
    FROM fct_outage_events AS e
    INNER JOIN dim_county AS c ON c.fips_code = e.fips_code
    INNER JOIN dim_storm_type AS t ON t.storm_type = e.storm_type
)
SELECT
    event_rank, event_id, county, state_abbr, event_year, event_start, event_end,
    ROUND(CAST(duration_hours AS DECIMAL(38, 6)), 1) AS duration_hours, peak_customers_out,
    ROUND(CAST(customer_hours_lost AS DECIMAL(38, 6)), 0) AS customer_hours_lost, storm_type, storm_group, attribution_rule
FROM ranked
WHERE event_rank <= 20
ORDER BY event_rank;

-- result: q1_top20_by_year
WITH
-- The same ranking within each event year.
ranked AS (
    SELECT
        ROW_NUMBER() OVER (PARTITION BY e.event_year ORDER BY e.customer_hours_lost DESC, e.event_id) AS year_rank,
        e.event_year,
        e.event_id,
        c.county,
        e.state_abbr,
        e.event_start,
        e.duration_hours,
        e.peak_customers_out,
        e.customer_hours_lost,
        e.storm_type
    FROM fct_outage_events AS e
    INNER JOIN dim_county AS c ON c.fips_code = e.fips_code
)
SELECT
    event_year, year_rank, event_id, county, state_abbr, event_start, ROUND(CAST(duration_hours AS DECIMAL(38, 6)), 1) AS duration_hours,
    peak_customers_out, ROUND(CAST(customer_hours_lost AS DECIMAL(38, 6)), 0) AS customer_hours_lost, storm_type
FROM ranked
WHERE year_rank <= 20
ORDER BY event_year, year_rank;

-- result: q1_top20_storm_mix
WITH
-- The top 20 of all years again, to count how many have a storm and of which family.
ranked AS (
    SELECT
        ROW_NUMBER() OVER (ORDER BY e.customer_hours_lost DESC, e.event_id) AS event_rank,
        t.storm_group,
        e.customer_hours_lost
    FROM fct_outage_events AS e
    INNER JOIN dim_storm_type AS t ON t.storm_type = e.storm_type
)
SELECT storm_group, COUNT(*) AS events, ROUND(CAST(SUM(customer_hours_lost) AS DECIMAL(38, 6)), 0) AS customer_hours_lost
FROM ranked
WHERE event_rank <= 20
GROUP BY storm_group
ORDER BY events DESC, storm_group;

-- result: q1_storm_share_all
WITH
-- Every event with its storm family; how much of all outage time has a NOAA storm behind it.
grouped AS (
    SELECT t.storm_group, COUNT(*) AS events, SUM(e.customer_hours_lost) AS customer_hours_lost
    FROM fct_outage_events AS e
    INNER JOIN dim_storm_type AS t ON t.storm_type = e.storm_type
    GROUP BY t.storm_group
)
SELECT
    storm_group,
    events,
    ROUND(CAST(customer_hours_lost AS DECIMAL(38, 6)), 0)                                             AS customer_hours_lost,
    ROUND(CAST(customer_hours_lost / SUM(customer_hours_lost) OVER () AS DECIMAL(38, 6)), 4)          AS share_of_customer_hours,
    ROUND(CAST(events * 1.0 / SUM(events) OVER () AS DECIMAL(38, 6)), 4)                              AS share_of_events
FROM grouped
ORDER BY customer_hours_lost DESC;
