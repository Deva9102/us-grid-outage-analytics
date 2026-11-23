-- =============================================================================
-- 02_silver.sql
-- Silver layer: one denominator table, one unified outage table and the empty readings.
--
--   dim_county_customers  one customer denominator per county for all years (D13, D21, D35, D58)
--   silver_outages        all EAGLE-I years, cleaned, partitioned by year and state
--   silver_empty_readings readings with an empty customers_out, kept out of silver_outages (D64)
--
-- Incremental (D56): silver_outages is created once and only the partitions of
-- incremental.load_years are replaced (INSERT INTO ... REPLACE WHERE year IN (...)), and the same
-- for silver_empty_readings; every other year is left as it is. dim_county_customers is rebuilt
-- every run but depends only on the denominator base years 2022-2024 (D58), so its existing rows
-- never change.
--
-- Rule numbers refer to docs/decisions.md. The same logic is tested locally in
-- scripts/test_silver_duckdb.py; keep the two in step.
--
-- Runs after 02_silver_sources.sql: the D21 calibration reads silver_eia_state_customers (D26).
-- =============================================================================

-- Raw timestamps carry no zone and are UTC (D1). Fixing the session zone makes
-- parsing and display UTC regardless of workspace defaults.
SET TIME ZONE 'UTC';

USE CATALOG ${project.catalog};
USE SCHEMA ${project.schema};


-- -----------------------------------------------------------------------------
-- dim_county_customers (D5, D9, D12, D13, D21, D35, D36)
-- -----------------------------------------------------------------------------

CREATE OR REPLACE TABLE dim_county_customers (
    fips_code            STRING  NOT NULL COMMENT '5-digit county FIPS',
    customers            BIGINT           COMMENT 'One denominator for all years; NULL if none (has_denominator = false)',
    denominator_source   STRING           COMMENT 'total_customers_2024, max_mcc_2024, mcc, or NULL',
    denominator_mismatch BOOLEAN NOT NULL COMMENT 'True when MCC and 2024 total_customers differ by more than ${denominator.mismatch_ratio}x (D12)',
    calibration_factor   DOUBLE  NOT NULL COMMENT 'D13 denominator / final denominator for this county; 1.0 if unchanged (D21, D35)',
    state_calibration_factor DOUBLE NOT NULL COMMENT 'State D13 total / EIA-861 ${calibration.eia_year} total where above ${calibration.state_ratio}, else 1.0 (D21)',  -- noqa: LT05
    peak_floor_applied   BOOLEAN NOT NULL COMMENT 'True when the county was held at its peak customers out (D35)',
    peak_floor_skipped   BOOLEAN NOT NULL COMMENT 'True when the peak exceeds ${calibration.peak_skip_ratio}x the D13 denominator, so no floor applies (D36)'
)
COMMENT 'Customer denominator per county, decisions D12, D13, D21, D35 and D36';

INSERT OVERWRITE dim_county_customers
WITH
-- Every county seen in any year gets a row, so no outage row loses its denominator join.
eaglei_counties AS (
    SELECT LPAD(TRIM(fips_code), 5, '0') AS fips_code FROM bronze_eaglei_2022
    UNION DISTINCT
    SELECT LPAD(TRIM(fips_code), 5, '0') FROM bronze_eaglei_2023
    UNION DISTINCT
    SELECT LPAD(TRIM(fips_code), 5, '0') FROM bronze_eaglei_2024
    UNION DISTINCT
    SELECT LPAD(TRIM(fips_code), 5, '0') FROM bronze_eaglei_2025
),
-- Counties reported in the denominator base years 2022-2024. Only these enter the D21 state
-- totals and the D35 floors, so a county first reported later cannot move the denominator of
-- any existing county (D58).
base_counties AS (
    SELECT LPAD(TRIM(fips_code), 5, '0') AS fips_code FROM bronze_eaglei_2022
    UNION DISTINCT
    SELECT LPAD(TRIM(fips_code), 5, '0') FROM bronze_eaglei_2023
    UNION DISTINCT
    SELECT LPAD(TRIM(fips_code), 5, '0') FROM bronze_eaglei_2024
),
-- 2024 total_customers is constant per county, so one value per county loses nothing (D13).
totals_2024 AS (
    SELECT
        LPAD(TRIM(fips_code), 5, '0')            AS fips_code,
        MAX(TRY_CAST(total_customers AS BIGINT)) AS total_customers_2024
    FROM bronze_eaglei_2024
    GROUP BY LPAD(TRIM(fips_code), 5, '0')
),
-- MCC stores FIPS as numbers (lost leading zeros) and ends with a Grand Total row (D5).
mcc AS (
    SELECT
        LPAD(TRIM(County_FIPS), 5, '0')  AS fips_code,
        TRY_CAST(Customers AS BIGINT)    AS mcc_customers
    FROM bronze_eaglei_mcc
    WHERE REGEXP_LIKE(TRIM(County_FIPS), '^[0-9]+$')
),
-- A gap above denominator.mismatch_ratio between the two sources is a data error, not growth (D12).
compared AS (
    SELECT
        c.fips_code,
        b.fips_code IS NOT NULL AS in_base_years,
        t.total_customers_2024,
        m.mcc_customers,
        COALESCE(
            GREATEST(t.total_customers_2024, m.mcc_customers)
                > ${denominator.mismatch_ratio} * LEAST(t.total_customers_2024, m.mcc_customers),
            FALSE
        ) AS is_mismatch
    FROM eaglei_counties AS c
    LEFT JOIN totals_2024 AS t ON t.fips_code = c.fips_code
    LEFT JOIN mcc         AS m ON m.fips_code = c.fips_code
    LEFT JOIN base_counties AS b ON b.fips_code = c.fips_code
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
        is_mismatch AS denominator_mismatch,
        in_base_years
    FROM compared
),
-- Highest customers out ever reported per county: the floor for calibration (D35).
-- Dropout readings (D19) are falls of more than 90%, so they are never the maximum.
-- Only the denominator base years 2022-2024 count: a later year must not move the one
-- denominator of earlier years (D58).
peaks AS (
    SELECT LPAD(TRIM(fips_code), 5, '0') AS fips_code, MAX(TRY_CAST(customers_out AS BIGINT)) AS peak_customers_out
    FROM (
        SELECT fips_code, customers_out FROM bronze_eaglei_2022
        UNION ALL
        SELECT fips_code, `sum` AS customers_out FROM bronze_eaglei_2023
        UNION ALL
        SELECT fips_code, customers_out FROM bronze_eaglei_2024
    ) AS readings
    GROUP BY LPAD(TRIM(fips_code), 5, '0')
),
-- State totals of the D13 denominators, compared with EIA-861 customers of calibration.eia_year (D21).
state_totals AS (
    SELECT r.state_abbr, SUM(d.customers) AS d13_customers
    FROM d13 AS d
    INNER JOIN bronze_state_regions AS r ON r.state_fips = LEFT(d.fips_code, 2)
    WHERE d.in_base_years
    GROUP BY r.state_abbr
),
-- A state is calibrated only where it exceeds EIA by more than calibration.state_ratio; never scaled up (D21).
states AS (
    SELECT
        s.state_abbr,
        e.customers AS eia_customers,
        CASE WHEN s.d13_customers > ${calibration.state_ratio} * e.customers THEN s.d13_customers / e.customers ELSE 1.0 END AS state_calibration_factor
    FROM state_totals AS s
    LEFT JOIN silver_eia_state_customers AS e ON e.state_abbr = s.state_abbr AND e.data_year = ${calibration.eia_year}
),
-- The floor is the peak, unless the peak is more than calibration.peak_skip_ratio x the D13 denominator: such a peak is
-- likely misattributed, so that county gets no floor and takes the common rescaling (D36).
floors AS (
    SELECT
        d.fips_code,
        d.customers AS d13_customers,
        COALESCE(p.peak_customers_out, 0) > ${calibration.peak_skip_ratio} * d.customers AS floor_skipped,
        CASE
            WHEN COALESCE(p.peak_customers_out, 0) > ${calibration.peak_skip_ratio} * d.customers THEN 0
            ELSE COALESCE(p.peak_customers_out, 0)
        END AS floor_customers
    FROM d13 AS d
    LEFT JOIN peaks AS p ON p.fips_code = d.fips_code
    WHERE d.customers IS NOT NULL AND d.in_base_years
),
-- Counties of calibrated states, ordered by how far their floor sits above their D13 value.
ordered AS (
    SELECT
        f.fips_code,
        f.d13_customers,
        f.floor_customers,
        f.floor_customers / f.d13_customers AS floor_ratio,
        f.floor_skipped,
        r.state_abbr,
        st.eia_customers,
        ROW_NUMBER() OVER (
            PARTITION BY r.state_abbr
            ORDER BY f.floor_customers / f.d13_customers DESC, f.fips_code
        ) AS pos
    FROM floors AS f
    INNER JOIN bronze_state_regions AS r ON r.state_fips = LEFT(f.fips_code, 2)
    INNER JOIN states AS st ON st.state_abbr = r.state_abbr
    WHERE st.state_calibration_factor > 1
),
-- Holding the first m counties at their floor leaves EIA minus those floors for the rest,
-- which are scaled by one common factor (D35). m = 0 is plain D21 scaling.
prefixes AS (
    SELECT state_abbr, 0 AS m, MAX(eia_customers) AS eia_customers, 0 AS floors_total,
           SUM(d13_customers) AS d13_rest, MAX(floor_ratio) AS next_ratio
    FROM ordered
    GROUP BY state_abbr
    UNION ALL
    SELECT
        state_abbr,
        pos,
        eia_customers,
        SUM(floor_customers) OVER (PARTITION BY state_abbr ORDER BY pos ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW),
        SUM(d13_customers) OVER (PARTITION BY state_abbr)
            - SUM(d13_customers) OVER (PARTITION BY state_abbr ORDER BY pos ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW),
        LEAD(floor_ratio) OVER (PARTITION BY state_abbr ORDER BY pos)
    FROM ordered
),
-- Iterating "floor every county below its floor, rescale the rest" stops at the smallest m
-- where the next county would no longer fall below its floor; that m is found directly here.
solution AS (
    SELECT state_abbr, m, (eia_customers - floors_total) / NULLIF(d13_rest, 0) AS scale
    FROM prefixes
    WHERE next_ratio IS NULL OR next_ratio <= (eia_customers - floors_total) / NULLIF(d13_rest, 0)
    QUALIFY ROW_NUMBER() OVER (PARTITION BY state_abbr ORDER BY m) = 1
),
final AS (
    SELECT
        d.fips_code,
        d.customers AS d13_customers,
        d.denominator_source,
        d.denominator_mismatch,
        -- A county first reported after the base years keeps its D13 value, uncalibrated (D58).
        CASE WHEN d.in_base_years THEN COALESCE(st.state_calibration_factor, 1.0) ELSE 1.0 END AS state_calibration_factor,
        COALESCE(o.pos <= s.m, FALSE)              AS peak_floor_applied,
        COALESCE(o.floor_skipped, FALSE)           AS peak_floor_skipped,
        CASE
            WHEN o.pos IS NULL THEN d.customers
            WHEN o.pos <= s.m  THEN o.floor_customers
            ELSE CAST(ROUND(o.d13_customers * s.scale) AS BIGINT)
        END AS customers
    FROM d13 AS d
    LEFT JOIN bronze_state_regions AS r ON r.state_fips = LEFT(d.fips_code, 2)
    LEFT JOIN states   AS st ON st.state_abbr = r.state_abbr
    LEFT JOIN ordered  AS o  ON o.fips_code = d.fips_code
    LEFT JOIN solution AS s  ON s.state_abbr = o.state_abbr
)
-- Still one denominator per county (D13); the D13 value stays derivable as customers x calibration_factor.
SELECT
    fips_code,
    customers,
    denominator_source,
    denominator_mismatch,
    CAST(COALESCE(d13_customers / NULLIF(customers, 0), 1.0) AS DOUBLE) AS calibration_factor,
    CAST(state_calibration_factor AS DOUBLE)                            AS state_calibration_factor,
    peak_floor_applied,
    peak_floor_skipped
FROM final;


-- -----------------------------------------------------------------------------
-- silver_outages (D1, D2, D4, D6, D7, D8, D15, D16)
-- -----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS silver_outages (
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

-- Only the partitions of the load years are replaced; Delta rejects a row of any other year (D56).
INSERT INTO silver_outages REPLACE WHERE year IN (${incremental.load_years})
WITH
-- The customers-out measure is named sum in 2023 (D2); total_customers exists only in 2024.
-- Every yearly file holds only readings of its own year (checked in D56), so a branch whose year
-- is not loaded is a constant FALSE filter and its table is never scanned.
unioned AS (
    SELECT fips_code, county, state, customers_out, CAST(NULL AS STRING) AS total_customers,
           run_start_time, source_file
    FROM bronze_eaglei_2022
    WHERE 2022 IN (${incremental.load_years})
    UNION ALL
    SELECT fips_code, county, state, `sum` AS customers_out, CAST(NULL AS STRING) AS total_customers,
           run_start_time, source_file
    FROM bronze_eaglei_2023
    WHERE 2023 IN (${incremental.load_years})
    UNION ALL
    SELECT fips_code, county, state, customers_out, total_customers,
           run_start_time, source_file
    FROM bronze_eaglei_2024
    WHERE 2024 IN (${incremental.load_years})
    UNION ALL
    SELECT fips_code, county, state, customers_out, CAST(NULL AS STRING) AS total_customers,
           run_start_time, source_file
    FROM bronze_eaglei_2025
    WHERE 2025 IN (${incremental.load_years})
),
-- Bronze is all text (D14): pad FIPS, cast counts, parse timestamps as UTC without conversion (D1).
typed AS (
    SELECT
        LPAD(TRIM(fips_code), 5, '0')                            AS fips_code,
        TRIM(county)                                             AS county,
        TRY_CAST(customers_out AS BIGINT)                        AS customers_out,
        TRY_CAST(total_customers AS BIGINT)                      AS total_customers,
        TRY_TO_TIMESTAMP(run_start_time, 'yyyy-MM-dd HH:mm:ss')  AS run_start_time,
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
        TIMESTAMP_SECONDS(FLOOR(UNIX_SECONDS(run_start_time) / 900) * 900) AS reading_time
    FROM valid
),
-- Flooring can create duplicate keys; keep the highest reading (D7).
deduped AS (
    SELECT *
    FROM floored
    QUALIFY ROW_NUMBER() OVER (
        PARTITION BY fips_code, reading_time
        ORDER BY customers_out DESC, source_file ASC
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
LEFT JOIN  dim_county_customers AS k ON k.fips_code  = d.fips_code
WHERE YEAR(d.reading_time) IN (${incremental.load_years});


-- -----------------------------------------------------------------------------
-- silver_empty_readings (D15, D62, D64)
-- Readings whose customers_out is empty. D15 keeps them out of silver_outages, but the county was
-- collected in that run, so Gold event detection needs to know where they are (D64).
-- -----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS silver_empty_readings (
    fips_code    STRING    NOT NULL COMMENT '5-digit county FIPS',
    reading_time TIMESTAMP NOT NULL COMMENT 'Start of the 15-minute collection run, UTC (D1, D7)',
    year         INT       NOT NULL COMMENT 'Calendar year of reading_time, UTC',
    source_file  STRING             COMMENT 'Bronze source file'
)
PARTITIONED BY (year)
COMMENT 'EAGLE-I readings with an empty customers_out, dropped from silver_outages (D15, D64)';

INSERT INTO silver_empty_readings REPLACE WHERE year IN (${incremental.load_years})
WITH
-- Only the measure, key and time are needed. The measure is named sum in 2023 (D2).
unioned AS (
    SELECT fips_code, customers_out, run_start_time, source_file
    FROM bronze_eaglei_2022
    WHERE 2022 IN (${incremental.load_years})
    UNION ALL
    SELECT fips_code, `sum` AS customers_out, run_start_time, source_file
    FROM bronze_eaglei_2023
    WHERE 2023 IN (${incremental.load_years})
    UNION ALL
    SELECT fips_code, customers_out, run_start_time, source_file
    FROM bronze_eaglei_2024
    WHERE 2024 IN (${incremental.load_years})
    UNION ALL
    SELECT fips_code, customers_out, run_start_time, source_file
    FROM bronze_eaglei_2025
    WHERE 2025 IN (${incremental.load_years})
),
-- Empty means no value at all; text that is present but not a number stays a plain D15 drop.
empty AS (
    SELECT
        LPAD(TRIM(fips_code), 5, '0')                            AS fips_code,
        TRY_TO_TIMESTAMP(run_start_time, 'yyyy-MM-dd HH:mm:ss')  AS run_start_time,
        source_file
    FROM unioned
    WHERE customers_out IS NULL OR TRIM(customers_out) = ''
),
-- Same placement rules as silver_outages: valid key and time, floored to the slot (D7, D15).
floored AS (
    SELECT
        fips_code,
        TIMESTAMP_SECONDS(FLOOR(UNIX_SECONDS(run_start_time) / 900) * 900) AS reading_time,
        source_file
    FROM empty
    WHERE fips_code RLIKE '^[0-9]{5}$'
      AND run_start_time IS NOT NULL
),
-- One row per county and slot, and none where the slot also has a real reading (D7 keeps that).
deduped AS (
    SELECT f.fips_code, f.reading_time, MIN(f.source_file) AS source_file
    FROM floored AS f
    INNER JOIN bronze_state_regions AS r ON r.state_fips = LEFT(f.fips_code, 2)
    ANTI JOIN silver_outages AS s
        ON  s.fips_code    = f.fips_code
        AND s.reading_time = f.reading_time
    GROUP BY f.fips_code, f.reading_time
)
SELECT fips_code, reading_time, YEAR(reading_time) AS year, source_file
FROM deduped
WHERE YEAR(reading_time) IN (${incremental.load_years});


-- -----------------------------------------------------------------------------
-- Checks (expected values from the DuckDB test, see docs/decisions.md)
-- -----------------------------------------------------------------------------

-- Denominator sources: total_customers_2024 2,687 / max_mcc_2024 372 / mcc 2 / NULL 2
SELECT denominator_source, COUNT(*) AS counties, SUM(customers) AS customers,
       COUNT_IF(state_calibration_factor > 1) AS calibrated_counties,
       COUNT_IF(peak_floor_applied) AS floored_counties,
       COUNT_IF(peak_floor_skipped) AS floor_skipped_counties
FROM dim_county_customers
GROUP BY denominator_source
ORDER BY counties DESC;

-- Rows and overcount flags per year
SELECT year, COUNT(*) AS row_count, COUNT_IF(exceeds_customers) AS exceeds_rows
FROM silver_outages
GROUP BY year
ORDER BY year;
