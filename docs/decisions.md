# Data Cleaning Decisions

Every cleaning decision for the pipeline, with the reason and the rows it touches.
Row counts come from DuckDB runs against the raw EAGLE-I files
(2022: 25,796,465 rows; 2023: 26,101,051; 2024: 27,701,334; 2025: 30,482,141, added
incrementally in D56). See `docs/data_profile.md`.

| # | Decision | Layer | Date |
|---|---|---|---|
| D1 | `run_start_time` is UTC, parse only | Silver | 2026-11-20 |
| D2 | Rename `sum` to `customers_out`; keep `total_customers` | Silver | 2026-11-20 |
| D3 | Missing rows = zero, except nationwide gaps | Gold | 2026-11-20 |
| D4 | Keep raw overcounts, flag them, cap in metrics | Silver / Gold | 2026-11-20 |
| D5 | Denominator: `total_customers`, else MCC | Silver | 2026-11-20 |
| D6 | `fips_code` forced to STRING in Bronze | Bronze | 2026-11-20 |
| D7 | Floor off-grid timestamps; dedupe keeping max | Silver | 2026-11-20 |
| D8 | Add `fema_region`; territories get `census_region = 'Territory'` | Silver | 2026-11-20 |
| D9 | Denominator fallback order and `has_denominator` | Silver / Gold | 2026-11-20 |
| D10 | Flag events that overlap a nationwide feed gap | Gold | 2026-11-20 |
| D11 | Exclude counties under 1,000 customers from per-1,000 rankings | Gold | 2026-11-20 |
| D12 | Use the larger of MCC and 2024 `total_customers` when they differ > 2x | Silver | 2026-11-20 |
| D13 | One denominator per county for all years (`dim_county_customers`) | Silver | 2026-11-20 |
| D14 | Bronze loads every column as STRING; Silver runs in a UTC session | Bronze / Silver | 2026-11-20 |
| D15 | Drop rows whose FIPS, timestamp or customers out cannot be parsed | Silver | 2026-11-20 |
| D16 | State and region attributes come from the state FIPS prefix | Silver | 2026-11-20 |
| D17 | Outage event definition and event metrics | Gold | 2026-11-20 |
| D18 | Event threshold scales with county size: GREATEST(100, 0.25% x customers) | Gold | 2026-11-20 |
| D19 | County feed dropouts cannot end or split an event | Gold | 2026-11-20 |
| D20 | Yearly EAGLE-I files reach Bronze as all-STRING Parquet | Bronze | 2026-11-20 |
| D21 | Calibrate county denominators to EIA-861 state totals above a 1.25 ratio | Silver | 2026-11-21 |
| D22 | Per-state coverage table; states below 70% customer coverage footnoted | Gold | 2026-11-21 |
| D23 | EIA-861 rules: Parts A+C+D, IEEE 1366 rankings, no county-to-utility attribution | Silver / Gold | 2026-11-21 |
| D24 | OE-417 times as local time of the first state; event type mapping file | Silver | 2026-11-21 |
| D25 | OE-417 covers 2022-2023 unless 2024 is added by hand; archive provenance | Bronze | 2026-11-21 |
| D26 | Added-source SQL files numbered by layer; run order | All | 2026-11-21 |
| D27 | Excel sources reach Bronze as raw-row Parquet, cells as text | Bronze | 2026-11-21 |
| D28 | NOAA state code crosswalk (PR 99, VI 96, water areas) | Silver | 2026-11-21 |
| D29 | NOAA times to UTC from the CZ_TIMEZONE offset | Silver | 2026-11-21 |
| D30 | NOAA events placed by county FIPS or the zone file in effect; unplaced counted | Silver | 2026-11-21 |
| D31 | NOAA damage parsed to dollars; event_weight for zone events | Silver | 2026-11-21 |
| D32 | EIA-861 Silver: data rows, reporting standard, customers, size bands | Silver | 2026-11-21 |
| D33 | OE-417 Silver parsing: rows, dates, restoration, area tokens | Silver | 2026-11-21 |
| D34 | OE-417 county names matched to FIPS once, in Silver | Silver | 2026-11-21 |
| D35 | Calibrated denominators never below a county's peak customers out (resolves Q4) | Silver | 2026-11-21 |
| D36 | No peak floor when the peak exceeds 1.25x the uncalibrated denominator (resolves Q5) | Silver | 2026-11-21 |
| D37 | Outage-to-storm match: same county, storm window overlap, causal types, severity ties (resolves Q3) | Gold | 2026-11-21 |
| D38 | State and county outage hours per 1,000 customers, ranked with coverage | Gold | 2026-11-21 |
| D39 | Utility SAIDI/SAIFI ranked within size bands, IEEE 1366 only, parent flags | Gold | 2026-11-21 |
| D40 | OE-417 incidents checked against EAGLE-I at county level | Gold | 2026-11-21 |
| D41 | Storm attribution: most severe storm active at the outage start, else largest overlap (resolves Q6) | Gold | 2026-11-21 |
| D42 | Storm window closes 1 hour after NOAA's end time (resolves Q7) | Gold | 2026-11-21 |
| D43 | State rankings: 50 states and DC; PR and VI reported separately, unranked (resolves Q8) | Gold | 2026-11-21 |
| D44 | County rankings: 50 states and DC; PR and VI reporting units reported separately, unranked | Gold | 2026-11-21 |
| D45 | Footnote county-years with capped share above 25% and peak above 3x customers | Gold | 2026-11-21 |
| D46 | Reviewed ranking exclusions file and entry criteria; Austin TX 2023 stays ranked | Gold | 2026-11-21 |
| D47 | Every tunable value in config/pipeline.yml; SQL reads it through placeholders | All | 2026-11-21 |
| D48 | Quality gates after each layer; results in gold_quality_results; a failed check stops the run | All | 2026-11-21 |
| D49 | Step logging to logs/, Makefile targets, CSV export split by year above 50 MB | All | 2026-11-21 |
| D50 | Gold CSV exports not committed; row counts must match expected exactly | All | 2026-11-21 |
| D51 | Continuous integration: real-data test fixture, pytest, linting | All | 2026-11-22 |
| D52 | States with unknown coverage are not ranked | Gold | 2026-11-22 |
| D53 | One shared SQL statement splitter that ignores semicolons in comments and literals | All | 2026-11-22 |
| D54 | Pipeline as a Databricks Job (Asset Bundle) of SQL tasks with a quality gate after each | All | 2026-11-22 |
| D55 | Gate tasks never retry; quality results kept 90 days | All | 2026-11-22 |
| D56 | Incremental loading: only the new year's Bronze table and Silver partition; events kept + rebuilt | All | 2026-11-22 |
| D57 | Event reprocess window: 7-day lookback, events open at the cut rebuilt whole | Gold | 2026-11-22 |
| D58 | 2025 does not change denominators; base years 2022-2024 | Silver | 2026-11-22 |
| D59 | 2025 sources: EAGLE-I, NOAA, NWS, EIA-861 loaded; OE-417 2024-2025 missing | All | 2026-11-22 |
| D60 | State-years with over 10% of customer-hours without a denominator are not ranked (CT 2025) | Gold | 2026-11-22 |
| D61 | County reliability rows start at the county's first reported year (restatement of 2022-2023 ranks) | Gold | 2026-11-22 |
| D62 | Empty 2025 readings: still dropped; they split the Puerto Rico blackout (Q10, resolved in D64) | Silver / Gold | 2026-11-22 |
| D63 | 2025 is a complete year; no partial-year flag | Gold | 2026-11-22 |
| D64 | Runs of empty readings up to 24 hours inside an outage are bridged like dropouts (resolves Q10) | Silver / Gold | 2026-11-22 |
| D65 | Python 3.13, the newest version every dbt adapter supports | All | 2026-11-22 |
| D66 | dbt star schema over Gold in its own environment; marts must equal Gold exactly | Marts | 2026-11-22 |
| D67 | EAGLE-I coverage history and DQI loaded (2018-2022 only); county-year coverage from the readings | Bronze / Silver / Marts | 2026-11-23 |
| D68 | Analysis layer: queries on the marts only, storm families, numbers in the docs checked against the queries | Analysis | 2026-11-23 |
| D69 | Two portability fixes: DOUBLE instead of FLOAT in the marts, no doubled quote in a Gold literal | Gold / Marts | 2026-11-23 |
| D70 | Power BI handoff: summary marts committed as CSV, events as Parquet on a draft GitHub Release; `dim_year` added | Marts / Export | 2026-11-23 |
| D71 | Restoration forecast: predict at event start + 2 h, eligible if still above threshold then; features known by then only; 2022-2024 train, 2025 test | Gold / Forecast | 2026-11-24 |

---

## D1. Timestamps are UTC

**Status:** Verified.

**What:** Parse `run_start_time` as a UTC timestamp. No timezone conversion is applied.

**Why:** The EAGLE-I data descriptor (Scientific Data, 2024), Data Records section, states that
all data is in UTC and that `run_start_time` marks the start of the collection run. Converting
would shift every reading. Any local-time analysis (for example, hour of day) must convert
explicitly at query time.

**Source:** https://pmc.ncbi.nlm.nih.gov/articles/PMC10915145/ (Data Records section).

**Rows affected:** none changed. All rows in all three years are parsed.

## D2. Unify the customers-out column

**What:** Rename the 2023 column `sum` to `customers_out`. Keep `total_customers` from 2024; it is
NULL for 2022 and 2023, which do not have it.

**Why:** The same measure has two names across years, and a union by column name would
otherwise fail or produce empty values.

**Rows affected:** 26,101,051 (all of 2023) renamed. 2024 `total_customers` is NULL in 73 rows.

## D3. Missing rows and collection gaps

**What:**
- A missing (county, 15-minute) row is treated as zero customers out.
- A timestamp with no rows for any county nationwide is a collection gap, not a zero.
  Gaps must not end or split an outage event: the event logic steps over them.
- An event still ends when a county has no qualifying reading (customers out at or above the
  D18 threshold) for
  more than 1 hour, counting only timestamps that were actually collected.

**Why:** The data descriptor says a missing row is either a true zero or a collection gap,
and the two are not distinguished. Zero is the only workable default for county-level
gaps. But when the whole country is missing at once, the feed was down, and treating that as
zero would split long outages into separate events.

**Rows affected:** rows exist for only 24.1% / 24.4% / 25.8% of county x 15-minute slots
(2022 / 2023 / 2024); the rest are implied zeros. Nationwide gaps, after D7 flooring:

| Year | Gaps | Timestamps (UTC, start of 15-minute run) |
|---|---|---|
| 2022 | 3 | 2022-10-18 23:15; 2022-10-19 00:15, 00:30 |
| 2023 | 16 | 2023-01-08 15:15; 2023-01-25 23:15; 2023-03-13 22:00; 2023-04-20 00:00; 2023-06-07 18:30; 2023-06-11 12:15, 12:30, 12:45, 13:00, 13:15, 13:30; 2023-06-15 19:00; 2023-07-25 14:15; 2023-08-08 10:15; 2023-08-14 18:15; 2023-08-15 10:15 |
| 2024 | 41 | 2024-04-24 18:00; 2024-05-23 01:30, 01:45; 2024-05-24 00:15 through 09:00 (36 consecutive slots, a 9-hour outage of the feed); 2024-10-17 18:30; 2024-12-19 20:00 |

2023 had 17 empty slots before flooring; the off-grid run at 20:31 on 2023-03-22 fills
the 20:30 slot (see D7). Events that overlap any of these gaps are flagged under D10.

## D4. Readings above the county customer count

**What:** Keep `customers_out` exactly as reported. Add a boolean `exceeds_customers`
(`customers_out > customers`, where `customers` is the final denominator in
`dim_county_customers`, D13). Rows without a denominator get `false`. Every per-1,000
metric and customer-hours figure uses `LEAST(customers_out, customers)`.

**Why:** Some utilities report outages that exceed the number of customers in the county,
most likely because a utility's total is assigned to one county. Example: Harris County, TX
(48201) peaked at 1,660,703 out against 1,344,930 customers during Hurricane Beryl on 2024-07-08.
Keeping the raw value keeps the source traceable; capping keeps the rates possible (never above
1,000 per 1,000).

**Rows affected:**

Recounted with the final D13 denominators (DuckDB, full years):

| Year | Rows flagged (final) | Counties (final) | First count (D5 denominator) |
|---|---|---|---|
| 2022 | 1,820 | 22 | 18,933 rows, 145 counties |
| 2023 | 365 | 20 | 12,240 rows, 180 counties |
| 2024 | 8,434 | 67 | 8,441 rows, 68 counties |

The first count compared 2022-2023 against MCC, whose undercounts (D12) made many normal
readings look like overcounts. With one 2024-based denominator per county, 2022 and 2023 drop by
about 90% and 97%. 2024 barely changes: only the 15 counties where MCC is larger (D12) get a
bigger denominator. Of the 10,619 remaining flags, 8,434 (79%) are in 2024. The largest in July
2024 are Texas counties during Hurricane Beryl: Polk (48373), San Jacinto (48407) and Harris (48201).

## D5. Customer denominator

**What:** Use 2024 `total_customers` where present, otherwise MCC customers. The full fallback
order and the handling of counties with neither is in D9; the final per-county rule is D13. When loading `MCC.csv`, pad
`County_FIPS` to 5 digits and drop the non-county `Grand Total` row.

**Why:** `total_customers` is reported with the readings and is the better denominator, but it only
exists in 2024. MCC (modeled county customers) is modeled as of 2022 and covers all years.
MCC stores FIPS as numbers, so codes for states 01-09 lost their leading zero.

**Rows affected:**
- MCC: 312 FIPS codes padded, 1 row (`Grand Total = 154,451,840`) dropped, 3,233 county rows kept.
- Denominator from `total_customers`: 27,701,261 rows (2024).
- Denominator from MCC: 25,721,097 (2022), 26,035,136 (2023), 0 (2024).
- No denominator from either source: 75,368 (2022), 65,915 (2023), 73 (2024). Resolved in D9.

## D6. FIPS codes stored as text in Bronze

**What:** Read `fips_code` with an explicit STRING type in the Databricks Bronze load. Do not rely
on schema inference.

**Why:** Inference can type FIPS as an integer and drop the leading zero for states 01-09,
which breaks every join on FIPS. The raw files have correct 5-character codes in all years
(checked: 0 short codes, 0 non-numeric).

**Rows affected:** all rows; no values change. 291 distinct county codes per year start with 0.

## D7. Off-grid timestamps and duplicate keys

**What:** Floor `run_start_time` to the 15-minute mark. If flooring produces more than one row for
the same (`fips_code`, `run_start_time`), keep the row with the max `customers_out`.

**Why:** Each reading belongs to one 15-minute collection run. A run that started late is still
that run. Keeping the max is conservative for outage counts and avoids double-counting.

**Rows affected:** 819 rows floored, all at 2023-03-22 20:31 to 20:30. Duplicate keys before and
after flooring: 0 in all years, so no rows are removed today. The rule stays in place for
future years.

## D8. FEMA region and territories

**What:** Add `fema_region` (I-X) next to `census_region` and `census_division`. Puerto Rico and
the US Virgin Islands get `fema_region = 'II'` and `census_region = 'Territory'`
(`census_division = 'Territory'`).

**Why:** Census regions do not include territories, but these territories have real outage
history (for example, hurricanes) that should stay in the data. FEMA regions cover them and
match how emergency response is organized.

**Rows affected (`census_region = 'Territory'`):** 276,867 (2022), 254,754 (2023), 276,456 (2024).

FEMA regions:

| Region | States |
|---|---|
| I | CT, ME, MA, NH, RI, VT |
| II | NJ, NY, PR, VI |
| III | DE, DC, MD, PA, VA, WV |
| IV | AL, FL, GA, KY, MS, NC, SC, TN |
| V | IL, IN, MI, MN, OH, WI |
| VI | AR, LA, NM, OK, TX |
| VII | IA, KS, MO, NE |
| VIII | CO, MT, ND, SD, UT, WY |
| IX | AZ, CA, HI, NV |
| X | AK, ID, OR, WA |

## D9. Denominator fallback and counties without one

**Superseded in part by D13.** The per-row order below is replaced by D13's single
per-county denominator. The `has_denominator` rule, the rows-without-denominator handling and the
county findings below still apply. The original order is kept for the record:

| Order | Source | `denominator_source` |
|---|---|---|
| a | the row's own `total_customers` | `total_customers` |
| b | MCC customers for the county | `mcc` |
| c | that county's 2024 `total_customers` | `total_customers_2024` |

D12 overrode this order for counties where MCC and 2024 `total_customers` differ by more than 2x,
and D13 then replaced it entirely with one denominator per county.

If none exist, `customers` is NULL and `has_denominator = false`. Those rows stay in raw totals
(customers out, customer-hours, event counts) but are excluded from every per-1,000 metric.
`LEAST(customers_out, customers)` from D4 applies only where `has_denominator = true`;
rows without a denominator use raw `customers_out` in raw totals.

**Why:** Dropping these rows would lose real outages from the national totals. But a rate
without a trustworthy denominator is worse than no rate. Step (c) uses a reported count for the
same county from the nearest year, which is better than leaving the county out of rankings.
`denominator_source` keeps it auditable which counties rest on a borrowed number.

**Rows affected:** step (c) recovers 8 of the 9 counties that lacked a denominator in 2022 and 2023.
Each has a single constant `total_customers` value in 2024:

| FIPS | County | 2024 `total_customers` |
|---|---|---|
| 06105 | Trinity, CA | 733 |
| 37075 | Graham, NC | 6,493 |
| 37087 | Haywood, NC | 66,709 |
| 37099 | Jackson, NC | 30,036 |
| 37113 | Macon, NC | 30,652 |
| 37173 | Swain, NC | 12,084 |
| 37175 | Transylvania, NC | 27,263 |
| 56031 | Platte, WY | 424 |

Still without a denominator (`has_denominator = false`): 2 counties, 3 county-years, 142 rows.

| FIPS | County | Years | Rows | Reason |
|---|---|---|---|---|
| 51720 | Norton city, VA | 2022, 2023, 2024 | 34 + 35 + 7 | not in MCC; 2024 `total_customers` is NULL in every row |
| 02063 | Chugach Census Area, AK | 2024 | 66 | created in 2019 from Valdez-Cordova (02261), not in MCC; 2024 `total_customers` NULL |

Chugach (02063) and MCC: MCC has no row for 02063 or for its sibling 02066 (Copper River), but it
does have the former Valdez-Cordova Census Area, 02261, with 5,469 customers. So MCC predates the
2019 split. The outage files follow the same change: 2022 and 2023 report the area as
02261 Valdez-Cordova, and 2024 reports 02063 Chugach (02066 does not appear in any year). The 02261
figure covers both successor areas, so it cannot be used for 02063 without a split ratio, and
02063 stays without a denominator. Year-over-year comparisons for this area must treat
02261 (2022-2023) and 02063 (2024) as a break in the series, not as the same county.

Summary of the 9 + 2 counties: step (c) recovers 8 of the 9 (2022-2023) and 0 of the 2 (2024).
Norton city appears in both groups, so 2 distinct counties remain without a denominator.
Rows recovered: 75,334 of 75,368 in 2022 and 65,880 of 65,915 in 2023; none in 2024.

Note: Trinity, CA (733) and Platte, WY (424) are far below their populations, so
`total_customers` likely counts only the utilities EAGLE-I tracks there. Their per-1,000 rates
are computed but should be read with that in mind and never headline a ranking on their own.

## D10. Events that overlap a feed gap

**What:** In Gold, any outage event whose time span overlaps a nationwide collection gap (D3) gets
`spans_feed_gap = true`. Findings report the duration of these events as uncertain, not as
a measured value.

**Why:** Under D3 the event logic steps over gaps instead of ending the event, which is the right
call, but nothing was measured during the gap. The customers out could have dropped to zero and
come back, so the true duration and customer-hours can be shorter than reported. The largest case
is the 9-hour gap on 2024-05-24 (00:15 to 09:00 UTC), where any event running through it could
have its duration overstated by up to 9 hours.

**How:** `gold_collection_runs` lists every 15-minute slot and marks the 60 nationwide gaps from D3
(3 in 2022, 16 in 2023, 41 in 2024; the DuckDB build reproduces these exactly). An event gets
`spans_feed_gap = true` when a gap slot falls strictly between its first and last qualifying
reading, and `feed_gap_hours` = gap slots x 0.25 is the most its duration can be overstated.

**Rows affected (DuckDB, full data, 0.25% threshold with D19):** 46 events in 2022, 704 in 2023,
234 in 2024 have `spans_feed_gap = true`. 33 events span the whole 2024-05-24 gap; they also cover
the two 2024-05-23 gap slots, so their `feed_gap_hours` is 9.5. With the earlier flat threshold of
100 the counts were 86 / 1,167 / 437 and 56 events; longer chained events crossed more gaps (D18).

Limitation: an event that ends just before a gap may really have continued through it. Those
events are not flagged, because nothing in the data shows they continued.

## D11. Minimum denominator for rankings

**What:** Counties whose denominator (`customers` in `dim_county_customers`, D13) is below 1,000
are excluded from every per-1,000 ranking and listed in a footnote under the ranking instead.
They stay in all raw totals (customers out, customer-hours, event counts). Under D13 each county
has one denominator for all years, so a county is either excluded in every year or in none.

**Why:** With a tiny denominator, a single outage swings the rate wildly, and the ranking would be
topped by counties where EAGLE-I tracks only a handful of customers. A footnote keeps them
visible without letting them dominate.

**Rows affected:**

| Year | Counties with a denominator | Excluded (D9 only) | Excluded (D9 + D12) | Excluded (D13, final) | Rows excluded (D13) |
|---|---|---|---|---|---|
| 2022 | 3,056 | 96 | 50 | **40** | 41,271 |
| 2023 | 3,057 | 96 | 50 | **40** | 44,374 |
| 2024 | 3,059 | 40 | 40 | **40** | 81,350 |

Under D13 the same 40 counties are excluded in every year, and all 40 appear in all three years.
They are the counties whose 2024 `total_customers` is below 1,000, so the 2024 count is unchanged.
2022 and 2023 drop from 50 to 40 because counties that previously used a small MCC value
(within 2x, so not caught by D12) now use their larger 2024 value. The remaining exclusions are
genuinely small, rural counties (for example Niobrara WY, Kalawao HI, Loving TX, Esmeralda NV).

Before D12, some large counties were excluded only because their MCC value is clearly wrong.
D12 and D13 replace these values with 2024 `total_customers`, so they are now ranked in every year:

| FIPS | County | MCC customers | 2024 `total_customers` |
|---|---|---|---|
| 51530 | Buena Vista city, VA | 1 | 3,365 |
| 51820 | Waynesboro city, VA | 6 | 11,820 |
| 51678 | Lexington city, VA | 16 | 2,991 |
| 37089 | Henderson, NC | 24 | 69,102 |
| 37181 | Vance, NC | 863 | 23,635 |
| 37001 | Alamance, NC | 925 | 90,017 |

These cases led to D12, which corrects them and the wider MCC undercount systematically.

## D12. Reconcile MCC with 2024 total_customers

**What:** For every county with both an MCC value and a 2024 `total_customers` value, compare the
two. If the larger is more than 2x the smaller, use the larger value as the denominator in every
year, set `denominator_source = 'max_mcc_2024'` and `denominator_mismatch = true`. All other
counties get their source from D13 with `denominator_mismatch = false`. This rule is step (a) of
D13.

**Why:**
- A county's real customer count changes only a few percent in two years, so a 2x gap
  between the 2022 model and the 2024 reported count is a data error, not growth.
- The common error is undercounting: a source that covers only some of a county's utilities
  reports too few customers. Overcounting is rare.
- A larger denominator gives a lower, more conservative per-1,000 rate. An undercount would
  inflate a county's rate and push it up the rankings.
- I use one value for all years so that a county's rate does not jump between 2023 and 2024
  just because the denominator source changed.

**Rows affected:**
- 3,051 counties have both values; none is zero.
- 372 counties (12.2%) differ by more than 2x and get `denominator_mismatch = true`. In 357 of
  them, 2024 `total_customers` is larger; in 15, MCC is larger.
- Most affected states: Texas 82, North Carolina 68, Missouri 39, Virginia 30, South Carolina 23.

Ten largest mismatches:

| FIPS | County | MCC | 2024 `total_customers` | Ratio | Used |
|---|---|---|---|---|---|
| 51530 | Buena Vista city, VA | 1 | 3,365 | 3,365x | 3,365 |
| 37089 | Henderson, NC | 24 | 69,102 | 2,879x | 69,102 |
| 51820 | Waynesboro city, VA | 6 | 11,820 | 1,970x | 11,820 |
| 51678 | Lexington city, VA | 16 | 2,991 | 187x | 2,991 |
| 37001 | Alamance, NC | 925 | 90,017 | 97x | 90,017 |
| 37129 | New Hanover, NC | 2,544 | 148,021 | 58x | 148,021 |
| 48243 | Jeff Davis, TX | 44 | 1,835 | 42x | 1,835 |
| 37063 | Durham, NC | 6,008 | 174,306 | 29x | 174,306 |
| 37181 | Vance, NC | 863 | 23,635 | 27x | 23,635 |
| 48019 | Bandera, TX | 1,495 | 33,685 | 22x | 33,685 |

Effect on D11: D12 alone drops excluded counties from 96 to 50 in 2022 and 2023 (40 in 2024);
with D13 the final count is 40 in every year (details in D11).

**Caveats:**
- The two sources disagree more than the rationale assumes, even below the threshold: the
  median ratio across all 3,051 counties is 1.20, and 438 more counties are between 1.5x and 2x.
  Under D13 those counties use their 2024 value in every year, so the general difference no
  longer causes year-over-year jumps. The 2x threshold targets clear errors only.
- Counties recovered by D9 step (c) have no MCC value, so D12 does not apply to them.
- The D4 `exceeds_customers` counts were computed before D12 and D13 and will change once the
  final denominators are applied. They will be recounted when Silver is built.
- A cross-check against EIA-861 customer counts is optional later work, not a blocker.

## D13. One denominator per county

**What:** Each county gets exactly one denominator, used for every year. It is chosen in this order:

| Order | Rule | `denominator_source` | `denominator_mismatch` |
|---|---|---|---|
| a | the county's 2024 `total_customers`, with D12 applied: if MCC differs by more than 2x, use the larger of the two | `total_customers_2024` or `max_mcc_2024` | false / true |
| b | MCC customers, if the county has no 2024 value | `mcc` | false |
| c | neither exists: `customers` is NULL and `has_denominator = false` (handled as in D9) | NULL | false |

The result is stored once, in a single table that Silver and Gold join on `fips_code`:

`dim_county_customers`

| Column | Type | Description |
|---|---|---|
| `fips_code` | STRING | 5-digit county FIPS, primary key |
| `customers` | BIGINT | the one denominator for all years; NULL if none |
| `denominator_source` | STRING | `total_customers_2024`, `max_mcc_2024`, `mcc`, or NULL |
| `denominator_mismatch` | BOOLEAN | true when D12's 2x rule picked the larger value |

`has_denominator` is derived as `customers IS NOT NULL`. The table covers every FIPS code that
appears in any EAGLE-I year.

**Why:** The D12 analysis found a 1.20 median ratio between MCC and 2024 `total_customers` across
3,051 counties. If a county used MCC in 2022-2023 and `total_customers` in 2024, its per-1,000
rate would shift by about 20% between 2023 and 2024 for the median county from the source
change alone, and year-over-year comparisons would measure the switch rather than outages. One
denominator per county makes every rate change come from the numerator. 2024 `total_customers`
goes first because it is reported with the readings; MCC is the fallback.

Note: within 2024, `total_customers` is constant per county (0 counties have more than one
value), so a single 2024 value per county loses nothing compared with the row-level value.

**Rows affected:** 3,063 distinct counties across all years.

| `denominator_source` | Counties | Sum of customers |
|---|---|---|
| `total_customers_2024` | 2,687 | 155,431,180 |
| `max_mcc_2024` | 372 | 21,741,301 |
| `mcc` | 2 | 73,945 |
| none (`has_denominator = false`) | 2 | - |

- `mcc` only: 02261 Valdez-Cordova AK (5,469) and 72031 Carolina PR (68,476). Both appear in
  2022-2023 but not in 2024.
- No denominator: 51720 Norton city VA and 02063 Chugach AK (see D9).
- Effect on D11: the same 40 counties are excluded in every year (see D11).

Built in `sql/databricks/02_silver.sql` from the Bronze tables. Tested in DuckDB
(`scripts/test_silver_duckdb.py`): 3,063 rows, 0 duplicate `fips_code`, counts per source as above.

## D14. Bronze is all text; Silver parses in UTC

**What:** Every column of every Bronze table (EAGLE-I years, MCC, region lookup) is loaded as
STRING with an explicit `read_files` schema. Silver casts counts with `TRY_CAST` and parses
`run_start_time` with `try_to_timestamp(..., 'yyyy-MM-dd HH:mm:ss')` after `SET TIME ZONE 'UTC'`.

**Why:** This extends D6 from FIPS to every column. Bronze then stores the files exactly as they
are, and a bad value can never fail the load or be changed by schema inference. Parsing a
zone-less timestamp uses the session time zone, so fixing it to UTC makes D1 hold regardless of
workspace defaults. The explicit MCC schema also sidesteps the byte-order mark at the start of
`MCC.csv`, which would otherwise end up in the first column name.

**Rows affected:** none changed. The Bronze tables add `source_file` and `loaded_at`. The yearly
files are read from Parquet with the same all-STRING columns (D20).

## D15. Rows that cannot be parsed

**What:** Silver drops a row if its padded `fips_code` is not 5 digits, `run_start_time` does not
parse, or `customers_out` is not an integer.

**Why:** Such a row cannot be placed in a county or a 15-minute slot, so it cannot feed any event
or rate. The profile found none, so this is a guard for future files, not a cleanup.

**Rows affected:** 0 in all three years (DuckDB, full data). FIPS codes padded: 0. 2025: 1,972,650
rows with an empty `customers_out` (D59).

## D16. State attributes from the state FIPS prefix

**What:** `state`, `state_abbr`, `census_region`, `census_division` and `fema_region` come from
`bronze_state_regions` (built by `scripts/census_regions.py`), joined on
`state_fips = LEFT(fips_code, 2)`. `state` is the lookup's name, not the raw text. The join is
INNER, so a row whose prefix is not in the lookup would be dropped.

**Why:** The project rule is to join on FIPS, never on names. The prefix join also makes every row
use one spelling of each state name, which matters because `state` is a partition column.

**Rows affected:** 0 rows dropped by the join, and 0 rows where the raw state name differs from
the lookup name (DuckDB, full data). The lookup has 53 rows: 50 states, DC, PR and VI.

**Location (changed 2026-11-20):** the lookup is written to `data/reference/state_regions.csv`
and committed, instead of `data/raw/census/regions/`. It is small reference data built by a
script, not a raw download, so it does not belong in the gitignored `data/raw/`, and a fresh clone
can run Silver without rebuilding it. On Databricks it is uploaded to
`/Volumes/workspace/outages/raw/reference/`, which `01_bronze.sql` reads. The content is
unchanged.

## Silver test run

`scripts/test_silver_duckdb.py` runs the same CTEs as `02_silver.sql` in DuckDB. Results on
2026-11-20:

| Step | Rule | July 2024 sample | All years |
|---|---|---|---|
| `unioned` | D2 rename and union | 2,762,980 | 79,598,850 |
| `typed` | D1, D14 parse and cast | 2,762,980 (+0) | 79,598,850 (+0) |
| `valid` | D15 drop unparseable | 2,762,980 (+0) | 79,598,850 (+0) |
| `floored` | D7 floor to 15 minutes | 0 rows changed | 819 rows changed |
| `deduped` | D7 dedupe, keep max | 2,762,980 (+0) | 79,598,850 (+0) |
| `silver_outages` | D8, D16 region join; D4 flag | 2,762,980 (+0) | 79,598,850 (+0) |

| Check | July 2024 sample | All years |
|---|---|---|
| `exceeds_customers = true` | 936 | 10,619 |
| Rows without a denominator (D9) | 1 | 142 |
| `census_region = 'Territory'` | 23,812 | 808,077 |

July 2024 does not exercise D7 (no off-grid timestamps or duplicates in 2024), so the script
also runs a synthetic check: a 20:31 reading floors to 20:30 and, as a duplicate of an existing
20:30 row, keeps the higher value. It passes. Totals match the profile and D4, D8 and D9.

---

## D17. Outage events

**What:** `gold_outage_events` (`sql/databricks/03_gold_events.sql`), one row per county event:
- A reading qualifies when raw `customers_out >= event_threshold`, where
  `event_threshold = GREATEST(100, 0.25% x customers)` (D18; it was a flat 100 before D18).
  The raw value is used because D4 keeps readings uncapped; the cap applies to metrics only.
  Readings inside a county feed dropout (D19) do not qualify.
- Readings are ordered per county. `LAG` gives the distance to the previous qualifying reading
  in active runs: collected runs (`gold_collection_runs.run_index`, so nationwide feed gaps add no
  time, D3) minus the county's own dropout runs (D19). More than 4 active runs (more than 1 hour)
  starts a new event; exactly 1 hour stays in the same event. A running `SUM` of the new-event
  flags numbers the events.
- `event_id` = `fips_code` + `-` + 5-digit sequence within the county, e.g. `48201-00250`. It is
  stable as long as the set of years loaded, the threshold and the dropout rule do not change.
- `event_start` is the first qualifying run; `event_end` is the end of the last qualifying run
  (its start + 15 minutes), so a single reading lasts 0.25 hours. `duration_hours` is wall-clock
  time and includes any short dips below the threshold, feed gaps and dropouts inside the event.
- `customer_hours_lost` = sum of `LEAST(customers_out, customers) x 0.25` over qualifying readings
  (D4, with the D13 denominator). Counties without a denominator use the raw value (D9).
  `customer_hours_lost_raw` keeps the uncapped sum. `peak_customers_out` is raw.
- `peak_out_per_1000` and `customer_hours_per_1000` use the D13 denominator, NULL without one.
  `ranking_eligible` = denominator of at least 1,000 (D11). `exceeds_customers` is true if any
  reading in the event was flagged (D4). `spans_feed_gap` / `feed_gap_hours` implement D10;
  `spans_dropout` / `dropout_hours` implement D19. `event_threshold` is stored per event.

**Why:** Measuring the gap in active runs is what makes D3 and D19 work: two readings either side
of a 9-hour feed outage are 1 run apart, not 37. Ending an event at the end of its last run makes
`duration_hours` and `customer_hours_lost` use the same 15-minute unit.

**Rows affected (DuckDB, full data, 0.25% threshold with D19):** 6,136,006 qualifying readings,
all assigned to exactly one event, with no overlaps and no duplicate IDs.

| Year | Events | Spans feed gap | Spans dropout | Has overcount | Not ranking eligible | Median / p95 hours | Customer-hours (M) |
|---|---|---|---|---|---|---|---|
| 2022 | 148,425 | 46 | 5,458 | 51 | 140 | 1.50 / 10.25 | 1,069.4 |
| 2023 | 143,479 | 704 | 4,704 | 35 | 160 | 1.50 / 11.00 | 876.3 |
| 2024 | 150,458 | 234 | 4,839 | 115 | 189 | 1.50 / 11.50 | 1,687.4 |

Ten largest events by `customer_hours_lost`:

| Event | County | Start (UTC) | End (UTC) | Hours | Peak out | Customer-hours | Gap | Dropout |
|---|---|---|---|---|---|---|---|---|
| 48201-00250 | Harris, TX | 2024-07-08 14:15 | 2024-07-19 05:30 | 255 | 1,660,703 | 135.5 M | no | yes |
| 72097-00360 | Mayagüez, PR | 2022-09-17 12:30 | 2022-10-20 06:00 | 786 | 219,197 | 70.0 M | yes | yes |
| 12071-00096 | Lee, FL | 2022-09-28 06:45 | 2022-10-21 14:30 | 560 | 456,573 | 66.6 M | yes | yes |
| 72113-00314 | Ponce, PR | 2022-09-18 09:00 | 2022-10-19 06:30 | 742 | 210,593 | 60.3 M | yes | yes |
| 72025-00354 | Caguas, PR | 2022-09-18 00:45 | 2022-10-13 00:30 | 600 | 243,802 | 51.6 M | no | yes |
| 72013-00311 | Arecibo, PR | 2022-09-17 10:15 | 2022-10-11 00:30 | 566 | 191,803 | 39.7 M | no | yes |
| 12103-00430 | Pinellas, FL | 2024-10-09 16:45 | 2024-10-19 00:15 | 224 | 449,310 | 39.2 M | yes | no |
| 45045-00314 | Greenville, SC | 2024-09-27 04:00 | 2024-10-09 22:00 | 306 | 270,050 | 33.8 M | no | no |
| 45083-00264 | Spartanburg, SC | 2024-09-27 07:30 | 2024-10-08 23:30 | 280 | 183,816 | 25.6 M | no | no |
| 37021-00329 | Buncombe, NC | 2024-09-27 02:30 | 2024-10-18 22:15 | 524 | 223,578 | 23.6 M | yes | yes |

The dates line up with Hurricane Beryl (Harris), Fiona (Puerto Rico), Ian (Lee), Milton (Pinellas)
and Helene (Greenville, Spartanburg, Buncombe). These are date matches only; the NOAA storm match
comes later. Harris and Buncombe are the top-10 events with an overcount. The flat-100 baseline
is in D18.

## D18. Event threshold scales with county size

**What:** A reading qualifies for an event when
`customers_out >= GREATEST(100, 0.0025 x customers)`, with `customers` from
`dim_county_customers` (D13). Counties without a denominator stay at 100. The share is set once,
in the `params` CTE of `gold_event_thresholds` in `03_gold_events.sql`, and each event stores its
`event_threshold`. The threshold is above 100 only in counties with more than 40,000 customers;
the largest, Los Angeles (3,799,750), gets 9,499.

**Why:** With a flat 100 (D17 as first built), 100 customers out is background noise in a large
county. The count rarely stays below 100 for more than an hour, so separate storms chain into one
long event (Q2): Pinellas FL had one 1,194-hour event from Helene through Milton, and Los Angeles CA
an 820-hour chain in May-June 2024. Analysis question 4 (longest restoration) would favor large
counties for that reason alone.

**How the share was chosen.** The first version of this decision picked 0.15%, the smallest share
that split Pinellas without breaking Beryl in Harris. That only worked inside a narrow window,
(0.1398%, 0.1727%], because a reporting dropout in Harris set the upper limit. D19 now handles such
dropouts directly, which removes that limit, and the share is chosen for wide margins instead.

Requirements, each with an exact split point. An event breaks when 4 consecutive active runs
(D17) are all below the threshold, so for a time window the critical threshold T* is the smallest
4-run maximum in it, and the critical share is T* / customers:

| Requirement | Window | T* | Customers | Critical share |
|---|---|---|---|---|
| Pinellas FL: Helene and Milton must split | Helene peak 2024-09-27 05:15 to Milton peak 2024-10-11 07:45 | 797 (2024-10-08 22:00) | 570,020 | > 0.1398% |
| Wayne MI: ice storm and March storm must split | 2023-02-23 22:00 to 2023-03-04 19:00 | 949 (2023-03-03 15:30) | 784,626 | > 0.1209% |
| Los Angeles CA: May-June 2024 chain must break | 2024-05-19 07:45 to 2024-06-19 12:00 | 112 (2024-06-13 21:00) | 3,799,750 | > 0.0029% |
| Harris TX: Beryl must stay one event | peak 2024-07-08 19:15 to 2024-07-16 00:00 | 175,159 (2024-07-15 23:45) | 1,344,930 | < 13.02% |
| No outage of 10,000+ customers may be dropped | largest county threshold must stay below 10,000 | | 3,799,750 | <= 0.263% |

The first four come from the data. The last one is a definition: an outage affecting 10,000 or more
customers is always an event, in any county. Without it the margins would favor ever higher shares.

**Sensitivity test** (`scripts/sensitivity_event_threshold.py`, DuckDB, all three years, D19 applied;
the real queries from `03_gold_events.sql` with only `event_share` changed):

| Share | Events | Median / p95 h | Customer-hours (M) | Dropouts | Pinellas | Wayne | Beryl | Los Angeles May-June 2024 | Baseline top 10 kept | Large outages lost |
|---|---|---|---|---|---|---|---|---|---|---|
| flat 100 | 675,901 | 1.75 / 12.50 | 3,967.5 | 34,887 | merged, 1,194 h | merged, 374 h | whole | 2 events, longest 820 h | 10 / 10 | 0 |
| 0.1% | 553,403 | 1.50 / 11.00 | 3,796.3 | 25,252 | merged, 617 h | merged, 322 h | whole | 23 events, longest 6.5 h | 10 / 10 | 0 |
| 0.15% | 506,777 | 1.50 / 11.00 | 3,731.9 | 22,558 | split, 252 h / 248 h | split, 210 h / 100 h | whole | 8 events, longest 3.8 h | 9 / 10 | 0 |
| **0.25%** | **442,362** | **1.50 / 11.00** | **3,633.1** | **19,050** | **split, 215 h / 224 h** | **split, 198 h / 100 h** | **whole** | **1 event, 1.2 h** | **9 / 10** | **0** |
| 0.5% | 346,564 | 1.50 / 11.25 | 3,463.1 | 14,436 | split, 197 h / 215 h | split, 193 h / 77 h | whole | none | 9 / 10 | 65 |

"Large outages lost" counts flat-100 events with a peak of 10,000+ customers out that no longer
fall inside any event. At 0.5% the 65 are in two counties with 12.5 M customer-hours; the five
largest are all in Los Angeles, with peaks of 16,564 to 18,540 (for example 2023-03-17 and 2024-02-10).

Events and duration by year (median / p95 hours):

| Share | 2022 | 2023 | 2024 |
|---|---|---|---|
| flat 100 | 228,097 (1.75 / 11.75) | 219,984 (1.75 / 12.50) | 227,820 (1.75 / 13.25) |
| 0.1% | 186,425 (1.50 / 10.50) | 179,638 (1.50 / 11.00) | 187,340 (1.50 / 11.75) |
| 0.15% | 170,551 (1.50 / 10.50) | 164,473 (1.50 / 11.00) | 171,753 (1.50 / 11.50) |
| 0.25% | 148,425 (1.50 / 10.25) | 143,479 (1.50 / 11.00) | 150,458 (1.50 / 11.50) |
| 0.5% | 116,177 (1.50 / 10.50) | 112,439 (1.50 / 11.00) | 117,948 (1.50 / 12.00) |

Five longest events per share:

| Share | Longest five (county, hours) |
|---|---|
| flat 100 | Los Angeles CA 1,328 (2022-11-15 to 2023-01-09); Maui HI 1,328; Pinellas FL 1,194; Palm Beach FL 1,081; Ponce PR 1,047 |
| 0.1% | Maui HI 1,328; Wilkinson MS 963; Rutherford NC 953; Yancey NC 808; Madison NC 804 |
| 0.15% | Maui HI 1,328; Wilkinson MS 963; Rutherford NC 953; Yancey NC 808; Madison NC 804 |
| 0.25% | Maui HI 1,091; Wilkinson MS 963; Rutherford NC 953; Yancey NC 808; Madison NC 804 |
| 0.5% | Wilkinson MS 963; Yancey NC 808; Madison NC 804; Mayagüez PR 762; Rutherford NC 759 |

From 0.1% up, the longest events are long real restorations: Helene in western North Carolina, the
2023 Maui fires, Fiona in Puerto Rico. Rutherford, Yancey, Madison and Wilkinson have fewer than
40,000 customers, so their threshold is 100 at every share tested.

Baseline top 10 (flat 100) under each share: rank of the event that contains each baseline event's
peak reading, and the share of its customer-hours kept:

| Baseline event | 0.1% | 0.15% | 0.25% | 0.5% |
|---|---|---|---|---|
| 1 Harris TX (Beryl) | 1, 100% | 1, 100% | 1, 100% | 1, 100% |
| 2 Mayagüez PR (Fiona) | 2, 100% | 2, 100% | 2, 100% | 2, 100% |
| 3 Lee FL (Ian) | 3, 98% | 3, 98% | 3, 98% | 3, 98% |
| 4 Ponce PR (Fiona) | 4, 99% | 4, 99% | 4, 99% | 4, 99% |
| 5 Caguas PR (Fiona) | 5, 100% | 5, 100% | 5, 100% | 5, 99% |
| 6 Pinellas FL (Helene + Milton) | 6, 100% | 7, 76% | 7, 76% | 7, 76% |
| 7 Arecibo PR (Fiona) | 7, 100% | 6, 100% | 6, 100% | 6, 100% |
| 8 Greenville SC (Helene) | 8, 100% | 8, 100% | 8, 100% | 8, 100% |
| 9 Wayne MI (ice storm + March storm) | 9, 100% | 13, 81% | 13, 81% | 13, 81% |
| 10 Spartanburg SC (Helene) | 10, 100% | 9, 100% | 9, 100% | 9, 100% |
| New in top 10 | none | Buncombe NC (Helene) | Buncombe NC | Buncombe NC |

The two changes from 0.15% up are the intended splits: Pinellas keeps its Milton part and Wayne its
ice storm. With D19, Harris keeps 100% at every share; without D19 it fell to 32% at 0.25% and above.

Margin between each county's threshold and its split point (positive = requirement met; for the
must-split rows it is threshold / T* - 1, for Harris T* / threshold - 1):

| Share | Pinellas | Wayne | Los Angeles | Harris | Smallest | Largest county threshold |
|---|---|---|---|---|---|---|
| flat 100 | -87% | -89% | -11% | huge | -89% (fails) | 100 |
| 0.1% | -28% | -17% | +3,293% | +12,924% | -28% (fails) | 3,800 |
| 0.15% | +7% | +24% | +4,989% | +8,582% | +7% | 5,700 |
| **0.25%** | **+79%** | **+107%** | **+8,382%** | **+5,110%** | **+79%** | **9,499** |
| 0.5% | +258% | +313% | +16,863% | +2,505% | +258% | 18,999 (drops 10,000+ outages) |

**Choice: 0.25%.** It is the share with the widest margins that still keeps every outage of
10,000+ customers.
- Every data requirement is met with at least 79% to spare. Pinellas's threshold (1,425) is 1.8x
  its split point and Wayne's (1,962) is 2.1x. The Pinellas split would only fail if its denominator
  were 44% too high, more than double the 20% median gap between MCC and 2024 `total_customers` in
  D12. Harris would only break at a share 52 times higher.
- 0.15% meets the same requirements but with a 7% margin on Pinellas, which a small denominator
  change could erase. 0.5% widens the margins further but stops counting 65 outages of 10,000+
  customers, so it fails the last requirement.
- The upper bound for that last requirement is 0.263%, so 0.25% sits near the top of the allowed
  range: the lower requirements are data-driven and are what the margin protects against.
- Against flat 100, events fall from 675,901 to 442,362 and customer-hours by 8.4% (3,968 M to
  3,633 M). That is background time in large counties that no longer counts as an event; no outage
  of 10,000+ customers is lost.

**Caveats:**
- A county outage below its threshold is not an event. In Los Angeles that is anything under 9,499
  customers out. Analysis that needs small outages in large counties should read Silver directly.
- If a denominator changes a lot (for example after an EIA-861 cross-check), rerun
  `scripts/sensitivity_event_threshold.py`; it prints these margins.
- Some long events remain where outages really lasted weeks (Fiona, Helene, the Maui fires). D10
  and D19 flag the ones whose duration crosses a feed gap or a dropout.

**Rows affected:** see D17 for the final event counts. Across the three years, events fall from
675,901 (flat 100 with D19) to 442,362, and qualifying readings to 6,136,006.

## D19. County feed dropouts

**What:** `gold_feed_dropouts` (`03_gold_events.sql`) detects reporting dropouts per county:
- A dropout starts at a reported reading that is below 10% of the county's reading in the previous
  run (a fall of more than 90%), where that previous reading was at or above the county's event
  threshold (D18).
- It ends at the first later reading back at 50% or more of the pre-drop level, if that reading
  comes no more than 5 runs after the drop started. The dropped readings then span at most 1 hour
  from first to last (for example 00:45 to 01:45). A drop that does not recover in time is real.
- Only reported readings can start a dropout. Missing rows stay zeros under D3; counting them as
  drops would let any outage that vanishes for up to 75 minutes and returns merge across D17's
  1-hour rule.
- Dropout runs are treated like D3 feed gaps for that county: their readings cannot qualify, and
  they are removed from the run count, so they can neither end nor split an event. Events containing
  them get `spans_dropout = true` and `dropout_hours` = dropout runs x 0.25. Raw `customers_out` in
  Silver is unchanged.

**Why:** Some utility feeds briefly report almost nothing in the middle of a major outage. In Harris
TX during Beryl, customers out fell from 1,095,633 to 2,323 at 2024-07-10 00:45 UTC, stayed near
2,322 until 01:45, and was back at 1,050,184 at 02:00. A million customers are not restored and lost
again within an hour. Without this rule such a dip either splits a storm into two events or, to
avoid that, forces the D18 share into a narrow window (the first version of D18).

**Rows affected (DuckDB, full data, 0.25% threshold):**

| Year | Dropouts | Counties | Dropout runs | Pre-drop level 10,000+ | Events spanning a dropout |
|---|---|---|---|---|---|
| 2022 | 6,746 | 1,845 | 13,135 | 126 | 5,458 |
| 2023 | 5,736 | 1,719 | 11,145 | 81 | 4,704 |
| 2024 | 6,568 | 1,806 | 13,039 | 342 | 4,839 |

Most dropouts are at small levels; 549 of 19,050 start from 10,000 or more customers out. The
count depends slightly on the share, because the pre-drop reading must be at or above the threshold
(34,887 at flat 100, 19,050 at 0.25%).

Ten largest dropouts by pre-drop customers out:

| County | Start (UTC) | Recovered (UTC) | Runs | Before | Dropped to | Recovered to |
|---|---|---|---|---|---|---|
| Harris, TX | 2024-07-09 15:30 | 15:45 | 1 | 1,338,147 | 3,161 | 1,328,310 |
| Harris, TX | 2024-07-09 16:00 | 16:15 | 1 | 1,328,310 | 3,161 | 1,315,776 |
| Harris, TX | 2024-07-10 00:45 | 02:00 | 5 | 1,095,633 | 2,323 | 1,050,184 |
| Harris, TX | 2024-07-10 03:00 | 03:15 | 1 | 1,041,416 | 2,339 | 1,036,922 |
| Harris, TX | 2024-07-10 03:30 | 03:45 | 1 | 1,036,922 | 2,339 | 1,036,231 |
| Harris, TX | 2024-07-10 05:30 | 05:45 | 1 | 1,026,513 | 2,339 | 1,029,798 |
| Hillsborough, FL | 2024-10-10 14:30 | 14:45 | 1 | 513,664 | 1,229 | 514,517 |
| Hillsborough, FL | 2024-10-11 01:00 | 01:30 | 2 | 509,954 | 1,140 | 509,718 |
| Hillsborough, FL | 2024-10-10 06:15 | 06:30 | 1 | 509,374 | 1,229 | 508,326 |
| Hillsborough, FL | 2024-10-10 06:45 | 07:15 | 2 | 508,326 | 1,229 | 507,795 |

Confirmed: Harris (48201) 2024-07-10 00:45-01:45 UTC is detected as one 5-run dropout. Fort Bend TX
(48157) has the same pattern at the same times (00:45-01:45, 03:00, 03:30 and 05:30, falling to 0),
which points to one utility feed failing across several counties. Fort Bend's Beryl outage is now one
event (2024-07-08 14:15 to 07-16 01:00, 178.8 h, 13.6 M customer-hours) instead of two. Hillsborough
FL shows the same kind of dropout during Milton.

**Caveats:**
- Dropout readings are left out of `customer_hours_lost`, as feed gaps are. For Harris/Beryl that is
  2.5 hours of a 255-hour event, so customer-hours are slightly low there.
- A real restoration of over 90% that is undone within an hour would be misread as a dropout. At
  the scale of the large cases above that is not plausible; for small counts it hardly matters,
  because the 1-hour rule of D17 already bridges most short gaps.

## D20. Yearly files reach Bronze as Parquet

**What:** `scripts/run_databricks.py` converts each yearly EAGLE-I CSV to Parquet with DuckDB
(`read_csv(..., all_varchar = true)`, zstd), writes it to `data/raw/eaglei_parquet/<year>/`
(gitignored) and uploads it to `/Volumes/workspace/outages/raw/eaglei_parquet/<year>/`.
`01_bronze.sql` reads these with `read_files(..., format => 'parquet')` and the same explicit
all-STRING schema as before. The small files (MCC, coverage history, DQI, region lookup) stay CSV.

**Why:** The CSVs are 3.5 GB; the Parquet files are 155 MB, so the upload to the Free Edition
volume takes about 30 seconds and Bronze loads read far less. Every column stays STRING, so D14
still holds: no value is typed, trimmed or changed before Silver. The raw CSVs remain the source of
record in `data/raw/eaglei/`.

**Rows affected:** none changed. The conversion checks that each Parquet file has the CSV's row count
and only STRING columns.

| Year | CSV | Parquet | Ratio | Rows |
|---|---|---|---|---|
| 2022 | 1.1 GB | 63.0 MB | 5.6% | 25,796,465 |
| 2023 | 1.1 GB | 62.6 MB | 5.5% | 26,101,051 |
| 2024 | 1.3 GB | 29.2 MB | 2.1% | 27,701,334 |
| 2025 | 1.3 GB | 67.5 MB | 5.0% | 30,482,141 (added in D56) |

## Databricks run

`scripts/run_databricks.py` ran `01_bronze.sql`, `02_silver.sql` and `03_gold_events.sql` statement
by statement on the Serverless Starter Warehouse (session time zone `Etc/UTC`, catalog `workspace`,
schema `outages`) on 2026-11-20. Every statement succeeded on the first run; `silver_outages` took
88 seconds and each Gold table under 10 seconds.

The Statement Execution API runs each statement in its own session, so the `USE` and
`SET TIME ZONE` lines in the .sql files are skipped. Catalog and schema are passed with every
statement, and the script stops unless the session time zone is UTC (D1).

Every table matches the DuckDB results:

| Table | Rows (Databricks = DuckDB) |
|---|---|
| bronze_eaglei_2022 / 2023 / 2024 | 25,796,465 / 26,101,051 / 27,701,334 |
| bronze_eaglei_mcc | 3,234 |
| bronze_state_regions | 53 |
| dim_county_customers | 3,063 |
| silver_outages | 79,598,850 |
| gold_collection_runs | 105,216 |
| gold_event_thresholds | 3,063 |
| gold_feed_dropouts | 19,050 |
| gold_outage_events | 442,362 |

Also identical: feed gaps per year (3 / 16 / 41), events per year (148,425 / 143,479 / 150,458),
dropouts per year (6,746 / 5,736 / 6,568), `exceeds_customers` rows per year (1,820 / 365 / 8,434),
denominator sources (2,687 / 372 / 2 / 2), and the top 10 events by `customer_hours_lost`, by
event ID and customer-hours (D17).

## D21. Calibrate denominators to EIA-861 state totals

**Amended by D35:** counties are no longer scaled by one state factor; each is held at or above its
peak customers out, and the rest of the state absorbs the difference. The tables below are the
original D21 measurements.

**What:** For each state, compare the sum of D13 county denominators with the EIA-861 2024 state
customer total (Sales to Ultimate Customers, Parts A + C + D only, never Part B; see D23). Where
the ratio D13 / EIA is above 1.25, divide every county denominator in that state by the ratio, so
the state total matches EIA and each county keeps its share. States at or below 1.25 are not
changed, and no state is ever scaled up: a lower EAGLE-I total usually means counties or utilities
EAGLE-I does not track (D22), not too few customers.
- Each county still has exactly one denominator for all years (D13), now
  `customers = ROUND(D13 customers / calibration_factor)`.
- `dim_county_customers` gets a fifth column, `calibration_factor` (DOUBLE, 1.0 where not
  calibrated). `denominator_source` and `denominator_mismatch` are unchanged, so the
  uncalibrated value stays derivable (`customers x calibration_factor`).
- EIA 2024 is used for all years, matching D13's single 2024-based denominator.

**Why:** The source profile (`docs/data_profile_sources.md`) found D13 totals far above EIA in some
states. In Massachusetts, EAGLE-I's own 2024 `total_customers` gives Suffolk County 1,666,496
customers for about 770,000 residents, and D12's larger-value rule keeps that value. Per-1,000
rates there would be about half their true value, which matters directly for analysis question 5
(Eversource and National Grid). EIA-861 is the utilities' own reported customer count, so it is the
right total; EAGLE-I still decides how that total splits across counties. The 1.25 threshold leaves
ordinary differences alone (median state ratio 1.012) and catches only clear inflation. This also
corrects part of D12's reasoning: undercounts are the common error in MCC, but EAGLE-I's 2024
`total_customers` overcounts in a few states.

**Rows affected:** 5 states, 246 counties.

| State | D13 customers | EIA 2024 (A+C+D) | Ratio before | calibration_factor | Calibrated total | Ratio after |
|---|---|---|---|---|---|---|
| MA | 6,799,970 | 3,372,904 | 2.016 | 2.0161 | 3,372,906 | 1.000 |
| SC | 5,758,961 | 2,998,873 | 1.920 | 1.9204 | 2,998,872 | 1.000 |
| HI | 668,078 | 506,988 | 1.318 | 1.3177 | 506,989 | 1.000 |
| MO | 4,321,653 | 3,347,316 | 1.291 | 1.2911 | 3,347,316 | 1.000 |
| SD | 658,178 | 516,156 | 1.275 | 1.2752 | 516,157 | 1.000 |

(Calibrated totals differ from EIA by 1-2 customers from rounding each county.)

- Suffolk County, MA (25025): 1,666,496 before, **826,611** after (factor 2.0161).
- National total: 177,246,426 before, 169,781,826 after, against EIA 165,391,292 (ratio 1.072 to 1.027).
- Counties scaled per state: MA 14, SC 46, HI 5, MO 115, SD 66.

Knock-on effects, measured in DuckDB, applied when Silver and Gold are rebuilt:
- D4 `exceeds_customers` rows: 1,820 / 365 / 8,434 before; **1,878 / 369 / 9,940** after (2022 /
  2023 / 2024), in 23 / 21 / 73 counties.
- D11: counties under 1,000 customers go from 40 to 41 (Buffalo County, SD, 46017: 1,239 to 972).
- D18: the event threshold falls in the 62 calibrated counties with more than 40,000 customers, so
  event counts in MA, SC, HI, MO and SD will change. None of the D18 test counties (Pinellas FL,
  Wayne MI, Los Angeles CA, Harris TX) is in a calibrated state, so D18's margins are unchanged.

**Implemented** (2026-11-21) in `02_silver.sql` (`dim_county_customers.calibration_factor`) and
measured with the full rebuild (`scripts/test_sources_duckdb.py`):

| State | Events before | Events after | Thresholds changed | Median threshold | Overcount rows | Customer-hours (M) |
|---|---|---|---|---|---|---|
| MA | 1,773 | 3,020 | 12 | 1,176 -> 584 | 0 -> 37 | 22.47 -> 26.44 |
| SC | 6,805 | 8,806 | 26 | 324 -> 169 | 0 -> 1,502 | 154.24 -> 145.68 |
| HI | 1,372 | 1,476 | 3 | 442 -> 336 | 0 -> 1 | 9.18 -> 9.42 |
| MO | 11,055 | 11,634 | 19 | 185 -> 143 | 0 -> 4 | 35.68 -> 36.20 |
| SD | 1,751 | 1,789 | 2 | 268 -> 210 | 15 -> 39 | 4.16 -> 4.20 |

(Overcount rows count all three years in that state. "Thresholds changed" counts counties whose D18
threshold is above 100, about 40,000+ customers.)

- National events: 442,362 to 446,331 (148,425 / 143,479 / 150,458 to 149,706 / 144,774 / 151,851).
  Dropouts: 19,050 to 19,195.
- **The top 10 is not unchanged.** The same 10 storms remain, and Beryl, Fiona, Ian and Milton are
  identical. But both South Carolina Helene events lose customer-hours, because the lower
  denominators cap their readings (D4): Greenville 33.81 M to 27.06 M, Spartanburg 25.63 M to
  22.54 M. Spartanburg drops from #9 to #10 behind Buncombe NC.
- The cause is that the uniform state factor pushes 9 of the 246 calibrated counties below the
  highest outage ever reported there (SC 5, HI 1, MA 1, MO 1, SD 1; SD already had 1 before).
  Greenville goes from 301,949 to 157,234 against a reported peak of 270,050; Spartanburg from
  256,231 to 133,428 against 183,816; Anderson from 158,516 to 82,544 against 106,940. South
  Carolina's inflation sits in other counties, so one factor under-corrects some counties and
  over-corrects these. See Q4.

## D22. Coverage table and footnotes

**What:** Gold gets a per-state coverage table: counties with EAGLE-I data, total counties (from the
NWS zone-county file in effect, `bp05mr24`), and the covered share of EIA customers,
`LEAST(calibrated EAGLE-I customers / EIA 2024 customers, 1)`. Every state ranking and regional
comparison shows coverage next to the result. States below 70% customer coverage are listed in a
footnote and not ranked.

**Why:** EAGLE-I does not track every county or utility. Comparing a fully covered state with a
partly covered one understates the second, and the reader cannot tell without the coverage figure.
Customer coverage matters more than county coverage: an untracked county with few customers barely
changes a state's picture.

**Rows affected:** 53 states and territories (50 states, DC, PR, VI). With D21 applied, **none is
below 70%**, so no state is footnoted today; 50 of 53 are at 90% or above. Lowest:

| State | EAGLE-I counties | Total counties | Customer coverage |
|---|---|---|---|
| AK | 9 | 30 | 76.5% |
| NE | 56 | 93 | 86.4% |
| DC | 1 | 1 | 89.2% |
| CO | 61 | 64 | 92.8% |
| WY | 22 | 23 | 94.5% |
| AZ | 15 | 15 | 94.7% |

Puerto Rico: EAGLE-I has 7 of 78 municipios, but these are **PREPA's 7 operating regions** filed
under the FIPS code of each region's namesake municipio: Arecibo, Bayamón, Caguas, Carolina,
Mayagüez, Ponce and San Juan. Together they hold 1.55 M customers against EIA's 1.51 M, so customer
coverage is complete but the geography is regional. The Fiona events in the top 10 (Mayagüez, Ponce,
Caguas, Arecibo) are region-level events, not single-municipio events, and findings must say so.
Per-1,000 rates for these regions are valid; county-level maps of PR are not. The US Virgin Islands
are reported by island (St. Croix, St. John, St. Thomas).

Caveat: coverage uses the D21 denominators, which are capped at EIA only above a ratio of 1.25. A
state between 1.0 and 1.25 shows 100% even if a few counties are missing.

**Implemented** (2026-11-21) as `gold_state_coverage` in `03_gold_coverage.sql`: total counties from
the latest NWS zone file in effect by 2024-12-31 (`bp05mr24`), counties with EAGLE-I data and their
calibrated customers from `dim_county_customers`, EIA 2024 customers from
`silver_eia_state_customers`, `customer_coverage` capped at 1, `ranking_eligible` (>= 70%), the
state's `calibration_factor`, and a `coverage_note` for PR (region-level data) and VI (by island).
Result: 53 rows, 0 states below 70%, lowest AK 76.5%, NE 86.4%, DC 89.2%. Hawaii shows 5 EAGLE-I
counties against 4 in the NWS file because Kalawao County (15005) has no NWS forecast zone.

## D23. EIA-861 rules

**What:**
- Customer totals from Sales to Ultimate Customers use Parts A (bundled), C (delivery-only) and D
  (bundled, other providers). Part B (energy-only) is never added.
- Reliability rankings (SAIDI, SAIFI) use only utilities reporting under the IEEE 1366 standard,
  with and without major event days. Utilities reporting under another standard are listed
  separately and never ranked together with IEEE reporters.
- There is no county-to-utility attribution. EAGLE-I is county-level, and a county is usually served
  by several utilities, so utility questions (analysis question 5) use EIA-861 only. Service
  Territory is used only to describe which counties a utility serves.

**Why:**
- In retail-choice states the same customer appears in Part B (energy supplier) and Part C (wires
  utility); B and C have identical customer totals in every year. Adding B double counts.
- IEEE 1366 and other standards define interruptions and major event days differently, so their
  SAIDI values are not comparable. No utility reports both, so there is no overlap to calibrate on.
- Service Territory lists counties by name with no shares of customers, and most counties have
  several utilities, so county outages cannot be split between utilities.

**Rows affected:**

| Year | Part B = Part C customers | IEEE SAIDI with MED | IEEE SAIDI without MED | Other standard only | Neither |
|---|---|---|---|---|---|
| 2022 | 15,423,554 | 714 | 696 | 241 | 9 |
| 2023 | 16,132,109 | 734 | 709 | 231 | 5 |
| 2024 | 17,481,113 | 746 | 730 | 222 | 6 |

- Reliability rows: 964 / 970 / 974; no row has both standards.
- Service Territory 2024: 2,876 of 3,232 counties are served by more than one utility (median 3,
  max 15).
- All Eversource and National Grid entities report under IEEE 1366: Connecticut Light & Power,
  NSTAR Electric, Public Service Co of NH, Massachusetts Electric, Nantucket Electric,
  Niagara Mohawk and Narragansett Electric.

## D24. OE-417 time zones and event types

**What:**
- OE-417 begin and restoration times are treated as **local time** of the first state listed in
  `Area Affected`, converted to UTC with that state's primary IANA time zone from
  `data/reference/state_time_zones.csv` (daylight saving time handled by the zone rules).
- An OE-417 incident matches an EAGLE-I event in its counties when the EAGLE-I start falls within
  +/-12 hours of the converted begin time. Rows without a state are not converted and not matched.
- Event types are normalized through `data/reference/oe417_event_types.csv` (committed). Key:
  lowercase, non-breaking spaces to spaces, leading dashes removed, separators unified to " - ",
  spaces collapsed. Each key maps to one of 12 categories; a combined type takes the first matching
  category in this priority: cyber, physical_attack, weather, equipment_failure, fuel_supply,
  generation_inadequacy, transmission_interruption, system_operations, vandalism_theft,
  suspicious_activity, other, unknown. "Threat of physical attack" counts as suspicious_activity.
  `multiple_types = Y` marks combined entries.

**Why:**
- The file states no time zone. Read as UTC, OE-417 begin times sit 4-6 hours before the matching
  EAGLE-I starts (most common offsets +5, +6, +4 h; `docs/data_profile_sources.md`), which fits US
  local time in the Eastern and Central zones. The first listed state is the best available
  location; states spanning two zones (for example Texas, Florida, Kentucky) can be off by one hour,
  which the +/-12 hour window absorbs.
- Event type text changed between form versions and is typed inconsistently (leading dashes,
  non-breaking spaces, a "Sever Weather" typo, several types in one cell). A committed mapping makes
  the categories reviewable and stable.

**Rows affected:** 738 OE-417 rows (390 in 2022, 348 in 2023). Event types: **49 raw variants**
(not 42, as stated in an earlier summary) collapse to 43 keys and 12 categories:

| Category | Rows |
|---|---|
| weather | 176 |
| vandalism_theft | 165 |
| suspicious_activity | 119 |
| system_operations | 105 |
| physical_attack | 53 |
| transmission_interruption | 38 |
| other | 28 |
| equipment_failure | 22 |
| cyber | 13 |
| unknown | 9 |
| fuel_supply | 6 |
| generation_inadequacy | 4 |

83 rows cannot be converted or matched: 32 have no begin date and 51 name no recognizable state.

## D25. OE-417 2024 availability and provenance

**What:** OE-417 covers 2022 and 2023 only, unless the 2024 file is added by hand. If
`data/raw/oe417/2024/` later holds the file, `scripts/download_oe417.py` verifies it and the
pipeline picks it up with no other change. Findings that use OE-417 state the years covered.

**Why:**
- The official host, `www.oe.netl.doe.gov`, publishes only an IPv6 address (AAAA
  `2620:111:a002:153::10:75`, no A record) and cannot be reached from an IPv4-only network
  (checked 2026-11-20 and 2026-11-21). `doe417.pnnl.gov` answers, but it is the filing portal for
  utilities, not the public data.
- The Internet Archive holds copies of the official 2022 and 2023 download URLs, but none for 2024.
  Archived captures of the summary page after December 2024 are HTTP 503 errors, and no download ID
  above 84 was ever captured.

**Provenance** (also recorded in `data/raw/oe417/<year>/OE417_<year>.source.txt`):

| Year | Official URL | Archive capture | Verified |
|---|---|---|---|
| 2022 | `download.aspx?type=OE417XLS&ID=82` | 2024-11-27 22:28:54 UTC (`20241127222854`) | 390 events, 2022-01-01 to 2022-12-31 |
| 2023 | `download.aspx?type=OE417XLS&ID=84` | 2024-12-19 21:18:45 UTC (`20241219211845`) | 348 rows, 316 with a begin date, 2023-01-01 to 2023-12-30 |
| 2024 | not available | none | manual download needed |

The files are the archive's raw bytes (`id_` URLs), not its HTML pages. xlrd warns that the 2022
file size is not a whole number of sectors; the file still reads completely, with events through
2022-12-31.

**Rows affected:** none removed. OE-417 has 738 rows instead of the roughly 1,100 a full three
years would hold.

## D26. SQL files for the added sources and run order

**What:** The added sources get their own files, numbered by layer as the project rules require:
`01_bronze_sources.sql`, `02_silver_sources.sql` and `03_gold_coverage.sql`. They run in this
order (`scripts/run_databricks.py`, `SQL_FILES`):

1. `01_bronze.sql`
2. `01_bronze_sources.sql`
3. `02_silver_sources.sql`
4. `02_silver.sql`
5. `03_gold_events.sql`
6. `03_gold_coverage.sql`

**Why:** The request was for the next file numbers (04, 05), but the project rules number SQL by layer
(01 Bronze, 02 Silver, 03 Gold, 04 analysis), and 04 is reserved for analysis. The order also has a
dependency: the D21 calibration in `02_silver.sql` reads `silver_eia_state_customers`, so the
source Silver file must run before it.

**Rows affected:** none.

## D27. Excel sources reach Bronze as raw-row Parquet

**What:** Databricks cannot read `.xlsx` or legacy `.xls`, so `scripts/raw_convert.py` converts the
EIA-861 workbooks and OE-417 summaries to Parquet locally. Every row of every sheet is kept in
order, with `source_name`, `sheet_name`, `row_number` and positional text columns `col_01 ..
col_NN` (30 for Reliability and Sales, 10 for Service Territory, 15 for OE-417). Headers, footers and
blank rows stay in; Silver decides what is data. The only transformation is cell type to text:
- an empty cell becomes NULL, and text is unchanged;
- whole numbers lose `.0`, and other numbers keep their round-trip text;
- date cells become `YYYY-MM-DD`;
- time-only cells become `HH:MM:SS` (OE-417 stores times as Excel times dated 1899);
- date-times become `YYYY-MM-DD HH:MM:SS`.

**Why:** This keeps Bronze as-is (D14) while making the files readable by `read_files`. Positional
columns avoid guessing header rows in Bronze, since EIA sheets have 1-3 header rows and the OE-417
header row changed name between years.

**Rows affected:** 3,042 Reliability, 8,791 Sales, 35,616 Service Territory and 742 OE-417 sheet
rows, none changed.

## D28. NOAA state code crosswalk

**What:** `data/reference/noaa_state_codes.csv` (built by `scripts/noaa_state_codes.py`, committed) maps
NOAA `STATE_FIPS` to Census state FIPS and an area type:
- **state:** the 50 states and DC, same codes as Census.
- **territory:** Puerto Rico is NOAA 99 (Census 72), and the US Virgin Islands are NOAA 96 (Census 78).
- **territory_not_tracked:** American Samoa (97) and Guam (98), which have no EAGLE-I data.
- **water:** 14 marine and Great Lakes areas (codes 81-95).

**Why:** A plain FIPS join would drop every Puerto Rico and Virgin Islands event, because NOAA does
not use Census codes for them. Water areas need to be recognized to keep them out of county tables.

**Rows affected:** 215,282 events, all mapped (0 unknown codes). 1,422 Puerto Rico and Virgin
Islands events are recovered: 1,061 county events and 361 zone events.

## D29. NOAA times to UTC

**What:** Begin and end times are built from the numeric parts (`BEGIN_YEARMONTH`, `BEGIN_DAY`,
`BEGIN_TIME`, and the same for END), which are local standard time. UTC = local - offset, where the
offset is the signed number at the end of `CZ_TIMEZONE` (`CST-6` = -6, `GST10` = +10). Daylight codes
(`EDT-4`, `CDT-5`, `PDT-7`) carry their own offset and use the same rule.

**Why:** EAGLE-I is UTC (D1), so storm-to-outage matching needs UTC. The numeric parts agree with
`BEGIN_DATE_TIME` on every row (0 mismatches, `docs/data_profile_sources.md`) and avoid parsing the
two-digit-year text format.

**Rows affected:** 215,282 events; 0 with a NULL `begin_utc`, 0 ending before they begin.

## D30. Placing NOAA events in counties

**What:**
- **County events (`CZ_TYPE = 'C'`):** county FIPS = Census state FIPS (D28) + 3-digit `CZ_FIPS`.
- **Zone events (`CZ_TYPE = 'Z'`):** expanded to every county the zone covers, using the NWS
  zone-county file in effect on the event's local begin date (`silver_nws_zone_versions`: each
  version is valid from its date until the next).
- **Not placed:** events in water areas, in territories without EAGLE-I data, or in zones absent
  from the file in effect go to `silver_storm_events_unplaced` with a reason, so they are counted
  rather than lost.

**Why:** About 46% of events are reported by zone (`docs/data_profile_sources.md`). Zones are redrawn twice a year, so the
file in effect on the event date is the right mapping (the profile showed about 1,000 fewer zone
events resolve with the latest file only). Water events can never match an EAGLE-I county.

**Rows affected:**
- 215,282 events in total; 206,558 are on land in a state or tracked territory.
- 206,526 events are placed, giving **232,414** event-county rows (115,080 county events, plus 91,446
  zone events expanding to 117,334 rows, 1.28 counties each, up to 10).
- **8,756 events are unplaced:** 8,544 in water, 180 in Guam or American Samoa, and 32 zones not in
  the file in effect (Florida 17, Illinois 14, Louisiana 1).
- 2,931 county-event rows and 5,679 zone-county rows fall in counties with no EAGLE-I data (for
  example Nebraska, D22). They stay in Silver, and the Gold match will simply find no outage there.
- Alaska county events use NOAA's own area codes (for example 02101 "Anchorage Muni to Bird Creek"),
  which are not Census county FIPS; Alaska has 9 EAGLE-I counties anyway (D22).

## D31. NOAA damage and event-level measures

**What:**
- `DAMAGE_PROPERTY` and `DAMAGE_CROPS` text (`10.00K`, `1.5M`, `2B`) becomes US dollars (K = 1e3,
  M = 1e6, B = 1e9). An empty value stays NULL, not 0: NOAA leaves it empty when no estimate was made.
- Deaths, injuries, magnitude and tornado scale are kept as reported.
- These are event-level values, so they repeat on each county row of a zone event.
  `county_count` and `event_weight = 1 / county_count` let a sum over county rows return the event
  total (`SUM(damage_property_usd * event_weight)`); summing raw values over county rows would count a
  zone event several times.

**Why:** Analysis needs numbers, not text, and must not inflate damage by expanding zones to
counties. NULL versus 0 keeps "no estimate" apart from "no damage".

**Rows affected:** 166,015 events with a property damage value and 49,267 with none (NULL);
every non-empty value parses. Totals: $53.1 bn property and $4.5 bn crops, 2022-2024.

## D32. EIA-861 Silver tables

**What:**
- Data rows are the rows whose first cell is a 4-digit year, in the sheets `Reliability_States`,
  `Reliability_Territories`, `States` and `Territories`. Other sheets (`State Totals`, `Decoupled`),
  headers and footers are skipped.
- `.` and empty mean "not reported" and become NULL.
- `reporting_standard` is `IEEE 1366` when any IEEE SAIDI or SAIFI value is present, otherwise
  `other` when any other-standard value is present. `saidi_with_med`, `saidi_without_med`,
  `saifi_with_med` and `saifi_without_med` come from that standard only (D23).
- `customers` is the Sales total for Parts A + C + D, summed over balancing authorities, for the same
  utility, state and year.
- **Size bands** by `customers`: `small` < 10,000; `medium` 10,000-99,999; `large` 100,000-499,999;
  `very_large` >= 500,000; `unknown` when the utility has no Sales row. The 500,000 cut puts every
  Eversource and National Grid operating company except Nantucket Electric (14,544, medium) into a
  peer group with other large utilities.
- `silver_eia_state_customers`: Parts A + C + D per state and year, used by D21 and D22.

**Why:** These rules follow the source layout and D23. The size bands give analysis question 5 a
like-for-like peer group.

**Rows affected:**
- `silver_utility_reliability`: 2,908 rows (964 / 970 / 974), unique per utility, state and year.
  2,204 are IEEE 1366 and 704 other-standard; 7 have no Sales customers.
- Sales data rows: 8,502, of which 5,908 are Parts A, C or D (2,594 Part B rows excluded).
- 2024 size bands: 138 small, 641 medium, 117 large, 73 very large (62 of them IEEE reporters),
  5 unknown.
- `silver_eia_state_customers`: 168 rows; the 2024 total is 165,391,292.

## D33. OE-417 Silver parsing

**What:** `silver_oe417_rows` holds one row per incident, `silver_oe417_locations` one row per state or
county named, and `silver_oe417` one row per incident with UTC times (D24) and the location lists.
- **Rows:** in each file, the header row is the one whose second cell reads `Date Event Began`.
  Non-blank rows after it are incidents. `incident_id` = report year + 4-digit row order, for
  example `2022-0001`.
- **Dates and times:** dates are `M/d/yyyy` text, ISO dates, or Excel day numbers stored as text
  (one restoration date reads `44641`, which is 2022-03-21). Times are `HH:MM:SS`. A missing time
  keeps the date at midnight, with `begin_time_reported = false`.
- **Restoration:** `restoration_status` is `reported`, `unknown` (including `- Unknown` and the
  `Unkonwn` typo), `ongoing`, `missing` or `unparsed`.
- **Customers and demand:** `customers_affected` and `demand_loss_mw` are numbers; `Unknown` and
  other text become NULL.
- **Area text:** footnote markers such as `[13]` and the ', City of' suffix of independent cities
  are removed. The text is then split on `:`, `;` and `,` into ordered tokens. A token that is a state
  name opens that state, and the tokens after it are its counties.

**Why:** These cover every format variant found in the two files, so no incident is dropped or
mis-parsed.

**Rows affected:**
- 742 sheet rows -> 738 incidents (390 in 2022, 348 in 2023). The 4 dropped rows are titles and
  headers; there are no blank rows.
- 32 incidents (all 2023) have no begin date; 75 have unknown customers.
- Restoration: 635 reported, 103 unknown.
- 939 state mentions in 700 incidents. 38 incidents name no recognizable state and get no time
  conversion.
- `begin_utc` is set for 668 incidents; the offsets applied are 4 to 8 hours.

## D34. Matching OE-417 county names to FIPS

**What:** OE-417 names counties as text, so it is the one place where names are matched. Both
sides, the OE-417 tokens and EAGLE-I county names from Bronze, are normalized the same way:
- lowercase; `&` becomes `and`; periods and apostrophes are removed; hyphens become spaces;
- `St`/`Ste` become `Saint`/`Sainte`;
- the suffixes County, Parish, Borough, Census Area, City and Borough, Municipality and Municipio
  are removed.

They then join on state + normalized name. A name that fits two EAGLE-I counties (for example
Baltimore County and Baltimore city, both named Baltimore in EAGLE-I) keeps both FIPS and is
flagged `ambiguous`.

**Why:** OE-417 has no FIPS codes. The match produces FIPS once, in Silver, so everything
downstream joins on FIPS, as the project rules require.

**Rows affected:** 1,028 county names listed. 1,026 match (1,021 exact rows, 10 ambiguous rows for
5 names), and 2 do not: Kearney and Wayne in Nebraska, counties without EAGLE-I data. 507 incidents
end up with at least one county.

## D35. Peak floor for calibrated denominators (resolves Q4)

**Amended by D36:** a peak above 1.25x the D13 denominator gives no floor; Harding SD (46063) is
therefore no longer floored, leaving 11 floored counties. The tables below are the original D35
measurements.

**What:** In the states D21 calibrates, no county's denominator may fall below its peak
`customers_out`, the highest reading EAGLE-I reported for it in 2022-2024. Counties that would fall
below are held at their peak. The remaining reduction is spread proportionally over the state's other
counties, so the state total still equals EIA-861 2024, and the process repeats until no county is
below its floor.
- Dropout readings (D19) are ignored by construction: a dropout is a fall of more than 90%, so it is
  never a county's maximum.
- The repeated process has an exact solution. The counties held at their floor are always those
  with the highest peak / D13 ratio, and the loop stops at the smallest such set for which every
  other county stays at or above its floor. `02_silver.sql` finds that set directly with window sums
  (CTEs `prefixes` and `solution`). `scripts/test_sources_duckdb.py` also runs the literal loop and
  confirms both give the same value for all 246 counties (2-3 rounds per state).
- `dim_county_customers` now has `calibration_factor` = D13 value / final value per county (the D13
  value stays derivable as `customers x calibration_factor`), `state_calibration_factor` (the D21
  state ratio), and `peak_floor_applied`.

**Why:** D21's single state factor pushed 9 counties below outages they actually reported, so their
readings were capped and flagged as overcounts. South Carolina's three largest Helene counties were
among them (Q4). A county cannot have had more customers out than it has customers, so its peak is a
hard lower bound. The state total still comes from EIA. Option C (splitting the EIA total by
EIA-861 Service Territory) is rejected: Service Territory lists which counties a utility serves but
has no customer counts per county, so it cannot split a total.

**Rows affected:** 246 counties in 5 states; **12 are held at their peak**, and the other 234 are
rescaled.

| FIPS | County | State | D13 | D21 only | D35 | Peak (UTC) | Peak / D13 | Flag |
|---|---|---|---|---|---|---|---|---|
| 15007 | Kauai | HI | 35,024 | 26,579 | 27,853 | 27,853 (2024-07-11 07:00) | 0.80 | |
| 25019 | Nantucket | MA | 6,451 | 3,200 | 5,764 | 5,764 (2022-01-29 16:30) | 0.89 | |
| 29510 | St. Louis city | MO | 107,523 | 83,281 | 83,685 | 83,685 (2023-07-02 07:00) | 0.78 | |
| 45045 | Greenville | SC | 301,949 | 157,234 | 270,050 | 270,050 (2024-09-27 22:00) | 0.89 | |
| 45083 | Spartanburg | SC | 256,231 | 133,428 | 183,816 | 183,816 (2024-09-28 21:15) | 0.72 | |
| 45007 | Anderson | SC | 158,516 | 82,544 | 106,940 | 106,940 (2024-09-27 23:45) | 0.67 | |
| 45073 | Oconee | SC | 77,419 | 40,315 | 37,716 | 37,716 (2024-09-27 15:00) | 0.49 | |
| 45081 | Saluda | SC | 28,065 | 14,614 | 15,102 | 15,102 (2024-09-28 18:30) | 0.54 | |
| 45023 | Chester | SC | 24,323 | 12,666 | 12,625 | 12,625 (2024-09-27 18:00) | 0.52 | |
| 45001 | Abbeville | SC | 20,118 | 10,476 | 9,954 | 9,954 (2024-09-28 23:30) | 0.49 | |
| 45065 | McCormick | SC | 10,529 | 5,483 | 6,369 | 6,369 (2024-10-01 23:45) | 0.60 | |
| 46063 | Harding | SD | 584 | 458 | 1,532 | 1,532 (2024-11-18 21:15) | **2.62** | possible misattribution |

The 8 South Carolina floors all fall in the Hurricane Helene days (2024-09-27 to 10-01).

Misattribution checks:
- **Peak above the uncalibrated denominator:** only Harding, SD. Its peak of 1,532 is 2.6 times its
  reported `total_customers` of 584, lasted 1.5 hours (1,532 then 1,464 for five readings), and is the
  only time it exceeded 632. That looks like another county's or utility's outage assigned to
  Harding. See Q5.
- **Isolated spike** (peak more than twice both neighbouring readings): none. Every floored peak is
  sustained; for example, Greenville spent 515 readings at or above half its peak.

Effects (DuckDB, all years; D13 = uncalibrated, D21 = uniform scaling, D35 = this rule):

| State | Events D13 / D21 / D35 | Overcount rows D13 / D21 / D35 | Customer-hours M, D13 / D21 / D35 |
|---|---|---|---|
| HI | 1,372 / 1,476 / 1,477 | 0 / 1 / 0 | 9.18 / 9.42 / 9.42 |
| MA | 1,773 / 3,020 / 3,020 | 0 / 37 / 0 | 22.47 / 26.44 / 26.45 |
| MO | 11,055 / 11,634 / 11,627 | 0 / 4 / 0 | 35.68 / 36.20 / 36.20 |
| SC | 6,805 / 8,806 / 8,742 | 0 / 1,502 / 0 | 154.24 / 145.68 / 156.13 |
| SD | 1,751 / 1,789 / 1,790 | 15 / 39 / 0 | 4.16 / 4.20 / 4.20 |

- National events: 446,331 under D21 become **446,262** (149,695 / 144,748 / 151,819). Dropouts:
  19,195 become 19,190.
- D4 overcount rows nationally: 1,878 / 369 / 9,940 under D21 become **1,818 / 365 / 8,421**,
  below even the uncalibrated 1,820 / 365 / 8,434.
- D11: counties under 1,000 customers: 41 under D21, 40 under D35 (Harding moves from 458 to 1,532).
- **Top 10:** the same storms in the same order as without calibration. Greenville is back to
  33.81 M customer-hours (27.06 M under D21) and Spartanburg to 25.64 M (22.54 M), so Spartanburg is
  #9 again ahead of Buncombe. They are 0.002% and 0.05% above the uncalibrated values, because the
  lower state factor slightly lengthens their events. The event IDs of the two SC events change
  (45045-00330, 45083-00354), because more events now precede them in those counties.

## D36. No peak floor for a likely misattributed peak (resolves Q5)

**What:** The D35 peak floor is skipped when a county's peak `customers_out` is more than 1.25 times
its uncalibrated (D13) denominator. That county gets no floor and takes the common D21/D35
rescaling of its state like any unfloored county. Raw readings are not changed; the high readings
stay in Silver and are flagged by `exceeds_customers` (D4). `dim_county_customers` gets
`peak_floor_skipped` (true for such counties in calibrated states).

**Why:** A county cannot have more customers out than customers. When a peak is well above the
county's own customer count, the more likely explanation is that a utility assigned another
county's outage to it, not that the county is larger than reported. Using such a peak as a floor
would inflate the denominator from a guess. 1.25 is the same tolerance D21 uses before calibrating a
state.
- Option A (keep the floor) is rejected: it raised Harding's denominator 2.6x from a 90-minute
  reading and moved it above the D11 ranking cutoff.
- Option C (exclude the peak in Silver) is rejected: it would delete data based on a guess. D36
  leaves the readings in place, visible and flagged, and only declines to build a denominator on
  them.

**Rows affected:** one county; 11 counties keep their D35 floor.

| FIPS | County | D13 | D35 (floored) | D36 | Below D11 cutoff of 1,000 |
|---|---|---|---|---|---|
| 46063 | Harding, SD | 584 | 1,532 | **458** | **yes**, excluded from per-1,000 rankings again |

- South Dakota now has no floored county, so every SD county equals its D21 value.
- Harding keeps all 39 readings above 458 flagged by `exceeds_customers` (6 of them from the
  2024-11-18 spike, peak 1,532). South Dakota overcount rows are 39, as under D21.
- D11: 41 counties below 1,000 (40 under D35).
- National: 446,261 events (149,695 / 144,747 / 151,819), 19,190 dropouts, overcount rows
  1,841 / 365 / 8,437.
- **Top 10:** unchanged from D35, the same storms in the same order as without calibration.
- Counties outside the calibrated states can also have a peak above 1.25x their denominator. D36
  does not affect them, because only calibrated states have floors; their readings are flagged by
  `exceeds_customers` as before. An earlier count of them used different criteria and is
  superseded: the list is `q2_possible_misattributions` (39 counties, 2022-2024 peaks), and
  `q2_misattribution_recount` counts it by first reported year.

## D37. Matching outage events to NOAA storms (resolves Q3)

**Amended by D41 and D42:** `storm_type` is now the most severe storm active at the outage start
(largest overlap only as a fallback), and the window closes 1 hour after NOAA's end. The tables below
are the original D37 measurements.

**What:** `gold_event_storm_match` (`03_gold_storm_match.sql`) gives every outage event one row:
- **Candidates:** storms in `silver_storm_events` in the same county (`fips_code`) whose window
  overlaps the outage. A storm's window opens 12 hours before its NOAA begin time and closes at its
  NOAA end time.
- **Only outage-causing types are candidates.** `data/reference/storm_event_severity.csv` (built by
  `scripts/storm_event_severity.py`, committed) lists all 54 NOAA event types. 32 can cause outages
  and 22 cannot: Drought, Dense Fog, Freezing Fog, Dense Smoke, Frost/Freeze, Funnel Cloud, High
  Surf, Rip Current, Sneakerwave, Astronomical Low Tide, Dust Devil, Volcanic Ashfall, Waterspout,
  and the 9 marine types.
- **Best match = largest overlap in hours.** Ties go to the more severe type, then the lower NOAA
  event id. Severity order (`severity_rank`, most severe first):
  1. tropical cyclones (Hurricane, Tropical Storm, Storm Surge/Tide, Tropical Depression);
  2. Tornado;
  3. ice and snow (Ice Storm, Blizzard, Winter Storm, Heavy Snow, Lake-Effect Snow, Sleet);
  4. wind (Thunderstorm Wind, High Wind, Strong Wind, Dust Storm);
  5. Wildfire;
  6. flooding (Flash Flood, Flood, Coastal Flood, Lakeshore Flood, Debris Flow, Heavy Rain,
     Tsunami, Seiche);
  7. Lightning, Hail;
  8. temperature (Excessive Heat, Heat, Extreme Cold/Wind Chill, Cold/Wind Chill, Winter Weather);
  9. Avalanche.
- **Outputs:** `storm_type` is the best match, or `unmatched`. The table also keeps
  `most_severe_storm_type` (the most severe overlapping storm), `overlap_hours` and
  `candidate_storms`.

**Why:**
- The window has to reach before NOAA's begin time because outages often start before a storm is
  logged in that county.
- Overlap with the whole outage, rather than only its start, catches long restorations.
- Drought (median NOAA duration 720 hours) and similar background conditions would otherwise
  overlap almost every outage in their county and win on overlap length without causing it.
- `most_severe_storm_type` is kept because largest overlap can pick a long flood record over a
  shorter tropical storm record in the same window (Q6).

**Rows affected (DuckDB, all years):** 446,261 events.

| Year | Matched events | Share of events | Share of customer-hours |
|---|---|---|---|
| 2022 | 14,566 | 9.7% | 56.2% |
| 2023 | 15,631 | 10.8% | 63.1% |
| 2024 | 15,262 | 10.1% | 62.3% |

Most outage events are short, local and unmatched (median 1.5 hours). Matched events carry 61% of
all customer-hours. By matched type, customer-hours (all years):

| Storm type | Events | Customer-hours (M) |
|---|---|---|
| Thunderstorm Wind | 8,812 | 347.9 |
| Tropical Storm | 922 | 286.3 |
| Hurricane (Typhoon) | 94 | 275.1 |
| Flood | 2,466 | 248.7 |
| High Wind | 3,274 | 177.7 |
| Flash Flood | 3,258 | 158.8 |
| Winter Storm | 3,578 | 136.7 |
| Ice Storm | 456 | 111.1 |

2,556 matched events (631.4 M customer-hours) have a best match that is not their most severe
overlapping storm.

Top 10 events:

| Rank | County | Start | Storm type (best) | Most severe overlapping |
|---|---|---|---|---|
| 1 | Harris TX (Beryl) | 2024-07-08 | unmatched | none |
| 2 | Mayagüez PR (Fiona) | 2022-09-17 | unmatched | none |
| 3 | Lee FL (Ian) | 2022-09-28 | Hurricane (Typhoon) | Hurricane (Typhoon) |
| 4 | Ponce PR (Fiona) | 2022-09-18 | Debris Flow | Flash Flood |
| 5 | Caguas PR (Fiona) | 2022-09-18 | Flash Flood | Flash Flood |
| 6 | Arecibo PR (Fiona) | 2022-09-17 | unmatched | none |
| 7 | Pinellas FL (Milton) | 2024-10-09 | Hurricane (Typhoon) | Hurricane (Typhoon) |
| 8 | Greenville SC (Helene) | 2024-09-27 | Flood | Tropical Storm |
| 9 | Spartanburg SC (Helene) | 2024-09-27 | Flood | Tropical Storm |
| 10 | Buncombe NC (Helene) | 2024-09-27 | Flood | Tropical Storm |

**Q3 breakdown.** The top 100 events by customer-hours matched NOAA 61% of the time under the profile
rule (any NOAA event active from 24 hours before to 2 hours after the outage start). Under D37 they
match **83%**. The 17 that remain:

| Cause | Events | Change made |
|---|---|---|
| Time window | 9 | **Changed:** the D37 window covers the whole outage and opens 12 h before the storm; this is what moved the rate from 61% to 83%. Left as specified: 3 events start 0.3-0.4 h after a NOAA report ends (Douglas NE, Wayne MI, Lake OH), and 6 more are 14-42 h after a storm or within days of one. An end allowance would catch the first 3 (Q7). |
| Coverage | 5 | **Left:** NOAA's file has no storm record at all for Harris, Montgomery, Fort Bend, Brazoria or Galveston during Beryl (2024-07-08, 192.5 M customer-hours together). Beryl is recorded only in neighboring offices' counties. A match cannot create missing records; findings will say that Beryl is unmatched because of a NOAA gap. |
| Geography | 3 | **Left:** Mayagüez and Arecibo are PREPA regions (D22). NOAA logs Fiona in other municipios of those regions, and our sources have no municipio-to-region list to bridge them. NOAA also has no hurricane-type record for Fiona in Puerto Rico, only Flash Flood, Flood, Debris Flow and Thunderstorm Wind. The third, San Juan on 2024-12-31, is most likely the island-wide blackout of that date, not a storm; it cannot be confirmed because OE-417 2024 is missing (D25). |
| Labels | 0 | **Changed:** non-causal types are excluded; this did not change the top-100 rate (83 either way). The overlap-versus-severity choice is left as specified, with `most_severe_storm_type` kept alongside (Q6). |

## D38. State and county reliability

**Amended by D43:** Puerto Rico and the Virgin Islands are no longer ranked with the states; they are
reported in `gold_territory_reliability`. The state table below is the original D38 measurement.

**What:** `gold_county_reliability` and `gold_state_reliability` (`03_gold_reliability.sql`):
- **Metric:** `outage_hours_per_1000_customers` = customer-hours lost (capped by the denominator,
  D4) x 1,000 / customers, using the calibrated one-per-county denominator (D13, D21, D35, D36).
- **Year:** an event counts in the year it starts.
- **Counties:** every county with EAGLE-I data appears in every year; a year without events counts
  as 0.
- **States:** the numerator uses only counties with a denominator (D9); `customer_hours_lost`
  keeps the raw total.
- **Ranking:** `RANK()`, where 1 = most outage hours per 1,000 customers and ties share a rank.
  Counties are ranked nationally and within their state, and only when their denominator is at
  least 1,000 (D11) and their state is ranking-eligible (D22). States are ranked nationally and
  within their Census region, and only when ranking-eligible (D22).
- **State output:** each state row carries D22 coverage (`eaglei_counties`, `total_counties`,
  `customer_coverage`).
- **Territories:** Puerto Rico rows say they are the 7 PREPA operating regions, not municipios;
  Virgin Islands rows say they are by island. PR and VI are ranked with the states (Census region
  'Territory').

**Why:** Per-1,000 rates make places of different size comparable (project rule). One denominator per
county keeps year-to-year changes about outages (D13). RANK keeps ties honest.

**Rows affected:** 9,189 county-year rows (3,063 counties x 3 years); 3,020 ranked per year (2 have no
denominator, 41 are under 1,000). 159 state-year rows (53 x 3), all ranking-eligible.

| Year | #1 | #2 | #3 | Highest of the 50 states and DC |
|---|---|---|---|---|
| 2022 | PR (186,176 h per 1,000) | VI (42,494) | ME (19,716) | Maine |
| 2023 | VI (39,899) | ME (35,355) | PR (29,135) | Maine |
| 2024 | VI (118,383) | PR (74,642) | SC (46,619) | South Carolina |

County #1: 2022 Mayagüez PR (the PREPA region), 2023 Austin TX, 2024 Yancey NC (Helene).
Territories top the state ranking every year (Q8).

## D39. Utility reliability rankings

**What:** `gold_utility_reliability` ranks EIA-861 utilities that report under IEEE 1366; utilities
reporting under another standard go to `gold_utility_reliability_other` (704 rows), listed and not
ranked (D23).
- **Ranks:** SAIDI and SAIFI, with and without major event days, each ranked with `RANK()` within
  data year and size band (D32). 1 = lowest value = most reliable. `rank_saidi_without_med` is the
  primary comparison, since major event days are what the storm analysis covers separately.
- **Not ranked:** rows in the `unknown` size band (no Sales customers; 3 per year), and rows with a
  NULL metric for that particular rank.
- **Flags:** `parent_company` and `is_eversource_or_national_grid`, by EIA utility number:
  - Eversource: Connecticut Light & Power (4176), NSTAR Electric (54913), Public Service Co of NH
    (15472).
  - National Grid: Massachusetts Electric (11804), Nantucket Electric (13206), Niagara Mohawk
    (13573).
  - Narragansett Electric (13214) is flagged only for 2022, as 'National Grid (sold to PPL in May
    2022)'. The sale date is public record; verify it before publishing.
- **Source-error check:** a row that repeats another utility's full metric set in the same year, and
  whose reliability customer count is more than 10% off its own Sales customers, is kept with a
  `data_quality_flag` and not ranked.

**Why:** IEEE and other-standard values are not comparable (D23). Size bands compare like with like
(analysis question 5). The source-error check catches one EIA error: in EIA-861 2023, NSTAR's row
repeats Connecticut Light & Power's values exactly, including CL&P's customer count (1,307,124 against
NSTAR's own 1,515,653 Sales customers). It is the only such duplicate in the three years.

**Rows affected:** 2,204 IEEE rows; 1 flagged (NSTAR 2023). Ranks within the very-large band, SAIDI
without MED (and with MED):

| Company | 2022 (of 62) | 2023 (of 64) | 2024 (of 62) |
|---|---|---|---|
| NSTAR Electric (Eversource) | 12 (31) | flagged | 11 (6) |
| Connecticut Light & Power (Eversource) | 14 (30) | 15 (29) | 16 (19) |
| Public Service Co of NH (Eversource) | 17 (52) | 20 (54) | 19 (49) |
| Massachusetts Electric (National Grid) | 29 (17) | 28 (41) | 25 (15) |
| Niagara Mohawk (National Grid) | 45 (44) | 43 (33) | 43 (44) |
| Narragansett Electric (National Grid until May 2022) | 9 (7) | - | - |

Nantucket Electric is in the medium band: 219 of 474 (2022), 95 of 484 (2023), 113 of 496 (2024).

## D40. OE-417 check against EAGLE-I

**What:** `gold_oe417_check` (`03_gold_oe417_check.sql`), one row per OE-417 incident:
- **Match:** an incident matches when an EAGLE-I event in one of its matched counties (D34) starts
  within +/-12 hours of the incident's UTC begin time (D24).
- **Statuses:** `matched` or `not matched`; `no county` (no county matched, so no county-level check
  is possible); `no time` (no begin date or no state).
- **Bands:** `customers_band` groups the reported customers: 0, 1-999, 1,000-9,999, 10,000+, unknown.
- **Detail:** the closest event (by start time) and the summed county peaks are kept for comparison.

**Why:** OE-417 is a utility's own report of an incident. Agreement with EAGLE-I shows how far each
source can be trusted. State-only incidents are not checked: any large state has an EAGLE-I event
almost every day (`docs/data_profile_sources.md`), so a state-level match would mean nothing.

**Rows affected:** 738 incidents: 180 matched, 303 not matched, 185 no county, 70 no time.

| Customers affected | Checkable | Matched | Agreement |
|---|---|---|---|
| 10,000+ | 75 | 62 | 82.7% |
| 1,000-9,999 | 28 | 21 | 75.0% |
| 1-999 | 11 | 5 | 45.5% |
| 0 | 331 | 76 | 23.0% |
| unknown | 38 | 16 | 42.1% |

| Category | Checkable | Matched | Agreement |
|---|---|---|---|
| weather | 77 | 61 | 79.2% |
| equipment_failure | 5 | 4 | 80.0% |
| system_operations | 72 | 35 | 48.6% |
| cyber | 11 | 4 | 36.4% |
| transmission_interruption | 28 | 8 | 28.6% |
| physical_attack | 43 | 12 | 27.9% |
| vandalism_theft | 128 | 35 | 27.3% |
| suspicious_activity | 98 | 18 | 18.4% |

Incidents with customer impact agree well (75-83% at 1,000+); incidents with no customers out (most
vandalism and suspicious activity) rarely appear in EAGLE-I, as expected. For the 83 matched incidents
with 1,000+ customers, EAGLE-I's summed county peak is a median 0.86 of the OE-417 count, and the
closest event starts a median 0.1 hours from the OE-417 time, which supports D24's local-time reading.

## D41. Storm attribution: the storm active when the outage began (resolves Q6)

**What:** `gold_event_storm_match.storm_type` is the storm active when the outage began.
- Among the candidate storms whose window covers the outage's `event_start` (D37 window, as extended
  by D42), the most severe type wins (D37 severity order), then the largest overlap, then the lower
  NOAA event id.
- If no storm covers the start, the D37 rule applies unchanged: largest overlap, ties to the more
  severe type.
- `attribution_rule` records which applied (`active_at_start` or `largest_overlap`).
  `most_severe_storm_type` stays a separate column (the most severe storm overlapping the outage at
  any point).

**Why:** Largest overlap favors long records. Flood and flash-flood entries often run for a day or
more, while a tropical storm or wind record for the same county lasts a few hours, so the cause of the
outage lost to its aftermath. The storm active at the start is what took the power out. Falling back
to the largest overlap keeps a match for outages that begin before any storm window, such as outages
already under way when NOAA's record begins more than 12 hours later.

**Rows affected (with D42):**
- 53,952 matched events are attributed by `active_at_start` (2,074.2 M customer-hours), and 1,651
  by the `largest_overlap` fallback (289.1 M).
- Of the 45,459 events matched both before and after, **3,647 change type** (616.5 M customer-hours).
  The largest changes:

| Before (D37) | Now | Events | Customer-hours (M) |
|---|---|---|---|
| Flood | Tropical Storm | 26 | 171.7 |
| Thunderstorm Wind | Tornado | 328 | 74.3 |
| Flash Flood | Thunderstorm Wind | 659 | 44.4 |
| Flood | High Wind | 64 | 34.5 |
| Excessive Heat | Thunderstorm Wind | 224 | 34.5 |
| Storm Surge/Tide | Hurricane (Typhoon) | 5 | 21.9 |

- Matched events whose storm type differs from `most_severe_storm_type` fall from 2,556 (631.4 M
  customer-hours) to 396 (127.7 M).
- **Top 10:** Greenville SC, Spartanburg SC and Buncombe NC (Helene) change from Flood to **Tropical
  Storm** (`active_at_start`). Lee FL and Pinellas FL stay Hurricane (Typhoon). Ponce PR (Debris Flow)
  and Caguas PR (Flash Flood) keep their D37 match through the fallback. Harris TX, Mayagüez PR and
  Arecibo PR remain unmatched (D37: no NOAA record or PREPA-region geography).

## D42. Storm window closes 1 hour after NOAA's end time (resolves Q7)

**What:** Every storm window in the match now runs from 12 hours before NOAA's begin time to 1 hour
after NOAA's end time (D37 closed it at the end time).

**Why:** Many NOAA reports are instantaneous (a wind gust or hail report with begin = end). An outage
that crosses its threshold 15-45 minutes after such a report never overlapped it, although the report
plainly describes its cause. One hour covers that lag. Three hours added little more (Q7: 58,938
matched against 55,603 at one hour), so the shorter allowance is kept to limit coincidental matches.

**Rows affected:**

| Year | Matched before | Matched now | Added |
|---|---|---|---|
| 2022 | 14,566 | 17,823 | 3,257 |
| 2023 | 15,631 | 19,332 | 3,701 |
| 2024 | 15,262 | 18,448 | 3,186 |

Matched events carry 59.3% / 70.2% / 65.7% of customer-hours by year (from 56.2% / 63.1% / 62.3%).
**Top 100:** 83 to **86** matched; the three added are the outages that began 0.3-0.4 h after a
storm report ended (Douglas NE, Wayne MI, Lake OH; D37 Q3 table). The other 14 unmatched top-100
events are unchanged in cause (D37).

## D43. State rankings cover the 50 states and DC; territories reported separately (resolves Q8)

**Extended by D44** to county rankings.

**What:**
- `gold_state_reliability` now holds only the 50 states and DC. National and Census-region ranks are
  computed among them.
- Puerto Rico and the US Virgin Islands move to `gold_territory_reliability`, with the same metrics
  (events, customer-hours, customers, outage hours per 1,000 customers, coverage), the number of
  reporting units, the geography note, and no rank.
- County rankings (`gold_county_reliability`) were unchanged by D43; D44 applies the same rule to them.

**Why:** Puerto Rico's 7 reporting units are PREPA operating regions and the Virgin Islands report by
island (D22). Their grids are islanded, and their storm exposure differs in kind. Ranking them with the
states put a territory at #1 every year and pushed the comparison the project is about, between
states, down the table.

**Rows affected:** `gold_state_reliability` 159 to 153 rows (51 x 3 years); `gold_territory_reliability`
6 rows.

| Year | New #1 state | Outage hours per 1,000 customers | Earlier rank |
|---|---|---|---|
| 2022 | Maine | 19,716 | 3 (behind PR, VI) |
| 2023 | Maine | 35,355 | 2 (behind VI) |
| 2024 | South Carolina | 46,619 | 3 (behind VI, PR) |

Territories, outage hours per 1,000 customers: PR 186,176 / 29,135 / 74,642 and VI 42,494 / 39,899 /
118,383 (2022 / 2023 / 2024).

## D44. County rankings cover the 50 states and DC; territory units reported separately

**What:**
- `gold_unit_reliability` (new) computes outage hours per 1,000 customers for every EAGLE-I reporting
  unit and year, unranked, with the D38 metric and eligibility rules.
- `gold_county_reliability` now selects only units in the 50 states and DC from it and ranks them
  (national and within state, D38).
- Puerto Rico's 7 PREPA operating regions and the Virgin Islands' 3 island districts move to
  `gold_territory_unit_reliability`: the same metrics, with the reporting unit, its customers and a
  geography note, and no rank.
- `gold_state_reliability` and `gold_territory_reliability` now aggregate from `gold_unit_reliability`;
  their values are unchanged.

**Why:** This is the rule of D43 applied to counties. A PREPA region holds 68,000-395,000 customers
across several municipios, and a Virgin Islands district is a whole island with its own grid.
Neither is a county, so ranking them with counties compares unlike units: in 2022 the five top
"counties" were all PREPA regions.

**Rows affected:** 30 rows moved (10 units x 3 years). `gold_county_reliability` goes from 9,189 to
9,159 rows, and ranked counties per year from 3,020 to 3,010. Every remaining county keeps its values;
only ranks change.

New top 5 counties (outage hours per 1,000 customers):

| Year | 1 | 2 | 3 | 4 | 5 |
|---|---|---|---|---|---|
| 2022 | Charlotte FL (123,103) | Franklin city VA (114,868) | Lee FL (102,091) | Hamilton NY (91,128) | Alcona MI (87,241) |
| 2023 | Austin TX (117,505) | Marion TX (115,955) | Mono CA (115,687) | Del Norte CA (107,263) | Madison FL (101,007) |
| 2024 | Yancey NC (497,902) | Mitchell NC (387,703) | Atkinson GA (352,557) | Jeff Davis GA (305,017) | Appling GA (226,341) |

Only 2022 changes: Mayagüez, Ponce, Caguas, Arecibo and Carolina (PREPA regions) held ranks 1-5.
Charlotte FL, Franklin city VA, Lee FL, Hamilton NY and Alcona MI move up from ranks 6, 7, 8, 10 and
11 (Bayamón held rank 9). In 2023 and 2024 no territory unit was in the top 5; the highest were St. John
VI at 17 (2023) and 12 (2024).

## D45. Footnote county-years whose rate rests on capped, implausible readings

**What:** A county-year is footnoted instead of ranked when both hold:
- more than 25% of its customer-hours come from readings above its customers, which D4 caps
  (`capped_share`);
- its peak customers out is more than 3 times its customers (`peak_to_customers`).

`capped_share` is measured over the readings inside each of the county's events at or above the
event threshold; it matches Gold customer-hours to 0.01%. `gold_county_reliability` gets
`capped_customer_hours`, `capped_share`, `peak_to_customers`, `footnote_reason`, `footnote_evidence`
and `rank_without_footnotes`. `ranking_eligible` is now true only when there is no footnote reason.
Footnoted county-years stay in every raw total (state and territory totals are unchanged) and
appear in `gold_county_ranking_footnotes` with the rank they would have had.
`gold_county_ranking_footnotes` also lists the county-years that were already unranked: no
denominator (D9), under 1,000 customers (D11), or below 70% state coverage (D22; none today).

**Why:** A large capped share can mean either of two things:
- **Misattribution:** a utility's outage assigned to the wrong county. The peak is then many times
  the county's customers (Austin TX 2024 at 12.5x, Waller TX 2024 at 6.2x).
- **Real damage with a small denominator:** the Helene counties of western North Carolina and
  Georgia have peaks of only 1.3-1.8x their customers.

Capped share alone would footnote the second group (25%: Yancey, Mitchell and Atkinson, the 2024
top 3). The peak condition limits the rule to the first group.

**Rows affected:** 6 county-years.

| Year | County | Would have ranked | Evidence |
|---|---|---|---|
| 2022 | Rich, UT (49033) | 192 | capped share 71.6%, peak 3.7x customers |
| 2023 | Rich, UT (49033) | 257 | capped share 56.6%, peak 3.9x customers |
| 2024 | Austin, TX (48015) | 7 | capped share 64.9%, peak 12.5x customers |
| 2024 | Waller, TX (48473) | 8 | capped share 68.2%, peak 6.2x customers |
| 2024 | Rich, UT (49033) | 308 | capped share 72.4%, peak 4.0x customers |
| 2024 | Cochise, AZ (04003) | 2,619 | capped share 34.2%, peak 8.8x customers |

Ranked counties per year: 3,010 before D45 in each year, now 3,009 (2022), 3,009 (2023) and 3,006 (2024). The top 5 of every
year is unchanged. `gold_county_ranking_footnotes`: 135 rows (123 D11, 6 D9, 6 D45).

## D46. Reviewed ranking exclusions

**What:** `data/reference/ranking_exclusions.csv` (committed) lists county-years excluded from rankings
after review, with columns `fips_code`, `year`, `county`, `state`, `reason`, `evidence`, `reviewed_on`.
`gold_county_reliability` reads it (`bronze_ranking_exclusions`). A listed county-year gets
`footnote_reason` 'reviewed exclusion (D46): <reason>' with its evidence, stays in raw totals and
appears in the footnote list.

**Entry criteria:** a county-year enters the file only when its large readings track a much larger
neighbouring county at a stable ratio across several separate events, measured with
`scripts/exclusion_evidence.py`:
- the neighbour is adjacent (stated in the evidence; adjacency is not in the data) and has at least
  10 times the county's customers;
- at least 500 15-minute readings where the county had 1,000+ customers out and the neighbour more
  than 0;
- at least 3 separate EAGLE-I events of the county, each with 20+ such readings;
- the coefficient of variation of the per-event median ratio (county / neighbour) is at most 0.25.

A fixed share of one large neighbour's outages, repeated across separate events, is how a utility's
system-wide count split across counties would look. Shared storms produce strong correlation but
not a stable ratio, so correlation alone is not enough (the Helene counties correlate 0.84-0.97 with
their neighbours).

**Why:** Some misattribution is visible only as a pattern, not as a single implausible reading, and
should be decided case by case with evidence, not by a threshold tuned to one county. A committed,
reviewed file keeps every exclusion visible and reversible.

**Review of Austin TX 2023 (rank 1):** stability measured on readings with Austin at 1,000+ customers
out:

| Pair | Readings | Events (20+ readings) | Median ratio | CV over readings | CV between events (event medians) |
|---|---|---|---|---|---|
| Austin TX 2023 vs Harris (not adjacent) | 969 | 66 (7) | 0.251 | 4.29 | 0.68 (0.14-0.77) |
| Austin TX 2023 vs Fort Bend (adjacent) | 969 | 66 (7) | 0.790 | 4.71 | 0.63 (0.41-2.08) |
| Austin TX 2024 vs Harris | 1,164 | 34 (9) | 0.275 | 6.64 | 1.86 |
| Austin TX 2024 vs Fort Bend | 1,152 | 33 (9) | 3.521 | 7.34 | 2.04 |
| Waller TX 2024 vs Harris (adjacent) | 1,351 | 54 (8) | 0.224 | 20.01 | 0.56 |
| Yancey NC 2024 vs Buncombe | 3,255 | 3 (2) | 1.873 | 3.17 | 1.17 |
| Mitchell NC 2024 vs McDowell | 2,293 | 6 (1) | 1.611 | 7.25 | n/a (1 event) |
| Madison NC 2024 vs Buncombe | 1,024 | 2 (1) | 0.028 | 2.04 | n/a (1 event) |
| Atkinson GA 2024 vs Coffee | 1,823 | 12 (2) | 0.443 | 9.59 | 0.67 |

**Outcome: Austin TX 2023 stays ranked (#1).** Its event-to-event CV (0.68 against Harris, 0.63
against Fort Bend) is far above 0.25, and as high as Atkinson GA's (0.67), whose Helene damage is real.
Austin's share of Harris's outages ranged from 14% to 77% between events, which is not a fixed
allocation. Harris is also not adjacent to Austin (Waller lies between). The earlier correlation (0.95)
comes from shared Houston-area storms. No pair in the table meets the criteria; the misattribution
cases of 2024 are caught by D45 instead. The file starts with a header only.

**Rows affected:** none today (0 entries).

## D47. Every tunable value lives in config/pipeline.yml

**What:** `config/pipeline.yml` holds every value a reviewer might tune: years; catalog, schema and
volume; the D12 mismatch ratio; the D21 calibration ratio, its EIA year and the D36 peak-skip ratio;
the D18 threshold share, the 100-customer floor and the 10,000-customer outage requirement; the
D17 gap rule; the D19 dropout shares and recovery window; the D22 coverage minimum; the D11 ranking
floor and the 51 ranked jurisdictions (D43); the D37/D42 storm window; the D40 OE-417 window and
bands; the D45 footnote thresholds; the D46 entry criteria; the D32 size bands and D39 utility
lists; quality tolerances and expected row counts (D48); export settings (D49).

The SQL files reference values as `${section.key}`. `scripts/pipeline_config.py` loads and validates
the file (types and ranges, so a typo fails before any SQL runs), adds derived values (volume path,
gap rule in 15-minute runs, percentage labels) and substitutes them before a statement is sent to
Databricks or translated for DuckDB. A placeholder without a value stops the run. The tests and
scripts (`run_databricks.py`, the DuckDB tests, `exclusion_evidence.py`, the download and profile
scripts, the sensitivity test's 10,000-customer check) read the same file.

**Not in the config, on purpose:** constants that define the data rather than tune it: the 15-minute
EAGLE-I collection run (`RUN_MINUTES`, and the 0.25 hours per reading that follows from it), the
per-1,000 normalisation, 5-digit FIPS, the Excel date epoch, NOAA's K/M/B damage suffixes. The
per-year Bronze statements also stay in `01_bronze.sql`, because the EAGLE-I column layout differs
by year (D2); the runner stops if a configured year has no Bronze statement.

**Why:** Thresholds were spread across nine SQL files and several scripts; changing one meant finding
every copy (the D18 share was also parsed out of the SQL by regex). One validated file makes each
rule visible, reviewable and changeable in one place.

**Rows affected:** none. With the current values, every rendered SQL statement is identical to the
previous SQL apart from comments (checked file by file), and the DuckDB and Databricks runs
reproduce every row count and the top 10 events.

## D48. Data quality gates after each layer

**What:** `sql/databricks/90_quality_checks.sql` holds 109 checks in three sections (Bronze, Silver,
Gold). Each statement returns `layer, check_name, observed, expected, passed`. The checks:
- row counts of all 43 tables within 1% of the verified run (`quality.row_count_tolerance`; exact
  match since D50);
- no duplicate or NULL primary keys in every Silver and Gold table;
- valid ranges: `customers_out >= 0`, 5-digit FIPS, readings on the 15-minute grid, years in the
  config, positive durations and reading counts, capped customer-hours <= raw, shares and coverage
  between 0 and 1, storm `event_weight` in (0, 1], no negative SAIDI/SAIFI;
- the event rules: every threshold >= the floor and < 10,000 (D18), dropouts inside the D19 rule,
  no overlapping events in a county, and every qualifying reading in exactly one event (each reading
  falls inside the latest event that started at or before it, and the event reading counts add up
  to the qualifying readings);
- calibrated state totals equal the EIA-861 totals within half a customer per county (rounding,
  D21), and no calibrated county below its peak unless D36 skipped its floor (D35);
- rankings hold only the 50 states and DC and no county under 1,000 customers (D11, D43, D44);
- every unranked county-year has a footnote reason, D45/D46 footnotes have evidence, D45 rows meet
  both thresholds, and the footnote list matches the unranked rows (D45, D46);
- referential integrity between facts and dimensions on FIPS, event, storm and incident keys.

`scripts/quality_checks.py` runs the checks on Databricks or on a local DuckDB build. The pipeline
runner runs each layer's section right after that layer's SQL files; a failed check stops the run
before the next layer is built. Every result row is appended to `gold_quality_results` with the run
timestamp (DuckDB runs write `logs/quality_results_<timestamp>.csv`).

**Why:** Until now the runner compared row counts and a few fixtures only after everything was built.
Checking each layer's invariants before the next is built stops a bad load from reaching the
rankings, and the results table keeps a history of every run.

The gates were tested by injecting faults into a local build (a deleted event, a raised threshold,
a county moved below its peak, a removed footnote reason, territory rows given a rank): each fault
failed its check.

**Rows affected:** none; all 109 checks pass in DuckDB and on Databricks.

## D49. Run logging, Makefile and Power BI export

**What:** The runners log each step (start time, duration, row count, status) to
`logs/<run>_<timestamp>.log` (gitignored) and print a summary table. A Makefile runs the project with
`setup`, `download`, `profile`, `test`, `pipeline`, `quality`, `export`, `all` and `clean` (README,
Setup). `scripts/export_gold.py` writes the tables in `export.tables` to `data/gold_exports/`; a table
whose CSV would exceed 50 MB is written as one file per year (`gold_outage_events` and
`gold_event_storm_match` are about 33 MB and 18 MB per year). The CSVs are not committed (D50).

**Why:** One command rebuilds everything from a fresh clone, and the logs show where time goes and
what each step produced.

**Rows affected:** none.

## D50. Gold exports stay out of git; row counts must match exactly

**What:** (1) I do not commit the Gold CSV exports. A full export is about 190 MB, most of it
`gold_outage_events` and `gold_event_storm_match`, which would bloat the repo even with every file
under 50 MB. `data/gold_exports/*.csv` is gitignored. Later, the large tables will be exported as
Parquet and attached to a GitHub Release, and only small summary tables will be committed.
(2) `quality.row_count_tolerance` is 0: every table's row count must equal `quality.expected_rows`.

**Why:** Release assets keep the repo small while still giving Power BI a download. The expected
row counts are a contract, not an estimate: the pipeline is deterministic, so any difference means
the data or logic changed, and I update the expected counts deliberately when that happens. A 1%
tolerance would have let more than 250,000 rows of one Bronze year go missing silently.

**Rows affected:** none; all 109 checks still pass with exact counts.

## D51. Continuous integration: a real-data test fixture, pytest, linting

**What:**
- **Fixture.** `tests/fixtures/` holds a 392 KB sample of real rows, copied unchanged from
  `data/raw/` by `scripts/build_test_fixture.py`: EAGLE-I readings of 13 counties in five windows
  (the Harris 2024-07-10 dropout, the 2024-05-24 nationwide feed gap, the 2023-03-22 20:31 run,
  Rich UT's capped readings, a Harris event matched by OE-417), one reading each for Kalawao HI and
  Norton city VA, and the matching MCC, NOAA, NWS zone, EIA-861 and OE-417 rows. All five Hawaii
  counties are included so the D21 calibration and Kauai's D35 floor equal the full-data values;
  Utah's five largest counties hold 75% of its EIA customers so Utah is ranked (D22). Sources are
  credited in `tests/fixtures/README.md` (EAGLE-I is CC BY 4.0). The fixture keeps every selected
  NOAA event with its narrative unchanged; the commit word scan treats files copied from public
  sources as data (see the hygiene scope below).
- **Real SQL in DuckDB.** `scripts/duckdb_pipeline.py` renders every file in the Databricks run
  order from `config/pipeline.yml`, splits it exactly as `run_databricks.py` does and runs each
  statement in DuckDB: session statements are skipped, Bronze `read_files()` reads the matching
  local files with the statement's own path, header, separator, encoding and column names,
  `INSERT OVERWRITE` becomes `DELETE` + `INSERT`, and queries go through `sql_dialect.py`, which
  now also translates `RLIKE`. Silver `silver_outages` is therefore tested from `02_silver.sql`
  itself, not from the hand-written steps of `test_silver_duckdb.py`.
- **pytest.** `tests/` asserts exact results on the fixture: row counts of all 43 tables
  (`tests/fixtures/expected_rows.yml`), denominators, D7 flooring, D4 flags, D18 thresholds, the
  feed gap, all 13 dropouts, all 27 events, storm attribution, coverage, county and state ranks,
  ranking footnotes (D9, D11, D22, D45), utility ranks with the D39 flag, the OE-417 check, and all
  109 quality gates (row counts compared with the fixture's counts through a config override).
  Rules real data never exercises are checked with synthetic rows through the same SQL: D7
  dedupe and D15 drops, the event boundaries of D3/D4/D17/D18/D19, D41/D42 storm windows, and D36
  via `calibration.peak_skip_ratio = 0.79`, which leaves Kauai at 26,579, its D21-only value. The
  full-data scripts run as `@pytest.mark.slow` tests, skipped when `data/raw/` is absent.
  `scripts/test_config.py` moved into `tests/test_config.py`.
- **Linting.** ruff (line length 140; rules E, F, W, I, UP, B, SIM) and sqlfluff (Databricks
  dialect). sqlfluff's placeholder templater fills each `${...}` with its value from
  `config/pipeline.yml`; `scripts/sqlfluff_config.py` writes those values into `.sqlfluff` and a
  test fails when they drift. sqlfluff runs with `--ignore-local-config --config .sqlfluff` so it
  reads no config outside the repo. Layout rules that contradict the house style (aligned columns,
  one-line count queries, CTE comments above each CTE, AND under WHERE) are excluded and listed
  with reasons in `.sqlfluff`; every other rule is enforced. Fixes: function names and boolean
  literals upper case, `UNION` written `UNION DISTINCT`, explicit `ASC`, positional `GROUP BY 1`
  replaced by the grouped expression, qualified column references, one self-alias removed, two
  table comments shortened. Python fixes are imports, `UTC`, explicit `zip(strict=False)`, files
  opened in context managers, one unused variable, and long lines wrapped.
- **Hygiene scope.** The pre-commit word scan checks code, SQL, docs, config, the README and commit
  messages for every listed word. Data files copied unchanged from public sources (the
  `tests/fixtures/` data files and the `data/reference/` CSVs) are checked only for tool and vendor
  names, not for ordinary English words that appear in source text such as NOAA storm narratives.
- **CI.** `.github/workflows/ci.yml` runs ruff, sqlfluff and the fast pytest suite on every push
  and pull request with uv; it needs no secrets. `make ci` runs the same checks locally.

**Why:** Every change to a SQL rule should be checked before it reaches Databricks, in seconds and
without the 3.6 GB of raw files. Real rows keep the tests honest about source quirks (unpadded MCC
FIPS, the 20:31 run, a dropout to 2,323 customers); exact expected values make any change in
results visible.

**Rows affected:** none. A full DuckDB rebuild with the linted SQL gives identical contents for all
27 tables compared (every row and column) and all 109 quality checks still pass.

Found while building the fixture (resolved in D52): `gold_state_coverage` computes
`LEAST(eaglei_customers / eia_customers, 1.0)`. `LEAST` skips NULLs in both Spark and DuckDB, so a
state with no EIA row or no EAGLE-I denominator gets coverage 1.0 and is ranked. In the full data
every state has both, so no result changes today; in the fixture, Virginia (one county without a
denominator) is ranked with no rate.

---

## D52. States with unknown coverage are not ranked (resolves Q9)

**What:** `gold_state_coverage` now handles missing inputs explicitly. Coverage is unknown (NULL)
when the state has no EIA-861 total for the calibration year, an EIA total of 0, or no county with
a denominator (`eaglei_customers` is NULL). A new column `coverage_status` reads
`coverage_unknown`, `below_minimum` or `covered`; only `covered` is ranking-eligible.
- `gold_state_reliability` gets a `footnote_reason` column: `coverage_unknown`, or the D22 reason
  for a state below the coverage minimum.
- County-years in a state with unknown coverage get the county footnote `coverage_unknown`, after
  D9 and D11 and before D22. `gold_unit_reliability` carries `state_coverage_status` for this.
- Missing denominators of individual counties in an otherwise covered state stay a county-level
  footnote (D9); they do not make the state's coverage unknown.
- Two quality gates: no ranking-eligible state with unknown coverage (and `coverage_status`
  consistent with `customer_coverage`), and no ranked state with unknown coverage. 111 checks now.

**Why:** The old expression `LEAST(eaglei / eia, 1.0)` returned 1.0 when either side was NULL,
because `LEAST` skips NULLs in Spark and DuckDB. A state missing its EIA row, or with no county
denominator, was therefore treated as fully covered and ranked with no rate.

**Rows affected:** none in the full data. Every state and territory with EAGLE-I counties has an EIA
total and at least one denominator, so a full DuckDB rebuild gives the same state and county ranks
and footnotes as before; the only differences are the new columns. In the fixture, Virginia (one
county, Norton city, with no denominator) is no longer ranked and is footnoted `coverage_unknown`.

---

## D53. One shared SQL statement splitter

**What:** `scripts/sql_split.py` is now the only place SQL text is split into statements. A small
tokenizer separates code from string literals (`'...'` with `''` and backslash escapes),
double-quoted strings, backtick identifiers, `--` line comments and `/* */` block comments; only a
semicolon in code ends a statement. It replaces:
- `split_statements`, `strip_comments` and `without_literals` in `run_databricks.py` (used by the
  Databricks runner, `quality_checks.py` and `duckdb_pipeline.py`);
- the regular expressions in `sql_dialect.table_statements` and
  `test_gold_events_duckdb.gold_statements`, which cut a `CREATE OR REPLACE TABLE ... AS` statement
  at the first line ending in `;`, so a comment or string ending in `;` would have cut a query short.

An unterminated literal or block comment now stops the run instead of swallowing the rest of the
file. `tests/test_sql_split.py` covers a comment ending in `;`, a string containing `;` (also at a
line end), block comments, escaped quotes, quoted identifiers and comment markers inside strings,
and checks that every statement of every pipeline file starts with a known keyword.

**Why:** Two different splitting rules existed, and the regex one depended on formatting. One
tested function makes the local tests, the DuckDB build and Databricks see the same statements.
The old `without_literals` (the DROP/ALTER safety check) also treated an apostrophe inside a `--`
comment (for example "county's") as the start of a string, which hid code from the check in four
statements; the tokenizer fixes that. All 101 statements still pass the safety check.

**Rows affected:** none. On every file in `sql/databricks/` the new splitter returns the same
statements as before, byte for byte, and `table_statements` the same 41 (table, query) pairs. A
full DuckDB rebuild from `data/raw/` gives identical contents in all tables (compared row by row
with `EXCEPT ALL` against a build made before the change, ignoring `loaded_at`), and all 111
quality checks pass.

---

## D54. The pipeline as a Databricks Job of SQL tasks

**What:** `databricks.yml` is a Databricks Asset Bundle with one job, `us_grid_outage_pipeline`,
of ten SQL file tasks on my SQL warehouse: `bronze`, `silver`, `gold_events`, `gold_storm_match`,
`gold_reliability`, each followed by its `_gate` task. Each task depends on the one before and has
one retry after a minute. A daily 06:00 UTC schedule is defined but `PAUSED`; email on failure is a
commented example. `docs/runbook.md` covers deploy, run, repair and failed gates.
- **Rendering: a render step, not committed rendered files.** A SQL file task cannot substitute the
  `${section.key}` placeholders (D47). `scripts/render_job_sql.py` renders them with the same
  `pipeline_config.render` and D53 splitter as `make pipeline` and writes `build/databricks/`
  (gitignored); `make job-deploy` always renders before it deploys, and the bundle uploads only that
  folder. Committed rendered files would be a second copy of every SQL file that could drift from
  `sql/databricks/` and `config/pipeline.yml`.
- **Task grouping.** The tasks run the nine pipeline files in exactly the order of
  `run_databricks.SQL_FILES` (checked when rendering): Bronze = `01_bronze` + `01_bronze_sources`,
  Silver = `02_silver_sources` + `02_silver`, gold_events = `03_gold_events` + `03_gold_coverage`,
  gold_storm_match = `03_gold_storm_match`, gold_reliability = `03_gold_reliability` +
  `03_gold_oe417_check`. Unlike the Statement Execution API, a SQL file task runs a file in one
  session, so its `USE` and `SET TIME ZONE 'UTC'` statements apply.
- **Gates.** Each gate checks the exact row count of every table its own task built, then runs
  checks from `90_quality_checks.sql`: Bronze and Silver checks in their layer's gate, each Gold
  check in the gate of the last task that builds a table it reads (most Gold checks read several
  Gold tables, so they land in the last gate). Every check of the file runs exactly once. Results
  go to a staging table `quality_gate_staging` (overwritten by every gate) and are appended to
  `gold_quality_results` (engine `databricks`); `raise_error()` then fails the task when any check
  failed, so the later tasks are skipped.
- **CLI without a global install.** `scripts/install_databricks_cli.py` downloads the pinned
  Databricks CLI release (1.24.0) into `.tools/` after checking its SHA-256 against the release
  checksums. `scripts/databricks_cli.py` passes the host, token and warehouse id from `.env` as
  environment variables, so nothing is written to `~/.databrickscfg`.
- The bundle target is not in development mode, which would rename the job per user and force the
  schedule paused, leaving `pause_status` no longer the single switch.
- `make pipeline` stays: it also converts and uploads the raw files, which the job assumes are
  already in the volume, and its verify step compares counts, detail checks and the top 10.

**Why:** A job gives scheduling, retries, task-level repair and a run history in the workspace,
while the SQL stays the single source in `sql/databricks/`. The paused schedule protects the Free
Edition quota.

**Rows affected:** none in the pipeline tables. Tested first in DuckDB (`tests/test_job_sql.py`):
the rendered task files run in job order on the fixture give the same 43 tables, row for row, as
the pipeline files; every gate passes; and a wrong expected count for `gold_event_storm_match`
stops the job at `gold_storm_match_gate`. One table is new in `workspace.outages`,
`quality_gate_staging`, and each job run appends 154 rows to `gold_quality_results` (the 111
checks plus one task row count for each of the 43 tables).

---

## D55. Gate tasks never retry; quality results kept for 90 days

**What:**
- In `databricks.yml` the five gate tasks (`*_gate`) have `max_retries: 0`. The five build tasks
  keep one retry after a minute.
- `gold_quality_results` keeps `quality.results_retention_days` (90) days of results. At the end of
  every gate run (each job gate task, and `scripts/quality_checks.py` on Databricks and DuckDB) the
  gate deletes rows with `run_ts` older than that:
  `DELETE FROM gold_quality_results WHERE run_ts < CURRENT_TIMESTAMP - INTERVAL 90 DAYS`. In a job
  gate it runs after the results are appended and before `raise_error()`, so it runs on failed gates
  too.
- The runners' safety check still refuses every DELETE except this exact statement on the results
  table (`run_databricks.RETENTION`).
- `docs/runbook.md` states that the job assumes the raw files are already in the volume and that
  `make pipeline` (or its convert and upload steps) uploads them.

**Why:** A build task can fail for a transient reason (warehouse start, a timeout), so one retry is
cheap insurance. A gate failure is a finding about the data: the same checks on the same tables
give the same answer, so a retry only delays the alert and spends quota. Each job run appends about
160 result rows; with a daily schedule the table would grow without bound, and results older than
a quarter are not used for diagnosis (the runbook query looks at the last day).

**Rows affected:** none in the pipeline tables. `gold_quality_results` rows older than 90 days are
deleted (none existed at the first run: the table dates from 2026-11-21).

## D56. Incremental loading: only the new year's Bronze table and Silver partition

**What:** `config/pipeline.yml` has `incremental.load_years` (now `[2025]`). A run loads only
those EAGLE-I years and leaves every other year untouched:
- **Bronze:** the runners (`run_databricks.for_this_run`, used by `make pipeline`, the job renderer
  and the DuckDB runner) drop the `CREATE OR REPLACE TABLE bronze_eaglei_<year>` statements of the
  other years, so `bronze_eaglei_2022` to `_2024` are not reloaded (their `loaded_at` is unchanged).
- **Silver:** `silver_outages` is created once (`CREATE TABLE IF NOT EXISTS`, still partitioned by
  year and state) and written with `INSERT INTO silver_outages REPLACE WHERE year IN (2025)`. Delta
  replaces only those partitions in one transaction and rejects any row of another year. Each
  Bronze branch of the union carries `WHERE <year> IN (load years)`, a constant filter, so tables
  of years not loaded are never scanned. This is exact because every yearly file holds only
  readings of its own year (checked: 0 rows outside the file year in 2022-2025), and the D7 floor
  never moves a reading into another year.
- **Gold events:** `gold_feed_dropouts` and `gold_outage_events` are created once and rewritten as
  the rows before the reprocess window (kept as they are) plus the rows rebuilt from it (D57).
  Rebuilt events continue each county's numbering after its last kept event, so event IDs never
  change. `gold_outage_events_rebuilt` keeps the events the last run rebuilt;
  `gold_event_reprocess_window` keeps where each county's window opened. The rebuilt table has no
  expected row count (it depends on the run); a gate checks that every rebuilt event is in
  `gold_outage_events` instead. The decimal columns are cast to the table's types (Databricks' own
  types for those expressions) so kept and rebuilt rows never pass through another type.
- **Downstream Gold** (coverage, storm match, reliability, OE-417 check) reads only Gold and the
  small dimensions and is rebuilt in full: a few seconds, and it must reflect the changed events.
- A full rebuild is the same code with every year in `load_years`
  (`run_databricks.py --full`); then nothing is kept. The local test runner builds full by default.
- New gate checks: Bronze row count of `bronze_eaglei_2025`; Gold row count of
  `gold_event_reprocess_window`; event numbers 1..n in time order per county; rebuilt events
  present in `gold_outage_events` (115 checks in all).

**Why:** Rebuilding 108 million Silver rows to add one year spends most of the Free Edition quota on
data that did not change, and rewriting old partitions risks changing published numbers. A
partition `REPLACE WHERE` is atomic and idempotent, so a retry or the daily schedule reloading the
current year gives the same rows. One code path for full and incremental runs means the incremental
result can be proven equal to a full rebuild.

**Rows affected (2025 load, 2026-11-22):**

| | Before (2022-2024) | After |
|---|---|---|
| `silver_outages` | 79,598,850 | 108,108,220 (2025: 28,509,370) |
| `gold_outage_events` | 446,261 | 602,479 |
| `gold_feed_dropouts` | 19,190 | 24,059 |
| `gold_collection_runs` | 105,216 | 140,256 |
| `dim_county_customers` | 3,063 | 3,079 |

**Proof:**
- Silver 2022-2024 row counts and checksums (sum of a row hash over every column, per year) are
  identical before and after, on Databricks (`xxhash64`) and in DuckDB (`hash`): 25,796,465 /
  26,101,051 / 27,701,334 rows. The Bronze tables of 2022-2024 keep their original `loaded_at`.
- In DuckDB on the full data, a 2022-2024 build followed by the incremental 2025 load equals a fresh
  full 2022-2025 build row for row in all 26 Silver, dimension and Gold tables (0 differing rows).
  The 2022-2024 build with the new SQL reproduces the previous verified counts exactly.
- The fixture test `tests/test_incremental.py` does the same on the sample, and checks that a rerun
  changes nothing.
- Databricks matches DuckDB on every row count, every detail check and the top 10.

**Run time:**

| | DuckDB (local) | Databricks job |
|---|---|---|
| Incremental 2025 load | 25 s | 375 s (bronze 53, silver 78, gold_events 37, storm match 7, reliability 121, gates 76) |
| Full rebuild | 61 s (2022-2025) | 485 s for the last full run of only 2022-2024 (bronze 109, silver 144, gold_events 43, reliability 104) |

On Databricks Bronze and Silver take about half the time of the 3-year full run, with less data
read; a full 4-year rebuild would be longer still. I did not run one on Databricks to save quota:
the DuckDB proof shows it gives the same rows.

## D57. Reprocess window for events: 7-day lookback, open events rebuilt whole

**What:** Dropouts and events are rebuilt from a per-county `reprocess_from`:
- the **cut** is `incremental.lookback_days` (7) before the first reading of the load years
  (2025-01-01 00:00 UTC, so the cut is 2024-12-25 00:00);
- a county with an event that ends after the cut is rebuilt from the start of its first such event
  (`reprocess_from = LEAST(cut, that start)`), so an event open at the cut is rebuilt whole;
- dropouts starting before the cut are kept; the rest are rebuilt from the readings from the run
  before the cut on (the drop rule compares with the previous run).

**Why 7 days:** The window has to cover everything a new reading can change: the 1-hour event gap
(D17), the 5-run dropout recovery (D19), and the gap measured in collected runs, which skips
nationwide feed gaps (D3; the longest is 9 hours). Reopening events that end after the cut makes
the result exact for any event length; the lookback only has to be longer than any gap that can
still join two readings, and 7 days is far above that while costing one week of 2024 readings
(under 2% of the data read). Without the reopen rule a fixed lookback would split any event that
started before it.

**Fixture test:** `tests/fixtures/` gains window W6 (2024-12-31 12:00 to 2025-01-02 00:00) with the
real readings of Monongalia WV, whose outage runs from 2024-12-31 19:30 into 2025, and Harris TX
(which reports in every slot, so the fixture's collection grid is real). Before 2025 is loaded the
event ends at the last 2024 reading (18 readings); after the incremental load it is the same event
`54061-00001`, with 114 readings, still counted in 2024.

**Rows affected (full data):** 17 counties had an event open at the cut, so their window opened
earlier (earliest 2024-12-24 15:45). 158,948 events were rebuilt. 57 events that started in 2024
now continue into 2025 and are longer; in the 2022-2024 build they ended at the last 2024 reading.
The largest is `28157-00227` Wilkinson MS, 2024-12-28 22:15 to 2025-01-03 02:45 (258,629
customer-hours). These 57 change 2024 customer-hours for 57 counties (events count in their start
year, D38) and move the 2024 rates of 19 states slightly; no state's 2024 rank changes. All other
2022-2024 events are identical. One more 2024 event matches a storm (18,448 to 18,449): one of the
longer events now overlaps a storm window.

## D58. 2025 does not change the denominators (D13 stays one denominator per county)

**What:** `dim_county_customers` keeps the D13 rule with 2022-2024 as the denominator base years
(`denominator.base_years`): the D21 state totals and the D35 peak floors use only counties and
readings of those years. A county first reported in 2025 gets its D13 value (MCC if it has one,
else none) and is not calibrated. The D35 quality check reads base-year peaks only (it failed on
the first Databricks run, with 5 calibrated counties whose 2025 peak exceeds their floor, before I
aligned it). A 2025 reading above a county's denominator is flagged and capped as any other (D4:
3,415 such rows in 2025).

**Why:** The 2025 EAGLE-I file has no `total_customers` column (five columns, like 2022), so there
is no 2025 customer count to switch to. The levers 2025 would offer (2025 peaks for D35, 2025
counties in the D21 totals, EIA-861 2025 for calibration) all rewrite earlier years: under D13 a
county's one denominator is used in every year. I measured that alternative in DuckDB:
- 237 counties in all 5 calibrated states would change denominator (Missouri 115, South Dakota
  66, South Carolina 39, Massachusetts 13, Hawaii 4); median change 0.7%, largest 109% (South
  Dakota would no longer be calibrated, because EIA-861 2025 grew past the 1.25 ratio).
- Every 2022-2024 rate in those states would move, and 25 published `exceeds_customers` flags would
  flip (21 in 2022, 4 in 2024).

Rates that change when a year is added would break year-over-year comparison, the point of D13.
Recommendation and choice: keep the base years 2022-2024; revisit only in a deliberate full
rebuild, recorded as its own decision.

**Rows affected:** 16 new rows in `dim_county_customers` (3,063 to 3,079), none of the existing
rows changed: 7 counties first reported in 2025 with an MCC denominator (Clark, Ford, Kiowa and
Meade KS; Johnson TN; Sabine TX; Klickitat WA) and Connecticut's 9 planning regions with none
(D59, D60).

## D59. 2025 sources: what is published, what is missing

**What and rows affected:**
- **EAGLE-I 2025** (figshare dataset version 4, the version already pinned): 30,482,141 rows,
  all dated 2025. Converted to Parquet (D20: 67.5 MB). In Silver, 1,972,650 rows (6.5%) are
  dropped by D15 because `customers_out` is empty; 2022-2024 had none. They are spread over 3,027
  counties (most in Illinois, Virginia and South Carolina) and treated as missing readings (D3),
  which a single gap does not split (the event gap is counted in runs). 121 more rows are
  removed by the D7 dedupe after flooring off-grid times. Silver 2025: 28,509,370 rows.
- **Connecticut planning regions:** from 2025-05-29 EAGLE-I reports Connecticut by its nine
  planning regions (FIPS 09110 to 09190, the Census county equivalents since 2022) instead of its
  eight counties. MCC has no row for them, so they have no denominator (D9); see D60.
- **NOAA Storm Events 2025:** `StormEvents_details-ftp_v1.0_d2025_c20261119.csv.gz`, 73,505 events.
  Storm matching covers 2025 (17,742 matched events).
- **NWS zone-county file:** `bp18mr25` (effective 2025-03-18, in force until `bp16ap26`) added to
  `scripts/download_nws_zone_county.py`; 7 versions now.
- **EIA-861 2025:** published and loaded. Utility rankings include 2025. Three 2025 reliability rows
  carry no reporting standard (`not reported`); like any non-IEEE row they are in neither utility
  table. One 2025 utility (19162) is flagged by the D39 repeated-values rule and not ranked.
  `calibration.eia_year` stays 2024 (D58).
- **OE-417 2024 and 2025: not available.** As in D25, the official host is IPv6-only and has no
  archived copy; `scripts/download_oe417.py` lists both as manual downloads. The OE-417 check (D40)
  covers 2022-2023 only, and findings say so. Dropping the files into `data/raw/oe417/<year>/` adds
  them with no code change.

## D60. A state-year mostly without denominators is footnoted, not ranked

**What:** In `gold_state_reliability`, a state-year with more than
`ranking.max_share_without_denominator` (10%) of its customer-hours in reporting units without a
denominator is footnoted ("over 10% of customer-hours in units without a denominator (D60)") and
not ranked. In `gold_county_reliability` the counties of such a state-year are footnoted the
same way.

**Why:** A state's rate divides the customer-hours of units with a denominator by their customers
(D9). Connecticut's 2025 hours after May 29 sit in planning regions without one, so its 2025 rate
would count about five months of outages against a full year of customers and rank Connecticut
far too reliable. Its eight counties' 2025 rates have the same gap.

**Rows affected:** only Connecticut 2025: 68% of its 2025 customer-hours are in planning regions.
No other state-year in 2022-2025 is above 0.5%, so no other rank changes. 1 state-year and 8
county-years footnoted. A proper fix needs denominators for the planning regions (for example from
a town-level crosswalk); that is an open question for me to decide.

## D61. A county has reliability rows only from its first reported year

**What:** `gold_unit_reliability` gives each county a row for every year from the first year
EAGLE-I reports it (`MIN(year)` in `silver_outages`), not for every year in the data. Quiet years
after that still count as zero.

**Why:** Before, every county got a row in every year, so a county first reported in 2025 would
have appeared in 2022-2024 as a county with zero outage hours and lowered its state's rate. That is
coverage growth reported as reliability, which this project must never do. The same rule applies
to the counties already first reported in 2023 or 2024.

**Rows affected:** 16 county-years from 2025 counties are never created. In 2022-2024, 10
county-years that were coverage-gap zeros are removed: 2022 Chugach AK, Lee, Prentiss and
Tishomingo MS, Garfield MT, Okanogan WA; 2023 Chugach AK, Lee and Tishomingo MS, Okanogan WA.
Ranked counties: 2022 3,009 to 3,004; 2023 3,009 to 3,006; 2024 unchanged at 3,006. State rates
rise where those counties had diluted them: Mississippi 2022 4,451 to 4,666 hours per 1,000
customers (rank 18 to 17), 2023 8,820 to 9,169 (11 to 10); Washington 2022 rank 14 to 13; Montana
2022 and Washington 2023 by under 1%. Arkansas and Kentucky 2022 and Hawaii 2023 move down one rank
as a result. No rank 1 changes.

**Status: accepted as a restatement (2026-11-22).** I reviewed the change and kept it. The
2022-2023 state and county ranks published before this commit are superseded; the before and
after values that changed are listed in `CHANGELOG.md`.

## D62. Empty 2025 readings: what they are and whether dropping them hides outages

**What:** 1,972,650 rows of EAGLE-I 2025 (6.5%) have an empty `customers_out`. D15 drops them,
so under D3 each one counts as a missing reading (zero customers out). I profiled them before
deciding anything; **the rule is unchanged until I decide Q10.**

**Findings (DuckDB, full data):**
- **Spread:** every day of 2025, 3,027 counties, 34,078 of the 35,028 collection runs; a median
  of 35 counties per run. Rising late in the year: 49,288 in February, 493,113 in October
  (mid-October peak, 33,301 on 2025-10-15). Only one run is nationwide-scale (2025-08-01 19:15,
  2,138 counties). The top 30 counties hold 9% of them.
- **Where:** Illinois (361,851, 34% of its rows), Virginia (214,617, 11%), South Carolina (207,890,
  30%; Allendale and neighbouring counties are empty most of the time from February), Nebraska (39%).
- **Mostly quiet periods:** the nearest readings around an empty one have a median of 2 customers
  out. Only 2,665 empty readings (0.14%) fall inside an event, while events cover 2.1% of
  county-slots, so they are much rarer during outages than by chance. Only 7,111 (0.36%) sit
  between two readings at or above the county's event threshold (D18).
- **Short gaps inside outages:** 1,370 runs of up to 1 hour between above-threshold readings. They
  do not split events (D3 needs more than 1 hour) but count as zero: about 1.1 M customer-hours
  (0.16% of 2025's 695.6 M), estimated as the lower of the two neighbouring readings.
- **Long gaps inside outages:** 164 runs longer than 1 hour between above-threshold readings. These
  end the event and start a new one. Most of the missing hours are from one case: **the Puerto
  Rico island-wide blackout of 2025-04-16.** In six of PREPA's seven regions (filed under Ponce,
  Mayagüez, Arecibo, San Juan, Bayamón and Caguas, D22) every reading from 2025-04-17 00:00 to 14:45
  UTC (60 runs) is empty while 85,000 to 273,000 customers per region were out on both sides. Each
  region's blackout is split into two events and about 10.8 M customer-hours are not counted. Rejoined, Ponce would be about 7.0 M
  customer-hours (now 3.07 M for the second half, 2025 rank 9) and the third-largest 2025 event.
  All other long gaps add up to about 1.8 M.
- **Top events:** the 20 largest 2025 events contain 61 empty readings in 15,981 slots (0.4%); Los
  Angeles 06037-00190 has 6 of 1,093.

**Why it matters:** an empty value is not a missing row. The county was collected but no count was
given, so treating it as zero (D3) is wrong in the rare case where the county was in an outage.
Puerto Rico is not ranked (D43), so no state or county rank changes; the event list and 2025
customer-hours do.

**Recommendation (Q10):** keep dropping empty readings from Silver, but in Gold treat a run of
empty readings like a D19 dropout for that county: it cannot end or split an event, and the event
gets `spans_feed_gap`-style hours instead of invented customers out. That fixes the Puerto Rico
split without inventing values for the 99.6% of empty readings in quiet periods. Filling them by
interpolation is not recommended: the neighbouring readings are often a day apart (median 27 hours).

**Rows affected:** none yet (finding only). **Resolved in D64** (2026-11-22): runs of empty readings
are bridged like dropouts, without filling in values.

## D63. 2025 is a complete year; no partial-year flag

**What:** Silver 2025 runs from 2025-01-01 00:00 to 2025-12-31 23:45 UTC, 35,028 distinct
collection runs (2022-2024: 35,024 to 35,095 of 35,040 or 35,136). The 2025 EAGLE-I file is a
full year, so I did not add a `partial_year` flag to the yearly outputs.

**Why:** a flag that is always false adds a column to every yearly table without information.
If a later year is loaded before December, I will add the flag then, with that year's first and
last reading.

**Rows affected:** none.


## D64. Runs of empty readings inside an outage are bridged like dropouts (resolves Q10)

**What:**
- **Silver:** `silver_empty_readings` keeps the EAGLE-I readings whose `customers_out` is empty
  (fips_code, reading_time, year, source_file). They are placed and floored like `silver_outages`
  (D7, D15, D16), one per county and slot, and never on a slot that also has a real reading. They
  stay out of `silver_outages`, and no value is filled in.
- **Gold events:** consecutive empty readings of a county form an empty run. It is **bridged** when
  the readings in the collected runs right before and right after it both qualify (at or above the
  county threshold, D18, and not dropout readings, D19) and it lasts no more than
  `events.max_empty_bridge_hours` (24 hours, 96 runs). A bridged run is skipped like a D19 dropout:
  it cannot end or split an event and adds no customer-hours. `bridged_empty_hours` records it.
- A run between two qualifying readings but **longer than 24 hours still ends the event**. An event
  whose first or last reading is next to one gets `spans_empty_gap = true`; its true length is unknown.
- Empty runs and their edge readings are read from all of Silver, not only the reprocess window
  (D57), so an event at the start of a window sees an empty run just before it. Config validation
  requires `events.max_empty_bridge_hours` to be shorter than `incremental.lookback_days`.
- The two columns are appended to `gold_outage_events`. The table already existed on Databricks, so
  `scripts/schema_migrations.py` (`make migrate`, run by `make job-run` and `make pipeline`) adds them
  with `ALTER TABLE ... ADD COLUMNS` and sets the existing rows to 0 and FALSE. Those are their true
  values: the rows built before D64 were from 2022-2024, which have no empty readings, or were in
  the reprocess window and were rebuilt by the same run. This is the only ALTER the runner allows,
  and only the exact statements that file generates.

**Why:** An empty reading is a collected run with no count (D62). Between two qualifying readings
the outage was still going, so counting the run as zero (D3) ended the Puerto Rico blackout events
after 15 hours. The 24-hour limit covers the 15-hour gap of 2025-04-17 and the 21-hour gap of
2025-01-01 with room to spare. Beyond a day I cannot assume the same outage continued; the next one
in Puerto Rico is 71 hours, so it still ends the event and is flagged.

**Rows affected (DuckDB full data, incremental run; Databricks identical):**
- `silver_empty_readings`: 1,972,650 rows, all in 2025; none on a slot with a real reading.
- 928 events contain bridged runs (871 hours bridged in total). They absorb 1,052 earlier events,
  so there are 124 fewer events: 2025 goes from 156,218 to 156,094 events.
- Total customer-hours do not change, because nothing is filled in. 1,857,571 customer-hours move
  from 2025 to 2024: three Puerto Rico events that start 2024-12-31 09:45 (the San Juan, Caguas and
  Ponce regions, the New Year's Eve blackout) cross a 21-hour empty run on 2025-01-01 and now run to
  2025-01-02 14:00. 2024: 1,689.5 M to 1,691.4 M; 2025: 695.6 M to 693.7 M.
- 20 events have `spans_empty_gap` (8.6 M customer-hours).
- **Puerto Rico blackout of 2025-04-16** (PREPA regions, D22), capped customer-hours before (two
  events) and after (one event, 15 hours bridged):

  | Region | Before | After | 2025 rank after |
  |---|---|---|---|
  | Ponce | 0.99 M + 3.07 M | 4.06 M | 5 |
  | Mayagüez | 0.97 M + 2.19 M | 3.16 M | 10 |
  | San Juan | 1.82 M + 0.80 M | 2.62 M | |
  | Arecibo | 0.65 M + 1.80 M | 2.45 M | |
  | Bayamón | 1.09 M + 1.21 M | 2.31 M | |
  | Caguas | 1.57 M + 0.53 M | 2.10 M | |

  Ponce, Bayamón and Caguas end next to the 71-hour empty run and have `spans_empty_gap`.
- **2025 top 10:** Los Angeles 21.2 M, Allegheny 14.4 M, San Bernardino 6.8 M, Riverside 5.8 M,
  **Ponce 4.06 M** (was ninth at 3.07 M), Cheboygan 3.7 M, Otsego 3.6 M, Ventura 3.5 M, St. Louis
  city 3.3 M, **Mayagüez 3.16 M** (new). Cheboygan 26047-00141 (2.9 M) drops out. The all-years top
  10 is unchanged.
- **Unchanged:** every 2022 and 2023 row of every Gold and Silver table (per-year checksums on
  Databricks before and after). In 2024 only the three Puerto Rico events, their storm-match rows and
  the Puerto Rico territory rows change; 2024 county and state reliability are identical. No state
  or county rank changes in any year (Puerto Rico is not ranked, D43). The incremental result equals
  a full 2022-2025 rebuild in all 28 Silver, dimension and Gold tables (DuckDB).
- Fixture: window W7 (Ponce and Harris, 2025-04-16 12:00 to 04-21 18:00) holds both runs: the
  15-hour one is bridged and the 71-hour one ends the event and is flagged.

## D65. Python 3.13, the newest version every dbt adapter supports

**What:** The project moves from Python 3.14 to 3.13: `.python-version` is `3.13` (`uv python pin
3.13`), `requires-python = ">=3.13"` and ruff's `target-version = "py313"` in `pyproject.toml`. CI
installs the version in `.python-version`, so it follows. `dbt/` has its own `.python-version`, 3.13.

**Why:** The dbt adapters I need do not all support 3.14. dbt-core 1.12.7, dbt-duckdb 1.11.1 and
dbt-adapters 1.24.6 list 3.14, but dbt-databricks 1.13.1 and dbt-snowflake 1.12.5 stop at 3.13, and
on 3.14 the Databricks adapter's dependencies warn that Pydantic V1 is not compatible with 3.14.
3.13 is the newest version all four support. Nothing in the pipeline needed 3.14.

**Rows affected:** none. After the switch the fast suite (106 tests), lint, all 119 quality checks
on the full data in DuckDB and the slow suite pass unchanged.

## D66. dbt star schema over Gold; the marts must equal Gold exactly

**What:**
- `dbt/` is a dbt project with its own uv environment (`dbt/pyproject.toml`, `dbt/uv.lock`):
  dbt-core, dbt-databricks, dbt-duckdb and dbt-snowflake. dbt-databricks 1.13.1 requires
  `databricks-sdk < 0.158`, while the pipeline uses 0.169 for the job and upload code, so the two
  cannot share one environment. `dbt/run_dbt.py` loads `../.env`, so no credential is printed or
  stored. Only `profiles.yml.example` is committed.
- **Sources:** the Silver and Gold tables of `workspace.outages`, plus two Bronze reference lookups
  (state FIPS regions, D16, and storm severity, D41). Freshness is checked on `silver_outages`
  (newest reading; warn after 400 days, because EAGLE-I is released yearly) and on
  `gold_quality_results` (newest run; warn after 8 days).
- **Marts**, tables in the same schema next to Gold, and nothing else is created:
  `fct_outage_events`, `fct_county_reliability`, `fct_state_reliability`,
  `fct_territory_reliability`, `fct_utility_reliability`, `dim_county`, `dim_state`, `dim_date`,
  `dim_storm_type` and `dim_utility`. They reshape Gold but never recompute a metric, so each
  rule stays in one place (`sql/databricks/`). The SQL uses dbt's cross-database macros (date
  spine, concat, type casts, `bool_or`) so the same models run on Databricks, DuckDB and Snowflake.
- **Event-year convention:** an event counts in the year it starts (UTC), and `event_date` joins
  `dim_date`. This is stated in the model docs.
- **Utilities:** IEEE 1366 and other-standard reporters share `fct_utility_reliability`, kept apart
  by `reporting_group`; only IEEE rows have ranks (D23, D39).
- **Tests (72):** unique and not_null on every key, relationships from every fact to its
  dimensions, accepted values for the categories, and four custom tests:
  - only the 50 states and DC are ranked;
  - every unranked row has a footnote reason, and no ranked row has one;
  - no calibrated county is below its base-year peak unless D36 skipped it;
  - the event fact equals Gold per year.
- `scripts/reconcile_marts.py` compares the marts with Gold: row counts, events and customer-hours
  per year, the top 10, and the rank 1 state and county per year. `make dbt-build` (Databricks) and
  `make dbt-test-local` (fixture in DuckDB) both end with it. CI runs dbt parse, dbt build and the
  reconciliation on the fixture with no secrets.

**Why:** The Power BI dashboard and the later Snowflake copy need a documented star schema with
tested keys. Building it on Gold, not beside it, keeps one definition of every number.

**Rows affected (Databricks, equal to DuckDB):** `fct_outage_events` 602,355; `fct_county_reliability`
12,217; `fct_state_reliability` 204; `fct_territory_reliability` 8; `fct_utility_reliability` 3,884
(2,963 IEEE 1366, 921 other standard); `dim_county` 3,079; `dim_state` 53; `dim_date` 1,461;
`dim_storm_type` 55 (54 NOAA types and 'unmatched'); `dim_utility` 937. Every reconciliation
matches Gold exactly:
- events per year: 149,695 / 144,747 / 151,819 / 156,094;
- customer-hours per year: 1,071.9 M / 878.5 M / 1,691.4 M / 693.7 M;
- the top 10 events, led by Harris 48201-00250;
- rank 1 state per year: ME, ME, SC, WV.

Two documented exceptions:
- `dim_county.county` is NULL for Klickitat WA (53039), which is in the MCC file but has no
  reading yet.
- 9 utility rows for American Samoa, Guam and the Northern Mariana Islands have no `dim_state`
  row. EAGLE-I does not cover those territories, so their relationship test excludes them.

## D67. EAGLE-I coverage metadata loaded; coverage after 2022 measured from the readings

**What:**
- `coverage_history.csv` and `DQI.csv` (already in the volume with MCC) now load into
  `bronze_eaglei_coverage_history` and `bronze_eaglei_dqi`, all text (D14).
- They are parsed in `silver_eaglei_coverage_history` and `silver_eaglei_dqi`
  (`02_silver_sources.sql`):
  - the year comes from the m/d/yy date;
  - FEMA regions 1-10 become I-X, as in the region lookup (D8);
  - shares stay as published.
- dbt marts `fct_published_coverage` (state-year) and `fct_data_quality_index` (FEMA region-year)
  expose them.
- `fct_county_coverage` (county-year: readings, first and last reading, customers) measures
  coverage from the readings for every year.
- The test fixture copies both files whole.

**Why:** Question 6 must not read coverage growth as outage growth. Both files stop at 2022 (56
states and territories x 2018-2022, and 10 FEMA regions x 2018-2022), so they cannot cover
2023-2025. For those years the check is the set of counties EAGLE-I reports each year, and a
comparison on the counties reported in every year.

**Rows affected:** 280 and 50 rows in each new Bronze and Silver table (fixture the same).
`fct_county_coverage`: one row per county-year with readings (3,047 / 3,049 / 3,052 / 3,026
counties in the 50 states and DC in 2022-2025, Q6). Four row-count checks are added: 123 quality
checks in total.

## D68. Analysis layer on the marts; every number in the docs is checked against a query

**What:**
- **Queries:** `sql/analysis/q1`-`q6` answer the six questions. They read only the dbt marts, use
  CTEs, and run unchanged on Databricks and DuckDB. Each statement is one named result
  (`-- result: <name>`).
- **Results:** `scripts/analysis.py run` writes the results to `docs/analysis_results/` as CSV,
  with one text form per value on both engines.
- **Docs:** `render` fills `docs/findings.md` and `docs/case_study.md` from templates in
  `docs/templates/`. Every number in them is a placeholder that names a result, a row and a column.
- **Check:** `check` reruns the queries, compares them with the committed CSVs and re-renders the
  docs; it fails on any difference (`make check-findings`). A fast pytest confirms the docs match
  the committed CSVs.
- **Charts:** `scripts/charts.py` draws the five charts from the same CSVs (`make charts`).
- **Data dictionary:** `docs/data_dictionary.md` is written from the dbt docs
  (`make data-dictionary`).
- **Rounding:** every rounded value is cast to DECIMAL first. Rounding a double at an exact half
  differed between the engines (104.35 to 104.3 or 104.4).
- **Storm families:** `dim_storm_type.storm_group` groups the NOAA types the questions compare:
  - Hurricane / tropical: the tropical_cyclone tier;
  - Winter weather: ice and snow plus Winter Weather and the cold types;
  - Thunderstorm wind;
  - Other wind;
  - Tornado;
  - Wildfire;
  - Heat;
  - Flood;
  - Other;
  - No storm matched.
- **Restoration:** Q4 reports durations for all events and for events with 10,000+ customers out
  at the peak, because the median event is 1.5 hours long.
- **Regions:** Q3 rates are customer-hours per 1,000 customers of the region per year.

**Why:** A number typed into a document drifts from the data the next time the pipeline runs. Here
it cannot: the check fails instead.

**Rows affected:** 23 results.
- **Same on both engines:** every result on Databricks is identical to DuckDB.
- **D36 reference list:** the "counties outside calibrated states with a peak above 1.25x
  customers" list now has 39 counties (38 in the states and DC, 1 PR region). D36 recorded 30
  when it was written, and I could not reproduce that figure; the findings report the current
  query and say so.

## D69. Two portability fixes found by running the same SQL on both engines

**What:**
1. The marts cast decimal Gold columns with `dbt.type_float()`. That is a 4-byte FLOAT on
   Databricks and DuckDB, so values lost precision (an event of 255.3 hours read 255.300003, and
   large capped customer-hour totals kept only about 7 significant digits). The marts now cast to
   DOUBLE, which is 8 bytes on all three engines.
2. A D60 footnote in `03_gold_reliability.sql` was written `'... the state''s customer-hours ...'`.
   DuckDB reads `''` as an escaped quote, but Spark SQL reads it as two adjacent literals, so
   Databricks stored "the states customer-hours". It now reads "... of customer-hours in the state
   in units without a denominator (D60)", with no quote to escape. No other literal in
   `sql/databricks/` has a doubled quote.

**Why:** Both bugs made the two engines disagree in ways the row-count and total checks did not
see. The analysis results now match exactly.

**Rows affected:**
1. The DOUBLE cast changes no value in Gold; the mart columns now equal Gold exactly.
2. The footnote text of 8 county-years in 2025 (the Connecticut planning regions) changes on
   Databricks; no rank changes.

## D70. Power BI handoff: committed summary CSVs, events on a GitHub Release, a year dimension

**What:**
1. `make export` (`scripts/export_marts.py`) now writes the dbt marts, not the Gold tables. The
   tables are listed in `mart_export` in `config/pipeline.yml`.
   - The 13 small marts (all dimensions, state, county, territory and utility reliability, and the
     three coverage marts) go to `data/gold_exports/summary/` as CSV and are committed. A
     `.gitignore` exception un-ignores that folder.
   - `fct_outage_events` goes to `data/gold_exports/release/` as Snappy Parquet. It is
     gitignored and published as a GitHub Release asset.
   - Rows are sorted on each table's key, so a rerun on unchanged marts writes byte-identical
     files.
   - `manifest.json` records rows, column types, bytes and SHA-256 per file.
   - CSV conventions: UTF-8, `true`/`false` booleans, empty for NULL, UTC timestamps as
     `YYYY-MM-DD HH:MM:SS`.
   - The old Gold CSV export stays available as `make export-gold` (D50).
2. `make release-draft` (`scripts/publish_release.py`) checks each Parquet file against the
   manifest and writes the release notes.
   - With the GitHub CLI, it creates a **draft** release on `Deva9102/us-grid-outage-analytics`, or
     replaces the assets of an existing draft. It never publishes, and it refuses to touch a
     published release.
   - Without the CLI, it prints the exact manual steps for creating the draft in the browser.
3. A new mart, `dim_year`, has one row per year any mart reports (2018-2025), with
   `has_readings` and `has_published_coverage`. The year-grain facts join to it, and relationship
   tests on each fact's year column enforce that.

**Why:**
- D50 deferred this split. The summary tables are small enough for git and change rarely, so the
  dashboard can be rebuilt from a clone or from raw GitHub URLs without Databricks.
- The event table is too large for git. A release keeps it versioned outside the history, and
  the manifest hash ties each download to the commit that described it.
- Draft-first means I review a release before it becomes public.
- Without `dim_year`, the yearly facts could only reach a year slicer through `dim_date`, which
  has many rows per year: a many-to-many relationship in Power BI. A one-row-per-year dimension
  keeps every relationship many-to-one, with one filter path.

**Rows affected:**
- No Gold or mart values change. `dim_year` has 8 rows; dbt build has 113 passing nodes and the
  marts still match Gold.
- Export from Databricks: 13 summary CSVs (4.1 MB), the largest being `fct_county_reliability`
  with 12,217 rows. `fct_outage_events` is 602,355 rows (25.6 MB Parquet).

## D71. Restoration-time forecast: prediction moment, eligible events, features and split

**What:**
- **Task.** At a fixed prediction moment, `event_start` + 2 hours (`forecast.prediction_hours`),
  predict an outage event's total `duration_hours` as a p50 and a p90.
- **Eligible events.** The county's reading at the prediction moment meets its event threshold
  (D18), and the event runs past that moment, so the reading belongs to this event and not to a
  later one. Left out:
  - events below the threshold at that moment, even if a later reading revives them within the
    1-hour gap rule (D17): at the prediction moment the outage does not look ongoing;
  - events with `spans_empty_gap` (D64): their true length is unknown, so the target is unreliable.
- **Split.** Train on 2022-2024, test on 2025, by `event_year` (UTC start year). Never random.
  Set in `config/pipeline.yml` (`forecast`), with validation that every test year comes after
  every training year.
- **Features.** `gold_restoration_features` in `sql/databricks/04_gold_forecast_features.sql`,
  rendered from config. Only information known at the prediction moment:
  - **Readings:** from a 15-minute slot grid that stops at the prediction moment: customers out at
    the start, the midpoint (1 h) and the prediction moment, growth (difference and ratio), and the
    peak so far, raw and as a capped share of the D13 denominator. A collected slot without a row
    is 0 (D3). A nationwide feed gap, or a reading inside a known dropout, is NULL.
  - **Flags:** a feed gap so far (D10), and a dropout so far (D19). A dropout counts only when its
    recovery reading is at or before the prediction moment, because D19 identifies a dropout only
    once the feed recovers.
  - **Storm at the start:** the most severe outage-capable NOAA storm (D41 order) whose D37/D42
    window covers `event_start` and whose begin time is at or before the prediction moment.
    Mapped to the D68 storm family through a new `gold_storm_family` table. A test keeps it equal
    to `dim_storm_type`.
  - **Calendar:** month, hour and weekday (0 = Monday) of the start, in the state's primary time
    zone.
  - **County:** census region, state, customers (D13) and the event threshold (D18).
  - **County history:** event count, events per year, eligible event count, and median duration
    of all and of eligible events. History uses only events of earlier years that had **ended
    before the event's year began**: a Dec 31 outage still running on Jan 1 is not yet history.
    History is NULL for 2022, which has no earlier year, and `history_years` (0-3) tells a model
    how much history there is.
- **Stage.** The forecast runs as a separate stage after Gold: `scripts/forecast_features.py`
  (`make forecast-features`). It is not in `run_databricks.SQL_FILES` or the Databricks Job, so a
  change to the forecast cannot stop the reliability pipeline. It has no row-count quality gate
  yet.
- **Dialect.** Two rewrites were added to `scripts/sql_dialect.py`:
  - `from_utc_timestamp` becomes DuckDB `timezone()`;
  - `weekday()` becomes `isodow() - 1`, because DuckDB's `weekday` counts from Sunday.
- **Baseline.** `scripts/forecast_baseline.py` (`make forecast-baseline`) writes
  `docs/forecast_baseline.md`. It uses training-year p50/p90 per storm family, and per storm
  family x region. A cell with fewer than 30 training events (`forecast.baseline_min_events`)
  falls back to its family, then to all events.

**Why:**
- **Prediction moment.** Two hours is when an estimated time of restoration is first useful to
  customers, and most short blips are over by then: the median event lasts 1.5 hours, so
  predicting at the start would mostly forecast noise.
- **Eligibility.** A rule that can be checked at the moment itself, the reading then, avoids
  choosing events with information from after it, such as "the event lasted more than 2 hours".
- **Split.** A time split tests what a deployed model faces: a year it has not seen.
- **History cut-off.** History is computed once per year from finished events, so it cannot carry
  the current event or any outage still running.
- **NOAA as a stand-in.** NOAA Storm Events records are published months later. Here they stand
  in for the storm type an operator knows from NWS warnings at the time; the begin-time rule
  keeps out storms that had not started yet.
- **Denominator.** The D13 county denominator is a fixed county attribute set from 2022-2024. It
  is not an outcome of any event, so I use it in every year.

**Rows affected (DuckDB full data; Databricks identical by a checksum of rows and column sums
per split):**
- 227,147 of 602,355 events run past the prediction moment. 5,426 are below the threshold at that
  moment and 13 span an empty gap, which leaves **221,708 eligible events**:
  - 2022: 54,928;
  - 2023: 53,105;
  - 2024: 56,440;
  - 2025: 57,235.
- 36,682 eligible events have a storm at the start. The full-event match of D37 attributes
  43,367 of them: the rest are matched only by storms that begin after the prediction moment, or
  by overlap later in the event.
- **Null rates:**
  - history: 24.8-25.1%, almost all 2022 by design;
  - `customers_out_at_mid`: 1.0% (dropouts and feed gaps);
  - `customers` and `peak_share_so_far`: 0.2% (counties without a denominator, D9).
- **Leakage tests** (`tests/test_forecast_features.py`):
  - each kind of future information (later readings, a dropout recovering later, a storm
    beginning later, a later feed gap, history from the event's own year or still running on
    Jan 1, a longer event) must leave every feature unchanged;
  - a twin just inside the moment must change the feature.
  Making the SQL read up to `event_end` instead of the prediction moment fails them.

---

## Open questions

Q1 is resolved in D9; Q2 (fixed 100-customer threshold) is resolved in D18 and D19.

**Q3.** Resolved in D37: 61% to 83% of the top 100 now match; the rest are explained by cause.

**Q4.** Resolved in D35 (option B; option C rejected).

**Q5.** Resolved in D36 (option B; options A and C rejected).

**Q6.** Resolved in D41.

**Q7.** Resolved in D42.

**Q8.** Resolved in D43.

**Q9.** Resolved in D52.

**Q10.** Resolved in D64.
