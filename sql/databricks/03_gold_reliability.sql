-- =============================================================================
-- 03_gold_reliability.sql
-- Gold layer: reliability rankings. Runs after 03_gold_coverage.sql (D26).
--
--   gold_unit_reliability            outage hours per 1,000 customers per reporting unit and year, unranked (D38, D44)
--   gold_county_reliability          the same for counties of the 50 states and DC, ranked (D38, D44)
--   gold_territory_unit_reliability  the same for PR PREPA regions and VI districts, unranked (D44)
--   gold_county_ranking_footnotes    county-years not ranked, with the rank they would have had (D45, D46)
--   gold_state_reliability           the same per state, 50 states and DC, with D22 coverage (D38, D43)
--   gold_territory_reliability       the same for Puerto Rico and the Virgin Islands, unranked (D43)
--   gold_utility_reliability         EIA-861 SAIDI / SAIFI ranked within size bands, IEEE 1366 only (D39)
--   gold_utility_reliability_other   other-standard utilities, listed, not ranked (D23, D39)
--
-- scripts/test_gold_analysis_duckdb.py runs these statements in DuckDB. Keep each in the form
-- CREATE OR REPLACE TABLE <name> COMMENT '...' AS <query>;
-- =============================================================================

SET TIME ZONE 'UTC';

USE CATALOG ${project.catalog};
USE SCHEMA ${project.schema};


CREATE OR REPLACE TABLE gold_unit_reliability
COMMENT 'Outage hours per 1,000 customers per EAGLE-I reporting unit and year, unranked base for counties and territories (D38, D44)'
AS
WITH
years AS (
    SELECT DISTINCT event_year AS year FROM gold_outage_events
),
-- The first year EAGLE-I reports each county. Years before it are a coverage gap, not zero
-- outages, so the county has no row for them (D58): coverage growth is never outage growth.
first_years AS (
    SELECT fips_code, MIN(year) AS first_year FROM silver_outages GROUP BY fips_code
),
-- Every county appears in every year from its first reported year, so a quiet year counts as zero.
counties AS (
    SELECT
        d.fips_code,
        d.customers,
        r.state_abbr,
        r.state_name,
        r.census_region,
        r.fema_region,
        f.first_year
    FROM dim_county_customers AS d
    INNER JOIN bronze_state_regions AS r ON r.state_fips = LEFT(d.fips_code, 2)
    INNER JOIN first_years AS f ON f.fips_code = d.fips_code
),
names AS (
    SELECT fips_code, MAX(county) AS county FROM gold_outage_events GROUP BY fips_code
),
-- Events count in the year they start; customer-hours are already capped by the denominator (D4).
totals AS (
    SELECT
        fips_code,
        event_year AS year,
        COUNT(*)                 AS events,
        SUM(customer_hours_lost) AS customer_hours_lost,
        MAX(peak_customers_out)  AS max_peak_customers_out
    FROM gold_outage_events
    GROUP BY fips_code, event_year
),
-- Customer-hours from readings above the county's customers, which D4 caps: measured over the
-- readings inside each event at or above its threshold (D45).
capping AS (
    SELECT
        e.fips_code,
        e.event_year AS year,
        SUM(CASE WHEN s.customers_out > d.customers THEN d.customers * 0.25 END) AS capped_customer_hours
    FROM gold_outage_events AS e
    INNER JOIN silver_outages AS s
        ON  s.fips_code      = e.fips_code
        AND s.reading_time  >= e.event_start
        AND s.reading_time   < e.event_end
        AND s.customers_out >= e.event_threshold
    INNER JOIN dim_county_customers AS d ON d.fips_code = e.fips_code
    GROUP BY e.fips_code, e.event_year
),
rated AS (
    SELECT
        y.year,
        c.fips_code,
        n.county,
        c.state_abbr,
        c.state_name,
        c.census_region,
        c.fema_region,
        c.customers,
        COALESCE(t.events, 0)                                          AS events,
        COALESCE(t.customer_hours_lost, 0)                             AS customer_hours_lost,
        t.max_peak_customers_out,
        COALESCE(t.customer_hours_lost, 0) * 1000.0 / NULLIF(c.customers, 0) AS outage_hours_per_1000_customers,
        COALESCE(cp.capped_customer_hours, 0)                          AS capped_customer_hours,
        COALESCE(cp.capped_customer_hours, 0) / NULLIF(t.customer_hours_lost, 0) AS capped_share,
        t.max_peak_customers_out * 1.0 / NULLIF(c.customers, 0)        AS peak_to_customers,
        -- Ranked only with a denominator of ranking.min_customers+ (D11) in a state covered at the coverage minimum (D22).
        c.customers IS NOT NULL AND c.customers >= ${ranking.min_customers} AND COALESCE(s.ranking_eligible, FALSE) AS ranking_eligible,
        COALESCE(s.coverage_status, 'coverage_unknown')                AS state_coverage_status
    FROM counties AS c
    INNER JOIN years AS y ON y.year >= c.first_year
    LEFT JOIN totals AS t ON t.fips_code = c.fips_code AND t.year = y.year
    LEFT JOIN names  AS n ON n.fips_code = c.fips_code
    LEFT JOIN capping AS cp ON cp.fips_code = c.fips_code AND cp.year = y.year
    LEFT JOIN gold_state_coverage AS s ON s.state_abbr = c.state_abbr
)
SELECT * FROM rated;


CREATE OR REPLACE TABLE gold_county_reliability
COMMENT 'Outage hours per 1,000 customers per county and year, 50 states and DC, ranked unless footnoted (D38, D44, D45, D46)'
AS
WITH
-- Share of each state-year's customer-hours in reporting units without a denominator (D60):
-- Connecticut's planning regions from 2025-05-29 have none, so its counties' 2025 rates cover
-- only part of the year.
state_years AS (
    SELECT
        year,
        state_abbr,
        COALESCE(SUM(CASE WHEN customers IS NULL THEN customer_hours_lost END), 0)
            / NULLIF(SUM(customer_hours_lost), 0) AS share_without_denominator
    FROM gold_unit_reliability
    GROUP BY year, state_abbr
),
-- Counties of the 50 states and DC only; territory reporting units have their own table (D44).
base AS (
    SELECT u.*, x.reason AS exclusion_reason, x.evidence AS exclusion_evidence,
           COALESCE(sy.share_without_denominator, 0) AS state_share_without_denominator
    FROM gold_unit_reliability AS u
    LEFT JOIN bronze_ranking_exclusions AS x
        ON x.fips_code = u.fips_code AND TRY_CAST(x.year AS INT) = u.year
    LEFT JOIN state_years AS sy ON sy.year = u.year AND sy.state_abbr = u.state_abbr
    WHERE u.census_region <> 'Territory'
),
-- Why a county-year is not ranked; the first reason that applies is kept. Footnoted county-years
-- stay in all raw totals (D9, D11, D22, D45, D46, D52).
reasons AS (
    SELECT
        *,
        CASE
            WHEN customers IS NULL THEN 'no denominator (D9)'
            WHEN customers < ${ranking.min_customers} THEN 'denominator under ${ranking.min_customers_label} customers (D11)'
            WHEN state_coverage_status = 'coverage_unknown' THEN 'coverage_unknown'
            WHEN NOT ranking_eligible THEN 'state below ${coverage.min_customer_coverage_pct}% customer coverage (D22)'
            WHEN state_share_without_denominator > ${ranking.max_share_without_denominator}
                THEN 'over ${ranking.max_share_without_denominator_pct}% of customer-hours in the state in units without a denominator (D60)'
            WHEN exclusion_reason IS NOT NULL THEN CONCAT('reviewed exclusion (D46): ', exclusion_reason)
            WHEN capped_share > ${footnotes.capped_share} AND peak_to_customers > ${footnotes.peak_to_customers}
                THEN 'over ${footnotes.capped_share_pct}% of customer-hours from capped readings and peak above ${footnotes.peak_to_customers_label}x customers (D45)'  -- noqa: LT05
        END AS footnote_reason,
        CASE
            WHEN exclusion_reason IS NOT NULL THEN exclusion_evidence
            WHEN capped_share > ${footnotes.capped_share} AND peak_to_customers > ${footnotes.peak_to_customers}
                THEN CONCAT('capped share ', CAST(ROUND(capped_share * 100, 1) AS STRING),
                            '%, peak ', CAST(ROUND(peak_to_customers, 1) AS STRING), 'x customers')
        END AS footnote_evidence
    FROM base
)
-- RANK: 1 = most outage hours per 1,000 customers; ties share a rank (D38). rank_without_footnotes is
-- the place a footnoted county-year would have had among all counties with a rate.
SELECT
    year,
    fips_code,
    county,
    state_abbr,
    state_name,
    census_region,
    fema_region,
    customers,
    events,
    customer_hours_lost,
    max_peak_customers_out,
    outage_hours_per_1000_customers,
    capped_customer_hours,
    capped_share,
    peak_to_customers,
    footnote_reason IS NULL AS ranking_eligible,
    footnote_reason,
    footnote_evidence,
    CASE WHEN outage_hours_per_1000_customers IS NOT NULL
         THEN RANK() OVER (PARTITION BY year, outage_hours_per_1000_customers IS NOT NULL
                           ORDER BY outage_hours_per_1000_customers DESC) END AS rank_without_footnotes,
    CASE WHEN footnote_reason IS NULL
         THEN RANK() OVER (PARTITION BY year, footnote_reason IS NULL ORDER BY outage_hours_per_1000_customers DESC) END AS national_rank,
    CASE WHEN footnote_reason IS NULL
         THEN RANK() OVER (PARTITION BY year, state_abbr, footnote_reason IS NULL ORDER BY outage_hours_per_1000_customers DESC) END AS state_rank
FROM reasons;


CREATE OR REPLACE TABLE gold_county_ranking_footnotes
COMMENT 'County-years shown as footnotes instead of ranks, with the rank they would have had and why (D11, D45, D46)'
AS
SELECT
    year,
    fips_code,
    county,
    state_abbr,
    customers,
    outage_hours_per_1000_customers,
    rank_without_footnotes AS would_have_rank,
    footnote_reason,
    footnote_evidence,
    capped_share,
    peak_to_customers
FROM gold_county_reliability
WHERE footnote_reason IS NOT NULL;


CREATE OR REPLACE TABLE gold_territory_unit_reliability
COMMENT 'Outage hours per 1,000 customers per year for the PR PREPA regions and VI districts, same metrics, unranked (D44)'
AS
-- Puerto Rico reports by PREPA operating region and the Virgin Islands by island; these are not
-- counties, so they are reported with the same metrics but not ranked (D44).
SELECT
    year,
    fips_code,
    county AS reporting_unit,
    state_abbr,
    state_name,
    customers,
    events,
    customer_hours_lost,
    max_peak_customers_out,
    outage_hours_per_1000_customers,
    CASE state_abbr
        WHEN 'PR' THEN 'PREPA operating region, reported under the FIPS of its namesake municipio'
        WHEN 'VI' THEN 'Island district'
    END AS geography_note
FROM gold_unit_reliability
WHERE census_region = 'Territory';


CREATE OR REPLACE TABLE gold_state_reliability
COMMENT 'Outage hours per 1,000 customers per year for the 50 states and DC, with D22 coverage, ranked where eligible (D38, D43)'
AS
WITH
-- Per-1,000 uses only counties with a denominator; raw totals use all counties (D9).
-- Only the 50 states and DC are ranked here; territories have their own table (D43).
states AS (
    SELECT
        year,
        state_abbr,
        MAX(state_name)                                                 AS state_name,
        MAX(census_region)                                              AS census_region,
        MAX(fema_region)                                                AS fema_region,
        SUM(events)                                                     AS events,
        SUM(customer_hours_lost)                                        AS customer_hours_lost,
        SUM(CASE WHEN customers IS NOT NULL THEN customer_hours_lost END) AS customer_hours_with_denominator,
        SUM(customers)                                                  AS customers
    FROM gold_unit_reliability
    WHERE census_region <> 'Territory'
    GROUP BY year, state_abbr
),
-- Ranked only when covered (D22, D52) and with most customer-hours in units with a denominator (D60).
eligibility AS (
    SELECT
        s.*,
        COALESCE(1 - s.customer_hours_with_denominator / NULLIF(s.customer_hours_lost, 0), 0) AS share_without_denominator,
        COALESCE(c.ranking_eligible, FALSE)
            AND COALESCE(1 - s.customer_hours_with_denominator / NULLIF(s.customer_hours_lost, 0), 0)
                <= ${ranking.max_share_without_denominator} AS rank_this_year
    FROM states AS s
    LEFT JOIN gold_state_coverage AS c ON c.state_abbr = s.state_abbr
)
SELECT
    s.year,
    s.state_abbr,
    s.state_name,
    s.census_region,
    s.fema_region,
    s.events,
    s.customer_hours_lost,
    s.customers,
    s.customer_hours_with_denominator * 1000.0 / NULLIF(s.customers, 0) AS outage_hours_per_1000_customers,
    c.eaglei_counties,
    c.total_counties,
    c.customer_coverage,
    c.ranking_eligible,
    CASE
        WHEN COALESCE(c.coverage_status, 'coverage_unknown') = 'coverage_unknown' THEN 'coverage_unknown'
        WHEN NOT c.ranking_eligible THEN 'state below ${coverage.min_customer_coverage_pct}% customer coverage (D22)'
        WHEN NOT s.rank_this_year
            THEN 'over ${ranking.max_share_without_denominator_pct}% of customer-hours in units without a denominator (D60)'
    END AS footnote_reason,
    CASE WHEN s.rank_this_year
         THEN RANK() OVER (PARTITION BY s.year, s.rank_this_year
                           ORDER BY s.customer_hours_with_denominator * 1000.0 / NULLIF(s.customers, 0) DESC) END AS national_rank,
    CASE WHEN s.rank_this_year
         THEN RANK() OVER (PARTITION BY s.year, s.census_region, s.rank_this_year
                           ORDER BY s.customer_hours_with_denominator * 1000.0 / NULLIF(s.customers, 0) DESC) END AS region_rank
FROM eligibility AS s
LEFT JOIN gold_state_coverage AS c ON c.state_abbr = s.state_abbr;


CREATE OR REPLACE TABLE gold_territory_reliability
COMMENT 'Outage hours per 1,000 customers per year for Puerto Rico and the US Virgin Islands, same metrics, unranked (D43)'
AS
WITH
-- Same aggregation as gold_state_reliability, for the territories only (D43).
territories AS (
    SELECT
        year,
        state_abbr,
        MAX(state_name)                                                 AS state_name,
        SUM(events)                                                     AS events,
        SUM(customer_hours_lost)                                        AS customer_hours_lost,
        SUM(CASE WHEN customers IS NOT NULL THEN customer_hours_lost END) AS customer_hours_with_denominator,
        SUM(customers)                                                  AS customers,
        COUNT(*)                                                        AS reporting_units
    FROM gold_unit_reliability
    WHERE census_region = 'Territory'
    GROUP BY year, state_abbr
)
SELECT
    t.year,
    t.state_abbr,
    t.state_name,
    t.events,
    t.customer_hours_lost,
    t.customers,
    t.customer_hours_with_denominator * 1000.0 / NULLIF(t.customers, 0) AS outage_hours_per_1000_customers,
    t.reporting_units,
    c.customer_coverage,
    CASE t.state_abbr
        WHEN 'PR' THEN 'Results for Puerto Rico are for the 7 PREPA operating regions, not municipios'
        WHEN 'VI' THEN 'Reported by island'
    END AS geography_note
FROM territories AS t
LEFT JOIN gold_state_coverage AS c ON c.state_abbr = t.state_abbr;


CREATE OR REPLACE TABLE gold_utility_reliability
COMMENT 'EIA-861 SAIDI / SAIFI for IEEE 1366 reporters, ranked within size band and year; 1 = most reliable (D39)'
AS
WITH
-- Eversource and National Grid operating companies by EIA utility number (D39; utilities in config).
flagged AS (
    SELECT
        u.*,
        CASE
            WHEN u.utility_number IN (${utilities.eversource_ids_sql}) THEN 'Eversource'
            WHEN u.utility_number IN (${utilities.national_grid_ids_sql}) THEN 'National Grid'
            WHEN u.utility_number = '${utilities.national_grid_sold.utility_number}' AND u.data_year = ${utilities.national_grid_sold.year}
                THEN '${utilities.national_grid_sold.label}'
        END AS parent_company
    FROM silver_utility_reliability AS u
    WHERE u.reporting_standard = 'IEEE 1366'
),
-- EIA rows that copy another utility's full metric set, with a reliability customer count more than
-- utilities.source_error_customer_share off the utility's own Sales count, are source errors: kept, flagged, not ranked (D39).
checked AS (
    SELECT
        *,
        COUNT(*) OVER (PARTITION BY data_year, saidi_with_med, saidi_without_med, saifi_with_med, saifi_without_med, reliability_customers) AS same_values
    FROM flagged
),
rankable AS (
    SELECT
        *,
        CASE
            WHEN same_values > 1 AND saidi_with_med IS NOT NULL
                 AND ABS(reliability_customers - customers) > ${utilities.source_error_customer_share} * customers
            THEN 'source row repeats the values of another utility'
        END AS data_quality_flag
    FROM checked
),
ranked_input AS (
    SELECT *, size_band <> 'unknown' AND data_quality_flag IS NULL AS in_size_band FROM rankable
)
-- Lower SAIDI / SAIFI is better, so rank 1 is the most reliable in its band (D39).
SELECT
    data_year,
    utility_number,
    utility_name,
    state_abbr,
    ownership,
    size_band,
    customers,
    saidi_with_med,
    saidi_without_med,
    saifi_with_med,
    saifi_without_med,
    parent_company,
    parent_company IS NOT NULL AS is_eversource_or_national_grid,
    data_quality_flag,
    COUNT(*) OVER (PARTITION BY data_year, size_band) AS utilities_in_band,
    CASE WHEN in_size_band AND saidi_without_med IS NOT NULL
         THEN RANK() OVER (PARTITION BY data_year, size_band, in_size_band AND saidi_without_med IS NOT NULL
                           ORDER BY saidi_without_med) END AS rank_saidi_without_med,
    CASE WHEN in_size_band AND saidi_with_med IS NOT NULL
         THEN RANK() OVER (PARTITION BY data_year, size_band, in_size_band AND saidi_with_med IS NOT NULL
                           ORDER BY saidi_with_med) END AS rank_saidi_with_med,
    CASE WHEN in_size_band AND saifi_without_med IS NOT NULL
         THEN RANK() OVER (PARTITION BY data_year, size_band, in_size_band AND saifi_without_med IS NOT NULL
                           ORDER BY saifi_without_med) END AS rank_saifi_without_med,
    CASE WHEN in_size_band AND saifi_with_med IS NOT NULL
         THEN RANK() OVER (PARTITION BY data_year, size_band, in_size_band AND saifi_with_med IS NOT NULL
                           ORDER BY saifi_with_med) END AS rank_saifi_with_med
FROM ranked_input;


CREATE OR REPLACE TABLE gold_utility_reliability_other
COMMENT 'EIA-861 utilities reporting under another standard; listed, never ranked with IEEE 1366 reporters (D23, D39)'
AS
SELECT
    data_year,
    utility_number,
    utility_name,
    state_abbr,
    ownership,
    size_band,
    customers,
    saidi_with_med,
    saidi_without_med,
    saifi_with_med,
    saifi_without_med
FROM silver_utility_reliability
WHERE reporting_standard = 'other';


-- -----------------------------------------------------------------------------
-- Checks: top 5 states per year, and the Eversource / National Grid ranks
-- -----------------------------------------------------------------------------

SELECT year, national_rank, state_abbr, ROUND(outage_hours_per_1000_customers) AS hours_per_1000, ROUND(customer_coverage, 3) AS coverage
FROM gold_state_reliability
WHERE national_rank <= 5
ORDER BY year, national_rank;

SELECT data_year, utility_name, state_abbr, size_band, rank_saidi_without_med, utilities_in_band
FROM gold_utility_reliability
WHERE is_eversource_or_national_grid
ORDER BY data_year, utility_name;
