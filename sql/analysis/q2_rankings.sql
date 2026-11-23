-- =============================================================================
-- Q2. States and counties with the most outage hours per 1,000 customers, per year.
-- Rates are capped customer-hours per 1,000 customers of the one-per-county denominator (D13,
-- D38). Only the 50 states and DC are ranked (D43, D44); unranked rows carry their footnote. A
-- county has rows from its first reported year (D61). Rank 1 = most outage hours.
-- =============================================================================

-- result: q2_state_ranks
-- Every state-year, ranked first, then the footnoted ones.
SELECT
    s.year,
    s.national_rank,
    d.state_name,
    s.state_abbr,
    d.census_region,
    ROUND(CAST(s.outage_hours_per_1000_customers AS DECIMAL(38, 6)), 1) AS outage_hours_per_1000,
    ROUND(CAST(s.customer_hours_lost AS DECIMAL(38, 6)), 0)             AS customer_hours_lost,
    s.events,
    s.footnote_reason
FROM fct_state_reliability AS s
INNER JOIN dim_state AS d ON d.state_abbr = s.state_abbr
ORDER BY s.year, s.national_rank NULLS LAST, s.state_abbr;

-- result: q2_county_top10
-- The ten ranked counties with the most outage hours per 1,000 customers in each year.
SELECT
    r.year,
    r.national_rank,
    c.county,
    r.state_abbr,
    r.fips_code,
    ROUND(CAST(r.outage_hours_per_1000_customers AS DECIMAL(38, 6)), 1) AS outage_hours_per_1000,
    r.customers,
    r.events
FROM fct_county_reliability AS r
INNER JOIN dim_county AS c ON c.fips_code = r.fips_code
WHERE r.national_rank <= 10
ORDER BY r.year, r.national_rank;

-- result: q2_county_footnoted
-- Footnoted counties that would have ranked in the top 25: why each is left out.
SELECT
    r.year,
    r.rank_without_footnotes,
    c.county,
    r.state_abbr,
    r.fips_code,
    ROUND(CAST(r.outage_hours_per_1000_customers AS DECIMAL(38, 6)), 1) AS outage_hours_per_1000,
    r.footnote_reason,
    r.footnote_evidence
FROM fct_county_reliability AS r
INNER JOIN dim_county AS c ON c.fips_code = r.fips_code
WHERE NOT r.is_ranked AND r.rank_without_footnotes <= 25
ORDER BY r.year, r.rank_without_footnotes;

-- result: q2_austin_tx
-- Austin County TX (48015): passed the D46 misattribution review and stays ranked.
SELECT
    r.year,
    r.national_rank,
    ROUND(CAST(r.outage_hours_per_1000_customers AS DECIMAL(38, 6)), 1) AS outage_hours_per_1000,
    r.customers,
    r.events,
    r.footnote_reason
FROM fct_county_reliability AS r
WHERE r.fips_code = '48015'
ORDER BY r.year;

-- result: q2_possible_misattributions
-- Counties outside the calibrated states whose highest 2022-2024 reading is above 1.25x their
-- customers (D36 reference list): their readings are flagged and capped (D4), not floored.
SELECT
    c.fips_code,
    c.county,
    c.state_abbr,
    c.customers,
    c.base_peak_customers_out,
    ROUND(CAST(c.base_peak_customers_out * 1.0 / c.customers AS DECIMAL(38, 6)), 2) AS peak_to_customers
FROM dim_county AS c
WHERE NOT c.is_calibrated
  AND c.base_peak_customers_out > 1.25 * c.customers
ORDER BY peak_to_customers DESC, c.fips_code;

-- result: q2_misattribution_recount
-- The same list counted by the year EAGLE-I first reports the county: the peak is already the
-- 2022-2024 base-year peak, so a county first reported in 2025 cannot be on it.
SELECT
    c.first_reported_year,
    COUNT(*) AS counties
FROM dim_county AS c
WHERE NOT c.is_calibrated
  AND c.base_peak_customers_out > 1.25 * c.customers
GROUP BY c.first_reported_year
ORDER BY c.first_reported_year;

-- result: q2_footnote_counts
-- Unranked state and county rows per year and reason.
SELECT 'state' AS level, year, footnote_reason, COUNT(*) AS rows_footnoted
FROM fct_state_reliability
WHERE NOT is_ranked
GROUP BY year, footnote_reason
UNION ALL
SELECT 'county', year, footnote_reason, COUNT(*)
FROM fct_county_reliability
WHERE NOT is_ranked
GROUP BY year, footnote_reason
ORDER BY level, year, rows_footnoted DESC, footnote_reason;

-- result: q2_ranked_counts
WITH
-- Ranked states per year.
states AS (
    SELECT year, COUNT(*) AS ranked_states FROM fct_state_reliability WHERE is_ranked GROUP BY year
),
-- Ranked counties per year.
counties AS (
    SELECT year, COUNT(*) AS ranked_counties FROM fct_county_reliability WHERE is_ranked GROUP BY year
)
SELECT s.year, s.ranked_states, c.ranked_counties
FROM states AS s
INNER JOIN counties AS c ON c.year = s.year
ORDER BY s.year;

-- result: q2_northeast_counties
WITH
-- Ranked Northeast counties (New England, New York, New Jersey, Pennsylvania), ranked again
-- within the region each year.
northeast AS (
    SELECT
        r.year,
        ROW_NUMBER() OVER (PARTITION BY r.year ORDER BY r.outage_hours_per_1000_customers DESC, r.fips_code) AS region_rank,
        r.national_rank,
        c.county,
        r.state_abbr,
        r.outage_hours_per_1000_customers,
        r.customers
    FROM fct_county_reliability AS r
    INNER JOIN dim_county AS c ON c.fips_code = r.fips_code
    INNER JOIN dim_state AS d ON d.state_abbr = r.state_abbr
    WHERE r.is_ranked AND d.census_region = 'Northeast'
)
SELECT year, region_rank, national_rank, county, state_abbr,
       ROUND(CAST(outage_hours_per_1000_customers AS DECIMAL(38, 6)), 1) AS outage_hours_per_1000, customers
FROM northeast
WHERE region_rank <= 5
ORDER BY year, region_rank;
