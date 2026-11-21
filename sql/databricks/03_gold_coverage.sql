-- =============================================================================
-- 03_gold_coverage.sql
-- Gold layer: EAGLE-I coverage per state (D22). Runs after 03_gold_events.sql (D26).
--
--   gold_state_coverage   counties and customers covered per state; states below 70%
--                         customer coverage are footnoted, not ranked
--
-- scripts/test_sources_duckdb.py runs this statement in DuckDB. Keep it in the form
-- CREATE OR REPLACE TABLE <name> COMMENT '...' AS <query>;
-- =============================================================================

SET TIME ZONE 'UTC';

USE CATALOG workspace;
USE SCHEMA outages;


CREATE OR REPLACE TABLE gold_state_coverage
COMMENT 'EAGLE-I coverage per state: counties with data, total counties, share of EIA-861 customers (D22)'
AS
WITH
-- Total counties come from the latest NWS zone-county file in effect during 2022-2024 (D22).
latest_zone_file AS (
    SELECT version
    FROM silver_nws_zone_versions
    WHERE effective_from <= make_date(2024, 12, 31)
    QUALIFY ROW_NUMBER() OVER (ORDER BY effective_from DESC) = 1
),
all_counties AS (
    SELECT LEFT(z.fips_code, 2) AS state_fips, COUNT(DISTINCT z.fips_code) AS total_counties
    FROM silver_nws_zone_county AS z
    INNER JOIN latest_zone_file AS l ON l.version = z.version
    GROUP BY 1
),
-- Counties with EAGLE-I data and their calibrated denominators (D13, D21).
eaglei AS (
    SELECT
        LEFT(fips_code, 2)                                   AS state_fips,
        COUNT(*)                                             AS eaglei_counties,
        COUNT_IF(customers IS NOT NULL)                      AS counties_with_denominator,
        SUM(customers)                                       AS eaglei_customers,
        MAX(state_calibration_factor)                        AS calibration_factor
    FROM dim_county_customers
    GROUP BY 1
),
eia AS (
    SELECT state_abbr, customers AS eia_customers
    FROM silver_eia_state_customers
    WHERE data_year = 2024
)
-- Customer coverage is capped at 100%; a state below 70% is footnoted, not ranked (D22).
SELECT
    r.state_abbr,
    r.state_name,
    r.census_region,
    r.fema_region,
    COALESCE(a.total_counties, 0)                                     AS total_counties,
    COALESCE(e.eaglei_counties, 0)                                    AS eaglei_counties,
    COALESCE(e.counties_with_denominator, 0)                          AS counties_with_denominator,
    e.eaglei_customers,
    i.eia_customers,
    LEAST(e.eaglei_customers / NULLIF(i.eia_customers, 0), 1.0)       AS customer_coverage,
    COALESCE(LEAST(e.eaglei_customers / NULLIF(i.eia_customers, 0), 1.0) >= 0.7, FALSE) AS ranking_eligible,
    COALESCE(e.calibration_factor, 1.0)                               AS calibration_factor,
    CASE r.state_abbr
        WHEN 'PR' THEN 'EAGLE-I reports the 7 PREPA operating regions under the FIPS of each namesake municipio; results are region-level'
        WHEN 'VI' THEN 'EAGLE-I reports the US Virgin Islands by island'
    END                                                               AS coverage_note
FROM bronze_state_regions AS r
LEFT JOIN all_counties AS a ON a.state_fips = r.state_fips
LEFT JOIN eaglei       AS e ON e.state_fips = r.state_fips
LEFT JOIN eia          AS i ON i.state_abbr = r.state_abbr;


-- -----------------------------------------------------------------------------
-- Check: states footnoted (below 70% customer coverage) and the lowest coverage
-- -----------------------------------------------------------------------------

SELECT state_abbr, eaglei_counties, total_counties, ROUND(customer_coverage, 3) AS customer_coverage, ranking_eligible
FROM gold_state_coverage
ORDER BY customer_coverage
LIMIT 8;
