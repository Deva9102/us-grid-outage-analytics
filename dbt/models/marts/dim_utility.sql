-- One row per EIA-861 utility number, with its newest name and ownership and its parent company
-- (D32, D39). A utility can report in several states; the facts carry the state.
WITH
-- Every reliability report of every utility, whatever its standard.
reports AS (
    SELECT data_year, utility_number, utility_name, state_abbr, ownership
    FROM {{ source('outages', 'silver_utility_reliability') }}
),
-- The newest report names the utility (names change after mergers).
ordered AS (
    SELECT
        utility_number,
        utility_name,
        ownership,
        ROW_NUMBER() OVER (PARTITION BY utility_number ORDER BY data_year DESC, state_abbr) AS newest
    FROM reports
),
-- Years and states the utility reported in.
spans AS (
    SELECT
        utility_number,
        MIN(data_year)                AS first_year,
        MAX(data_year)                AS last_year,
        COUNT(DISTINCT state_abbr)    AS states_reported
    FROM reports
    GROUP BY utility_number
),
-- Parent company and the Eversource / National Grid flag come from the ranked table (D39).
parents AS (
    SELECT
        utility_number,
        MAX(parent_company)                                   AS parent_company,
        {{ dbt.bool_or('is_eversource_or_national_grid') }}   AS is_eversource_or_national_grid
    FROM {{ source('outages', 'gold_utility_reliability') }}
    GROUP BY utility_number
)
SELECT
    o.utility_number,
    o.utility_name,
    o.ownership,
    p.parent_company,
    COALESCE(p.is_eversource_or_national_grid, FALSE)        AS is_eversource_or_national_grid,
    s.first_year,
    s.last_year,
    CAST(s.states_reported AS {{ dbt.type_bigint() }})       AS states_reported
FROM ordered AS o
INNER JOIN spans AS s ON s.utility_number = o.utility_number
LEFT JOIN parents AS p ON p.utility_number = o.utility_number
WHERE o.newest = 1
