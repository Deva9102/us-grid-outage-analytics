-- =============================================================================
-- 02_silver_sources.sql
-- Silver layer for the added sources. Runs after 01_bronze_sources.sql and before
-- 02_silver.sql, which needs silver_eia_state_customers for the D21 calibration (D26).
--
--   silver_eia_state_customers     customers per state and year, EIA-861 Parts A+C+D (D23)
--   silver_utility_reliability     one row per utility, state, year (D23, D32)
--   silver_nws_zone_versions       zone-county file versions and their effective dates (D30)
--   silver_nws_zone_county         zone -> county per version (D30)
--   silver_storm_event_details     one row per NOAA event, all events (D28, D29, D31)
--   silver_storm_events            one row per NOAA event per county (D30, D31)
--   silver_storm_events_unplaced   NOAA events that cannot be placed in a county, with reason (D30)
--   silver_oe417_rows              one row per OE-417 incident, parsed fields (D33)
--   silver_oe417_locations         states and counties named per incident (D33)
--   silver_oe417                   one row per OE-417 incident with UTC times and locations (D24, D33)
--
-- scripts/test_sources_duckdb.py runs these statements in DuckDB. Keep each statement
-- in the form CREATE OR REPLACE TABLE <name> COMMENT '...' AS <query>;
-- =============================================================================

SET TIME ZONE 'UTC';

USE CATALOG ${project.catalog};
USE SCHEMA ${project.schema};


-- -----------------------------------------------------------------------------
-- EIA-861
-- -----------------------------------------------------------------------------

CREATE OR REPLACE TABLE silver_eia_state_customers
COMMENT 'EIA-861 customers per state and year, Sales Parts A + C + D (D23)'
AS
WITH
-- Data rows start with a 4-digit year; header and footer rows do not (D32).
sales AS (
    SELECT
        TRY_CAST(col_01 AS INT)                        AS data_year,
        TRIM(col_02)                               AS utility_number,
        TRIM(col_04)                               AS part,
        TRIM(col_07)                               AS state_abbr,
        TRY_CAST(col_24 AS BIGINT)                 AS total_customers
    FROM bronze_eia861_sales
    WHERE sheet_name IN ('States', 'Territories')
      AND regexp_like(col_01, '^[0-9]{4}$')
)
-- Part B (energy-only) repeats the Part C (delivery-only) customers in retail-choice states (D23).
SELECT
    data_year,
    state_abbr,
    SUM(total_customers)            AS customers,
    COUNT(DISTINCT utility_number)  AS utilities
FROM sales
WHERE part IN ('A', 'C', 'D')
GROUP BY data_year, state_abbr;


CREATE OR REPLACE TABLE silver_utility_reliability
COMMENT 'EIA-861 reliability per utility, state and year with reporting standard, customers and size band (D23, D32)'
AS
WITH
-- Positional columns follow the Reliability sheet layout; '.' means not reported and becomes NULL (D32).
reliability AS (
    SELECT
        TRY_CAST(col_01 AS INT)            AS data_year,
        TRIM(col_02)                   AS utility_number,
        TRIM(col_03)                   AS utility_name,
        TRIM(col_04)                   AS state_abbr,
        TRIM(col_05)                   AS ownership,
        TRY_CAST(col_06 AS DOUBLE)     AS ieee_saidi_with_med,
        TRY_CAST(col_07 AS DOUBLE)     AS ieee_saifi_with_med,
        TRY_CAST(col_09 AS DOUBLE)     AS ieee_saidi_without_med,
        TRY_CAST(col_10 AS DOUBLE)     AS ieee_saifi_without_med,
        TRY_CAST(col_15 AS BIGINT)     AS ieee_customers,
        TRY_CAST(col_18 AS DOUBLE)     AS other_saidi_with_med,
        TRY_CAST(col_19 AS DOUBLE)     AS other_saifi_with_med,
        TRY_CAST(col_21 AS DOUBLE)     AS other_saidi_without_med,
        TRY_CAST(col_22 AS DOUBLE)     AS other_saifi_without_med,
        TRY_CAST(col_24 AS BIGINT)     AS other_customers
    FROM bronze_eia861_reliability
    WHERE sheet_name IN ('Reliability_States', 'Reliability_Territories')
      AND regexp_like(col_01, '^[0-9]{4}$')
),
-- A utility reports under one standard; metrics are taken from that standard only (D23).
standard AS (
    SELECT
        *,
        CASE
            WHEN COALESCE(ieee_saidi_with_med, ieee_saidi_without_med, ieee_saifi_with_med, ieee_saifi_without_med) IS NOT NULL
                THEN 'IEEE 1366'
            WHEN COALESCE(other_saidi_with_med, other_saidi_without_med, other_saifi_with_med, other_saifi_without_med) IS NOT NULL
                THEN 'other'
            ELSE 'not reported'
        END AS reporting_standard
    FROM reliability
),
-- Customers per utility, state and year from Sales, Parts A + C + D, summed over balancing authorities.
sales AS (
    SELECT
        TRY_CAST(col_01 AS INT)            AS data_year,
        TRIM(col_02)                   AS utility_number,
        TRIM(col_07)                   AS state_abbr,
        SUM(TRY_CAST(col_24 AS BIGINT)) AS customers
    FROM bronze_eia861_sales
    WHERE sheet_name IN ('States', 'Territories')
      AND regexp_like(col_01, '^[0-9]{4}$')
      AND TRIM(col_04) IN ('A', 'C', 'D')
    GROUP BY 1, 2, 3
)
-- Size bands by Sales customers, edges from utilities.size_band_edges (D32).
SELECT
    s.data_year,
    s.utility_number,
    s.utility_name,
    s.state_abbr,
    s.ownership,
    s.reporting_standard,
    CASE s.reporting_standard WHEN 'IEEE 1366' THEN s.ieee_saidi_with_med    WHEN 'other' THEN s.other_saidi_with_med    END AS saidi_with_med,
    CASE s.reporting_standard WHEN 'IEEE 1366' THEN s.ieee_saidi_without_med WHEN 'other' THEN s.other_saidi_without_med END AS saidi_without_med,
    CASE s.reporting_standard WHEN 'IEEE 1366' THEN s.ieee_saifi_with_med    WHEN 'other' THEN s.other_saifi_with_med    END AS saifi_with_med,
    CASE s.reporting_standard WHEN 'IEEE 1366' THEN s.ieee_saifi_without_med WHEN 'other' THEN s.other_saifi_without_med END AS saifi_without_med,
    CASE s.reporting_standard WHEN 'IEEE 1366' THEN s.ieee_customers         WHEN 'other' THEN s.other_customers         END AS reliability_customers,
    c.customers AS customers,
    CASE
        WHEN c.customers IS NULL   THEN 'unknown'
        WHEN c.customers < ${utilities.size_band_small}   THEN 'small'
        WHEN c.customers < ${utilities.size_band_medium}  THEN 'medium'
        WHEN c.customers < ${utilities.size_band_large}  THEN 'large'
        ELSE 'very_large'
    END AS size_band
FROM standard AS s
LEFT JOIN sales AS c
    ON  c.data_year      = s.data_year
    AND c.utility_number = s.utility_number
    AND c.state_abbr     = s.state_abbr;


-- -----------------------------------------------------------------------------
-- NWS zone-county versions
-- -----------------------------------------------------------------------------

CREATE OR REPLACE TABLE silver_nws_zone_versions
COMMENT 'NWS zone-county file versions; each is valid from its date until the next (D30)'
AS
WITH
-- The version is in the file name, bp<day><2-letter month><yy>.
files AS (
    SELECT DISTINCT regexp_extract(source_file, '(bp[0-9]{2}[a-z]{2}[0-9]{2})', 1) AS version
    FROM bronze_nws_zone_county
),
-- NWS month codes are two letters, not standard abbreviations.
dated AS (
    SELECT
        version,
        make_date(
            2000 + CAST(substr(version, 7, 2) AS INT),
            CASE substr(version, 5, 2)
                WHEN 'ja' THEN 1 WHEN 'fe' THEN 2 WHEN 'mr' THEN 3 WHEN 'ap' THEN 4
                WHEN 'my' THEN 5 WHEN 'jn' THEN 6 WHEN 'jl' THEN 7 WHEN 'au' THEN 8
                WHEN 'se' THEN 9 WHEN 'sp' THEN 9 WHEN 'oc' THEN 10 WHEN 'nv' THEN 11
                WHEN 'no' THEN 11 WHEN 'de' THEN 12 WHEN 'dc' THEN 12
            END,
            CAST(substr(version, 3, 2) AS INT)
        ) AS effective_from
    FROM files
)
-- The newest downloaded version has no end date.
SELECT
    version,
    effective_from,
    LEAD(effective_from) OVER (ORDER BY effective_from) AS effective_to
FROM dated;


CREATE OR REPLACE TABLE silver_nws_zone_county
COMMENT 'NWS forecast zone to county FIPS per version (D30)'
AS
SELECT DISTINCT
    v.version,
    UPPER(TRIM(z.state))                                   AS state_abbr,
    LPAD(TRIM(z.zone), 3, '0')                             AS zone,
    CONCAT(UPPER(TRIM(z.state)), LPAD(TRIM(z.zone), 3, '0')) AS zone_key,
    LPAD(TRIM(z.fips), 5, '0')                             AS fips_code
FROM bronze_nws_zone_county AS z
INNER JOIN silver_nws_zone_versions AS v
    ON v.version = regexp_extract(z.source_file, '(bp[0-9]{2}[a-z]{2}[0-9]{2})', 1);


-- -----------------------------------------------------------------------------
-- NOAA Storm Events
-- -----------------------------------------------------------------------------

CREATE OR REPLACE TABLE silver_storm_event_details
COMMENT 'NOAA Storm Events, one row per event with UTC times and parsed damage (D28, D29, D31)'
AS
WITH
-- NOAA uses its own codes for territories and water areas; the crosswalk maps them (D28).
coded AS (
    SELECT n.*, c.state_fips AS census_state_fips, c.area_type, r.state_abbr
    FROM bronze_noaa_storm_events AS n
    LEFT JOIN bronze_noaa_state_codes AS c ON c.noaa_state_fips = LPAD(TRIM(n.STATE_FIPS), 2, '0')
    LEFT JOIN bronze_state_regions    AS r ON r.state_fips = c.state_fips
),
-- Local standard time from the numeric parts; CZ_TIMEZONE carries the UTC offset (D29).
timed AS (
    SELECT
        *,
        try_to_timestamp(CONCAT(TRIM(BEGIN_YEARMONTH), LPAD(TRIM(BEGIN_DAY), 2, '0'), LPAD(TRIM(BEGIN_TIME), 4, '0')), 'yyyyMMddHHmm') AS begin_local,
        try_to_timestamp(CONCAT(TRIM(END_YEARMONTH), LPAD(TRIM(END_DAY), 2, '0'), LPAD(TRIM(END_TIME), 4, '0')), 'yyyyMMddHHmm')       AS end_local,
        TRY_CAST(regexp_extract(TRIM(CZ_TIMEZONE), '(-?[0-9]+)$', 1) AS INT)                                                             AS utc_offset_hours
    FROM coded
)
-- Damage text like 10.00K / 1.5M / 2B becomes US dollars; an empty value stays NULL, not 0 (D31).
SELECT
    CAST(EVENT_ID AS BIGINT)                AS event_id,
    CAST(EPISODE_ID AS BIGINT)              AS episode_id,
    TRIM(EVENT_TYPE)                        AS event_type,
    TRIM(CZ_TYPE)                           AS location_type,
    LPAD(TRIM(CZ_FIPS), 3, '0')             AS cz_fips,
    TRIM(CZ_NAME)                           AS cz_name,
    TRIM(STATE)                             AS noaa_state,
    LPAD(TRIM(STATE_FIPS), 2, '0')          AS noaa_state_fips,
    census_state_fips                       AS state_fips,
    state_abbr,
    area_type,
    begin_local,
    end_local,
    TRIM(CZ_TIMEZONE)                       AS cz_timezone,
    utc_offset_hours,
    begin_local - INTERVAL 1 HOUR * utc_offset_hours AS begin_utc,
    end_local   - INTERVAL 1 HOUR * utc_offset_hours AS end_utc,
    CASE
        WHEN regexp_like(TRIM(DAMAGE_PROPERTY), '^[0-9.]+[KMB]?$')
        THEN TRY_CAST(regexp_extract(TRIM(DAMAGE_PROPERTY), '^([0-9.]+)', 1) AS DOUBLE)
             * CASE RIGHT(TRIM(DAMAGE_PROPERTY), 1) WHEN 'K' THEN 1E3 WHEN 'M' THEN 1E6 WHEN 'B' THEN 1E9 ELSE 1 END
    END                                     AS damage_property_usd,
    CASE
        WHEN regexp_like(TRIM(DAMAGE_CROPS), '^[0-9.]+[KMB]?$')
        THEN TRY_CAST(regexp_extract(TRIM(DAMAGE_CROPS), '^([0-9.]+)', 1) AS DOUBLE)
             * CASE RIGHT(TRIM(DAMAGE_CROPS), 1) WHEN 'K' THEN 1E3 WHEN 'M' THEN 1E6 WHEN 'B' THEN 1E9 ELSE 1 END
    END                                     AS damage_crops_usd,
    TRY_CAST(DEATHS_DIRECT AS INT)          AS deaths_direct,
    TRY_CAST(DEATHS_INDIRECT AS INT)        AS deaths_indirect,
    TRY_CAST(INJURIES_DIRECT AS INT)        AS injuries_direct,
    TRY_CAST(INJURIES_INDIRECT AS INT)      AS injuries_indirect,
    TRY_CAST(MAGNITUDE AS DOUBLE)           AS magnitude,
    TRIM(MAGNITUDE_TYPE)                    AS magnitude_type,
    TRIM(TOR_F_SCALE)                       AS tor_f_scale,
    source_file
FROM timed;


CREATE OR REPLACE TABLE silver_storm_events
COMMENT 'NOAA Storm Events, one row per event per county; zone events expanded with the zone file in effect (D30, D31)'
AS
WITH
-- County events: the county FIPS is the state FIPS plus CZ_FIPS (D30).
county_events AS (
    SELECT
        event_id,
        CONCAT(state_fips, cz_fips)  AS fips_code,
        CAST(NULL AS STRING)         AS zone_key,
        CAST(NULL AS STRING)         AS zone_version
    FROM silver_storm_event_details
    WHERE location_type = 'C' AND area_type IN ('state', 'territory')
),
-- Zone events: the zone file in effect on the local begin date maps the zone to its counties (D30).
zone_events AS (
    SELECT DISTINCT
        d.event_id,
        z.fips_code,
        z.zone_key,
        z.version AS zone_version
    FROM silver_storm_event_details AS d
    INNER JOIN silver_nws_zone_versions AS v
        ON  CAST(d.begin_local AS DATE) >= v.effective_from
        AND (v.effective_to IS NULL OR CAST(d.begin_local AS DATE) < v.effective_to)
    INNER JOIN silver_nws_zone_county AS z
        ON  z.version  = v.version
        AND z.zone_key = CONCAT(d.state_abbr, d.cz_fips)
    WHERE d.location_type = 'Z' AND d.area_type IN ('state', 'territory')
),
placed AS (
    SELECT * FROM county_events
    UNION ALL
    SELECT * FROM zone_events
)
-- Event-level measures repeat on each county row; event_weight = 1 / county_count lets sums
-- across counties return the event total (D31).
SELECT
    d.event_id,
    d.episode_id,
    p.fips_code,
    d.state_abbr,
    d.location_type,
    p.zone_key,
    p.zone_version,
    d.event_type,
    d.begin_utc,
    d.end_utc,
    d.cz_timezone,
    d.damage_property_usd,
    d.damage_crops_usd,
    d.deaths_direct,
    d.deaths_indirect,
    d.injuries_direct,
    d.injuries_indirect,
    d.magnitude,
    d.magnitude_type,
    d.tor_f_scale,
    COUNT(*) OVER (PARTITION BY d.event_id)        AS county_count,
    1.0 / COUNT(*) OVER (PARTITION BY d.event_id)  AS event_weight,
    YEAR(d.begin_utc)                              AS year
FROM placed AS p
INNER JOIN silver_storm_event_details AS d ON d.event_id = p.event_id;


CREATE OR REPLACE TABLE silver_storm_events_unplaced
COMMENT 'NOAA events with no county: water areas, untracked territories, zones missing from the file (D30)'
AS
SELECT
    d.event_id,
    d.event_type,
    d.noaa_state,
    d.location_type,
    d.begin_utc,
    YEAR(d.begin_utc) AS year,
    CASE
        WHEN d.area_type = 'water'                 THEN 'water'
        WHEN d.area_type = 'territory_not_tracked' THEN 'territory_not_tracked'
        WHEN d.area_type IS NULL                   THEN 'unknown_state_code'
        WHEN d.location_type = 'Z'                 THEN 'zone_not_in_file'
        ELSE 'other'
    END AS reason
FROM silver_storm_event_details AS d
WHERE NOT EXISTS (SELECT 1 FROM silver_storm_events AS s WHERE s.event_id = d.event_id);


-- -----------------------------------------------------------------------------
-- OE-417
-- -----------------------------------------------------------------------------

CREATE OR REPLACE TABLE silver_oe417_rows
COMMENT 'OE-417 incidents, one row each, parsed but not yet located (D33)'
AS
WITH
-- The header row is the one whose second cell reads Date Event Began; data rows follow it (D33).
headers AS (
    SELECT source_name, MIN(CAST(row_number AS INT)) AS header_row
    FROM bronze_oe417
    WHERE TRIM(col_02) = 'Date Event Began'
    GROUP BY source_name
),
-- Rows after the header with at least one non-empty cell are incidents.
data_rows AS (
    SELECT
        b.*,
        CAST(regexp_extract(b.source_name, '([0-9]{4})', 1) AS INT) AS report_year,
        CAST(b.row_number AS INT)                                  AS sheet_row
    FROM bronze_oe417 AS b
    INNER JOIN headers AS h
        ON h.source_name = b.source_name AND CAST(b.row_number AS INT) > h.header_row
    WHERE CONCAT(COALESCE(TRIM(col_01), ''), COALESCE(TRIM(col_02), ''), COALESCE(TRIM(col_03), ''),
                 COALESCE(TRIM(col_04), ''), COALESCE(TRIM(col_05), ''), COALESCE(TRIM(col_06), ''),
                 COALESCE(TRIM(col_07), ''), COALESCE(TRIM(col_08), ''), COALESCE(TRIM(col_09), ''),
                 COALESCE(TRIM(col_10), ''), COALESCE(TRIM(col_11), '')) <> ''
),
-- Dates are M/d/yyyy text, ISO dates, or Excel day numbers stored as text; times are HH:MM:SS (D27, D33).
parsed AS (
    SELECT
        report_year,
        sheet_row,
        CONCAT(CAST(report_year AS STRING), '-',
               LPAD(CAST(ROW_NUMBER() OVER (PARTITION BY report_year ORDER BY sheet_row) AS STRING), 4, '0')) AS incident_id,
        COALESCE(try_to_timestamp(TRIM(col_02), 'M/d/yyyy'), try_to_timestamp(TRIM(col_02), 'yyyy-MM-dd'),
                 CASE WHEN regexp_like(TRIM(col_02), '^[0-9]{5}$')
                      THEN timestamp_seconds((CAST(TRIM(col_02) AS BIGINT) - 25569) * 86400) END) AS begin_date,
        COALESCE(try_to_timestamp(TRIM(col_04), 'M/d/yyyy'), try_to_timestamp(TRIM(col_04), 'yyyy-MM-dd'),
                 CASE WHEN regexp_like(TRIM(col_04), '^[0-9]{5}$')
                      THEN timestamp_seconds((CAST(TRIM(col_04) AS BIGINT) - 25569) * 86400) END) AS restoration_date,
        CASE WHEN regexp_like(TRIM(col_03), '^[0-9]{1,2}:[0-9]{2}(:[0-9]{2})?$')
             THEN CAST(split_part(TRIM(col_03), ':', 1) AS INT) * 3600 + CAST(split_part(TRIM(col_03), ':', 2) AS INT) * 60
                  + COALESCE(TRY_CAST(split_part(TRIM(col_03), ':', 3) AS INT), 0)
        END AS begin_seconds,
        CASE WHEN regexp_like(TRIM(col_05), '^[0-9]{1,2}:[0-9]{2}(:[0-9]{2})?$')
             THEN CAST(split_part(TRIM(col_05), ':', 1) AS INT) * 3600 + CAST(split_part(TRIM(col_05), ':', 2) AS INT) * 60
                  + COALESCE(TRY_CAST(split_part(TRIM(col_05), ':', 3) AS INT), 0)
        END AS restoration_seconds,
        regexp_replace(LOWER(TRIM(COALESCE(col_04, ''))), '^[- ]+', '') AS restoration_text,
        REPLACE(regexp_replace(REPLACE(REPLACE(COALESCE(col_06, ''), chr(160), ' '), '[', ''), '[0-9]+]', ''),
                ', City of', '') AS area_text,
        TRIM(col_07) AS nerc_region,
        TRIM(col_08) AS alert_criteria,
        TRIM(col_09) AS event_type_raw,
        TRY_CAST(REPLACE(TRIM(col_10), ',', '') AS DOUBLE) AS demand_loss_mw,
        CAST(TRY_CAST(REPLACE(TRIM(col_11), ',', '') AS DOUBLE) AS BIGINT) AS customers_affected
    FROM data_rows
)
-- Area text drops footnote markers such as [13] and the ', City of' suffix of independent cities (D33).
-- Event type key: lowercase, spaces for non-breaking spaces, no leading dash, ' - ' separators (D24).
SELECT
    incident_id,
    report_year,
    sheet_row,
    CASE WHEN begin_date IS NOT NULL
         THEN timestamp_seconds(unix_seconds(begin_date) + COALESCE(begin_seconds, 0)) END AS begin_local,
    begin_seconds IS NOT NULL AS begin_time_reported,
    CASE WHEN restoration_date IS NOT NULL
         THEN timestamp_seconds(unix_seconds(restoration_date) + COALESCE(restoration_seconds, 0)) END AS restoration_local,
    CASE
        WHEN restoration_date IS NOT NULL       THEN 'reported'
        WHEN restoration_text LIKE 'unk%'      THEN 'unknown'
        WHEN restoration_text LIKE 'ongoing%'  THEN 'ongoing'
        WHEN restoration_text = ''             THEN 'missing'
        ELSE 'unparsed'
    END AS restoration_status,
    area_text,
    nerc_region,
    alert_criteria,
    event_type_raw,
    TRIM(regexp_replace(regexp_replace(regexp_replace(
        LOWER(TRIM(REPLACE(COALESCE(event_type_raw, ''), chr(160), ' '))),
        '^[- ]+', ''), ' *- +', ' - '), ' +', ' ')) AS event_type_key,
    demand_loss_mw,
    customers_affected
FROM parsed;


CREATE OR REPLACE TABLE silver_oe417_locations
COMMENT 'States and counties named in OE-417 Area Affected, county names matched to EAGLE-I FIPS (D33, D34)'
AS
WITH
-- Area Affected reads State: County, County; State: ... Split on : ; and , into ordered tokens.
token_lists AS (
    SELECT incident_id, split(area_text, '[:;,]') AS parts
    FROM silver_oe417_rows
    WHERE TRIM(area_text) <> ''
),
positions AS (
    SELECT incident_id, parts, explode(sequence(1, cardinality(parts))) AS pos
    FROM token_lists
),
tokens AS (
    SELECT incident_id, pos, TRIM(element_at(parts, pos)) AS token
    FROM positions
),
-- A token that is a state name opens that state's list; the other tokens are its counties.
classified AS (
    SELECT t.incident_id, t.pos, t.token, r.state_abbr AS token_state
    FROM tokens AS t
    LEFT JOIN bronze_state_regions AS r ON LOWER(r.state_name) = LOWER(t.token)
    WHERE t.token <> ''
),
with_state_pos AS (
    SELECT
        *,
        MAX(CASE WHEN token_state IS NOT NULL THEN pos END) OVER (
            PARTITION BY incident_id ORDER BY pos ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ) AS state_pos
    FROM classified
),
located AS (
    SELECT w.incident_id, w.pos, w.token, w.token_state, s.token_state AS state_abbr
    FROM with_state_pos AS w
    LEFT JOIN classified AS s ON s.incident_id = w.incident_id AND s.pos = w.state_pos
),
-- County names are normalized the same way on both sides: lowercase, no punctuation,
-- St = Saint, no County/Parish/Borough/Census Area/Municipality suffix (D34).
counties AS (
    SELECT
        incident_id, pos, state_abbr, token AS county_name_raw,
        TRIM(regexp_replace(regexp_replace(regexp_replace(regexp_replace(
            REPLACE(REPLACE(REPLACE(REPLACE(LOWER(TRIM(token)), '&', ' and '), '.', ''), chr(39), ''), '-', ' '),
            '^st ', 'saint '), '^ste ', 'sainte '),
            '(^| )(city and borough|census area|county|parish|borough|municipality|municipio)( |$)', ' '),
            ' +', ' ')) AS county_key
    FROM located
    WHERE token_state IS NULL AND state_abbr IS NOT NULL
),
eaglei_counties AS (
    SELECT fips_code, county FROM bronze_eaglei_2022
    UNION
    SELECT fips_code, county FROM bronze_eaglei_2023
    UNION
    SELECT fips_code, county FROM bronze_eaglei_2024
),
eaglei_names AS (
    SELECT DISTINCT
        LPAD(TRIM(e.fips_code), 5, '0') AS fips_code,
        r.state_abbr,
        TRIM(regexp_replace(regexp_replace(regexp_replace(regexp_replace(
            REPLACE(REPLACE(REPLACE(REPLACE(LOWER(TRIM(e.county)), '&', ' and '), '.', ''), chr(39), ''), '-', ' '),
            '^st ', 'saint '), '^ste ', 'sainte '),
            '(^| )(city and borough|census area|county|parish|borough|municipality|municipio)( |$)', ' '),
            ' +', ' ')) AS county_key
    FROM eaglei_counties AS e
    INNER JOIN bronze_state_regions AS r ON r.state_fips = LEFT(LPAD(TRIM(e.fips_code), 5, '0'), 2)
),
-- A name that fits two EAGLE-I counties (Baltimore city and county) keeps both, flagged (D34).
matched AS (
    SELECT
        c.*,
        e.fips_code,
        COUNT(e.fips_code) OVER (PARTITION BY c.incident_id, c.pos) AS candidates
    FROM counties AS c
    LEFT JOIN eaglei_names AS e ON e.state_abbr = c.state_abbr AND e.county_key = c.county_key
)
SELECT
    incident_id,
    pos                    AS token_position,
    'state'                AS location_level,
    token_state            AS state_abbr,
    CAST(NULL AS STRING)   AS county_name_raw,
    CAST(NULL AS STRING)   AS fips_code,
    CAST(NULL AS STRING)   AS match_type
FROM located
WHERE token_state IS NOT NULL
UNION ALL
SELECT
    incident_id,
    pos,
    'county',
    state_abbr,
    county_name_raw,
    fips_code,
    CASE WHEN fips_code IS NULL THEN 'unmatched' WHEN candidates > 1 THEN 'ambiguous' ELSE 'exact' END
FROM matched;


CREATE OR REPLACE TABLE silver_oe417
COMMENT 'OE-417 incidents with UTC times, states and counties affected, event category (D24, D33)'
AS
WITH
-- States and matched counties per incident.
locations AS (
    SELECT
        incident_id,
        array_sort(array_agg(DISTINCT state_abbr) FILTER (WHERE state_abbr IS NOT NULL)) AS states_affected,
        array_sort(array_agg(DISTINCT fips_code) FILTER (WHERE fips_code IS NOT NULL))   AS counties_affected,
        COUNT(DISTINCT token_position) FILTER (WHERE location_level = 'county')          AS county_names_listed,
        COUNT(DISTINCT token_position) FILTER (WHERE location_level = 'county' AND fips_code IS NULL) AS county_names_unmatched
    FROM silver_oe417_locations
    GROUP BY incident_id
),
-- Times are local to the first state listed (D24).
first_state AS (
    SELECT incident_id, state_abbr
    FROM silver_oe417_locations
    WHERE location_level = 'state'
    QUALIFY ROW_NUMBER() OVER (PARTITION BY incident_id ORDER BY token_position) = 1
)
SELECT
    r.incident_id,
    r.report_year,
    f.state_abbr                                                AS primary_state,
    z.primary_time_zone                                         AS time_zone,
    r.begin_local,
    to_utc_timestamp(r.begin_local, z.primary_time_zone)        AS begin_utc,
    r.begin_time_reported,
    r.restoration_local,
    to_utc_timestamp(r.restoration_local, z.primary_time_zone)  AS restoration_utc,
    r.restoration_status,
    l.states_affected,
    l.counties_affected,
    CASE WHEN l.counties_affected IS NULL THEN 0 ELSE cardinality(l.counties_affected) END AS county_count,
    COALESCE(l.county_names_listed, 0)                          AS county_names_listed,
    COALESCE(l.county_names_unmatched, 0)                       AS county_names_unmatched,
    r.event_type_raw,
    r.event_type_key,
    COALESCE(t.category, 'unmapped')                            AS event_category,
    COALESCE(t.multiple_types = 'Y', FALSE)                     AS multiple_types,
    r.nerc_region,
    r.alert_criteria,
    r.demand_loss_mw,
    r.customers_affected,
    r.area_text
FROM silver_oe417_rows AS r
LEFT JOIN locations AS l ON l.incident_id = r.incident_id
LEFT JOIN first_state AS f ON f.incident_id = r.incident_id
LEFT JOIN bronze_state_time_zones AS z ON z.state_abbr = f.state_abbr
LEFT JOIN bronze_oe417_event_types AS t ON t.event_type_key = r.event_type_key;


-- -----------------------------------------------------------------------------
-- Checks (expected values: scripts/run_databricks.py)
-- -----------------------------------------------------------------------------

SELECT 'silver_storm_events' AS table_name, COUNT(*) AS row_count FROM silver_storm_events
UNION ALL SELECT 'silver_storm_event_details', COUNT(*) FROM silver_storm_event_details
UNION ALL SELECT 'silver_storm_events_unplaced', COUNT(*) FROM silver_storm_events_unplaced
UNION ALL SELECT 'silver_utility_reliability', COUNT(*) FROM silver_utility_reliability
UNION ALL SELECT 'silver_eia_state_customers', COUNT(*) FROM silver_eia_state_customers
UNION ALL SELECT 'silver_oe417', COUNT(*) FROM silver_oe417
UNION ALL SELECT 'silver_oe417_locations', COUNT(*) FROM silver_oe417_locations;
