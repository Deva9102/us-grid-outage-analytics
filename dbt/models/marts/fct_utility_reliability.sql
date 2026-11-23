-- EIA-861 SAIDI and SAIFI per utility, state and year (D23, D39). IEEE 1366 reporters are ranked
-- within size band and year (1 = most reliable); utilities on another standard are kept apart in
-- reporting_group = 'other standard' and never ranked, because the two standards do not compare.
WITH
-- IEEE 1366 reporters, ranked unless flagged as a source error (D39).
ieee AS (
    SELECT
        data_year, utility_number, state_abbr, size_band, customers,
        saidi_with_med, saidi_without_med, saifi_with_med, saifi_without_med,
        'IEEE 1366'                                    AS reporting_group,
        data_quality_flag,
        CAST(utilities_in_band AS {{ dbt.type_bigint() }}) AS utilities_in_band,
        rank_saidi_without_med, rank_saidi_with_med, rank_saifi_without_med, rank_saifi_with_med
    FROM {{ source('outages', 'gold_utility_reliability') }}
),
-- Other-standard reporters: listed with the same metrics, no ranks.
other AS (
    SELECT
        data_year, utility_number, state_abbr, size_band, customers,
        saidi_with_med, saidi_without_med, saifi_with_med, saifi_without_med,
        'other standard'                               AS reporting_group,
        CAST(NULL AS {{ dbt.type_string() }})          AS data_quality_flag,
        CAST(NULL AS {{ dbt.type_bigint() }})          AS utilities_in_band,
        CAST(NULL AS {{ dbt.type_bigint() }})          AS rank_saidi_without_med,
        CAST(NULL AS {{ dbt.type_bigint() }})          AS rank_saidi_with_med,
        CAST(NULL AS {{ dbt.type_bigint() }})          AS rank_saifi_without_med,
        CAST(NULL AS {{ dbt.type_bigint() }})          AS rank_saifi_with_med
    FROM {{ source('outages', 'gold_utility_reliability_other') }}
),
-- Both groups in one table; reporting_group keeps them apart.
combined AS (
    SELECT * FROM ieee
    UNION ALL
    SELECT * FROM other
)
SELECT
    {{ dbt.concat(["CAST(data_year AS " ~ dbt.type_string() ~ ")", "'-'", "utility_number", "'-'", "state_abbr"]) }} AS utility_report_key,
    data_year,
    utility_number,
    state_abbr,
    reporting_group,
    size_band,
    CAST(customers AS {{ dbt.type_bigint() }})          AS customers,
    saidi_with_med,
    saidi_without_med,
    saifi_with_med,
    saifi_without_med,
    data_quality_flag,
    utilities_in_band,
    rank_saidi_without_med IS NOT NULL                  AS is_ranked,
    rank_saidi_without_med,
    rank_saidi_with_med,
    rank_saifi_without_med,
    rank_saifi_with_med
FROM combined
