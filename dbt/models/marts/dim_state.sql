-- One row per state, DC and territory (53), with Census and FEMA regions and EAGLE-I coverage.
WITH
-- Region attributes come from the state FIPS lookup, as in Silver (D8, D16).
regions AS (
    SELECT state_fips, state_abbr, state_name, census_region, census_division, fema_region
    FROM {{ source('outages', 'bronze_state_regions') }}
),
-- Customer coverage against EIA-861 decides whether a state can be ranked (D22, D52).
coverage AS (
    SELECT state_abbr, total_counties, eaglei_counties, eaglei_customers, eia_customers,
           customer_coverage, ranking_eligible, coverage_status, calibration_factor
    FROM {{ source('outages', 'gold_state_coverage') }}
)
SELECT
    r.state_abbr,
    r.state_fips,
    r.state_name,
    r.census_region,
    r.census_division,
    r.fema_region,
    r.census_region <> 'Territory'                                 AS is_ranked_jurisdiction,
    CAST(c.total_counties AS {{ dbt.type_bigint() }})              AS total_counties,
    CAST(c.eaglei_counties AS {{ dbt.type_bigint() }})             AS eaglei_counties,
    CAST(c.eaglei_customers AS {{ dbt.type_bigint() }})            AS eaglei_customers,
    CAST(c.eia_customers AS {{ dbt.type_bigint() }})               AS eia_customers,
    c.customer_coverage,
    c.coverage_status,
    c.ranking_eligible                                             AS coverage_ranking_eligible,
    c.calibration_factor
FROM regions AS r
LEFT JOIN coverage AS c ON c.state_abbr = r.state_abbr
