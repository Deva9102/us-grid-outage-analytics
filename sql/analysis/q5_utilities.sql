-- =============================================================================
-- Q5. Utility reliability from EIA-861: SAIDI (minutes without power per customer per year) and
-- SAIFI (interruptions per customer) ranked within size bands, IEEE 1366 reporters only (D23,
-- D39); 1 = most reliable. Eversource and National Grid operating companies against their peers.
-- Figures "without MED" exclude major event days, the usual basis for comparing utilities.
-- =============================================================================

-- result: q5_band_summary
-- The spread of each band: the yardstick a utility is ranked against.
SELECT
    data_year,
    size_band,
    COUNT(*)                                                                    AS ranked_utilities,
    ROUND(CAST(PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY saidi_without_med) AS DECIMAL(38, 6)), 1)   AS saidi_p25,
    ROUND(CAST(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY saidi_without_med) AS DECIMAL(38, 6)), 1)    AS saidi_median,
    ROUND(CAST(PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY saidi_without_med) AS DECIMAL(38, 6)), 1)   AS saidi_p75,
    ROUND(CAST(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY saifi_without_med) AS DECIMAL(38, 6)), 3)    AS saifi_median
FROM fct_utility_reliability
WHERE is_ranked
GROUP BY data_year, size_band
ORDER BY data_year, size_band;

-- result: q5_eversource_national_grid
WITH
-- Band medians, to say how far each company sits from its peers.
bands AS (
    SELECT
        data_year,
        size_band,
        PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY saidi_without_med) AS saidi_median,
        PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY saifi_without_med) AS saifi_median
    FROM fct_utility_reliability
    WHERE is_ranked
    GROUP BY data_year, size_band
)
SELECT
    f.data_year,
    u.parent_company,
    u.utility_name,
    f.state_abbr,
    f.size_band,
    f.reporting_group,
    ROUND(CAST(f.saidi_without_med AS DECIMAL(38, 6)), 1)                    AS saidi_without_med,
    f.rank_saidi_without_med,
    f.utilities_in_band,
    ROUND(CAST(b.saidi_median AS DECIMAL(38, 6)), 1)                         AS band_saidi_median,
    ROUND(CAST(f.saidi_without_med / b.saidi_median AS DECIMAL(38, 6)), 2)   AS saidi_vs_median,
    ROUND(CAST(f.saidi_without_med - b.saidi_median AS DECIMAL(38, 6)), 1)   AS saidi_minutes_above_median,
    ROUND(CAST(f.saifi_without_med AS DECIMAL(38, 6)), 3)                    AS saifi_without_med,
    f.rank_saifi_without_med,
    ROUND(CAST(f.saidi_with_med AS DECIMAL(38, 6)), 1)                       AS saidi_with_med,
    f.rank_saidi_with_med,
    f.data_quality_flag
FROM fct_utility_reliability AS f
INNER JOIN dim_utility AS u ON u.utility_number = f.utility_number
LEFT JOIN bands AS b ON b.data_year = f.data_year AND b.size_band = f.size_band
WHERE u.is_eversource_or_national_grid
ORDER BY f.data_year, u.parent_company, f.state_abbr, u.utility_name;

-- result: q5_benchmark_latest
WITH
-- The newest year with an Eversource or National Grid company ranked.
latest AS (
    SELECT MAX(f.data_year) AS data_year
    FROM fct_utility_reliability AS f
    INNER JOIN dim_utility AS u ON u.utility_number = f.utility_number
    WHERE u.is_eversource_or_national_grid AND f.is_ranked
),
-- The bands those companies are ranked in that year.
peer_bands AS (
    SELECT DISTINCT f.size_band
    FROM fct_utility_reliability AS f
    INNER JOIN dim_utility AS u ON u.utility_number = f.utility_number
    INNER JOIN latest AS l ON l.data_year = f.data_year
    WHERE u.is_eversource_or_national_grid AND f.is_ranked
)
SELECT
    f.data_year,
    f.size_band,
    u.utility_name,
    f.state_abbr,
    COALESCE(u.parent_company, '')                AS parent_company,
    u.is_eversource_or_national_grid,
    ROUND(CAST(f.saidi_without_med AS DECIMAL(38, 6)), 1)                 AS saidi_without_med,
    f.rank_saidi_without_med,
    f.utilities_in_band
FROM fct_utility_reliability AS f
INNER JOIN dim_utility AS u ON u.utility_number = f.utility_number
INNER JOIN latest AS l ON l.data_year = f.data_year
INNER JOIN peer_bands AS p ON p.size_band = f.size_band
WHERE f.is_ranked
ORDER BY f.size_band, f.rank_saidi_without_med, u.utility_name;
