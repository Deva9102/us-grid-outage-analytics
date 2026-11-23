-- Mirrors the D43/D44 quality gate: only the 50 states and DC are ranked, and no year ranks more
-- states than there are jurisdictions. Returns the offending rows.
WITH
-- Ranked jurisdictions are every non-territory in the state lookup.
jurisdictions AS (
    SELECT state_abbr FROM {{ ref('dim_state') }} WHERE is_ranked_jurisdiction
),
-- Ranked states and counties outside them.
outside AS (
    SELECT 'state' AS level, s.state_abbr, s.year
    FROM {{ ref('fct_state_reliability') }} AS s
    LEFT JOIN jurisdictions AS j ON j.state_abbr = s.state_abbr
    WHERE s.is_ranked AND j.state_abbr IS NULL
    UNION ALL
    SELECT 'county', c.state_abbr, c.year
    FROM {{ ref('fct_county_reliability') }} AS c
    LEFT JOIN jurisdictions AS j ON j.state_abbr = c.state_abbr
    WHERE c.is_ranked AND j.state_abbr IS NULL
),
-- Years with more ranked states than jurisdictions.
too_many AS (
    SELECT 'state count' AS level, CAST(NULL AS {{ dbt.type_string() }}) AS state_abbr, year
    FROM {{ ref('fct_state_reliability') }}
    WHERE is_ranked
    GROUP BY year
    HAVING COUNT(DISTINCT state_abbr) > {{ var('ranked_jurisdictions') }}
)
SELECT * FROM outside
UNION ALL
SELECT * FROM too_many
