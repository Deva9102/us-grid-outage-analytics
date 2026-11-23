-- One row per county and year in which EAGLE-I reports the county (D67). The release publishes
-- coverage only up to 2022, so for every year this is the coverage measure: which counties report,
-- and the customers they hold. Analyses compare years on the same counties with it, so coverage
-- growth is never read as outage growth.
WITH
-- A county reports in a year when it has at least one reading (rows exist only when customers
-- are out, D3, so the count is activity, not hours of coverage).
readings AS (
    SELECT
        fips_code,
        year,
        COUNT(*)            AS readings,
        MIN(reading_time)   AS first_reading,
        MAX(reading_time)   AS last_reading
    FROM {{ source('outages', 'silver_outages') }}
    GROUP BY fips_code, year
),
-- State and denominator of each county.
counties AS (
    SELECT fips_code, state_abbr, customers FROM {{ ref('dim_county') }}
)
SELECT
    {{ dbt.concat(["r.fips_code", "'-'", "CAST(r.year AS " ~ dbt.type_string() ~ ")"]) }} AS county_year_key,
    r.fips_code,
    c.state_abbr,
    r.year,
    CAST(r.readings AS {{ dbt.type_bigint() }})        AS readings,
    r.first_reading,
    r.last_reading,
    c.customers
FROM readings AS r
INNER JOIN counties AS c ON c.fips_code = r.fips_code
