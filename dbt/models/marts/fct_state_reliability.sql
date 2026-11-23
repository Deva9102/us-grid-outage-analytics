-- Outage hours per 1,000 customers per state and year, 50 states and DC only (D38, D43). States
-- below the coverage minimum, with unknown coverage or mostly without denominators are footnoted,
-- not ranked (D22, D52, D60).
WITH
-- The ranked state table as Gold built it.
states AS (
    SELECT * FROM {{ source('outages', 'gold_state_reliability') }}
)
SELECT
    {{ dbt.concat(["state_abbr", "'-'", "CAST(year AS " ~ dbt.type_string() ~ ")"]) }} AS state_year_key,
    state_abbr,
    year,
    CAST(events AS {{ dbt.type_bigint() }})                      AS events,
    customer_hours_lost,
    CAST(customers AS {{ dbt.type_bigint() }})                   AS customers,
    outage_hours_per_1000_customers,
    CAST(eaglei_counties AS {{ dbt.type_bigint() }})             AS eaglei_counties,
    CAST(total_counties AS {{ dbt.type_bigint() }})              AS total_counties,
    customer_coverage,
    ranking_eligible,
    national_rank IS NOT NULL                                    AS is_ranked,
    national_rank,
    region_rank,
    footnote_reason
FROM states
