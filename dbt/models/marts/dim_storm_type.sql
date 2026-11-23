-- One row per NOAA event type, with the severity used to attribute an outage to a storm (D41),
-- plus 'unmatched' for events with no storm (D37).
WITH
-- The severity list is text in Bronze (D14); cast once here.
severity AS (
    SELECT
        event_type                                         AS storm_type,
        CAST(severity_rank AS {{ dbt.type_int() }})        AS severity_rank,
        severity_tier                                      AS storm_tier,
        can_cause_outage = 'Y'                             AS can_cause_outage
    FROM {{ source('outages', 'bronze_storm_event_severity') }}
),
-- Events without a matching storm carry storm_type 'unmatched' in gold_event_storm_match.
unmatched AS (
    SELECT
        'unmatched'                                        AS storm_type,
        CAST(NULL AS {{ dbt.type_int() }})                 AS severity_rank,
        'unmatched'                                        AS storm_tier,
        FALSE                                              AS can_cause_outage
)
SELECT * FROM severity
UNION ALL
SELECT * FROM unmatched
