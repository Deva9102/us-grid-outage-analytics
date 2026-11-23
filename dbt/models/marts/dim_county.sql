-- One row per county or reporting unit with a denominator row (D13): name, state, regions,
-- customers and how the denominator was set (D5, D9, D12, D21, D35, D36).
WITH
-- The denominator table is the county list of record.
denominators AS (
    SELECT fips_code, customers, denominator_source, denominator_mismatch, calibration_factor,
           state_calibration_factor, peak_floor_applied, peak_floor_skipped
    FROM {{ source('outages', 'dim_county_customers') }}
),
-- Names as EAGLE-I reports them, one per county and year, with the base-year peak (D35, D58).
county_years AS (
    SELECT
        fips_code,
        year,
        MAX(county)                                                       AS county,
        MAX(customers_out)                                                AS peak_customers_out
    FROM {{ source('outages', 'silver_outages') }}
    GROUP BY fips_code, year
),
-- The latest year's name is the county's name; the first year is when EAGLE-I first reports it (D61).
ordered AS (
    SELECT
        fips_code,
        county,
        ROW_NUMBER() OVER (PARTITION BY fips_code ORDER BY year DESC) AS newest
    FROM county_years
),
-- Per county: first reported year and the D35 floor (highest reading in the base years).
spans AS (
    SELECT
        fips_code,
        MIN(year)                                                         AS first_reported_year,
        MAX(CASE WHEN year IN ({{ var('denominator_base_years') | join(', ') }})
                 THEN peak_customers_out END)                             AS base_peak_customers_out
    FROM county_years
    GROUP BY fips_code
),
-- State attributes from the state FIPS prefix, never from names (D16).
states AS (
    SELECT state_fips, state_abbr, state_name, census_region, fema_region
    FROM {{ source('outages', 'bronze_state_regions') }}
)
SELECT
    d.fips_code,
    o.county,
    s.state_abbr,
    s.state_name,
    s.census_region,
    s.fema_region,
    d.customers,
    d.denominator_source,
    d.customers IS NOT NULL                                               AS has_denominator,
    d.denominator_mismatch,
    d.calibration_factor,
    d.state_calibration_factor,
    d.state_calibration_factor > 1                                        AS is_calibrated,
    d.peak_floor_applied,
    d.peak_floor_skipped,
    p.base_peak_customers_out,
    p.first_reported_year
FROM denominators AS d
LEFT JOIN ordered AS o ON o.fips_code = d.fips_code AND o.newest = 1
LEFT JOIN spans AS p ON p.fips_code = d.fips_code
LEFT JOIN states AS s ON s.state_fips = SUBSTRING(d.fips_code, 1, 2)
