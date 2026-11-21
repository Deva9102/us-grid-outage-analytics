# Data Cleaning Decisions

Every cleaning decision for the pipeline, with the reason and the rows it touches.
Row counts come from DuckDB runs against the raw EAGLE-I files
(2022: 25,796,465 rows; 2023: 26,101,051; 2024: 27,701,334). See `docs/data_profile.md`.

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

**Rows affected:** 0 in all three years (DuckDB, full data). FIPS codes padded: 0.

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

---

## Open questions

Q1 is resolved in D9; Q2 (fixed 100-customer threshold) is resolved in D18 and D19.

**Q3. Why only 62% of the top 100 EAGLE-I events match a NOAA event (for Prompt 8c).** In the
source profile, 74% of the top 1,000 EAGLE-I events by customer-hours have a NOAA event in the same
county between 24 hours before and 2 hours after the outage starts, but only 62% of the top 100.
To break down before the storm match is built:
- Coverage and geography: the Puerto Rico regions (D22) are matched by the namesake municipio only,
  while NOAA reports Fiona by zone or by other municipios in the region.
- Time windows: long hurricane events can start before NOAA's begin time in that county, or NOAA's
  zone records can begin later than the first outages.
- Event type labels: hurricane impacts are often recorded as Tropical Storm, Storm Surge/Tide,
  High Wind or Flash Flood, in zones rather than counties.

**Q4. D21 uniform scaling pushes some counties below their own reported peaks.** 9 of 246 calibrated
counties end below the largest outage EAGLE-I ever reported there; South Carolina's three largest
Helene counties (Greenville, Spartanburg, Anderson) are among them, and SC gains 1,502 overcount
flags. Options:
- A. Keep D21 as is and footnote SC.
- B. Floor each calibrated county at its highest reported outage, and spread the remaining
  reduction over the other counties of the state.
- C. Split the EIA state total across counties using EIA-861 Service Territory (utilities per county)
  instead of EAGLE-I's shares.

B is the smallest change that keeps every real peak possible.
