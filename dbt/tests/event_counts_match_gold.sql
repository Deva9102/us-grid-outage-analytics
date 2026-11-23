-- The event fact is Gold's event table, row for row: same events and customer-hours per year.
WITH
-- Per-year totals of the mart and of its source.
mart AS (
    SELECT event_year, COUNT(*) AS events, SUM(customer_hours_lost) AS customer_hours
    FROM {{ ref('fct_outage_events') }}
    GROUP BY event_year
),
gold AS (
    SELECT event_year, COUNT(*) AS events, SUM(customer_hours_lost) AS customer_hours
    FROM {{ source('outages', 'gold_outage_events') }}
    GROUP BY event_year
)
SELECT g.event_year, g.events, m.events AS mart_events
FROM gold AS g
LEFT JOIN mart AS m ON m.event_year = g.event_year
WHERE m.events IS NULL OR m.events <> g.events OR ABS(m.customer_hours - g.customer_hours) > 0.5
