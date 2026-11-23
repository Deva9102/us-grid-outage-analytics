-- =============================================================================
-- Q3. Regional comparison: which storm families cost each Census region the most outage hours.
-- 50 states and DC (territories are reported apart, D43). Storm families come from
-- dim_storm_type.storm_group (D68). Rates are customer-hours per 1,000 customers of the region per
-- year, averaged over the years in the data, so regions of different size compare.
-- =============================================================================

-- result: q3_region_storm
WITH
-- Customers per region: the D13 denominators of its counties.
region_customers AS (
    SELECT census_region, SUM(customers) AS customers
    FROM dim_county
    WHERE census_region <> 'Territory'
    GROUP BY census_region
),
-- Years in the data, to turn totals into yearly averages.
years AS (
    SELECT COUNT(DISTINCT event_year) AS n_years FROM fct_outage_events
),
-- Customer-hours per region and storm family.
by_group AS (
    SELECT
        d.census_region,
        t.storm_group,
        COUNT(*)                  AS events,
        SUM(e.customer_hours_lost) AS customer_hours_lost
    FROM fct_outage_events AS e
    INNER JOIN dim_state AS d ON d.state_abbr = e.state_abbr
    INNER JOIN dim_storm_type AS t ON t.storm_type = e.storm_type
    WHERE d.is_ranked_jurisdiction
    GROUP BY d.census_region, t.storm_group
),
-- Share of the region's customer-hours.
shared AS (
    SELECT
        *,
        customer_hours_lost / SUM(customer_hours_lost) OVER (PARTITION BY census_region) AS share_of_region
    FROM by_group
)
SELECT
    s.census_region,
    s.storm_group,
    s.events,
    ROUND(CAST(s.customer_hours_lost AS DECIMAL(38, 6)), 0)                                               AS customer_hours_lost,
    ROUND(CAST(s.share_of_region AS DECIMAL(38, 6)), 4)                                                   AS share_of_region,
    ROUND(CAST(s.customer_hours_lost * 1000.0 / r.customers / y.n_years AS DECIMAL(38, 6)), 1)            AS hours_per_1000_per_year
FROM shared AS s
INNER JOIN region_customers AS r ON r.census_region = s.census_region
CROSS JOIN years AS y
ORDER BY s.census_region, s.customer_hours_lost DESC;

-- result: q3_named_comparisons
WITH
-- The four comparisons the project set out to make, each as a set of events.
tagged AS (
    SELECT
        CASE
            WHEN d.census_region = 'Northeast' AND t.storm_group = 'Winter weather'
                THEN 'Northeast winter storms'
            WHEN e.state_abbr IN ('TX', 'LA', 'MS', 'AL', 'FL') AND t.storm_group = 'Hurricane / tropical'
                THEN 'Gulf Coast hurricanes'
            WHEN d.census_region = 'West' AND t.storm_group = 'Wildfire'
                THEN 'West wildfires'
            WHEN e.state_abbr = 'TX' AND t.storm_group = 'Winter weather'
                THEN 'Texas winter weather and cold'
        END AS comparison,
        e.event_year,
        e.customer_hours_lost,
        e.duration_hours
    FROM fct_outage_events AS e
    INNER JOIN dim_state AS d ON d.state_abbr = e.state_abbr
    INNER JOIN dim_storm_type AS t ON t.storm_type = e.storm_type
)
SELECT
    comparison,
    event_year,
    COUNT(*)                                  AS events,
    ROUND(CAST(SUM(customer_hours_lost) AS DECIMAL(38, 6)), 0)        AS customer_hours_lost,
    ROUND(CAST(MAX(customer_hours_lost) AS DECIMAL(38, 6)), 0)        AS largest_event_customer_hours,
    ROUND(CAST(AVG(duration_hours) AS DECIMAL(38, 6)), 1)             AS mean_duration_hours
FROM tagged
WHERE comparison IS NOT NULL
GROUP BY comparison, event_year
ORDER BY comparison, event_year;
