-- Puerto Rico and the US Virgin Islands per year: same metrics as the states, never ranked
-- (D43). Puerto Rico's reporting units are PREPA's operating regions, not municipios (D22).
WITH
-- The territory table as Gold built it.
territories AS (
    SELECT * FROM {{ source('outages', 'gold_territory_reliability') }}
)
SELECT
    {{ dbt.concat(["state_abbr", "'-'", "CAST(year AS " ~ dbt.type_string() ~ ")"]) }} AS territory_year_key,
    state_abbr,
    year,
    CAST(events AS {{ dbt.type_bigint() }})                      AS events,
    customer_hours_lost,
    CAST(customers AS {{ dbt.type_bigint() }})                   AS customers,
    outage_hours_per_1000_customers,
    CAST(reporting_units AS {{ dbt.type_bigint() }})             AS reporting_units,
    customer_coverage,
    geography_note
FROM territories
