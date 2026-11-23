-- One row per county outage event with its storm attribution, flags and per-1,000 values.
-- An event counts in the year it starts: event_year and event_date come from event_start (UTC),
-- also when the event runs into the next year (D57, D64).
WITH
-- The events as Gold built them (D3, D4, D10, D17-D19, D64).
events AS (
    SELECT * FROM {{ source('outages', 'gold_outage_events') }}
),
-- One storm attribution per event, or 'unmatched' (D37, D41, D42).
storms AS (
    SELECT event_id, storm_type, storm_tier, storm_event_id, storm_begin_utc, storm_end_utc,
           overlap_hours, attribution_rule, most_severe_storm_type, candidate_storms
    FROM {{ source('outages', 'gold_event_storm_match') }}
)
SELECT
    e.event_id,
    e.fips_code,
    e.state_abbr,
    CAST(e.event_start AS DATE)                                  AS event_date,
    e.event_year,
    e.event_start,
    e.event_end,
    CAST(e.duration_hours AS {{ dbt.type_float() }})             AS duration_hours,
    e.reading_count,
    e.peak_customers_out,
    e.event_threshold,
    e.customer_hours_lost,
    e.customer_hours_lost_raw,
    e.customers,
    e.denominator_source,
    e.has_denominator,
    e.ranking_eligible,
    CAST(e.peak_out_per_1000 AS {{ dbt.type_float() }})          AS peak_out_per_1000,
    e.customer_hours_per_1000,
    e.exceeds_customers,
    e.spans_feed_gap,
    CAST(e.feed_gap_hours AS {{ dbt.type_float() }})             AS feed_gap_hours,
    e.spans_dropout,
    CAST(e.dropout_hours AS {{ dbt.type_float() }})              AS dropout_hours,
    CAST(e.bridged_empty_hours AS {{ dbt.type_float() }})        AS bridged_empty_hours,
    e.spans_empty_gap,
    s.storm_type,
    s.storm_tier,
    s.storm_event_id,
    s.storm_begin_utc,
    s.storm_end_utc,
    s.overlap_hours,
    s.attribution_rule,
    s.most_severe_storm_type,
    s.candidate_storms
FROM events AS e
LEFT JOIN storms AS s ON s.event_id = e.event_id
