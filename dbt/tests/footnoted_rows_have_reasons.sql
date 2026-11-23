-- Mirrors the D45/D46/D52 quality gates: every unranked state or county row says why, and no
-- ranked row carries a footnote. Returns the offending rows.
SELECT 'county' AS level, county_year_key AS row_key, footnote_reason
FROM {{ ref('fct_county_reliability') }}
WHERE (NOT is_ranked AND footnote_reason IS NULL)
   OR (is_ranked AND footnote_reason IS NOT NULL)
UNION ALL
SELECT 'state', state_year_key, footnote_reason
FROM {{ ref('fct_state_reliability') }}
WHERE (NOT is_ranked AND footnote_reason IS NULL)
   OR (is_ranked AND footnote_reason IS NOT NULL)
