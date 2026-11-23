<!-- Written by scripts/data_dictionary.py from the dbt docs; edit dbt/models/*.yml, not this file. -->
# Data dictionary: dbt marts

Every table and column of the star schema in `dbt/` (D66), with the type the warehouse reports (databricks), its meaning and where it comes from. The marts are tables in `workspace.outages`; they reshape the Gold tables and never recompute a metric. Rule numbers (D-numbers) refer to `docs/decisions.md`. An event counts in the year it starts.

| Table | Grain | Rows from |
|---|---|---|
| [`fct_county_coverage`](#fct_county_coverage) | One row per county and year in which EAGLE-I reports the county (D67). | `silver_outages`, `dim_county` |
| [`fct_county_reliability`](#fct_county_reliability) | Outage hours per 1,000 customers per county and year for the 50 states and DC, ranked nationally and within the state (D38, D44). | `gold_county_reliability` |
| [`fct_data_quality_index`](#fct_data_quality_index) | EAGLE-I's data quality index per FEMA region and year (DQI.csv, D67), 2018-2022 only. | `silver_eaglei_dqi` |
| [`fct_outage_events`](#fct_outage_events) | One row per county outage event: readings at or above the county's threshold, a gap of more than 1 hour of active runs starts a new event (D17, D18). | `gold_event_storm_match`, `gold_outage_events` |
| [`fct_published_coverage`](#fct_published_coverage) | EAGLE-I's published customer coverage per state and year (coverage_history.csv, D67), 2018-2022 only. | `silver_eaglei_coverage_history` |
| [`fct_state_reliability`](#fct_state_reliability) | Outage hours per 1,000 customers per state and year for the 50 states and DC, ranked nationally and within the Census region (D38, D43). | `gold_state_reliability` |
| [`fct_territory_reliability`](#fct_territory_reliability) | Puerto Rico and the US Virgin Islands per year, same metrics as the states, never ranked (D43). | `gold_territory_reliability` |
| [`fct_utility_reliability`](#fct_utility_reliability) | EIA-861 SAIDI and SAIFI per utility, state and year, with and without major event days. | `gold_utility_reliability`, `gold_utility_reliability_other` |
| [`dim_county`](#dim_county) | One row per county or reporting unit with a customer denominator (D13), including PR PREPA regions, VI districts and Connecticut's planning regions (D60). | `dim_county_customers`, `silver_outages`, `bronze_state_regions` |
| [`dim_date`](#dim_date) | One row per calendar day of the configured years. | a date spine, no upstream table |
| [`dim_state`](#dim_state) | One row per state, DC and territory (53). | `bronze_state_regions`, `gold_state_coverage` |
| [`dim_storm_type`](#dim_storm_type) | One row per NOAA event type, with the severity rank and tier the storm attribution uses (D41), plus 'unmatched' for events with no storm (D37). | `bronze_storm_event_severity` |
| [`dim_utility`](#dim_utility) | One row per EIA-861 utility number with its newest name and ownership (D32) and its parent company (D39). | `silver_utility_reliability`, `gold_utility_reliability` |
| [`dim_year`](#dim_year) | One row per year any mart reports, 2018-2025 (D70). | `dim_date`, `fct_published_coverage` |

## fct_county_coverage

One row per county and year in which EAGLE-I reports the county (D67). EAGLE-I publishes coverage only up to 2022, so this is the coverage measure for every year: which counties report and the customers they hold. Year-over-year comparisons use counties that report in every year, so coverage growth is never read as outage growth.

| Column | Type | Meaning | Source |
|---|---|---|---|
| `county_year_key` | string | <fips_code>-<year> (primary key). | computed in `fct_county_coverage.sql` |
| `fips_code` | string | County FIPS. | `silver_outages.fips_code` |
| `state_abbr` | string | 2-letter state code. | `silver_outages.state_abbr` |
| `year` | integer | Calendar year of the readings. | `silver_outages.year` |
| `readings` | bigint | 15-minute readings in the year. EAGLE-I has a row only when customers are out (D3), so this measures activity, not hours of coverage. | computed in `fct_county_coverage.sql` |
| `first_reading` | timestamp | First reading of the year, UTC. | computed in `fct_county_coverage.sql` |
| `last_reading` | timestamp | Last reading of the year, UTC. | computed in `fct_county_coverage.sql` |
| `customers` | bigint | County denominator (D13); NULL when none (D9). | `dim_county.customers` |

## fct_county_reliability

Outage hours per 1,000 customers per county and year for the 50 states and DC, ranked nationally and within the state (D38, D44). A county has rows from its first reported year (D61); events count in the year they start. Unranked rows carry the footnote reason.

| Column | Type | Meaning | Source |
|---|---|---|---|
| `county_year_key` | string | <fips_code>-<year> (primary key). | computed in `fct_county_reliability.sql` |
| `fips_code` | string | County FIPS. | `gold_county_reliability.fips_code` |
| `state_abbr` | string | 2-letter state code. | `gold_county_reliability.state_abbr` |
| `year` | integer | Calendar year (events count in the year they start). | `gold_county_reliability.year` |
| `customers` | bigint | County denominator (D13). | `gold_county_reliability.customers` |
| `events` | bigint | Events starting in the year. | `gold_county_reliability.events` |
| `customer_hours_lost` | double | Capped customer-hours of those events (D4). | `gold_county_reliability.customer_hours_lost` |
| `max_peak_customers_out` | bigint | Highest event peak in the year. | `gold_county_reliability.max_peak_customers_out` |
| `outage_hours_per_1000_customers` | double | customer_hours_lost per 1,000 customers, the ranking measure (D38). | `gold_county_reliability.outage_hours_per_1000_customers` |
| `capped_customer_hours` | double | Customer-hours removed by the D4 cap. | `gold_county_reliability.capped_customer_hours` |
| `capped_share` | double | Share of raw customer-hours removed by the cap (D45). | `gold_county_reliability.capped_share` |
| `peak_to_customers` | decimal(38,16) | Highest reading over the denominator (D45). | `gold_county_reliability.peak_to_customers` |
| `ranking_eligible` | boolean | Denominator of at least 1,000 customers (D11). | `gold_county_reliability.ranking_eligible` |
| `is_ranked` | boolean | The row has a national rank. | computed in `fct_county_reliability.sql` |
| `national_rank` | integer | Rank among ranked counties in the year, 1 = most outage hours. | `gold_county_reliability.national_rank` |
| `state_rank` | integer | Rank within the state. | `gold_county_reliability.state_rank` |
| `rank_without_footnotes` | integer | The rank the county would have had without its footnote (D45, D46). | `gold_county_reliability.rank_without_footnotes` |
| `footnote_reason` | string | Why the row is not ranked (D9, D11, D22, D45, D46, D52, D60); NULL when ranked. | `gold_county_reliability.footnote_reason` |
| `footnote_evidence` | string | The numbers behind a D45 or D46 footnote. | `gold_county_reliability.footnote_evidence` |

## fct_data_quality_index

EAGLE-I's data quality index per FEMA region and year (DQI.csv, D67), 2018-2022 only.

| Column | Type | Meaning | Source |
|---|---|---|---|
| `region_year_key` | string | <fema_region>-<year> (primary key). | computed in `fct_data_quality_index.sql` |
| `fema_region` | string | FEMA region I-X (D8). | `silver_eaglei_dqi.fema_region` |
| `year` | integer | Year of the index. | `silver_eaglei_dqi.year` |
| `success_rate_pct` | double | Share of collection attempts that succeeded, in percent. | `silver_eaglei_dqi.success_rate_pct` |
| `percent_enabled` | double | Share of known utilities whose outage feed is collected, in percent. | `silver_eaglei_dqi.percent_enabled` |
| `spatial_precision_pct` | double | Share of customers whose outages are placed at county level, in percent. | `silver_eaglei_dqi.spatial_precision_pct` |
| `customer_coverage_pct` | double | Share of customers covered, in percent. | `silver_eaglei_dqi.customer_coverage_pct` |
| `max_covered` | bigint | Most customers covered during the year. | `silver_eaglei_dqi.max_covered` |
| `total_customers` | bigint | Customers in the region. | `silver_eaglei_dqi.total_customers` |
| `dqi` | double | EAGLE-I data quality index, 0-100. | `silver_eaglei_dqi.dqi` |

## fct_outage_events

One row per county outage event: readings at or above the county's threshold, a gap of more than 1 hour of active runs starts a new event (D17, D18). Event-year convention: an event counts in the year it starts (event_year and event_date from event_start, UTC), also when it runs into the next year, so customer-hours are never split across years (D57, D64). Customer-hours are capped at the county denominator (D4).

| Column | Type | Meaning | Source |
|---|---|---|---|
| `event_id` | string | <fips_code>-<number of the event in its county> (primary key). | `gold_outage_events.event_id` |
| `fips_code` | string | County FIPS. | `gold_outage_events.fips_code` |
| `state_abbr` | string | 2-letter state code. | `gold_outage_events.state_abbr` |
| `event_date` | date | Day the event starts (UTC); joins dim_date. | computed in `fct_outage_events.sql` |
| `event_year` | integer | Year the event starts (UTC). The year an event counts in. | `gold_outage_events.event_year` |
| `event_start` | timestamp | First qualifying reading, UTC. | `gold_outage_events.event_start` |
| `event_end` | timestamp | End of the last qualifying run, UTC (D17). | `gold_outage_events.event_end` |
| `duration_hours` | double | event_end - event_start in hours. | `gold_outage_events.duration_hours` |
| `reading_count` | bigint | Qualifying readings in the event. | `gold_outage_events.reading_count` |
| `peak_customers_out` | bigint | Highest customers out, uncapped (D4). | `gold_outage_events.peak_customers_out` |
| `event_threshold` | double | The county's event threshold, GREATEST(100, 0.25% of customers) (D18). | `gold_outage_events.event_threshold` |
| `customer_hours_lost` | double | Customer-hours, each reading capped at the denominator (D4). | `gold_outage_events.customer_hours_lost` |
| `customer_hours_lost_raw` | double | Customer-hours, uncapped. | `gold_outage_events.customer_hours_lost_raw` |
| `customers` | bigint | County denominator (D13). | `gold_outage_events.customers` |
| `denominator_source` | string | Where the denominator comes from (D13). | `gold_outage_events.denominator_source` |
| `has_denominator` | boolean | False when the county has no denominator (D9). | `gold_outage_events.has_denominator` |
| `ranking_eligible` | boolean | Denominator of at least 1,000 customers (D11). | `gold_outage_events.ranking_eligible` |
| `peak_out_per_1000` | double | Capped peak per 1,000 customers. | `gold_outage_events.peak_out_per_1000` |
| `customer_hours_per_1000` | double | Customer-hours per 1,000 customers. | `gold_outage_events.customer_hours_per_1000` |
| `exceeds_customers` | boolean | Some reading above the denominator (D4). | `gold_outage_events.exceeds_customers` |
| `spans_feed_gap` | boolean | A nationwide feed gap falls inside the event (D10). | `gold_outage_events.spans_feed_gap` |
| `feed_gap_hours` | double | Hours of nationwide feed gap inside the event (D10). | `gold_outage_events.feed_gap_hours` |
| `spans_dropout` | boolean | A county feed dropout falls inside the event (D19). | `gold_outage_events.spans_dropout` |
| `dropout_hours` | double | Hours of dropout inside the event (D19). | `gold_outage_events.dropout_hours` |
| `bridged_empty_hours` | double | Hours of empty readings bridged inside the event (D64); they add no customer-hours. | `gold_outage_events.bridged_empty_hours` |
| `spans_empty_gap` | boolean | The event starts or ends next to an empty run too long to bridge (D64). | `gold_outage_events.spans_empty_gap` |
| `storm_type` | string | NOAA event type attributed to the outage, or 'unmatched' (D37, D41). | `gold_event_storm_match.storm_type` |
| `storm_tier` | string | Tier of the attributed storm; NULL when unmatched. | `gold_event_storm_match.storm_tier` |
| `storm_event_id` | bigint | NOAA event id of the attributed storm. | `gold_event_storm_match.storm_event_id` |
| `storm_begin_utc` | timestamp | Start of the attributed storm, UTC (D29). | `gold_event_storm_match.storm_begin_utc` |
| `storm_end_utc` | timestamp | End of the attributed storm, UTC (D29). | `gold_event_storm_match.storm_end_utc` |
| `overlap_hours` | decimal(27,6) | Hours the storm window overlaps the event (D37, D42). | `gold_event_storm_match.overlap_hours` |
| `attribution_rule` | string | active_at_start (most severe storm active at the start) or largest_overlap (D41). | `gold_event_storm_match.attribution_rule` |
| `most_severe_storm_type` | string | Most severe type among the candidate storms (D41). | `gold_event_storm_match.most_severe_storm_type` |
| `candidate_storms` | bigint | Storms whose window overlapped the event (D37). | `gold_event_storm_match.candidate_storms` |

## fct_published_coverage

EAGLE-I's published customer coverage per state and year (coverage_history.csv, D67), 2018-2022 only. Includes American Samoa, Guam and the Northern Mariana Islands, which have no EAGLE-I counties.

| Column | Type | Meaning | Source |
|---|---|---|---|
| `state_year_key` | string | <state_abbr>-<year> (primary key). | computed in `fct_published_coverage.sql` |
| `state_abbr` | string | 2-letter state or territory code. | `silver_eaglei_coverage_history.state_abbr` |
| `year` | integer | Year of the published coverage. | `silver_eaglei_coverage_history.year` |
| `total_customers` | bigint | Customers in the state, as EAGLE-I counts them. | `silver_eaglei_coverage_history.total_customers` |
| `min_covered` | bigint | Fewest customers covered by EAGLE-I's collection during the year. | `silver_eaglei_coverage_history.min_covered` |
| `max_covered` | bigint | Most customers covered during the year. | `silver_eaglei_coverage_history.max_covered` |
| `min_share_covered` | double | min_covered / total_customers. | `silver_eaglei_coverage_history.min_share_covered` |
| `max_share_covered` | double | max_covered / total_customers. | `silver_eaglei_coverage_history.max_share_covered` |

## fct_state_reliability

Outage hours per 1,000 customers per state and year for the 50 states and DC, ranked nationally and within the Census region (D38, D43). Events count in the year they start.

| Column | Type | Meaning | Source |
|---|---|---|---|
| `state_year_key` | string | <state_abbr>-<year> (primary key). | computed in `fct_state_reliability.sql` |
| `state_abbr` | string | 2-letter state code. | `gold_state_reliability.state_abbr` |
| `year` | integer | Calendar year. | `gold_state_reliability.year` |
| `events` | bigint | Events starting in the year in the state's counties. | `gold_state_reliability.events` |
| `customer_hours_lost` | double | Capped customer-hours of those events (D4). | `gold_state_reliability.customer_hours_lost` |
| `customers` | bigint | Sum of the county denominators (D13). | `gold_state_reliability.customers` |
| `outage_hours_per_1000_customers` | double | customer_hours_lost per 1,000 customers, the ranking measure (D38). | `gold_state_reliability.outage_hours_per_1000_customers` |
| `eaglei_counties` | bigint | Counties EAGLE-I reports in the state (D22). | `gold_state_reliability.eaglei_counties` |
| `total_counties` | bigint | Counties in the state (D22). | `gold_state_reliability.total_counties` |
| `customer_coverage` | double | EAGLE-I share of EIA-861 customers (D22). | `gold_state_reliability.customer_coverage` |
| `ranking_eligible` | boolean | Coverage allows a rank (D22, D52). | `gold_state_reliability.ranking_eligible` |
| `is_ranked` | boolean | The row has a national rank. | computed in `fct_state_reliability.sql` |
| `national_rank` | integer | Rank among ranked states in the year, 1 = most outage hours. | `gold_state_reliability.national_rank` |
| `region_rank` | integer | Rank within the Census region. | `gold_state_reliability.region_rank` |
| `footnote_reason` | string | Why the row is not ranked (D22, D52, D60); NULL when ranked. | `gold_state_reliability.footnote_reason` |

## fct_territory_reliability

Puerto Rico and the US Virgin Islands per year, same metrics as the states, never ranked (D43). Puerto Rico's units are PREPA's seven operating regions (D22).

| Column | Type | Meaning | Source |
|---|---|---|---|
| `territory_year_key` | string | <state_abbr>-<year> (primary key). | computed in `fct_territory_reliability.sql` |
| `state_abbr` | string | PR or VI. | `gold_territory_reliability.state_abbr` |
| `year` | integer | Calendar year. | `gold_territory_reliability.year` |
| `events` | bigint | Events starting in the year. | `gold_territory_reliability.events` |
| `customer_hours_lost` | double | Capped customer-hours (D4). | `gold_territory_reliability.customer_hours_lost` |
| `customers` | bigint | Sum of the reporting units' denominators. | `gold_territory_reliability.customers` |
| `outage_hours_per_1000_customers` | double | customer_hours_lost per 1,000 customers. | `gold_territory_reliability.outage_hours_per_1000_customers` |
| `reporting_units` | bigint | EAGLE-I reporting units in the territory. | `gold_territory_reliability.reporting_units` |
| `customer_coverage` | double | EAGLE-I share of EIA-861 customers, where known. | `gold_territory_reliability.customer_coverage` |
| `geography_note` | string | What the reporting units are (D43, D44). | `gold_territory_reliability.geography_note` |

## fct_utility_reliability

EIA-861 SAIDI and SAIFI per utility, state and year, with and without major event days. IEEE 1366 reporters are ranked within size band and year, 1 = most reliable (D39); utilities on another standard are in reporting_group 'other standard' and never ranked (D23). Reliability rows with no reported standard are in neither group.

| Column | Type | Meaning | Source |
|---|---|---|---|
| `utility_report_key` | string | <data_year>-<utility_number>-<state_abbr> (primary key). | computed in `fct_utility_reliability.sql` |
| `data_year` | integer | EIA-861 data year. | `gold_utility_reliability.data_year` |
| `utility_number` | string | EIA utility number. | `gold_utility_reliability.utility_number` |
| `state_abbr` | string | State of the report. EIA-861 also covers American Samoa (AS), Guam (GU) and the Northern Mariana Islands (MP), which EAGLE-I and dim_state do not; their 9 rows are kept here and left out of the relationship test (D66). | `gold_utility_reliability.state_abbr` |
| `reporting_group` | string | IEEE 1366 (ranked) or other standard (never ranked). | computed in `fct_utility_reliability.sql` |
| `size_band` | string | Customer size band the ranks are computed in (D32, D39). | `gold_utility_reliability.size_band` |
| `customers` | bigint | Customers served in the state (EIA-861). | `gold_utility_reliability.customers` |
| `saidi_with_med` | double | SAIDI in minutes, major event days included. | `gold_utility_reliability.saidi_with_med` |
| `saidi_without_med` | double | SAIDI in minutes, major event days excluded. | `gold_utility_reliability.saidi_without_med` |
| `saifi_with_med` | double | SAIFI, interruptions per customer, major event days included. | `gold_utility_reliability.saifi_with_med` |
| `saifi_without_med` | double | SAIFI, major event days excluded. | `gold_utility_reliability.saifi_without_med` |
| `data_quality_flag` | string | Why an IEEE row is not ranked (D39 source-error rule). | `gold_utility_reliability.data_quality_flag` |
| `utilities_in_band` | bigint | Ranked IEEE utilities in the band and year. | `gold_utility_reliability.utilities_in_band` |
| `is_ranked` | boolean | The row has ranks. | computed in `fct_utility_reliability.sql` |
| `rank_saidi_without_med` | bigint | Rank by SAIDI without major event days, 1 = most reliable. | `gold_utility_reliability.rank_saidi_without_med` |
| `rank_saidi_with_med` | bigint | Rank by SAIDI with major event days. | `gold_utility_reliability.rank_saidi_with_med` |
| `rank_saifi_without_med` | bigint | Rank by SAIFI without major event days. | `gold_utility_reliability.rank_saifi_without_med` |
| `rank_saifi_with_med` | bigint | Rank by SAIFI with major event days. | `gold_utility_reliability.rank_saifi_with_med` |

## dim_county

One row per county or reporting unit with a customer denominator (D13), including PR PREPA regions, VI districts and Connecticut's planning regions (D60). Join on fips_code, never on the county name.

| Column | Type | Meaning | Source |
|---|---|---|---|
| `fips_code` | string | 5-digit county FIPS (primary key). | `dim_county_customers.fips_code` |
| `county` | string | County name as EAGLE-I reports it in its newest year. NULL for a county that is in the MCC file but has no reading yet. | `silver_outages.county` |
| `state_abbr` | string | 2-letter state code from the FIPS prefix (D16). | `silver_outages.state_abbr` |
| `state_name` | string | State name. | `bronze_state_regions.state_name` |
| `census_region` | string | Census region, or Territory (D8). | `silver_outages.census_region` |
| `fema_region` | string | FEMA region I-X (D8). | `silver_outages.fema_region` |
| `customers` | bigint | The county's one denominator for all years (D13); NULL when none (D9). | `dim_county_customers.customers` |
| `denominator_source` | string | Where the denominator comes from (D5, D12, D13). | `dim_county_customers.denominator_source` |
| `has_denominator` | boolean | False when the county has no denominator (D9). | computed in `dim_county.sql` |
| `denominator_mismatch` | boolean | MCC and 2024 total_customers differ by more than 2x (D12). | `dim_county_customers.denominator_mismatch` |
| `calibration_factor` | double | Factor applied to this county's denominator (D21, D35). | `dim_county_customers.calibration_factor` |
| `state_calibration_factor` | double | The state's D21 factor (EAGLE-I total over EIA-861 total), 1 when not calibrated. | `dim_county_customers.state_calibration_factor` |
| `is_calibrated` | boolean | The state was calibrated to EIA-861 (D21). | computed in `dim_county.sql` |
| `peak_floor_applied` | boolean | The calibrated denominator was raised to the county's peak customers out (D35). | `dim_county_customers.peak_floor_applied` |
| `peak_floor_skipped` | boolean | The peak was over 1.25x the uncalibrated denominator, so no floor (D36). | `dim_county_customers.peak_floor_skipped` |
| `base_peak_customers_out` | bigint | Highest customers out in the denominator base years 2022-2024, the D35 floor (D58). | computed in `dim_county.sql` |
| `first_reported_year` | integer | First year EAGLE-I reports the county; it has reliability rows from then on (D61). | computed in `dim_county.sql` |

## dim_date

One row per calendar day of the configured years. Facts join on the day an event starts: an event counts in the year it starts (UTC), even when it runs into the next year.

| Column | Type | Meaning | Source |
|---|---|---|---|
| `date_day` | date | Calendar day (primary key). | computed in `dim_date.sql` |
| `date_key` | integer | The day as an integer yyyymmdd, for tools that prefer integer keys. | computed in `dim_date.sql` |
| `year` | integer | Calendar year. | computed in `dim_date.sql` |
| `quarter` | integer | Calendar quarter, 1-4. | computed in `dim_date.sql` |
| `month` | integer | Calendar month, 1-12. | computed in `dim_date.sql` |
| `day_of_month` | integer | Day of the month, 1-31. | computed in `dim_date.sql` |
| `month_start` | date | First day of the month, for monthly roll-ups. | computed in `dim_date.sql` |

## dim_state

One row per state, DC and territory (53). The 50 states and DC are the ranked jurisdictions; Puerto Rico and the US Virgin Islands are reported but never ranked (D43).

| Column | Type | Meaning | Source |
|---|---|---|---|
| `state_abbr` | string | 2-letter state or territory code (primary key). | `bronze_state_regions.state_abbr` |
| `state_fips` | string | 2-digit state FIPS code, the prefix of every county FIPS in the state (D16). | `bronze_state_regions.state_fips` |
| `state_name` | string | State or territory name. | `bronze_state_regions.state_name` |
| `census_region` | string | Census region, or Territory (D8). | `bronze_state_regions.census_region` |
| `census_division` | string | Census division, or Territory (D8). | `bronze_state_regions.census_division` |
| `fema_region` | string | FEMA region I-X (D8). | `bronze_state_regions.fema_region` |
| `is_ranked_jurisdiction` | boolean | True for the 50 states and DC, the only places ranked (D43, D44). | computed in `dim_state.sql` |
| `total_counties` | bigint | Counties or county equivalents in the state (D22). | `gold_state_coverage.total_counties` |
| `eaglei_counties` | bigint | Counties EAGLE-I reports in the state (D22). | `gold_state_coverage.eaglei_counties` |
| `eaglei_customers` | bigint | Customers of the EAGLE-I counties, from the D13 denominators (D22). | `gold_state_coverage.eaglei_customers` |
| `eia_customers` | bigint | EIA-861 customers in the state for calibration.eia_year (D21, D22). | `gold_state_coverage.eia_customers` |
| `customer_coverage` | double | eaglei_customers / eia_customers, capped at 1; NULL when unknown (D22, D52). | `gold_state_coverage.customer_coverage` |
| `coverage_status` | string | covered, below_minimum (under 70%) or coverage_unknown (D22, D52). | `gold_state_coverage.coverage_status` |
| `coverage_ranking_eligible` | boolean | Coverage allows the state to be ranked (D22, D52). Other rules can still footnote a year (D60). | computed in `dim_state.sql` |
| `calibration_factor` | double | Factor applied to the state's county denominators (D21); 1 when not calibrated. | `gold_state_coverage.calibration_factor` |

## dim_storm_type

One row per NOAA event type, with the severity rank and tier the storm attribution uses (D41), plus 'unmatched' for events with no storm (D37).

| Column | Type | Meaning | Source |
|---|---|---|---|
| `storm_type` | string | NOAA event type, or 'unmatched' (primary key). | computed in `dim_storm_type.sql` |
| `severity_rank` | integer | 1 = most severe; ties broken by overlap (D41). NULL for 'unmatched'. | `bronze_storm_event_severity.severity_rank` |
| `storm_tier` | string | Grouping of event types used in the findings. | computed in `dim_storm_type.sql` |
| `can_cause_outage` | boolean | The event type can be matched to an outage (D37). | `bronze_storm_event_severity.can_cause_outage` |
| `storm_group` | string | Storm family the analysis compares (D68): Hurricane / tropical, Winter weather (ice, snow and cold), Thunderstorm wind, Other wind, Tornado, Wildfire, Heat, Flood, Other, or No storm matched. | computed in `dim_storm_type.sql` |

## dim_utility

One row per EIA-861 utility number with its newest name and ownership (D32) and its parent company (D39). Utility reliability comes only from EIA-861, never from EAGLE-I counties (D23).

| Column | Type | Meaning | Source |
|---|---|---|---|
| `utility_number` | string | EIA utility number (primary key). | `silver_utility_reliability.utility_number` |
| `utility_name` | string | Name in the newest report. | `silver_utility_reliability.utility_name` |
| `ownership` | string | Ownership type as EIA reports it. | `silver_utility_reliability.ownership` |
| `parent_company` | string | Parent company where known (D39), e.g. Eversource or National Grid. | `gold_utility_reliability.parent_company` |
| `is_eversource_or_national_grid` | boolean | One of the Eversource or National Grid operating companies compared in question 5 (D39). | `gold_utility_reliability.is_eversource_or_national_grid` |
| `first_year` | integer | First year with a reliability report. | computed in `dim_utility.sql` |
| `last_year` | integer | Newest year with a reliability report. | computed in `dim_utility.sql` |
| `states_reported` | bigint | States the utility reported reliability in. | computed in `dim_utility.sql` |

## dim_year

One row per year any mart reports, 2018-2025 (D70). The year slicer for Power BI: the year-grain facts join here directly and events join through dim_date.

| Column | Type | Meaning | Source |
|---|---|---|---|
| `year` | integer | Calendar year (primary key). | `dim_date.year` |
| `has_readings` | boolean | EAGLE-I readings, and so events and reliability rows, exist for the year. | computed in `dim_year.sql` |
| `has_published_coverage` | boolean | EAGLE-I published coverage and the data quality index exist for the year (D67). | computed in `dim_year.sql` |
