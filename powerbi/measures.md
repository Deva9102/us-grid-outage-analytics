# DAX measures

These measures go into the model described in [data_model.md](data_model.md). I keep them in one
empty table, `_Measures` (Enter data > a table with one blank column, which I then hide). Each
measure answers the same question as a query in `sql/analysis/`, so it can be checked against the
saved results in `docs/analysis_results/`. The check is given under each measure. Slice years with
`dim_year[year]`; an event counts in the year it starts.

## Core measures

### Customer Hours Lost
Total customers out times hours out, summed over the outage events in the filter context.

```dax
Customer Hours Lost =
SUM ( fct_outage_events[customer_hours_lost] )
```
Format: whole number, thousands separator. Check: by year, with
`dim_state[is_ranked_jurisdiction] = TRUE`, it equals `customer_hours_lost` in
`q6_national_trend.csv`.

### Number of Events
How many outage events are in the filter context (gaps and islands: 100+ customers out, a gap of
over an hour starts a new event).

```dax
Number of Events =
COUNTROWS ( fct_outage_events )
```
Check: `events` in `q6_national_trend.csv`, under the same filter as above.

### Median Restoration Hours
Typical event duration, from the first to the last reading at or above the threshold. Half of the
events restore faster than this.

```dax
Median Restoration Hours =
MEDIAN ( fct_outage_events[duration_hours] )
```
Format: 0.0. DAX MEDIAN interpolates like `PERCENTILE_CONT(0.5)` in the queries. Check: by
`dim_storm_type[storm_group]`, `median_hours` in `q4_duration_by_storm.csv`.

### P90 Restoration Hours
The long tail: 9 in 10 events restore within this many hours.

```dax
P90 Restoration Hours =
PERCENTILE.INC ( fct_outage_events[duration_hours], 0.9 )
```
Format: 0.0. Check: `p90_hours` in `q4_duration_by_storm.csv`. The findings focus on events with
10,000+ customers out at the peak; the two large-event variants below reproduce
`large_median_hours` and `large_p90_hours`.

### Outage Hours per 1k Customers
Customer-hours lost per 1,000 customers, the rate I rank places by. It is customer-weighted, so a
region or several years combine correctly.

```dax
Outage Hours per 1k Customers =
DIVIDE (
    SUMX (
        fct_state_reliability,
        fct_state_reliability[outage_hours_per_1000_customers] * fct_state_reliability[customers]
    ),
    SUM ( fct_state_reliability[customers] )
)
```
For one state-year this returns the stored rate. That matters for CT and AK in 2025: their
customer-hours include units without a customer count (D60), which the stored rate leaves out. A
plain `SUM(hours) / SUM(customers)` would overstate them. Over several years the result is per
customer-year. Check: by state for a year, `outage_hours_per_1000` in `q2_state_ranks.csv`. The
county version for the map and county tables is the same formula on `fct_county_reliability`:

```dax
County Outage Hours per 1k Customers =
DIVIDE (
    SUMX (
        fct_county_reliability,
        fct_county_reliability[outage_hours_per_1000_customers] * fct_county_reliability[customers]
    ),
    SUM ( fct_county_reliability[customers] )
)
```

### Matched-to-Storm %
Share of customer-hours from events that a NOAA storm was active over when they started (D37,
D41).

```dax
Matched-to-Storm % =
DIVIDE (
    CALCULATE (
        [Customer Hours Lost],
        KEEPFILTERS ( dim_storm_type[storm_group] <> "No storm matched" )
    ),
    [Customer Hours Lost]
)
```
Format: percentage, 1 decimal. KEEPFILTERS keeps a storm-group slicer working. Check: over all
events it equals 1 minus `share_of_customer_hours` of "No storm matched" in
`q1_storm_share_all.csv`.

### Worst Event
The single event with the most customer-hours in the filter context, as text for a card or a
tooltip.

```dax
Worst Event =
VAR TopEvent =
    TOPN (
        1,
        fct_outage_events,
        fct_outage_events[customer_hours_lost], DESC,
        fct_outage_events[event_id], ASC
    )
RETURN
    MAXX (
        TopEvent,
        RELATED ( dim_county[county] ) & ", " & RELATED ( dim_county[state_abbr] )
            & " (" & FORMAT ( fct_outage_events[event_start], "yyyy-mm-dd" ) & ", "
            & FORMAT ( fct_outage_events[customer_hours_lost] / 1000000, "0.0" )
            & " M customer-hours, " & RELATED ( dim_storm_type[storm_group] ) & ")"
    )
```
The tie-break on `event_id` matches the queries. Check: with no filters it names the first row of
`q1_top20_all_years.csv`, and by year the first row per year of `q1_top20_by_year.csv`.

### YoY Change
Change in customer-hours against the year before, for the year in context.

```dax
YoY Change =
VAR ThisYear = MAX ( dim_year[year] )
VAR CurrentHours = [Customer Hours Lost]
VAR PreviousHours =
    CALCULATE ( [Customer Hours Lost], dim_year[year] = ThisYear - 1 )
RETURN
    IF (
        HASONEVALUE ( dim_year[year] ) && NOT ISBLANK ( PreviousHours ),
        DIVIDE ( CurrentHours - PreviousHours, PreviousHours )
    )
```
Format: +0.0%;-0.0%;0.0%. It is blank for the first reading year (2022). Use the `dim_year` slicer,
not a date range: a date range on `dim_date` would also filter out the previous year. Growth in
customer-hours is only meaningful with the coverage check on page 6 (D67). Check: the ratio of
consecutive `customer_hours_lost` values in `q6_national_trend.csv`, under the same filter as
Customer Hours Lost.

### Utility SAIDI vs Peer Median
A utility's SAIDI without major event days, divided by the median of the ranked IEEE 1366
utilities in its size band and year. 1.00 is the median; below 1 is better than its peers.

```dax
Utility SAIDI vs Peer Median =
VAR ThisYear = SELECTEDVALUE ( fct_utility_reliability[data_year] )
VAR Band = SELECTEDVALUE ( fct_utility_reliability[size_band] )
VAR Own = SELECTEDVALUE ( fct_utility_reliability[saidi_without_med] )
VAR PeerMedian =
    CALCULATE (
        MEDIAN ( fct_utility_reliability[saidi_without_med] ),
        REMOVEFILTERS ( fct_utility_reliability ),
        REMOVEFILTERS ( dim_utility ),
        REMOVEFILTERS ( dim_state ),
        REMOVEFILTERS ( dim_year ),
        fct_utility_reliability[data_year] = ThisYear,
        fct_utility_reliability[size_band] = Band,
        fct_utility_reliability[is_ranked] = TRUE ()
    )
RETURN
    IF (
        HASONEVALUE ( fct_utility_reliability[utility_report_key] ),
        DIVIDE ( Own, PeerMedian )
    )
```
Format: 0.00"x". It is defined per utility, state and year row (one EIA-861 report); a total row
shows blank. Unranked rows (D39 flag, other standard) still get a ratio, but their rank is blank.
Check: `saidi_vs_median` in `q5_eversource_national_grid.csv`.

## Helper measures

```dax
Median Restoration Hours (10k+) =
CALCULATE ( [Median Restoration Hours], KEEPFILTERS ( fct_outage_events[peak_customers_out] >= 10000 ) )

P90 Restoration Hours (10k+) =
CALCULATE ( [P90 Restoration Hours], KEEPFILTERS ( fct_outage_events[peak_customers_out] >= 10000 ) )
```
Restoration of the outages a storm team staffs for. Check: `large_median_hours` and
`large_p90_hours` in `q4_duration_by_storm.csv`, and by region in `q4_duration_by_region.csv`.

```dax
Peer Median SAIDI =
VAR ThisYear = SELECTEDVALUE ( fct_utility_reliability[data_year] )
VAR Band = SELECTEDVALUE ( fct_utility_reliability[size_band] )
RETURN
    CALCULATE (
        MEDIAN ( fct_utility_reliability[saidi_without_med] ),
        REMOVEFILTERS ( fct_utility_reliability ),
        REMOVEFILTERS ( dim_utility ),
        REMOVEFILTERS ( dim_state ),
        REMOVEFILTERS ( dim_year ),
        fct_utility_reliability[data_year] = ThisYear,
        fct_utility_reliability[size_band] = Band,
        fct_utility_reliability[is_ranked] = TRUE ()
    )
```
The band median as a reference line. Check: `band_saidi_median` in `q5_eversource_national_grid.csv`.

```dax
Utility Highlight Color =
IF ( SELECTEDVALUE ( dim_utility[is_eversource_or_national_grid] ), "#EB6834", "#B9B8B2" )
```
Bar colour for conditional formatting (Format > Bars > fx > Field value): orange for Eversource
and National Grid companies, grey for peers. The bars are also labelled with the company name, so
the highlight does not rely on colour alone.

```dax
Reporting Counties =
DISTINCTCOUNT ( fct_county_coverage[fips_code] )

Footnoted Rows =
CALCULATE ( COUNTROWS ( fct_county_reliability ), fct_county_reliability[is_ranked] = FALSE () )
```
Coverage and footnote counts for page 6. Check: `reporting_counties` in `q6_national_trend.csv`
(with the ranked-jurisdiction filter), and the county rows of `q2_footnote_counts.csv`.
