-- =============================================================================
-- 01_bronze_sources.sql
-- Bronze layer for the added sources: NOAA Storm Events, NWS zone-county files,
-- EIA-861, DOE OE-417, and their reference lookups.
--
-- Run after 01_bronze.sql (it creates the schema and volume) and before
-- 02_silver_sources.sql (D26). Every column is STRING (D14); each table adds
-- source_file and loaded_at.
--
-- scripts/run_databricks.py uploads these files to the volume:
--   data/raw/noaa_storm_events/<year>/*.csv.gz          -> raw/noaa_storm_events/<year>/
--   data/raw/nws_zone_county/<year>/bp*.dbx             -> raw/nws_zone_county/<year>/
--   data/raw/eia861_parquet/<year>/*.parquet            -> raw/eia861_parquet/<year>/   (D27)
--   data/raw/oe417_parquet/<year>/*.parquet             -> raw/oe417_parquet/<year>/    (D27)
--   data/reference/{noaa_state_codes,oe417_event_types,state_time_zones}.csv -> raw/reference/
-- =============================================================================

USE CATALOG workspace;
USE SCHEMA outages;


-- -----------------------------------------------------------------------------
-- NOAA Storm Events details (gzipped CSV, narratives span lines and contain quotes)
-- -----------------------------------------------------------------------------

CREATE OR REPLACE TABLE bronze_noaa_storm_events
COMMENT 'NOAA Storm Events details files, all columns as text'
AS
SELECT
    *,
    _metadata.file_path AS source_file,
    current_timestamp() AS loaded_at
FROM read_files(
    '/Volumes/workspace/outages/raw/noaa_storm_events/*/*.csv.gz',
    format => 'csv',
    header => true,
    multiLine => true,
    escape => '"',
    inferColumnTypes => false
);


-- -----------------------------------------------------------------------------
-- NWS zone-county correlation files (pipe-delimited, no header, Latin-1)
-- -----------------------------------------------------------------------------

CREATE OR REPLACE TABLE bronze_nws_zone_county
COMMENT 'NWS public forecast zone to county correlation, one file per effective date'
AS
SELECT
    *,
    _metadata.file_path AS source_file,
    current_timestamp() AS loaded_at
FROM read_files(
    '/Volumes/workspace/outages/raw/nws_zone_county/*/*.dbx',
    format => 'csv',
    sep => '|',
    header => false,
    encoding => 'ISO-8859-1',
    schema => 'state STRING, zone STRING, cwa STRING, name STRING, state_zone STRING, county STRING, fips STRING, time_zone STRING, fe_area STRING, lat STRING, lon STRING'
);


-- -----------------------------------------------------------------------------
-- EIA-861 workbooks as raw rows (D27): sheet_name, row_number, col_01 .. col_NN
-- -----------------------------------------------------------------------------

CREATE OR REPLACE TABLE bronze_eia861_reliability
COMMENT 'EIA-861 Reliability workbooks, every row of every sheet as text'
AS
SELECT
    *,
    _metadata.file_path AS source_file,
    current_timestamp() AS loaded_at
FROM read_files('/Volumes/workspace/outages/raw/eia861_parquet/*/reliability_*.parquet', format => 'parquet');

CREATE OR REPLACE TABLE bronze_eia861_sales
COMMENT 'EIA-861 Sales to Ultimate Customers workbooks, every row of every sheet as text'
AS
SELECT
    *,
    _metadata.file_path AS source_file,
    current_timestamp() AS loaded_at
FROM read_files('/Volumes/workspace/outages/raw/eia861_parquet/*/sales_*.parquet', format => 'parquet');

CREATE OR REPLACE TABLE bronze_eia861_service_territory
COMMENT 'EIA-861 Service Territory workbooks, every row of every sheet as text'
AS
SELECT
    *,
    _metadata.file_path AS source_file,
    current_timestamp() AS loaded_at
FROM read_files('/Volumes/workspace/outages/raw/eia861_parquet/*/service_territory_*.parquet', format => 'parquet');


-- -----------------------------------------------------------------------------
-- OE-417 annual summaries as raw rows (D27)
-- -----------------------------------------------------------------------------

CREATE OR REPLACE TABLE bronze_oe417
COMMENT 'DOE OE-417 annual summary workbooks, every row as text'
AS
SELECT
    *,
    _metadata.file_path AS source_file,
    current_timestamp() AS loaded_at
FROM read_files('/Volumes/workspace/outages/raw/oe417_parquet/*/oe417_*.parquet', format => 'parquet');


-- -----------------------------------------------------------------------------
-- Reference lookups (committed in data/reference/)
-- -----------------------------------------------------------------------------

CREATE OR REPLACE TABLE bronze_noaa_state_codes
COMMENT 'NOAA STATE_FIPS to Census state FIPS and area type (D28)'
AS
SELECT
    *,
    _metadata.file_path AS source_file,
    current_timestamp() AS loaded_at
FROM read_files(
    '/Volumes/workspace/outages/raw/reference/noaa_state_codes.csv',
    format => 'csv',
    header => true,
    schema => 'noaa_state_fips STRING, noaa_state_name STRING, state_fips STRING, area_type STRING'
);

CREATE OR REPLACE TABLE bronze_oe417_event_types
COMMENT 'OE-417 event type key to category mapping (D24)'
AS
SELECT
    *,
    _metadata.file_path AS source_file,
    current_timestamp() AS loaded_at
FROM read_files(
    '/Volumes/workspace/outages/raw/reference/oe417_event_types.csv',
    format => 'csv',
    header => true,
    schema => 'event_type_key STRING, category STRING, multiple_types STRING, rows_2022_2023 STRING'
);

CREATE OR REPLACE TABLE bronze_state_time_zones
COMMENT 'Primary IANA time zone per state (D24)'
AS
SELECT
    *,
    _metadata.file_path AS source_file,
    current_timestamp() AS loaded_at
FROM read_files(
    '/Volumes/workspace/outages/raw/reference/state_time_zones.csv',
    format => 'csv',
    header => true,
    schema => 'state_abbr STRING, state_name STRING, primary_time_zone STRING'
);


-- -----------------------------------------------------------------------------
-- Load check (expected values: scripts/run_databricks.py)
-- -----------------------------------------------------------------------------

SELECT 'bronze_noaa_storm_events' AS table_name, COUNT(*) AS row_count FROM bronze_noaa_storm_events
UNION ALL SELECT 'bronze_nws_zone_county', COUNT(*) FROM bronze_nws_zone_county
UNION ALL SELECT 'bronze_eia861_reliability', COUNT(*) FROM bronze_eia861_reliability
UNION ALL SELECT 'bronze_eia861_sales', COUNT(*) FROM bronze_eia861_sales
UNION ALL SELECT 'bronze_eia861_service_territory', COUNT(*) FROM bronze_eia861_service_territory
UNION ALL SELECT 'bronze_oe417', COUNT(*) FROM bronze_oe417
UNION ALL SELECT 'bronze_noaa_state_codes', COUNT(*) FROM bronze_noaa_state_codes
UNION ALL SELECT 'bronze_oe417_event_types', COUNT(*) FROM bronze_oe417_event_types
UNION ALL SELECT 'bronze_state_time_zones', COUNT(*) FROM bronze_state_time_zones;
