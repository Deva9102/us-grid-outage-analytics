-- One row per year any mart reports (D70): the year slicer for Power BI. The year-grain facts
-- (reliability, coverage, data quality) join here directly; events join through dim_date.
WITH
-- Years with EAGLE-I readings: the date spine, so every event start year is present.
reading_years AS (
    SELECT DISTINCT year FROM {{ ref('dim_date') }}
),
-- Years EAGLE-I published coverage for (2018-2022), which reach back before the readings (D67).
published_years AS (
    SELECT DISTINCT year FROM {{ ref('fct_published_coverage') }}
),
-- Every year from either list, once.
all_years AS (
    SELECT year FROM reading_years
    UNION
    SELECT year FROM published_years
)
SELECT
    a.year,
    r.year IS NOT NULL                                                    AS has_readings,
    p.year IS NOT NULL                                                    AS has_published_coverage
FROM all_years AS a
LEFT JOIN reading_years AS r ON r.year = a.year
LEFT JOIN published_years AS p ON p.year = a.year
