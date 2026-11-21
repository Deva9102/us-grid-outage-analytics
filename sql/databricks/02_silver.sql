-- =============================================================================
-- 02_silver.sql
-- Silver layer: one denominator table and one unified outage table.
--
--   dim_county_customers  one customer denominator per county for all years (D13, D21)
--   silver_outages        all EAGLE-I years, cleaned, partitioned by year and state
--
-- Rule numbers refer to docs/decisions.md. The same logic is tested locally in
-- scripts/test_silver_duckdb.py; keep the two in step.
--
-- Runs after 02_silver_sources.sql: the D21 calibration reads silver_eia_state_customers (D26).
-- =============================================================================

-- Raw timestamps carry no zone and are UTC (D1). Fixing the session zone makes
-- parsing and display UTC regardless of workspace defaults.
SET TIME ZONE 'UTC';

USE CATALOG workspace;
USE SCHEMA outages;


-- -----------------------------------------------------------------------------
-- dim_county_customers (D5, D9, D12, D13, D21)
-- -----------------------------------------------------------------------------

CREATE OR REPLACE TABLE dim_county_customers (
    fips_code            STRING  NOT NULL COMMENT '5-digit county FIPS',
    customers            BIGINT           COMMENT 'One denominator for all years; NULL if none (has_denominator = false)',
    denominator_source   STRING           COMMENT 'total_customers_2024, max_mcc_2024, mcc, or NULL',
    denominator_mismatch BOOLEAN NOT NULL COMMENT 'True when MCC and 2024 total_customers differ by more than 2x (D12)',
    calibration_factor   DOUBLE  NOT NULL COMMENT 'State D13 total / EIA-861 2024 total where above 1.25, else 1.0 (D21)'
)
COMMENT 'Customer denominator per county, decisions D12, D13 and D21';

INSERT OVERWRITE dim_county_customers
WITH
-- Every county seen in any year gets a row, so no outage row loses its denominator join.
eaglei_counties AS (
    SELECT LPAD(TRIM(fips_code), 5, '0') AS fips_code FROM bronze_eaglei_2022
    UNION
    SELECT LPAD(TRIM(fips_code), 5, '0') FROM bronze_eaglei_2023
    UNION
    SELECT LPAD(TRIM(fips_code), 5, '0') FROM bronze_eaglei_2024
),
-- 2024 total_customers is constant per county, so one value per county loses nothing (D13).
totals_2024 AS (
    SELECT
        LPAD(TRIM(fips_code), 5, '0')            AS fips_code,
        MAX(TRY_CAST(total_customers AS BIGINT)) AS total_customers_2024
    FROM bronze_eaglei_2024
    GROUP BY 1
),
-- MCC stores FIPS as numbers (lost leading zeros) and ends with a Grand Total row (D5).
mcc AS (
    SELECT
        LPAD(TRIM(County_FIPS), 5, '0')  AS fips_code,
        TRY_CAST(Customers AS BIGINT)    AS mcc_customers
    FROM bronze_eaglei_mcc
    WHERE TRIM(County_FIPS) RLIKE '^[0-9]+$'
),
-- A gap above 2x between the two sources is a data error, not growth (D12).
compared AS (
    SELECT
        c.fips_code,
        t.total_customers_2024,
        m.mcc_customers,
        COALESCE(
            GREATEST(t.total_customers_2024, m.mcc_customers)
                > 2 * LEAST(t.total_customers_2024, m.mcc_customers),
            FALSE
        ) AS is_mismatch
    FROM eaglei_counties AS c
    LEFT JOIN totals_2024 AS t ON t.fips_code = c.fips_code
    LEFT JOIN mcc         AS m ON m.fips_code = c.fips_code
),
-- Fallback order (D13): 2024 value with the D12 rule, then MCC, then none.
d13 AS (
    SELECT
        fips_code,
        CASE
            WHEN is_mismatch                      THEN GREATEST(total_customers_2024, mcc_customers)
            WHEN total_customers_2024 IS NOT NULL THEN total_customers_2024
            ELSE mcc_customers
        END AS customers,
        CASE
            WHEN is_mismatch                      THEN 'max_mcc_2024'
            WHEN total_customers_2024 IS NOT NULL THEN 'total_customers_2024'
            WHEN mcc_customers IS NOT NULL        THEN 'mcc'
        END AS denominator_source,
        is_mismatch AS denominator_mismatch
    FROM compared
),
-- State totals of the D13 denominators, compared with EIA-861 2024 customers (D21).
state_totals AS (
    SELECT r.state_abbr, SUM(d.customers) AS d13_customers
    FROM d13 AS d
    INNER JOIN bronze_state_regions AS r ON r.state_fips = LEFT(d.fips_code, 2)
    GROUP BY r.state_abbr
),
-- Scale a state down only where it exceeds EIA by more than 25%; never scale up (D21).
factors AS (
    SELECT
        s.state_abbr,
        CASE WHEN s.d13_customers > 1.25 * e.customers THEN s.d13_customers / e.customers ELSE 1.0 END AS calibration_factor
    FROM state_totals AS s
    LEFT JOIN silver_eia_state_customers AS e ON e.state_abbr = s.state_abbr AND e.data_year = 2024
)
-- Each county keeps its share of the state; still one denominator per county (D13).
SELECT
    d.fips_code,
    CAST(ROUND(d.customers / COALESCE(f.calibration_factor, 1.0)) AS BIGINT) AS customers,
    d.denominator_source,
    d.denominator_mismatch,
    CAST(COALESCE(f.calibration_factor, 1.0) AS DOUBLE) AS calibration_factor
FROM d13 AS d
LEFT JOIN bronze_state_regions AS r ON r.state_fips = LEFT(d.fips_code, 2)
LEFT JOIN factors AS f ON f.state_abbr = r.state_abbr;


-- -----------------------------------------------------------------------------
-- silver_outages (D1, D2, D4, D6, D7, D8, D15, D16)
-- -----------------------------------------------------------------------------

CREATE OR REPLACE TABLE silver_outages (
    fips_code         STRING    NOT NULL COMMENT '5-digit county FIPS',
    county            STRING             COMMENT 'County name as reported by EAGLE-I',
    state             STRING    NOT NULL COMMENT 'State name from the region lookup, joined on state FIPS',
    state_abbr        STRING             COMMENT '2-letter state code',
    census_region     STRING             COMMENT 'Northeast, Midwest, South, West, or Territory (D8)',
    census_division   STRING             COMMENT 'Census division, or Territory (D8)',
    fema_region       STRING             COMMENT 'FEMA region I-X (D8)',
    reading_time      TIMESTAMP NOT NULL COMMENT 'Start of the 15-minute collection run, UTC (D1, D7)',
    customers_out     BIGINT    NOT NULL COMMENT 'Customers out as reported, never capped (D4)',
    total_customers   BIGINT             COMMENT 'Reported with the reading; 2024 only (D2)',
    exceeds_customers BOOLEAN   NOT NULL COMMENT 'customers_out > dim_county_customers.customers (D4)',
    year              INT       NOT NULL COMMENT 'Calendar year of reading_time, UTC',
    source_file       STRING             COMMENT 'Bronze source file'
)
PARTITIONED BY (year, state)
COMMENT 'EAGLE-I county outages, all years unified';

INSERT OVERWRITE silver_outages
WITH
-- The customers-out measure is named sum in 2023 (D2); total_customers exists only in 2024.
unioned AS (
    SELECT fips_code, county, state, customers_out, CAST(NULL AS STRING) AS total_customers,
           run_start_time, source_file
    FROM bronze_eaglei_2022
    UNION ALL
    SELECT fips_code, county, state, `sum` AS customers_out, CAST(NULL AS STRING) AS total_customers,
           run_start_time, source_file
    FROM bronze_eaglei_2023
    UNION ALL
    SELECT fips_code, county, state, customers_out, total_customers,
           run_start_time, source_file
    FROM bronze_eaglei_2024
),
-- Bronze is all text (D14): pad FIPS, cast counts, parse timestamps as UTC without conversion (D1).
typed AS (
    SELECT
        LPAD(TRIM(fips_code), 5, '0')                            AS fips_code,
        TRIM(county)                                             AS county,
        TRY_CAST(customers_out AS BIGINT)                        AS customers_out,
        TRY_CAST(total_customers AS BIGINT)                      AS total_customers,
        try_to_timestamp(run_start_time, 'yyyy-MM-dd HH:mm:ss')  AS run_start_time,
        source_file
    FROM unioned
),
-- Rows that cannot be parsed cannot be placed in time or space, so they are dropped (D15).
valid AS (
    SELECT *
    FROM typed
    WHERE fips_code RLIKE '^[0-9]{5}$'
      AND run_start_time IS NOT NULL
      AND customers_out IS NOT NULL
),
-- A late run still belongs to its 15-minute slot (D7).
floored AS (
    SELECT
        *,
        timestamp_seconds(FLOOR(unix_seconds(run_start_time) / 900) * 900) AS reading_time
    FROM valid
),
-- Flooring can create duplicate keys; keep the highest reading (D7).
deduped AS (
    SELECT *
    FROM floored
    QUALIFY ROW_NUMBER() OVER (
        PARTITION BY fips_code, reading_time
        ORDER BY customers_out DESC, source_file
    ) = 1
)
-- Region attributes come from the state FIPS prefix, never from names (D8, D16).
-- The denominator comes from the one-per-county table (D13) and drives the overcount flag (D4).
SELECT
    d.fips_code,
    d.county,
    r.state_name                                         AS state,
    r.state_abbr,
    r.census_region,
    r.census_division,
    r.fema_region,
    d.reading_time,
    d.customers_out,
    d.total_customers,
    COALESCE(d.customers_out > k.customers, FALSE)       AS exceeds_customers,
    YEAR(d.reading_time)                                 AS year,
    d.source_file
FROM deduped AS d
INNER JOIN bronze_state_regions AS r ON r.state_fips = LEFT(d.fips_code, 2)
LEFT JOIN  dim_county_customers AS k ON k.fips_code  = d.fips_code;


-- -----------------------------------------------------------------------------
-- Checks (expected values from the DuckDB test, see docs/decisions.md)
-- -----------------------------------------------------------------------------

-- Denominator sources: total_customers_2024 2,687 / max_mcc_2024 372 / mcc 2 / NULL 2
SELECT denominator_source, COUNT(*) AS counties, SUM(customers) AS customers,
       COUNT_IF(calibration_factor > 1) AS calibrated_counties
FROM dim_county_customers
GROUP BY denominator_source
ORDER BY counties DESC;

-- Rows and overcount flags per year
SELECT year, COUNT(*) AS row_count, COUNT_IF(exceeds_customers) AS exceeds_rows
FROM silver_outages
GROUP BY year
ORDER BY year;
