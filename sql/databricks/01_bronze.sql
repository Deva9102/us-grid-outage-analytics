-- =============================================================================
-- 01_bronze.sql
-- Bronze layer: raw files loaded as-is into workspace.outages.
--
-- Every column is loaded as STRING (D6, D14). Types are applied in Silver, so a
-- bad value can never fail the load or be silently changed by schema inference.
-- Each table adds source_file and loaded_at.
--
-- Incremental runs (D56): only the bronze_eaglei_<year> tables of incremental.load_years are
-- rebuilt; the runners skip the statements of the other years, so those tables stay untouched.
--
-- The yearly EAGLE-I files are read as Parquet: the raw CSVs converted locally by
-- DuckDB with every column as STRING, values unchanged (D20). scripts/run_databricks.py
-- converts and uploads these files so the paths match:
--   data/raw/eaglei_parquet/<year>/eaglei_outages_<year>.parquet -> /Volumes/workspace/outages/raw/eaglei_parquet/<year>/
--   data/raw/eaglei/metadata/{MCC,coverage_history,DQI}.csv      -> /Volumes/workspace/outages/raw/eaglei/metadata/
--   data/reference/state_regions.csv                             -> /Volumes/workspace/outages/raw/reference/
-- =============================================================================

CREATE SCHEMA IF NOT EXISTS ${project.catalog}.${project.schema}
COMMENT 'US power outages and storm impact pipeline';

CREATE VOLUME IF NOT EXISTS ${project.catalog}.${project.schema}.${project.volume}
COMMENT 'Raw source files, uploaded unchanged from data/raw/';

USE CATALOG ${project.catalog};
USE SCHEMA ${project.schema};


-- -----------------------------------------------------------------------------
-- EAGLE-I county outages, one table per year (column names differ by year: D2)
-- -----------------------------------------------------------------------------

CREATE OR REPLACE TABLE bronze_eaglei_2022
COMMENT 'EAGLE-I 2022 county outages, raw text columns'
AS
SELECT
    *,
    _metadata.file_path AS source_file,
    CURRENT_TIMESTAMP() AS loaded_at
FROM READ_FILES(
    '${project.volume_path}/eaglei_parquet/2022/',
    format => 'parquet',
    schema => 'fips_code STRING, county STRING, state STRING, customers_out STRING, run_start_time STRING'
);

CREATE OR REPLACE TABLE bronze_eaglei_2023
COMMENT 'EAGLE-I 2023 county outages, raw text columns (customers out is named sum)'
AS
SELECT
    *,
    _metadata.file_path AS source_file,
    CURRENT_TIMESTAMP() AS loaded_at
FROM READ_FILES(
    '${project.volume_path}/eaglei_parquet/2023/',
    format => 'parquet',
    schema => 'fips_code STRING, county STRING, state STRING, `sum` STRING, run_start_time STRING'
);

CREATE OR REPLACE TABLE bronze_eaglei_2024
COMMENT 'EAGLE-I 2024 county outages, raw text columns (adds total_customers)'
AS
SELECT
    *,
    _metadata.file_path AS source_file,
    CURRENT_TIMESTAMP() AS loaded_at
FROM READ_FILES(
    '${project.volume_path}/eaglei_parquet/2024/',
    format => 'parquet',
    schema => 'fips_code STRING, county STRING, state STRING, customers_out STRING, run_start_time STRING, total_customers STRING'
);

CREATE OR REPLACE TABLE bronze_eaglei_2025
COMMENT 'EAGLE-I 2025 county outages, raw text columns (no total_customers, as in 2022)'
AS
SELECT
    *,
    _metadata.file_path AS source_file,
    CURRENT_TIMESTAMP() AS loaded_at
FROM READ_FILES(
    '${project.volume_path}/eaglei_parquet/2025/',
    format => 'parquet',
    schema => 'fips_code STRING, county STRING, state STRING, customers_out STRING, run_start_time STRING'
);


-- -----------------------------------------------------------------------------
-- Reference files used by Silver
-- -----------------------------------------------------------------------------

-- MCC.csv starts with a byte-order mark and ends with a Grand Total row. The explicit
-- schema sets clean column names; the Grand Total row is removed in Silver (D5).
CREATE OR REPLACE TABLE bronze_eaglei_mcc
COMMENT 'EAGLE-I modeled customers per county (MCC.csv), raw text columns'
AS
SELECT
    *,
    _metadata.file_path AS source_file,
    CURRENT_TIMESTAMP() AS loaded_at
FROM READ_FILES(
    '${project.volume_path}/eaglei/metadata/MCC.csv',
    format => 'csv',
    header => TRUE,
    schema => 'County_FIPS STRING, Customers STRING'
);

-- coverage_history.csv: share of each state's customers EAGLE-I covered, per year (D67). The
-- release's file stops at 2022; dates are written m/d/yy.
CREATE OR REPLACE TABLE bronze_eaglei_coverage_history
COMMENT 'EAGLE-I published customer coverage per state and year (coverage_history.csv), raw text columns'
AS
SELECT
    *,
    _metadata.file_path AS source_file,
    CURRENT_TIMESTAMP() AS loaded_at
FROM READ_FILES(
    '${project.volume_path}/eaglei/metadata/coverage_history.csv',
    format => 'csv',
    header => TRUE,
    schema => 'year STRING, state STRING, total_customers STRING, min_covered STRING, max_covered STRING, min_pct_covered STRING, max_pct_covered STRING'
);

-- DQI.csv: EAGLE-I data quality index per FEMA region and year (D67). Also stops at 2022.
CREATE OR REPLACE TABLE bronze_eaglei_dqi
COMMENT 'EAGLE-I data quality index per FEMA region and year (DQI.csv), raw text columns'
AS
SELECT
    *,
    _metadata.file_path AS source_file,
    CURRENT_TIMESTAMP() AS loaded_at
FROM READ_FILES(
    '${project.volume_path}/eaglei/metadata/DQI.csv',
    format => 'csv',
    header => TRUE,
    schema => 'fema STRING, year STRING, success_rate STRING, percent_enabled STRING, spatial_precision STRING, cust_coverage STRING, max_covered STRING, total_customers STRING, DQI STRING'  -- noqa: LT05
);

-- Built by scripts/census_regions.py (D8, D16).
CREATE OR REPLACE TABLE bronze_state_regions
COMMENT 'State FIPS to Census region, Census division and FEMA region'
AS
SELECT
    *,
    _metadata.file_path AS source_file,
    CURRENT_TIMESTAMP() AS loaded_at
FROM READ_FILES(
    '${project.volume_path}/reference/state_regions.csv',
    format => 'csv',
    header => TRUE,
    schema => 'state_fips STRING, state_abbr STRING, state_name STRING, census_region STRING, census_division STRING, fema_region STRING'
);


-- -----------------------------------------------------------------------------
-- Load check: row counts should match the local profile (docs/data_profile.md)
-- 2022: 25,796,465   2023: 26,101,051   2024: 27,701,334   2025: 30,482,141   MCC: 3,234   regions: 53
-- -----------------------------------------------------------------------------

SELECT 'bronze_eaglei_2022' AS table_name, COUNT(*) AS row_count FROM bronze_eaglei_2022
UNION ALL SELECT 'bronze_eaglei_2023', COUNT(*) FROM bronze_eaglei_2023
UNION ALL SELECT 'bronze_eaglei_2024', COUNT(*) FROM bronze_eaglei_2024
UNION ALL SELECT 'bronze_eaglei_2025', COUNT(*) FROM bronze_eaglei_2025
UNION ALL SELECT 'bronze_eaglei_mcc', COUNT(*) FROM bronze_eaglei_mcc
UNION ALL SELECT 'bronze_eaglei_coverage_history', COUNT(*) FROM bronze_eaglei_coverage_history
UNION ALL SELECT 'bronze_eaglei_dqi', COUNT(*) FROM bronze_eaglei_dqi
UNION ALL SELECT 'bronze_state_regions', COUNT(*) FROM bronze_state_regions;
