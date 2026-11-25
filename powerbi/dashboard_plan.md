# Dashboard plan

Seven pages, each answering one question. The model is in [data_model.md](data_model.md), the
measures in [measures.md](measures.md) and the theme in [theme.json](theme.json) (View > Themes >
Browse for themes). The findings behind each page are in [../docs/findings.md](../docs/findings.md).

Rules for every page:
- **Slicers.** One row of slicers across the top: `dim_year[year]` (single select, default 2024),
  then the page's own slicers. Sync the year slicer across pages 1-5. Page 6 has its own year
  slicer, because it covers 2018-2022.
- **Colour.** At most six colours per visual, in the theme order. Further categories fold into
  grey, and "No storm matched" is always grey (`#B9B8B2`). Bars are one colour unless the colour
  carries meaning, and visuals with more than one series show a legend or data labels.
- **Footnotes.** Any visual showing rates or ranks gets a text box under it: "Ranks exclude
  footnoted places; see page 6."
- **Conventions.** A note in every page footer: "Times UTC; an event counts in the year it starts;
  source: DOE EAGLE-I, NOAA, EIA-861."

## 1. US overview

**Question:** How much power did US customers lose to outages in the year, and was it worse than
the year before?

| Visual | Fields |
|---|---|
| 4 cards | [Customer Hours Lost], [Number of Events], [YoY Change], [Matched-to-Storm %] |
| Card (wide) | [Worst Event] |
| Clustered column chart, one colour | Axis `dim_year[year]` (interaction with the year slicer off), value [Customer Hours Lost] |
| Bar chart, top 10 | Axis `dim_state[state_name]`, value [Outage Hours per 1k Customers], filter `fct_state_reliability[is_ranked] = TRUE` |
| Stacked bar chart, 100% | Axis `dim_state[census_region]`, legend `dim_storm_type[storm_group]` (top 5 plus grey), value [Customer Hours Lost] |

**Slicers:** year; `dim_state[census_region]`.

## 2. State and county map

**Question:** Which states and counties lose the most outage hours per 1,000 customers, and which of
those rankings come with a footnote?

| Visual | Fields |
|---|---|
| Filled map (states) | Location `dim_state[state_name]`, colour saturation [Outage Hours per 1k Customers], sequential blue gradient from `#CDE2FB` to `#0D366B` |
| Shape map or Azure map (counties) | Location `dim_county[fips_code]` (with a US counties TopoJSON keyed on 5-digit FIPS), colour [County Outage Hours per 1k Customers], same gradient |
| Table: state ranking | `fct_state_reliability[national_rank]`, `dim_state[state_name]`, [Outage Hours per 1k Customers], `fct_state_reliability[footnote_reason]` |
| Table: county top 25 | `fct_county_reliability[national_rank]`, `dim_county[county]`, `dim_state[state_abbr]`, [County Outage Hours per 1k Customers], `fct_county_reliability[footnote_reason]` |
| Tooltip page | `fct_county_reliability[footnote_evidence]`, `fct_county_reliability[capped_share]`, `fct_county_reliability[peak_to_customers]` |

**Slicers:** year; `dim_state[census_region]`; `dim_state[state_name]`; a toggle "Ranked only" on
`fct_county_reliability[is_ranked]`.

**Notes on the page:** Puerto Rico is shown by PREPA operating region, not by municipio (D22), and
is never ranked (D43). Connecticut 2025 is footnoted because it is reported by planning region
(D60). Counties with a peak above 1.25x their customers may be misattributed (D36); Hamilton
County NY is the clearest case and is a lead to check, not a finding.

## 3. Storms and restoration

**Question:** Which kinds of storm cause the most outage time, and how long does each take to
restore?

| Visual | Fields |
|---|---|
| Bar chart | Axis `dim_storm_type[storm_group]`, value [Customer Hours Lost], sorted descending |
| Dot plot (line and clustered column, columns hidden, or the Deneb visual) | Axis `dim_storm_type[storm_group]`, values [Median Restoration Hours (10k+)] (blue) and [P90 Restoration Hours (10k+)] (orange), legend shown |
| Matrix | Rows `dim_state[census_region]`, columns `dim_storm_type[storm_group]`, value [Customer Hours Lost] as % of row total |
| Card pair | [Median Restoration Hours], [P90 Restoration Hours] for all events |

**Slicers:** year; `dim_state[census_region]`; a "Large events only" toggle (a bookmark switching
between the 10k+ and the all-events measures).

**Notes on the page:** Duration is from the first to the last reading at or above the event
threshold, a proxy for restoration. A storm match means a NOAA storm was active in the county when
the outage started (D41), not proof that it caused it.

## 4. Event drill-down

**Question:** What happened in a specific outage event: where, when, how big, how long, and which
storm?

| Visual | Fields |
|---|---|
| Table, top 20 by customer-hours | `dim_county[county]`, `dim_state[state_abbr]`, `fct_outage_events[event_start]`, `fct_outage_events[event_end]`, `fct_outage_events[duration_hours]`, `fct_outage_events[peak_customers_out]`, [Customer Hours Lost], `dim_storm_type[storm_group]` |
| Line chart (drill-through target) | Axis `dim_date[date_day]`, value [Customer Hours Lost], for the selected county |
| Multi-row card | `fct_outage_events[storm_event_id]`, `fct_outage_events[storm_begin_utc]`, `fct_outage_events[storm_end_utc]`, `fct_outage_events[overlap_hours]` |
| Card row: quality flags | `spans_feed_gap`, `spans_dropout`, `spans_empty_gap`, `exceeds_customers` (count of TRUE) |

**Slicers:** year; `dim_state[state_name]`; `dim_county[county]`; `dim_storm_type[storm_group]`;
a numeric range on `fct_outage_events[peak_customers_out]`.

**Drill-through:** from any county on pages 1-3 to this page, on `dim_county[fips_code]`.

**Notes on the page:** Events that span a feed gap, a dropout or a bridged run of empty readings
(D19, D64) are flagged. Their duration includes the bridged time.

## 5. Utility reliability benchmark

**Question:** How do the Eversource and National Grid operating companies compare on SAIDI and
SAIFI with utilities of the same size?

| Visual | Fields |
|---|---|
| Bar chart (horizontal), one bar per utility and state | Axis `dim_utility[utility_name]` and `fct_utility_reliability[state_abbr]`, value `saidi_without_med`, bar colour from [Utility Highlight Color], constant line [Peer Median SAIDI] |
| Table | `dim_utility[parent_company]`, `dim_utility[utility_name]`, `fct_utility_reliability[state_abbr]`, `rank_saidi_without_med`, `utilities_in_band`, [Utility SAIDI vs Peer Median], `saifi_without_med`, `saidi_with_med`, `data_quality_flag`; conditional icons on [Utility SAIDI vs Peer Median] (below 1 good, above 1 bad) |
| Line chart | Axis `dim_year[year]`, value [Utility SAIDI vs Peer Median], legend `dim_utility[utility_name]`, filtered to `is_eversource_or_national_grid = TRUE`, reference line at 1.00 |
| Scatter | X `saifi_without_med`, Y `saidi_without_med`, details `dim_utility[utility_name]`, colour from [Utility Highlight Color] |

**Slicers:** year; `fct_utility_reliability[size_band]` (default very_large);
`fct_utility_reliability[reporting_group]` (default IEEE 1366); `dim_state[state_name]`
(non-blank).

**Notes on the page:** The ranks use IEEE 1366 reporters only, without major event days, and
1 = most reliable (D23, D39). Rows with a D39 data quality flag are shown but not ranked. EAGLE-I
is county-level, so these comparisons come only from EIA-861.

## 6. Data quality and coverage

**Question:** Can the numbers on pages 1-5 be trusted: how complete is the coverage each year, and
which places are footnoted or restated?

| Visual | Fields |
|---|---|
| Line chart | Axis `dim_year[year]`, value [Reporting Counties] (2022-2025) |
| Line chart | Axis `dim_year[year]`, value `fct_published_coverage[max_share_covered]` weighted by `total_customers` (2018-2022) |
| Line chart | Axis `dim_year[year]`, value average `fct_data_quality_index[dqi]`, legend `fema_region` (six largest regions, rest grey) |
| Table: footnotes | `fct_county_reliability[footnote_reason]`, `dim_year[year]`, [Footnoted Rows] |
| Table: possible misattributions | `dim_county[county]`, `dim_county[state_abbr]`, `dim_county[customers]`, `dim_county[base_peak_customers_out]`, filtered to `is_calibrated = FALSE` and peak above 1.25x customers (a calculated column) |
| Text box | The notes below |

**Slicers:** `dim_year[year]` (its own, multi-select); `dim_state[census_region]`.

**Text box:**
- Coverage growth is not outage growth. Compare years on the same counties (D67).
- The county rankings for 2022-2023 were restated when the 2025 load added first-reported years
  (D61). See CHANGELOG.md.
- Connecticut 2025 is reported by planning region and footnoted (D60).
- OE-417 disturbance reports are used for 2022-2023 only (D59).
- EAGLE-I misses outages under 15 minutes and is less reliable for small and rural utilities.

## 7. Restoration forecast

**Question:** Two hours into an outage, how well can its total length be forecast, and where is
the forecast trustworthy?

Data: `workspace.outages.gold_restoration_predictions` (one row per eligible event and model;
`eval_split` = `validation` for 2024, `test` for 2025), related to `fct_outage_events` on
`event_id` for the actual `duration_hours`, storm group and region. Feature importance comes from
`docs/forecast_results.json` (`importance`), imported as a small table. Design: D71, D72; numbers:
`docs/forecast_results.md`.

| Visual | Fields |
|---|---|
| Scatter (log axes) | X `p50_hours`, Y actual `duration_hours`, filtered to `model = 'hgb'` and `eval_split = 'test'`; a y = x reference line |
| Clustered bar: p90 coverage by storm family | Axis `dim_storm_type[storm_group]`, value [P90 Coverage] (share of events with actual <= `p90_hours`), legend `model`; a constant line at 90%; event count in the tooltip |
| Card row | [P50 MAE Hours] and [P90 Coverage] for `hgb`, and the same for `baseline` |
| Bar: feature importance | Axis `feature`, value `mae_p50_increase`, top 12, sorted descending |
| Text box | The notes below |

**Slicers:** `model` (single select, default `hgb`); `eval_split` (default `test`);
`dim_state[census_region]`.

**Measures (add to measures.md when built):** [P90 Coverage] = share of rows with
`duration_hours <= p90_hours`; [P50 MAE Hours] = average of `ABS(duration_hours - p50_hours)`.

**Text box:**
- The forecast is made 2 hours after an outage starts, for outages still above their county
  threshold then. It does not cover short blips.
- Storm type comes from NOAA Storm Events, published months later; it stands in for the live NWS
  warnings an operator would have. The "no storm features" model shows what the forecast is worth
  without it.
- Hurricane / tropical results rest on few events, and 2025 has too few to judge. Show the event
  count next to every group.
