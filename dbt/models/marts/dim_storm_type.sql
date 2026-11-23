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
),
-- Every event type with its severity, then the analysis group (D68): the storm families the
-- questions compare. Cold-weather types sit with winter storms, heat apart from them.
typed AS (
    SELECT * FROM severity
    UNION ALL
    SELECT * FROM unmatched
)
SELECT
    storm_type,
    severity_rank,
    storm_tier,
    can_cause_outage,
    CASE
        WHEN storm_tier = 'tropical_cyclone'                          THEN 'Hurricane / tropical'
        WHEN storm_tier = 'ice_snow'
          OR storm_type IN ('Winter Weather', 'Cold/Wind Chill',
                            'Extreme Cold/Wind Chill')                THEN 'Winter weather'
        WHEN storm_type = 'Thunderstorm Wind'                         THEN 'Thunderstorm wind'
        WHEN storm_tier = 'wind'                                      THEN 'Other wind'
        WHEN storm_tier = 'tornado'                                   THEN 'Tornado'
        WHEN storm_tier = 'wildfire'                                  THEN 'Wildfire'
        WHEN storm_type IN ('Excessive Heat', 'Heat')                 THEN 'Heat'
        WHEN storm_tier = 'flood'                                     THEN 'Flood'
        WHEN storm_tier = 'unmatched'                                 THEN 'No storm matched'
        ELSE 'Other'
    END AS storm_group
FROM typed
