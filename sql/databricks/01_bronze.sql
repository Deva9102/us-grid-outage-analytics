-- =============================================================================
-- 01_bronze.sql
-- Bronze layer: raw files loaded as-is into workspace.outages.
--
-- Every column is loaded as STRING (D6, D14). Types are applied in Silver, so a
-- bad value can never fail the load or be silently changed by schema inference.
-- Each table adds source_file and loaded_at.
--
-- Before running the CREATE TABLE statements, upload these local files to the
-- volume so the paths match:
--   data/raw/eaglei/<year>/eaglei_outages_<year>.csv -> /Volumes/workspace/outages/raw/eaglei/<year>/
--   data/raw/eaglei/metadata/MCC.csv                 -> /Volumes/workspace/outages/raw/eaglei/metadata/
--   data/reference/state_regions.csv                 -> /Volumes/workspace/outages/raw/reference/
-- =============================================================================

CREATE SCHEMA IF NOT EXISTS workspace.outages
COMMENT 'US power outages and storm impact pipeline';

CREATE VOLUME IF NOT EXISTS workspace.outages.raw
COMMENT 'Raw source files, uploaded unchanged from data/raw/';

USE CATALOG workspace;
USE SCHEMA outages;


-- -----------------------------------------------------------------------------
-- EAGLE-I county outages, one table per year (column names differ by year: D2)
-- -----------------------------------------------------------------------------

CREATE OR REPLACE TABLE bronze_eaglei_2022
COMMENT 'EAGLE-I 2022 county outages, raw text columns'
AS
SELECT
    *,
    _metadata.file_path AS source_file,
    current_timestamp() AS loaded_at
FROM read_files(
    '/Volumes/workspace/outages/raw/eaglei/2022/',
    format => 'csv',
    header => true,
    schema => 'fips_code STRING, county STRING, state STRING, customers_out STRING, run_start_time STRING'
);

CREATE OR REPLACE TABLE bronze_eaglei_2023
COMMENT 'EAGLE-I 2023 county outages, raw text columns (customers out is named sum)'
AS
SELECT
    *,
    _metadata.file_path AS source_file,
    current_timestamp() AS loaded_at
FROM read_files(
    '/Volumes/workspace/outages/raw/eaglei/2023/',
    format => 'csv',
    header => true,
    schema => 'fips_code STRING, county STRING, state STRING, `sum` STRING, run_start_time STRING'
);

CREATE OR REPLACE TABLE bronze_eaglei_2024
COMMENT 'EAGLE-I 2024 county outages, raw text columns (adds total_customers)'
AS
SELECT
    *,
    _metadata.file_path AS source_file,
    current_timestamp() AS loaded_at
FROM read_files(
    '/Volumes/workspace/outages/raw/eaglei/2024/',
    format => 'csv',
    header => true,
    schema => 'fips_code STRING, county STRING, state STRING, customers_out STRING, run_start_time STRING, total_customers STRING'
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
    current_timestamp() AS loaded_at
FROM read_files(
    '/Volumes/workspace/outages/raw/eaglei/metadata/MCC.csv',
    format => 'csv',
    header => true,
    schema => 'County_FIPS STRING, Customers STRING'
);

-- Built by scripts/census_regions.py (D8, D16).
CREATE OR REPLACE TABLE bronze_state_regions
COMMENT 'State FIPS to Census region, Census division and FEMA region'
AS
SELECT
    *,
    _metadata.file_path AS source_file,
    current_timestamp() AS loaded_at
FROM read_files(
    '/Volumes/workspace/outages/raw/reference/state_regions.csv',
    format => 'csv',
    header => true,
    schema => 'state_fips STRING, state_abbr STRING, state_name STRING, census_region STRING, census_division STRING, fema_region STRING'
);


-- -----------------------------------------------------------------------------
-- Load check: row counts should match the local profile (docs/data_profile.md)
-- 2022: 25,796,465   2023: 26,101,051   2024: 27,701,334   MCC: 3,234   regions: 53
-- -----------------------------------------------------------------------------

SELECT 'bronze_eaglei_2022' AS table_name, COUNT(*) AS row_count FROM bronze_eaglei_2022
UNION ALL SELECT 'bronze_eaglei_2023', COUNT(*) FROM bronze_eaglei_2023
UNION ALL SELECT 'bronze_eaglei_2024', COUNT(*) FROM bronze_eaglei_2024
UNION ALL SELECT 'bronze_eaglei_mcc', COUNT(*) FROM bronze_eaglei_mcc
UNION ALL SELECT 'bronze_state_regions', COUNT(*) FROM bronze_state_regions;
