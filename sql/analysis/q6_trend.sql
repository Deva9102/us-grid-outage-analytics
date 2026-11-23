-- =============================================================================
-- Q6. The 2022-2025 trend in outage hours, with the coverage check that keeps coverage growth
-- from being read as outage growth. 50 states and DC. EAGLE-I publishes coverage and its data
-- quality index only up to 2022 (D67), so the years are also compared on the same counties: those
-- EAGLE-I reports in every year. Years are event start years.
-- =============================================================================

-- result: q6_national_trend
WITH
-- Outage events and customer-hours per year.
outages AS (
    SELECT e.event_year AS year, COUNT(*) AS events, SUM(e.customer_hours_lost) AS customer_hours_lost
    FROM fct_outage_events AS e
    INNER JOIN dim_state AS d ON d.state_abbr = e.state_abbr
    WHERE d.is_ranked_jurisdiction
    GROUP BY e.event_year
),
-- Counties reporting each year and the customers they hold (D13 denominators).
coverage AS (
    SELECT c.year, COUNT(*) AS reporting_counties, SUM(c.customers) AS covered_customers
    FROM fct_county_coverage AS c
    INNER JOIN dim_state AS d ON d.state_abbr = c.state_abbr
    WHERE d.is_ranked_jurisdiction
    GROUP BY c.year
),
-- EIA-861 customers of the 50 states and DC (calibration year), the national total.
national AS (
    SELECT SUM(eia_customers) AS eia_customers FROM dim_state WHERE is_ranked_jurisdiction
)
SELECT
    o.year,
    o.events,
    ROUND(CAST(o.customer_hours_lost AS DECIMAL(38, 6)), 0)                                   AS customer_hours_lost,
    c.reporting_counties,
    c.covered_customers,
    ROUND(CAST(c.covered_customers * 1.0 / n.eia_customers AS DECIMAL(38, 6)), 4)             AS share_of_eia_customers,
    ROUND(CAST(o.customer_hours_lost * 1000.0 / c.covered_customers AS DECIMAL(38, 6)), 1)    AS hours_per_1000_covered,
    -- Each year against the first: the trend in one number.
    ROUND(CAST(o.customer_hours_lost / FIRST_VALUE(o.customer_hours_lost) OVER (ORDER BY o.year) AS DECIMAL(38, 6)), 2) AS vs_first_year
FROM outages AS o
INNER JOIN coverage AS c ON c.year = o.year
CROSS JOIN national AS n
ORDER BY o.year;

-- result: q6_same_counties
WITH
-- Years in the data.
years AS (
    SELECT COUNT(DISTINCT year) AS n_years FROM fct_county_coverage
),
-- Counties of the 50 states and DC that EAGLE-I reports in every year.
panel AS (
    SELECT c.fips_code
    FROM fct_county_coverage AS c
    INNER JOIN dim_state AS d ON d.state_abbr = c.state_abbr
    CROSS JOIN years AS y
    WHERE d.is_ranked_jurisdiction
    GROUP BY c.fips_code
    HAVING COUNT(DISTINCT c.year) = MAX(y.n_years)
),
-- Their customers.
panel_customers AS (
    SELECT COUNT(*) AS panel_counties, SUM(k.customers) AS panel_customers
    FROM panel AS p
    INNER JOIN dim_county AS k ON k.fips_code = p.fips_code
),
-- Their events and customer-hours per year.
panel_outages AS (
    SELECT e.event_year AS year, COUNT(*) AS events, SUM(e.customer_hours_lost) AS customer_hours_lost
    FROM fct_outage_events AS e
    INNER JOIN panel AS p ON p.fips_code = e.fips_code
    GROUP BY e.event_year
)
SELECT
    o.year,
    c.panel_counties,
    c.panel_customers,
    o.events,
    ROUND(CAST(o.customer_hours_lost AS DECIMAL(38, 6)), 0)                                   AS customer_hours_lost,
    ROUND(CAST(o.customer_hours_lost * 1000.0 / c.panel_customers AS DECIMAL(38, 6)), 1)      AS hours_per_1000,
    ROUND(CAST(o.customer_hours_lost / FIRST_VALUE(o.customer_hours_lost) OVER (ORDER BY o.year) AS DECIMAL(38, 6)), 2) AS vs_first_year
FROM panel_outages AS o
CROSS JOIN panel_customers AS c
ORDER BY o.year;

-- result: q6_published_coverage
WITH
-- EAGLE-I's published coverage summed over the 50 states and DC.
published AS (
    SELECT p.year, SUM(p.max_covered) AS max_covered, SUM(p.total_customers) AS total_customers
    FROM fct_published_coverage AS p
    INNER JOIN dim_state AS d ON d.state_abbr = p.state_abbr
    WHERE d.is_ranked_jurisdiction
    GROUP BY p.year
),
-- The published data quality index, averaged over the ten FEMA regions.
quality AS (
    SELECT year, AVG(dqi) AS mean_dqi, MIN(dqi) AS min_dqi
    FROM fct_data_quality_index
    GROUP BY year
)
SELECT
    p.year,
    ROUND(CAST(p.max_covered * 1.0 / p.total_customers AS DECIMAL(38, 6)), 4)   AS max_share_covered,
    ROUND(CAST(q.mean_dqi AS DECIMAL(38, 6)), 1)                                AS mean_dqi,
    ROUND(CAST(q.min_dqi AS DECIMAL(38, 6)), 1)                                 AS min_dqi
FROM published AS p
INNER JOIN quality AS q ON q.year = p.year
ORDER BY p.year;

-- result: q6_first_reported
-- Counties of the 50 states and DC by the first year EAGLE-I reports them (D61).
SELECT c.first_reported_year, COUNT(*) AS counties, SUM(c.customers) AS customers
FROM dim_county AS c
INNER JOIN dim_state AS d ON d.state_abbr = c.state_abbr
WHERE d.is_ranked_jurisdiction AND c.first_reported_year IS NOT NULL
GROUP BY c.first_reported_year
ORDER BY c.first_reported_year;
