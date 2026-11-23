-- Outage hours per 1,000 customers per county and year, 50 states and DC only (D38, D44). A
-- county has rows from its first reported year (D61). Unranked rows carry the footnote reason
-- (D9, D11, D22, D45, D46, D52, D60); ranked rows have none.
WITH
-- The ranked county table as Gold built it.
counties AS (
    SELECT * FROM {{ source('outages', 'gold_county_reliability') }}
)
SELECT
    {{ dbt.concat(["fips_code", "'-'", "CAST(year AS " ~ dbt.type_string() ~ ")"]) }} AS county_year_key,
    fips_code,
    state_abbr,
    year,
    CAST(customers AS {{ dbt.type_bigint() }})                   AS customers,
    CAST(events AS {{ dbt.type_bigint() }})                      AS events,
    customer_hours_lost,
    max_peak_customers_out,
    outage_hours_per_1000_customers,
    CAST(capped_customer_hours AS {{ dbt.type_float() }})        AS capped_customer_hours,
    capped_share,
    peak_to_customers,
    ranking_eligible,
    national_rank IS NOT NULL                                    AS is_ranked,
    national_rank,
    state_rank,
    rank_without_footnotes,
    footnote_reason,
    footnote_evidence
FROM counties
