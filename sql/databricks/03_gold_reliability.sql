-- =============================================================================
-- 03_gold_reliability.sql
-- Gold layer: reliability rankings. Runs after 03_gold_coverage.sql (D26).
--
--   gold_unit_reliability            outage hours per 1,000 customers per reporting unit and year, unranked (D38, D44)
--   gold_county_reliability          the same for counties of the 50 states and DC, ranked (D38, D44)
--   gold_territory_unit_reliability  the same for PR PREPA regions and VI districts, unranked (D44)
--   gold_state_reliability           the same per state, 50 states and DC, with D22 coverage (D38, D43)
--   gold_territory_reliability       the same for Puerto Rico and the Virgin Islands, unranked (D43)
--   gold_utility_reliability         EIA-861 SAIDI / SAIFI ranked within size bands, IEEE 1366 only (D39)
--   gold_utility_reliability_other   other-standard utilities, listed, not ranked (D23, D39)
--
-- scripts/test_gold_analysis_duckdb.py runs these statements in DuckDB. Keep each in the form
-- CREATE OR REPLACE TABLE <name> COMMENT '...' AS <query>;
-- =============================================================================

SET TIME ZONE 'UTC';

USE CATALOG workspace;
USE SCHEMA outages;


CREATE OR REPLACE TABLE gold_unit_reliability
COMMENT 'Outage hours per 1,000 customers per EAGLE-I reporting unit and year, unranked base for counties and territories (D38, D44)'
AS
WITH
years AS (
    SELECT DISTINCT event_year AS year FROM gold_outage_events
),
-- Every county with EAGLE-I data appears in every year, so a quiet year counts as zero.
counties AS (
    SELECT
        d.fips_code,
        d.customers,
        r.state_abbr,
        r.state_name,
        r.census_region,
        r.fema_region
    FROM dim_county_customers AS d
    INNER JOIN bronze_state_regions AS r ON r.state_fips = LEFT(d.fips_code, 2)
),
names AS (
    SELECT fips_code, MAX(county) AS county FROM gold_outage_events GROUP BY fips_code
),
-- Events count in the year they start; customer-hours are already capped by the denominator (D4).
totals AS (
    SELECT
        fips_code,
        event_year AS year,
        COUNT(*)                 AS events,
        SUM(customer_hours_lost) AS customer_hours_lost,
        MAX(peak_customers_out)  AS max_peak_customers_out
    FROM gold_outage_events
    GROUP BY fips_code, event_year
),
rated AS (
    SELECT
        y.year,
        c.fips_code,
        n.county,
        c.state_abbr,
        c.state_name,
        c.census_region,
        c.fema_region,
        c.customers,
        COALESCE(t.events, 0)                                          AS events,
        COALESCE(t.customer_hours_lost, 0)                             AS customer_hours_lost,
        t.max_peak_customers_out,
        COALESCE(t.customer_hours_lost, 0) * 1000.0 / NULLIF(c.customers, 0) AS outage_hours_per_1000_customers,
        -- Ranked only with a denominator of 1,000+ (D11) in a state covered at 70%+ (D22).
        c.customers IS NOT NULL AND c.customers >= 1000 AND COALESCE(s.ranking_eligible, FALSE) AS ranking_eligible
    FROM counties AS c
    CROSS JOIN years AS y
    LEFT JOIN totals AS t ON t.fips_code = c.fips_code AND t.year = y.year
    LEFT JOIN names  AS n ON n.fips_code = c.fips_code
    LEFT JOIN gold_state_coverage AS s ON s.state_abbr = c.state_abbr
)
SELECT * FROM rated;


CREATE OR REPLACE TABLE gold_county_reliability
COMMENT 'Outage hours per 1,000 customers per county and year, 50 states and DC, ranked where eligible (D38, D44)'
AS
-- Counties of the 50 states and DC only; territory reporting units have their own table (D44).
-- RANK: 1 = most outage hours per 1,000 customers; ties share a rank (D38).
SELECT
    *,
    CASE WHEN ranking_eligible
         THEN RANK() OVER (PARTITION BY year, ranking_eligible ORDER BY outage_hours_per_1000_customers DESC) END AS national_rank,
    CASE WHEN ranking_eligible
         THEN RANK() OVER (PARTITION BY year, state_abbr, ranking_eligible ORDER BY outage_hours_per_1000_customers DESC) END AS state_rank
FROM gold_unit_reliability
WHERE census_region <> 'Territory';


CREATE OR REPLACE TABLE gold_territory_unit_reliability
COMMENT 'Outage hours per 1,000 customers per year for the PR PREPA regions and VI districts, same metrics, unranked (D44)'
AS
-- Puerto Rico reports by PREPA operating region and the Virgin Islands by island; these are not
-- counties, so they are reported with the same metrics but not ranked (D44).
SELECT
    year,
    fips_code,
    county AS reporting_unit,
    state_abbr,
    state_name,
    customers,
    events,
    customer_hours_lost,
    max_peak_customers_out,
    outage_hours_per_1000_customers,
    CASE state_abbr
        WHEN 'PR' THEN 'PREPA operating region, reported under the FIPS of its namesake municipio'
        WHEN 'VI' THEN 'Island district'
    END AS geography_note
FROM gold_unit_reliability
WHERE census_region = 'Territory';


CREATE OR REPLACE TABLE gold_state_reliability
COMMENT 'Outage hours per 1,000 customers per year for the 50 states and DC, with D22 coverage, ranked where eligible (D38, D43)'
AS
WITH
-- Per-1,000 uses only counties with a denominator; raw totals use all counties (D9).
-- Only the 50 states and DC are ranked here; territories have their own table (D43).
states AS (
    SELECT
        year,
        state_abbr,
        MAX(state_name)                                                 AS state_name,
        MAX(census_region)                                              AS census_region,
        MAX(fema_region)                                                AS fema_region,
        SUM(events)                                                     AS events,
        SUM(customer_hours_lost)                                        AS customer_hours_lost,
        SUM(CASE WHEN customers IS NOT NULL THEN customer_hours_lost END) AS customer_hours_with_denominator,
        SUM(customers)                                                  AS customers
    FROM gold_unit_reliability
    WHERE census_region <> 'Territory'
    GROUP BY year, state_abbr
)
SELECT
    s.year,
    s.state_abbr,
    s.state_name,
    s.census_region,
    s.fema_region,
    s.events,
    s.customer_hours_lost,
    s.customers,
    s.customer_hours_with_denominator * 1000.0 / NULLIF(s.customers, 0) AS outage_hours_per_1000_customers,
    c.eaglei_counties,
    c.total_counties,
    c.customer_coverage,
    c.ranking_eligible,
    CASE WHEN c.ranking_eligible
         THEN RANK() OVER (PARTITION BY s.year, c.ranking_eligible
                           ORDER BY s.customer_hours_with_denominator * 1000.0 / NULLIF(s.customers, 0) DESC) END AS national_rank,
    CASE WHEN c.ranking_eligible
         THEN RANK() OVER (PARTITION BY s.year, s.census_region, c.ranking_eligible
                           ORDER BY s.customer_hours_with_denominator * 1000.0 / NULLIF(s.customers, 0) DESC) END AS region_rank
FROM states AS s
LEFT JOIN gold_state_coverage AS c ON c.state_abbr = s.state_abbr;


CREATE OR REPLACE TABLE gold_territory_reliability
COMMENT 'Outage hours per 1,000 customers per year for Puerto Rico and the US Virgin Islands, same metrics, unranked (D43)'
AS
WITH
-- Same aggregation as gold_state_reliability, for the territories only (D43).
territories AS (
    SELECT
        year,
        state_abbr,
        MAX(state_name)                                                 AS state_name,
        SUM(events)                                                     AS events,
        SUM(customer_hours_lost)                                        AS customer_hours_lost,
        SUM(CASE WHEN customers IS NOT NULL THEN customer_hours_lost END) AS customer_hours_with_denominator,
        SUM(customers)                                                  AS customers,
        COUNT(*)                                                        AS reporting_units
    FROM gold_unit_reliability
    WHERE census_region = 'Territory'
    GROUP BY year, state_abbr
)
SELECT
    t.year,
    t.state_abbr,
    t.state_name,
    t.events,
    t.customer_hours_lost,
    t.customers,
    t.customer_hours_with_denominator * 1000.0 / NULLIF(t.customers, 0) AS outage_hours_per_1000_customers,
    t.reporting_units,
    c.customer_coverage,
    CASE t.state_abbr
        WHEN 'PR' THEN 'Results for Puerto Rico are for the 7 PREPA operating regions, not municipios'
        WHEN 'VI' THEN 'Reported by island'
    END AS geography_note
FROM territories AS t
LEFT JOIN gold_state_coverage AS c ON c.state_abbr = t.state_abbr;


CREATE OR REPLACE TABLE gold_utility_reliability
COMMENT 'EIA-861 SAIDI / SAIFI for IEEE 1366 reporters, ranked within size band and year; 1 = most reliable (D39)'
AS
WITH
-- Eversource and National Grid operating companies by EIA utility number (D39).
flagged AS (
    SELECT
        u.*,
        CASE
            WHEN u.utility_number IN ('4176', '54913', '15472') THEN 'Eversource'
            WHEN u.utility_number IN ('11804', '13206', '13573') THEN 'National Grid'
            WHEN u.utility_number = '13214' AND u.data_year = 2022 THEN 'National Grid (sold to PPL in May 2022)'
        END AS parent_company
    FROM silver_utility_reliability AS u
    WHERE u.reporting_standard = 'IEEE 1366'
),
-- EIA rows that copy another utility's full metric set, with a reliability customer count more than
-- 10% off the utility's own Sales count, are source errors: kept, flagged, not ranked (D39).
checked AS (
    SELECT
        *,
        COUNT(*) OVER (PARTITION BY data_year, saidi_with_med, saidi_without_med, saifi_with_med, saifi_without_med, reliability_customers) AS same_values
    FROM flagged
),
rankable AS (
    SELECT
        *,
        CASE
            WHEN same_values > 1 AND saidi_with_med IS NOT NULL
                 AND ABS(reliability_customers - customers) > 0.1 * customers
            THEN 'source row repeats the values of another utility'
        END AS data_quality_flag
    FROM checked
),
ranked_input AS (
    SELECT *, size_band <> 'unknown' AND data_quality_flag IS NULL AS in_size_band FROM rankable
)
-- Lower SAIDI / SAIFI is better, so rank 1 is the most reliable in its band (D39).
SELECT
    data_year,
    utility_number,
    utility_name,
    state_abbr,
    ownership,
    size_band,
    customers,
    saidi_with_med,
    saidi_without_med,
    saifi_with_med,
    saifi_without_med,
    parent_company,
    parent_company IS NOT NULL AS is_eversource_or_national_grid,
    data_quality_flag,
    COUNT(*) OVER (PARTITION BY data_year, size_band) AS utilities_in_band,
    CASE WHEN in_size_band AND saidi_without_med IS NOT NULL
         THEN RANK() OVER (PARTITION BY data_year, size_band, in_size_band AND saidi_without_med IS NOT NULL
                           ORDER BY saidi_without_med) END AS rank_saidi_without_med,
    CASE WHEN in_size_band AND saidi_with_med IS NOT NULL
         THEN RANK() OVER (PARTITION BY data_year, size_band, in_size_band AND saidi_with_med IS NOT NULL
                           ORDER BY saidi_with_med) END AS rank_saidi_with_med,
    CASE WHEN in_size_band AND saifi_without_med IS NOT NULL
         THEN RANK() OVER (PARTITION BY data_year, size_band, in_size_band AND saifi_without_med IS NOT NULL
                           ORDER BY saifi_without_med) END AS rank_saifi_without_med,
    CASE WHEN in_size_band AND saifi_with_med IS NOT NULL
         THEN RANK() OVER (PARTITION BY data_year, size_band, in_size_band AND saifi_with_med IS NOT NULL
                           ORDER BY saifi_with_med) END AS rank_saifi_with_med
FROM ranked_input;


CREATE OR REPLACE TABLE gold_utility_reliability_other
COMMENT 'EIA-861 utilities reporting under another standard; listed, never ranked with IEEE 1366 reporters (D23, D39)'
AS
SELECT
    data_year,
    utility_number,
    utility_name,
    state_abbr,
    ownership,
    size_band,
    customers,
    saidi_with_med,
    saidi_without_med,
    saifi_with_med,
    saifi_without_med
FROM silver_utility_reliability
WHERE reporting_standard = 'other';


-- -----------------------------------------------------------------------------
-- Checks: top 5 states per year, and the Eversource / National Grid ranks
-- -----------------------------------------------------------------------------

SELECT year, national_rank, state_abbr, ROUND(outage_hours_per_1000_customers) AS hours_per_1000, ROUND(customer_coverage, 3) AS coverage
FROM gold_state_reliability
WHERE national_rank <= 5
ORDER BY year, national_rank;

SELECT data_year, utility_name, state_abbr, size_band, rank_saidi_without_med, utilities_in_band
FROM gold_utility_reliability
WHERE is_eversource_or_national_grid
ORDER BY data_year, utility_name;
