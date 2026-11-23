-- EAGLE-I's data quality index per FEMA region and year, as published with the data (DQI.csv,
-- D67): collection success, utilities enabled, spatial precision and customer coverage, combined
-- into one index. Published for 2018-2022 only.
WITH
-- The parsed file.
dqi AS (
    SELECT * FROM {{ source('outages', 'silver_eaglei_dqi') }}
)
SELECT
    {{ dbt.concat(["fema_region", "'-'", "CAST(year AS " ~ dbt.type_string() ~ ")"]) }} AS region_year_key,
    fema_region,
    year,
    success_rate_pct,
    percent_enabled,
    spatial_precision_pct,
    customer_coverage_pct,
    max_covered,
    total_customers,
    dqi
FROM dqi
