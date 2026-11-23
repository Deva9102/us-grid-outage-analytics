-- EAGLE-I's own coverage per state and year, as published with the data (coverage_history.csv,
-- D67): the share of the state's customers covered by the utilities EAGLE-I collects. Published
-- for 2018-2022 only; it also lists territories that EAGLE-I has no counties for (AS, GU, MP).
WITH
-- The parsed file.
coverage AS (
    SELECT * FROM {{ source('outages', 'silver_eaglei_coverage_history') }}
)
SELECT
    {{ dbt.concat(["state_abbr", "'-'", "CAST(year AS " ~ dbt.type_string() ~ ")"]) }} AS state_year_key,
    state_abbr,
    year,
    total_customers,
    min_covered,
    max_covered,
    min_share_covered,
    max_share_covered
FROM coverage
