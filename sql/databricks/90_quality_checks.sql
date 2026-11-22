-- =============================================================================
-- 90_quality_checks.sql
-- Data quality gates (D48). scripts/quality_checks.py runs these after each layer and on demand.
--
-- Every statement returns rows of
--   layer STRING, check_name STRING, observed DOUBLE, expected STRING, passed BOOLEAN
-- and a check passes only when passed is TRUE. Most checks count violating rows, so observed is
-- the number of bad rows and expected is '0'. Statements run in the section of their layer
-- (marked by "-- @layer <name>"); the runner writes every row to gold_quality_results with the
-- run timestamp and stops the pipeline if any check fails.
--
-- Values come from config/pipeline.yml (D47): row-count tolerance, expected row counts, event
-- rules, ranking rules. Statements are plain SELECTs so the same file runs in DuckDB
-- (translated by scripts/sql_dialect.py) and on Databricks.
-- =============================================================================


-- @layer bronze

-- Bronze row counts are within quality.row_count_tolerance of the verified run.
WITH
-- One count per Bronze table with its expected value from the config.
counts AS (
    SELECT 'bronze_eaglei_2022' AS table_name, COUNT(*) AS observed, ${quality.expected_rows.bronze_eaglei_2022} AS expected FROM bronze_eaglei_2022
    UNION ALL SELECT 'bronze_eaglei_2023', COUNT(*), ${quality.expected_rows.bronze_eaglei_2023} FROM bronze_eaglei_2023
    UNION ALL SELECT 'bronze_eaglei_2024', COUNT(*), ${quality.expected_rows.bronze_eaglei_2024} FROM bronze_eaglei_2024
    UNION ALL SELECT 'bronze_eaglei_mcc', COUNT(*), ${quality.expected_rows.bronze_eaglei_mcc} FROM bronze_eaglei_mcc
    UNION ALL SELECT 'bronze_state_regions', COUNT(*), ${quality.expected_rows.bronze_state_regions} FROM bronze_state_regions
    UNION ALL SELECT 'bronze_noaa_storm_events', COUNT(*), ${quality.expected_rows.bronze_noaa_storm_events} FROM bronze_noaa_storm_events
    UNION ALL SELECT 'bronze_nws_zone_county', COUNT(*), ${quality.expected_rows.bronze_nws_zone_county} FROM bronze_nws_zone_county
    UNION ALL SELECT 'bronze_eia861_reliability', COUNT(*), ${quality.expected_rows.bronze_eia861_reliability} FROM bronze_eia861_reliability
    UNION ALL SELECT 'bronze_eia861_sales', COUNT(*), ${quality.expected_rows.bronze_eia861_sales} FROM bronze_eia861_sales
    UNION ALL SELECT 'bronze_eia861_service_territory', COUNT(*), ${quality.expected_rows.bronze_eia861_service_territory} FROM bronze_eia861_service_territory
    UNION ALL SELECT 'bronze_oe417', COUNT(*), ${quality.expected_rows.bronze_oe417} FROM bronze_oe417
    UNION ALL SELECT 'bronze_noaa_state_codes', COUNT(*), ${quality.expected_rows.bronze_noaa_state_codes} FROM bronze_noaa_state_codes
    UNION ALL SELECT 'bronze_oe417_event_types', COUNT(*), ${quality.expected_rows.bronze_oe417_event_types} FROM bronze_oe417_event_types
    UNION ALL SELECT 'bronze_state_time_zones', COUNT(*), ${quality.expected_rows.bronze_state_time_zones} FROM bronze_state_time_zones
    UNION ALL SELECT 'bronze_storm_event_severity', COUNT(*), ${quality.expected_rows.bronze_storm_event_severity} FROM bronze_storm_event_severity
    UNION ALL SELECT 'bronze_ranking_exclusions', COUNT(*), ${quality.expected_rows.bronze_ranking_exclusions} FROM bronze_ranking_exclusions
)
SELECT
    'bronze'                                                              AS layer,
    CONCAT('row count: ', table_name)                                     AS check_name,
    CAST(observed AS DOUBLE)                                              AS observed,
    CONCAT(CAST(expected AS STRING), ' +/- ', CAST(${quality.row_count_tolerance} * 100 AS STRING), '%') AS expected,
    ABS(observed - expected) <= ${quality.row_count_tolerance} * expected AS passed
FROM counts;

-- The ranked jurisdictions are the 50 states and DC: the region lookup must hold exactly that many
-- non-territories (D43, D44), so the ranking checks in Gold compare against a complete list.
SELECT
    'bronze' AS layer,
    'region lookup has the 50 states and DC (D43)' AS check_name,
    CAST(COUNT_IF(census_region <> 'Territory') AS DOUBLE) AS observed,
    '${ranking.ranked_jurisdictions}' AS expected,
    COUNT_IF(census_region <> 'Territory') = ${ranking.ranked_jurisdictions} AND COUNT(*) = COUNT(DISTINCT state_fips) AS passed
FROM bronze_state_regions;


-- @layer silver

-- Silver row counts are within quality.row_count_tolerance of the verified run.
WITH
-- One count per Silver table with its expected value from the config.
counts AS (
    SELECT 'silver_eia_state_customers' AS table_name, COUNT(*) AS observed, ${quality.expected_rows.silver_eia_state_customers} AS expected
    FROM silver_eia_state_customers
    UNION ALL SELECT 'silver_utility_reliability', COUNT(*), ${quality.expected_rows.silver_utility_reliability} FROM silver_utility_reliability
    UNION ALL SELECT 'silver_nws_zone_versions', COUNT(*), ${quality.expected_rows.silver_nws_zone_versions} FROM silver_nws_zone_versions
    UNION ALL SELECT 'silver_nws_zone_county', COUNT(*), ${quality.expected_rows.silver_nws_zone_county} FROM silver_nws_zone_county
    UNION ALL SELECT 'silver_storm_event_details', COUNT(*), ${quality.expected_rows.silver_storm_event_details} FROM silver_storm_event_details
    UNION ALL SELECT 'silver_storm_events', COUNT(*), ${quality.expected_rows.silver_storm_events} FROM silver_storm_events
    UNION ALL SELECT 'silver_storm_events_unplaced', COUNT(*), ${quality.expected_rows.silver_storm_events_unplaced} FROM silver_storm_events_unplaced
    UNION ALL SELECT 'silver_oe417_rows', COUNT(*), ${quality.expected_rows.silver_oe417_rows} FROM silver_oe417_rows
    UNION ALL SELECT 'silver_oe417_locations', COUNT(*), ${quality.expected_rows.silver_oe417_locations} FROM silver_oe417_locations
    UNION ALL SELECT 'silver_oe417', COUNT(*), ${quality.expected_rows.silver_oe417} FROM silver_oe417
    UNION ALL SELECT 'dim_county_customers', COUNT(*), ${quality.expected_rows.dim_county_customers} FROM dim_county_customers
    UNION ALL SELECT 'silver_outages', COUNT(*), ${quality.expected_rows.silver_outages} FROM silver_outages
)
SELECT
    'silver'                                                              AS layer,
    CONCAT('row count: ', table_name)                                     AS check_name,
    CAST(observed AS DOUBLE)                                              AS observed,
    CONCAT(CAST(expected AS STRING), ' +/- ', CAST(${quality.row_count_tolerance} * 100 AS STRING), '%') AS expected,
    ABS(observed - expected) <= ${quality.row_count_tolerance} * expected AS passed
FROM counts;

-- Primary keys: no duplicates and no NULLs in the key columns of the Silver tables.
WITH
-- silver_outages is keyed by county and 15-minute slot after the D7 dedupe.
outage_dupes AS (
    SELECT COUNT(*) AS n FROM (
        SELECT fips_code, reading_time FROM silver_outages GROUP BY fips_code, reading_time HAVING COUNT(*) > 1
    ) AS d
),
-- Zone events are expanded to counties, so storm rows are keyed by NOAA event and county (D30).
storm_dupes AS (
    SELECT COUNT(*) AS n FROM (
        SELECT event_id, fips_code FROM silver_storm_events GROUP BY event_id, fips_code HAVING COUNT(*) > 1
    ) AS d
),
-- EIA-861 reliability is reported per utility, state and year (D32).
utility_dupes AS (
    SELECT COUNT(*) AS n FROM (
        SELECT data_year, utility_number, state_abbr FROM silver_utility_reliability
        GROUP BY data_year, utility_number, state_abbr HAVING COUNT(*) > 1
    ) AS d
),
checks AS (
    SELECT 'silver_outages: duplicate (fips_code, reading_time)' AS check_name, CAST(n AS DOUBLE) AS observed FROM outage_dupes
    UNION ALL
    SELECT 'silver_outages: NULL in fips_code, reading_time, year or state',
           CAST(COUNT_IF(fips_code IS NULL OR reading_time IS NULL OR year IS NULL OR state IS NULL) AS DOUBLE)
    FROM silver_outages
    UNION ALL
    SELECT 'dim_county_customers: duplicate or NULL fips_code',
           CAST(COUNT(*) - COUNT(DISTINCT fips_code) + COUNT_IF(fips_code IS NULL) AS DOUBLE)
    FROM dim_county_customers
    UNION ALL
    SELECT 'silver_storm_events: duplicate (event_id, fips_code)', CAST(n AS DOUBLE) FROM storm_dupes
    UNION ALL
    SELECT 'silver_storm_events: NULL in event_id or fips_code',
           CAST(COUNT_IF(event_id IS NULL OR fips_code IS NULL) AS DOUBLE)
    FROM silver_storm_events
    UNION ALL
    SELECT 'silver_utility_reliability: duplicate (data_year, utility_number, state_abbr)', CAST(n AS DOUBLE) FROM utility_dupes
    UNION ALL
    SELECT 'silver_utility_reliability: NULL in data_year, utility_number or state_abbr',
           CAST(COUNT_IF(data_year IS NULL OR utility_number IS NULL OR state_abbr IS NULL) AS DOUBLE)
    FROM silver_utility_reliability
    UNION ALL
    SELECT 'silver_oe417: duplicate or NULL incident_id',
           CAST(COUNT(*) - COUNT(DISTINCT incident_id) + COUNT_IF(incident_id IS NULL) AS DOUBLE)
    FROM silver_oe417
    UNION ALL
    SELECT 'silver_eia_state_customers: duplicate (data_year, state_abbr)',
           CAST(COUNT(*) - COUNT(DISTINCT CONCAT(CAST(data_year AS STRING), '-', state_abbr)) AS DOUBLE)
    FROM silver_eia_state_customers
)
SELECT 'silver' AS layer, check_name, observed, '0' AS expected, observed = 0 AS passed FROM checks;

-- Valid values: FIPS shape, 15-minute grid, years in the config, counts and shares in range.
WITH
checks AS (
    SELECT 'silver_outages: customers_out < 0' AS check_name, CAST(COUNT_IF(customers_out < 0) AS DOUBLE) AS observed
    FROM silver_outages
    UNION ALL
    SELECT 'silver_outages: fips_code not 5 digits (D6)', CAST(COUNT_IF(NOT REGEXP_LIKE(fips_code, '^[0-9]{5}$')) AS DOUBLE)
    FROM silver_outages
    UNION ALL
    SELECT 'silver_outages: reading_time off the 15-minute grid (D7)',
           CAST(COUNT_IF(MINUTE(reading_time) % 15 <> 0 OR SECOND(reading_time) <> 0) AS DOUBLE)
    FROM silver_outages
    UNION ALL
    SELECT 'silver_outages: year outside config years', CAST(COUNT_IF(year NOT IN (${years.sql})) AS DOUBLE)
    FROM silver_outages
    UNION ALL
    SELECT 'dim_county_customers: customers <= 0', CAST(COUNT_IF(customers <= 0) AS DOUBLE)
    FROM dim_county_customers
    UNION ALL
    SELECT 'dim_county_customers: calibration_factor <= 0 or state factor < 1 (D21)',
           CAST(COUNT_IF(calibration_factor <= 0 OR state_calibration_factor < 1) AS DOUBLE)
    FROM dim_county_customers
    UNION ALL
    SELECT 'silver_storm_events: event_weight outside (0, 1] (D31)',
           CAST(COUNT_IF(event_weight <= 0 OR event_weight > 1) AS DOUBLE)
    FROM silver_storm_events
    UNION ALL
    SELECT 'silver_utility_reliability: negative SAIDI or SAIFI',
           CAST(COUNT_IF(saidi_with_med < 0 OR saidi_without_med < 0 OR saifi_with_med < 0 OR saifi_without_med < 0) AS DOUBLE)
    FROM silver_utility_reliability
)
SELECT 'silver' AS layer, check_name, observed, '0' AS expected, observed = 0 AS passed FROM checks;

-- In calibrated states the county denominators add up to the EIA-861 state total (D21, D35).
-- Each scaled county is rounded to a whole customer, so a state may differ by at most half a
-- customer per county.
WITH
-- County denominators summed per calibrated state.
calibrated AS (
    SELECT r.state_abbr, SUM(d.customers) AS customers, COUNT(*) AS counties
    FROM dim_county_customers AS d
    INNER JOIN bronze_state_regions AS r ON r.state_fips = LEFT(d.fips_code, 2)
    WHERE d.state_calibration_factor > 1 AND d.customers IS NOT NULL
    GROUP BY r.state_abbr
),
-- The EIA-861 totals of the calibration year.
compared AS (
    SELECT c.state_abbr, c.customers, c.counties, e.customers AS eia_customers
    FROM calibrated AS c
    LEFT JOIN silver_eia_state_customers AS e
        ON e.state_abbr = c.state_abbr AND e.data_year = ${calibration.eia_year}
)
SELECT
    'silver' AS layer,
    'calibrated state totals equal EIA-861 (D21)' AS check_name,
    CAST(COUNT_IF(eia_customers IS NULL OR ABS(customers - eia_customers) > 0.5 * counties) AS DOUBLE) AS observed,
    '0 states off' AS expected,
    COUNT_IF(eia_customers IS NULL OR ABS(customers - eia_customers) > 0.5 * counties) = 0 AS passed
FROM compared;

-- No county of a calibrated state sits below its peak customers out, unless D36 skipped its floor.
WITH
-- Highest reading per county across all years: the D35 floor.
peaks AS (
    SELECT fips_code, MAX(customers_out) AS peak_customers_out
    FROM silver_outages
    GROUP BY fips_code
)
SELECT
    'silver' AS layer,
    'calibrated county below its peak without the D36 skip (D35)' AS check_name,
    CAST(COUNT(*) AS DOUBLE) AS observed,
    '0' AS expected,
    COUNT(*) = 0 AS passed
FROM dim_county_customers AS d
INNER JOIN peaks AS p ON p.fips_code = d.fips_code
WHERE d.state_calibration_factor > 1
  AND d.customers < p.peak_customers_out
  AND NOT d.peak_floor_skipped;

-- Referential integrity: every Silver fact row joins its dimensions on the 5-digit FIPS.
WITH
checks AS (
    SELECT 'silver_outages: fips_code missing from dim_county_customers' AS check_name, CAST(COUNT(*) AS DOUBLE) AS observed
    FROM silver_outages AS s
    LEFT JOIN dim_county_customers AS d ON d.fips_code = s.fips_code
    WHERE d.fips_code IS NULL
    UNION ALL
    SELECT 'silver_outages: state prefix missing from bronze_state_regions', CAST(COUNT(*) AS DOUBLE)
    FROM silver_outages AS s
    LEFT JOIN bronze_state_regions AS r ON r.state_fips = LEFT(s.fips_code, 2)
    WHERE r.state_fips IS NULL
    UNION ALL
    SELECT 'silver_oe417_locations: incident_id missing from silver_oe417', CAST(COUNT(*) AS DOUBLE)
    FROM silver_oe417_locations AS l
    LEFT JOIN silver_oe417 AS o ON o.incident_id = l.incident_id
    WHERE o.incident_id IS NULL
)
SELECT 'silver' AS layer, check_name, observed, '0' AS expected, observed = 0 AS passed FROM checks;


-- @layer gold

-- Gold row counts are within quality.row_count_tolerance of the verified run.
WITH
-- One count per Gold table with its expected value from the config.
counts AS (
    SELECT 'gold_collection_runs' AS table_name, COUNT(*) AS observed, ${quality.expected_rows.gold_collection_runs} AS expected FROM gold_collection_runs
    UNION ALL SELECT 'gold_event_thresholds', COUNT(*), ${quality.expected_rows.gold_event_thresholds} FROM gold_event_thresholds
    UNION ALL SELECT 'gold_feed_dropouts', COUNT(*), ${quality.expected_rows.gold_feed_dropouts} FROM gold_feed_dropouts
    UNION ALL SELECT 'gold_outage_events', COUNT(*), ${quality.expected_rows.gold_outage_events} FROM gold_outage_events
    UNION ALL SELECT 'gold_state_coverage', COUNT(*), ${quality.expected_rows.gold_state_coverage} FROM gold_state_coverage
    UNION ALL SELECT 'gold_event_storm_match', COUNT(*), ${quality.expected_rows.gold_event_storm_match} FROM gold_event_storm_match
    UNION ALL SELECT 'gold_unit_reliability', COUNT(*), ${quality.expected_rows.gold_unit_reliability} FROM gold_unit_reliability
    UNION ALL SELECT 'gold_county_reliability', COUNT(*), ${quality.expected_rows.gold_county_reliability} FROM gold_county_reliability
    UNION ALL SELECT 'gold_territory_unit_reliability', COUNT(*), ${quality.expected_rows.gold_territory_unit_reliability} FROM gold_territory_unit_reliability
    UNION ALL SELECT 'gold_county_ranking_footnotes', COUNT(*), ${quality.expected_rows.gold_county_ranking_footnotes} FROM gold_county_ranking_footnotes
    UNION ALL SELECT 'gold_state_reliability', COUNT(*), ${quality.expected_rows.gold_state_reliability} FROM gold_state_reliability
    UNION ALL SELECT 'gold_territory_reliability', COUNT(*), ${quality.expected_rows.gold_territory_reliability} FROM gold_territory_reliability
    UNION ALL SELECT 'gold_utility_reliability', COUNT(*), ${quality.expected_rows.gold_utility_reliability} FROM gold_utility_reliability
    UNION ALL SELECT 'gold_utility_reliability_other', COUNT(*), ${quality.expected_rows.gold_utility_reliability_other} FROM gold_utility_reliability_other
    UNION ALL SELECT 'gold_oe417_check', COUNT(*), ${quality.expected_rows.gold_oe417_check} FROM gold_oe417_check
)
SELECT
    'gold'                                                                AS layer,
    CONCAT('row count: ', table_name)                                     AS check_name,
    CAST(observed AS DOUBLE)                                              AS observed,
    CONCAT(CAST(expected AS STRING), ' +/- ', CAST(${quality.row_count_tolerance} * 100 AS STRING), '%') AS expected,
    ABS(observed - expected) <= ${quality.row_count_tolerance} * expected AS passed
FROM counts;

-- Primary keys: no duplicates and no NULLs in the key columns of the Gold tables.
WITH
checks AS (
    SELECT 'gold_collection_runs: duplicate or NULL slot_time' AS check_name,
           CAST(COUNT(*) - COUNT(DISTINCT slot_time) + COUNT_IF(slot_time IS NULL) AS DOUBLE) AS observed
    FROM gold_collection_runs
    UNION ALL
    SELECT 'gold_event_thresholds: duplicate or NULL fips_code',
           CAST(COUNT(*) - COUNT(DISTINCT fips_code) + COUNT_IF(fips_code IS NULL) AS DOUBLE)
    FROM gold_event_thresholds
    UNION ALL
    SELECT 'gold_feed_dropouts: duplicate (fips_code, drop_start_run)',
           CAST(COUNT(*) - COUNT(DISTINCT CONCAT(fips_code, '-', CAST(drop_start_run AS STRING))) AS DOUBLE)
    FROM gold_feed_dropouts
    UNION ALL
    SELECT 'gold_outage_events: duplicate or NULL event_id',
           CAST(COUNT(*) - COUNT(DISTINCT event_id) + COUNT_IF(event_id IS NULL OR fips_code IS NULL) AS DOUBLE)
    FROM gold_outage_events
    UNION ALL
    SELECT 'gold_event_storm_match: duplicate or NULL event_id',
           CAST(COUNT(*) - COUNT(DISTINCT event_id) + COUNT_IF(event_id IS NULL) AS DOUBLE)
    FROM gold_event_storm_match
    UNION ALL
    SELECT 'gold_state_coverage: duplicate or NULL state_abbr',
           CAST(COUNT(*) - COUNT(DISTINCT state_abbr) + COUNT_IF(state_abbr IS NULL) AS DOUBLE)
    FROM gold_state_coverage
    UNION ALL
    SELECT 'gold_unit_reliability: duplicate or NULL (year, fips_code)',
           CAST(COUNT(*) - COUNT(DISTINCT CONCAT(CAST(year AS STRING), '-', fips_code)) + COUNT_IF(year IS NULL OR fips_code IS NULL) AS DOUBLE)
    FROM gold_unit_reliability
    UNION ALL
    SELECT 'gold_county_reliability: duplicate or NULL (year, fips_code)',
           CAST(COUNT(*) - COUNT(DISTINCT CONCAT(CAST(year AS STRING), '-', fips_code)) + COUNT_IF(year IS NULL OR fips_code IS NULL) AS DOUBLE)
    FROM gold_county_reliability
    UNION ALL
    SELECT 'gold_state_reliability: duplicate or NULL (year, state_abbr)',
           CAST(COUNT(*) - COUNT(DISTINCT CONCAT(CAST(year AS STRING), '-', state_abbr)) + COUNT_IF(year IS NULL OR state_abbr IS NULL) AS DOUBLE)
    FROM gold_state_reliability
    UNION ALL
    SELECT 'gold_utility_reliability: duplicate (data_year, utility_number, state_abbr)',
           CAST(COUNT(*) - COUNT(DISTINCT CONCAT(CAST(data_year AS STRING), '-', utility_number, '-', state_abbr)) AS DOUBLE)
    FROM gold_utility_reliability
    UNION ALL
    SELECT 'gold_oe417_check: duplicate or NULL incident_id',
           CAST(COUNT(*) - COUNT(DISTINCT incident_id) + COUNT_IF(incident_id IS NULL) AS DOUBLE)
    FROM gold_oe417_check
)
SELECT 'gold' AS layer, check_name, observed, '0' AS expected, observed = 0 AS passed FROM checks;

-- Valid values: positive durations, shares between 0 and 1, the event and dropout rules hold.
WITH
checks AS (
    SELECT 'gold_outage_events: duration_hours <= 0 or reading_count <= 0' AS check_name,
           CAST(COUNT_IF(duration_hours <= 0 OR reading_count <= 0 OR event_end <= event_start) AS DOUBLE) AS observed
    FROM gold_outage_events
    UNION ALL
    SELECT 'gold_outage_events: customer-hours negative or capped above raw (D4)',
           CAST(COUNT_IF(customer_hours_lost < 0 OR customer_hours_lost > customer_hours_lost_raw * (1 + ${quality.float_tolerance})) AS DOUBLE)
    FROM gold_outage_events
    UNION ALL
    SELECT 'gold_outage_events: peak below the event threshold (D18)',
           CAST(COUNT_IF(peak_customers_out < event_threshold) AS DOUBLE)
    FROM gold_outage_events
    UNION ALL
    SELECT 'gold_outage_events: event_year outside config years', CAST(COUNT_IF(event_year NOT IN (${years.sql})) AS DOUBLE)
    FROM gold_outage_events
    UNION ALL
    SELECT 'gold_event_thresholds: threshold below events.min_customers_out (D18)',
           CAST(COUNT_IF(event_threshold < ${events.min_customers_out}) AS DOUBLE)
    FROM gold_event_thresholds
    UNION ALL
    SELECT 'gold_event_thresholds: a threshold reaches events.large_outage_customers (D18)',
           CAST(COUNT_IF(event_threshold >= ${events.large_outage_customers}) AS DOUBLE)
    FROM gold_event_thresholds
    UNION ALL
    SELECT 'gold_feed_dropouts: outside the D19 rule',
           CAST(COUNT_IF(dropout_runs < 1 OR dropout_runs > ${dropouts.recovery_max_runs}
                         OR dropped_customers_out >= ${dropouts.drop_below_share} * pre_drop_customers_out
                         OR recovery_customers_out < ${dropouts.recovery_share} * pre_drop_customers_out) AS DOUBLE)
    FROM gold_feed_dropouts
    UNION ALL
    SELECT 'gold_state_coverage: customer_coverage outside [0, 1] (D22)',
           CAST(COUNT_IF(customer_coverage < 0 OR customer_coverage > 1) AS DOUBLE)
    FROM gold_state_coverage
    UNION ALL
    SELECT 'gold_state_coverage: eligible with unknown coverage, or status inconsistent (D52)',
           CAST(COUNT_IF((customer_coverage IS NULL) <> (coverage_status = 'coverage_unknown')
                         OR (ranking_eligible AND coverage_status <> 'covered')) AS DOUBLE)
    FROM gold_state_coverage
    UNION ALL
    SELECT 'gold_state_reliability: ranked state with unknown coverage (D52)',
           CAST(COUNT_IF(national_rank IS NOT NULL AND (customer_coverage IS NULL OR footnote_reason IS NOT NULL)) AS DOUBLE)
    FROM gold_state_reliability
    UNION ALL
    SELECT 'gold_county_reliability: capped_share outside [0, 1] (D45)',
           CAST(COUNT_IF(capped_share < 0 OR capped_share > 1 + ${quality.float_tolerance}) AS DOUBLE)
    FROM gold_county_reliability
    UNION ALL
    SELECT 'gold_county_reliability: negative outage hours per 1,000',
           CAST(COUNT_IF(outage_hours_per_1000_customers < 0 OR customer_hours_lost < 0) AS DOUBLE)
    FROM gold_county_reliability
    UNION ALL
    SELECT 'gold_event_storm_match: matched storm with no overlap (D37)',
           CAST(COUNT_IF(storm_type <> 'unmatched' AND (overlap_hours IS NULL OR overlap_hours <= 0)) AS DOUBLE)
    FROM gold_event_storm_match
    UNION ALL
    SELECT 'gold_utility_reliability: ranked row that is flagged or out of band (D39)',
           CAST(COUNT_IF(rank_saidi_without_med IS NOT NULL AND (data_quality_flag IS NOT NULL OR size_band = 'unknown')) AS DOUBLE)
    FROM gold_utility_reliability
)
SELECT 'gold' AS layer, check_name, observed, '0' AS expected, observed = 0 AS passed FROM checks;

-- Events of one county never overlap, so a reading can belong to at most one of them.
WITH
-- The previous event's end for each event of the same county.
ordered AS (
    SELECT event_start, LAG(event_end) OVER (PARTITION BY fips_code ORDER BY event_start) AS previous_end
    FROM gold_outage_events
)
SELECT
    'gold' AS layer,
    'gold_outage_events: overlapping events in a county' AS check_name,
    CAST(COUNT_IF(previous_end > event_start) AS DOUBLE) AS observed,
    '0' AS expected,
    COUNT_IF(previous_end > event_start) = 0 AS passed
FROM ordered;

-- Every qualifying reading lies in exactly one event (D17-D19): it falls inside the latest event
-- that started at or before it, and the event reading counts add up to the qualifying readings.
WITH
-- Runs of each county's feed dropouts; those readings were not measured and qualify for nothing (D19).
dropout_runs_all AS (
    SELECT fips_code, EXPLODE(SEQUENCE(drop_start_run, recovery_run - 1)) AS run_index
    FROM gold_feed_dropouts
),
dropout_runs AS (
    SELECT DISTINCT fips_code, run_index FROM dropout_runs_all
),
-- Readings at or above the county threshold outside dropouts, as in 03_gold_events.sql.
qualifying AS (
    SELECT s.fips_code, s.reading_time
    FROM silver_outages AS s
    INNER JOIN gold_collection_runs AS r ON r.slot_time = s.reading_time
    LEFT JOIN gold_event_thresholds AS t ON t.fips_code = s.fips_code
    LEFT JOIN dropout_runs AS d ON d.fips_code = s.fips_code AND d.run_index = r.run_index
    WHERE s.customers_out >= COALESCE(t.event_threshold, ${events.min_customers_out})
      AND d.run_index IS NULL
),
-- Event starts and readings on one timeline per county; an event start sorts before a reading
-- at the same time.
timeline AS (
    SELECT fips_code, reading_time AS t, CAST(NULL AS TIMESTAMP) AS event_start, 1 AS is_reading FROM qualifying
    UNION ALL
    SELECT fips_code, event_start AS t, event_start, 0 FROM gold_outage_events
),
-- Event starts only increase in time, so a running MAX gives the latest event start so far.
carried AS (
    SELECT
        fips_code,
        t,
        is_reading,
        MAX(event_start) OVER (PARTITION BY fips_code ORDER BY t, is_reading
                               ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS latest_start
    FROM timeline
),
-- Each reading with the end of that event; a reading outside it belongs to no event.
assigned AS (
    SELECT c.t, e.event_end
    FROM carried AS c
    LEFT JOIN gold_outage_events AS e ON e.fips_code = c.fips_code AND e.event_start = c.latest_start
    WHERE c.is_reading = 1
),
totals AS (
    SELECT
        COUNT_IF(event_end IS NULL OR t >= event_end)            AS outside_event,
        COUNT(*)                                                 AS qualifying_readings,
        (SELECT SUM(e.reading_count) FROM gold_outage_events AS e) AS event_readings
    FROM assigned
)
SELECT 'gold' AS layer, 'qualifying reading outside every event (D17)' AS check_name,
       CAST(outside_event AS DOUBLE) AS observed, '0' AS expected, outside_event = 0 AS passed
FROM totals
UNION ALL
SELECT 'gold', 'qualifying readings minus event reading counts (D17)',
       CAST(qualifying_readings - event_readings AS DOUBLE), '0', qualifying_readings = event_readings
FROM totals;

-- Rankings hold only the 50 states and DC (D43, D44).
WITH
-- The ranked jurisdictions: every non-territory in the region lookup.
jurisdictions AS (
    SELECT state_abbr FROM bronze_state_regions WHERE census_region <> 'Territory'
),
checks AS (
    SELECT 'gold_state_reliability: ranked row outside the 50 states and DC' AS check_name, CAST(COUNT(*) AS DOUBLE) AS observed
    FROM gold_state_reliability AS s
    LEFT JOIN jurisdictions AS j ON j.state_abbr = s.state_abbr
    WHERE s.national_rank IS NOT NULL AND j.state_abbr IS NULL
    UNION ALL
    SELECT 'gold_state_reliability: more ranked states than jurisdictions in a year',
           CAST(COUNT_IF(ranked > ${ranking.ranked_jurisdictions}) AS DOUBLE)
    FROM (SELECT year, COUNT(DISTINCT state_abbr) AS ranked FROM gold_state_reliability
          WHERE national_rank IS NOT NULL GROUP BY year) AS y
    UNION ALL
    SELECT 'gold_county_reliability: ranked county outside the 50 states and DC', CAST(COUNT(*) AS DOUBLE)
    FROM gold_county_reliability AS c
    LEFT JOIN jurisdictions AS j ON j.state_abbr = c.state_abbr
    WHERE c.national_rank IS NOT NULL AND j.state_abbr IS NULL
    UNION ALL
    SELECT 'gold_county_reliability: ranked county under ranking.min_customers (D11)',
           CAST(COUNT_IF(national_rank IS NOT NULL AND (customers IS NULL OR customers < ${ranking.min_customers})) AS DOUBLE)
    FROM gold_county_reliability
)
SELECT 'gold' AS layer, check_name, observed, '0' AS expected, observed = 0 AS passed FROM checks;

-- Every footnoted county-year has a reason, and the footnote list matches the unranked rows (D45, D46).
WITH
checks AS (
    SELECT 'gold_county_reliability: unranked row without a footnote reason' AS check_name,
           CAST(COUNT_IF((NOT ranking_eligible OR national_rank IS NULL) AND footnote_reason IS NULL) AS DOUBLE) AS observed
    FROM gold_county_reliability
    UNION ALL
    SELECT 'gold_county_reliability: ranked row with a footnote reason',
           CAST(COUNT_IF(national_rank IS NOT NULL AND footnote_reason IS NOT NULL) AS DOUBLE)
    FROM gold_county_reliability
    UNION ALL
    SELECT 'gold_county_ranking_footnotes: row without reason, or D45/D46 row without evidence',
           CAST(COUNT_IF(footnote_reason IS NULL
                         OR ((footnote_reason LIKE '%(D45)%' OR footnote_reason LIKE '%(D46)%') AND footnote_evidence IS NULL)) AS DOUBLE)
    FROM gold_county_ranking_footnotes
    UNION ALL
    SELECT 'gold_county_ranking_footnotes: rows differ from unranked county-years',
           CAST(ABS((SELECT COUNT(*) FROM gold_county_ranking_footnotes)
                    - (SELECT COUNT_IF(NOT ranking_eligible) FROM gold_county_reliability)) AS DOUBLE)
    UNION ALL
    SELECT 'gold_county_ranking_footnotes: D45 row not meeting both footnotes thresholds',
           CAST(COUNT_IF(footnote_reason LIKE '%(D45)%'
                         AND NOT (capped_share > ${footnotes.capped_share} AND peak_to_customers > ${footnotes.peak_to_customers})) AS DOUBLE)
    FROM gold_county_ranking_footnotes
)
SELECT 'gold' AS layer, check_name, observed, '0' AS expected, observed = 0 AS passed FROM checks;

-- Referential integrity between Gold facts and their dimensions.
WITH
checks AS (
    SELECT 'gold_outage_events: fips_code missing from dim_county_customers' AS check_name, CAST(COUNT(*) AS DOUBLE) AS observed
    FROM gold_outage_events AS e
    LEFT JOIN dim_county_customers AS d ON d.fips_code = e.fips_code
    WHERE d.fips_code IS NULL
    UNION ALL
    SELECT 'gold_outage_events: state_abbr missing from bronze_state_regions', CAST(COUNT(*) AS DOUBLE)
    FROM gold_outage_events AS e
    LEFT JOIN bronze_state_regions AS r ON r.state_abbr = e.state_abbr
    WHERE r.state_abbr IS NULL
    UNION ALL
    SELECT 'gold_event_storm_match: event_id missing from gold_outage_events', CAST(COUNT(*) AS DOUBLE)
    FROM gold_event_storm_match AS m
    LEFT JOIN gold_outage_events AS e ON e.event_id = m.event_id
    WHERE e.event_id IS NULL
    UNION ALL
    SELECT 'gold_event_storm_match: storm missing from silver_storm_events', CAST(COUNT(*) AS DOUBLE)
    FROM gold_event_storm_match AS m
    LEFT JOIN silver_storm_events AS s ON s.event_id = m.storm_event_id AND s.fips_code = m.fips_code
    WHERE m.storm_event_id IS NOT NULL AND s.event_id IS NULL
    UNION ALL
    SELECT 'gold_unit_reliability: fips_code missing from dim_county_customers', CAST(COUNT(*) AS DOUBLE)
    FROM gold_unit_reliability AS u
    LEFT JOIN dim_county_customers AS d ON d.fips_code = u.fips_code
    WHERE d.fips_code IS NULL
    UNION ALL
    SELECT 'gold_county_ranking_footnotes: county-year missing from gold_county_reliability', CAST(COUNT(*) AS DOUBLE)
    FROM gold_county_ranking_footnotes AS f
    LEFT JOIN gold_county_reliability AS c ON c.year = f.year AND c.fips_code = f.fips_code
    WHERE c.fips_code IS NULL
    UNION ALL
    SELECT 'gold_state_reliability: state missing from gold_state_coverage', CAST(COUNT(*) AS DOUBLE)
    FROM gold_state_reliability AS s
    LEFT JOIN gold_state_coverage AS c ON c.state_abbr = s.state_abbr
    WHERE c.state_abbr IS NULL
    UNION ALL
    SELECT 'gold_oe417_check: incident or closest event missing', CAST(COUNT(*) AS DOUBLE)
    FROM gold_oe417_check AS k
    LEFT JOIN silver_oe417 AS o ON o.incident_id = k.incident_id
    LEFT JOIN gold_outage_events AS e ON e.event_id = k.closest_event_id
    WHERE o.incident_id IS NULL OR (k.closest_event_id IS NOT NULL AND e.event_id IS NULL)
)
SELECT 'gold' AS layer, check_name, observed, '0' AS expected, observed = 0 AS passed FROM checks;
