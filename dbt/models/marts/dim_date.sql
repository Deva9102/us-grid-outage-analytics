-- One row per calendar day from date_spine_start to date_spine_end (exclusive). Events join on
-- the date they start (event_date), because an event counts in the year it starts.
WITH
-- dbt's portable date spine: the same SQL on Databricks, DuckDB and Snowflake.
days AS (
    {{ dbt.date_spine(
        "day",
        "CAST('" ~ var('date_spine_start') ~ "' AS DATE)",
        "CAST('" ~ var('date_spine_end') ~ "' AS DATE)"
    ) }}
),
-- The spine returns a timestamp on some engines; the dimension key is a plain date.
dated AS (
    SELECT CAST(date_day AS DATE) AS date_day FROM days
)
SELECT
    date_day,
    CAST(EXTRACT(YEAR FROM date_day) * 10000 + EXTRACT(MONTH FROM date_day) * 100
         + EXTRACT(DAY FROM date_day) AS {{ dbt.type_int() }})              AS date_key,
    CAST(EXTRACT(YEAR FROM date_day) AS {{ dbt.type_int() }})              AS year,
    CAST(EXTRACT(QUARTER FROM date_day) AS {{ dbt.type_int() }})           AS quarter,
    CAST(EXTRACT(MONTH FROM date_day) AS {{ dbt.type_int() }})             AS month,
    CAST(EXTRACT(DAY FROM date_day) AS {{ dbt.type_int() }})               AS day_of_month,
    CAST({{ dbt.date_trunc('month', 'date_day') }} AS DATE)                 AS month_start
FROM dated
