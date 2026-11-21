# Data Profile: Storm, Zone, Reliability and Disturbance Sources

Profiled on 2026-11-21 with DuckDB 2.0.1 using `scripts/profile_sources.py`. Raw files are read only. Join rates are measured against EAGLE-I Silver and Gold rebuilt in DuckDB with the final rules (D1-D20, 0.25% event threshold): 3,063 counties, 442,362 outage events.

## 1. NOAA Storm Events (details files)

Files: `data/raw/noaa_storm_events/<year>/StormEvents_details-ftp_v1.0_d<year>_c20261119.csv.gz` (NCEI rebuilt all three years on 2026-11-19). One row per event; an event is one weather phenomenon in one county or forecast zone.

### Rows by year and location type

| year | events | episodes | county_C | zone_Z | other | event_types | first_begin_utc | last_end_utc |
|---|---|---|---|---|---|---|---|---|
| 2022 | 69,887 | 10,464 | 32,927 | 36,960 | 0 | 53 | 2021-12-31 14:00 | 2023-01-01 07:59 |
| 2023 | 75,593 | 10,359 | 42,515 | 33,078 | 0 | 51 | 2022-12-31 14:00 | 2024-01-01 06:59 |
| 2024 | 69,802 | 9,909 | 39,719 | 30,083 | 0 | 50 | 2024-01-01 04:00 | 2025-01-01 09:59 |

### Columns and nulls (all years)

Read as text. Null means empty or missing.

| column | null_or_empty | share |
|---|---|---|
| BEGIN_YEARMONTH | 0 | 0.0% |
| BEGIN_DAY | 0 | 0.0% |
| BEGIN_TIME | 0 | 0.0% |
| END_YEARMONTH | 0 | 0.0% |
| END_DAY | 0 | 0.0% |
| END_TIME | 0 | 0.0% |
| EPISODE_ID | 0 | 0.0% |
| EVENT_ID | 0 | 0.0% |
| STATE | 0 | 0.0% |
| STATE_FIPS | 0 | 0.0% |
| YEAR | 0 | 0.0% |
| MONTH_NAME | 0 | 0.0% |
| EVENT_TYPE | 0 | 0.0% |
| CZ_TYPE | 0 | 0.0% |
| CZ_FIPS | 0 | 0.0% |
| CZ_NAME | 0 | 0.0% |
| WFO | 0 | 0.0% |
| BEGIN_DATE_TIME | 0 | 0.0% |
| CZ_TIMEZONE | 0 | 0.0% |
| END_DATE_TIME | 0 | 0.0% |
| INJURIES_DIRECT | 0 | 0.0% |
| INJURIES_INDIRECT | 0 | 0.0% |
| DEATHS_DIRECT | 0 | 0.0% |
| DEATHS_INDIRECT | 0 | 0.0% |
| DAMAGE_PROPERTY | 49,267 | 22.9% |
| DAMAGE_CROPS | 49,550 | 23.0% |
| SOURCE | 0 | 0.0% |
| MAGNITUDE | 104,763 | 48.7% |
| MAGNITUDE_TYPE | 132,724 | 61.7% |
| FLOOD_CAUSE | 196,105 | 91.1% |
| CATEGORY | 215,167 | 99.9% |
| TOR_F_SCALE | 210,238 | 97.7% |
| TOR_LENGTH | 210,238 | 97.7% |
| TOR_WIDTH | 210,238 | 97.7% |
| TOR_OTHER_WFO | 214,516 | 99.6% |
| TOR_OTHER_CZ_STATE | 214,516 | 99.6% |
| TOR_OTHER_CZ_FIPS | 214,516 | 99.6% |
| TOR_OTHER_CZ_NAME | 214,516 | 99.6% |
| BEGIN_RANGE | 91,790 | 42.6% |
| BEGIN_AZIMUTH | 91,790 | 42.6% |
| BEGIN_LOCATION | 91,790 | 42.6% |
| END_RANGE | 91,790 | 42.6% |
| END_AZIMUTH | 91,790 | 42.6% |
| END_LOCATION | 91,790 | 42.6% |
| BEGIN_LAT | 91,790 | 42.6% |
| BEGIN_LON | 91,790 | 42.6% |
| END_LAT | 91,790 | 42.6% |
| END_LON | 91,790 | 42.6% |
| EPISODE_NARRATIVE | 0 | 0.0% |
| EVENT_NARRATIVE | 38,885 | 18.1% |
| DATA_SOURCE | 0 | 0.0% |

### Time zone handling

`BEGIN_DATE_TIME` / `END_DATE_TIME` (and the numeric `BEGIN_YEARMONTH`, `BEGIN_DAY`, `BEGIN_TIME` parts) are **local standard time** of the county or zone. `CZ_TIMEZONE` holds the offset, e.g. `CST-6` = UTC-6, `GST10` = UTC+10 (Guam). UTC = local - offset. A few rows carry daylight codes (`EDT-4`, `CDT-5`, `PDT-7`), which the same rule handles.

| cz_timezone | utc_offset_h | events | unparsed |
|---|---|---|---|
| CST-6 | -6 | 105,653 | 0 |
| EST-5 | -5 | 66,478 | 0 |
| MST-7 | -7 | 26,308 | 0 |
| PST-8 | -8 | 12,831 | 0 |
| AST-4 | -4 | 1,446 | 0 |
| HST-10 | -10 | 1,111 | 0 |
| AKST-9 | -9 | 1,042 | 0 |
| PDT-7 | -7 | 178 | 0 |
| GST10 | 10 | 104 | 0 |
| SST-11 | -11 | 78 | 0 |
| EDT-4 | -4 | 41 | 0 |
| CDT-5 | -5 | 12 | 0 |

The numeric parts agree with `BEGIN_DATE_TIME` (0 mismatches). 0 events end before they begin.

### Top event types

| event_type | events | by_county | by_zone |
|---|---|---|---|
| Thunderstorm Wind | 58,772 | 58,772 | 0 |
| Hail | 27,882 | 27,882 | 0 |
| Drought | 16,161 | 1 | 16,160 |
| High Wind | 12,664 | 4 | 12,660 |
| Flash Flood | 11,383 | 11,383 | 0 |
| Winter Weather | 11,210 | 0 | 11,210 |
| Excessive Heat | 9,100 | 0 | 9,100 |
| Heat | 8,441 | 2 | 8,439 |
| Winter Storm | 8,104 | 0 | 8,104 |
| Marine Thunderstorm Wind | 7,414 | 0 | 7,414 |
| Flood | 7,279 | 7,279 | 0 |
| Heavy Snow | 7,068 | 5 | 7,063 |
| Tornado | 5,044 | 5,044 | 0 |
| Strong Wind | 3,478 | 1 | 3,477 |
| Extreme Cold/Wind Chill | 2,968 | 0 | 2,968 |
| Heavy Rain | 2,840 | 2,840 | 0 |
| Dense Fog | 1,854 | 0 | 1,854 |
| Cold/Wind Chill | 1,854 | 0 | 1,854 |
| Blizzard | 1,619 | 0 | 1,619 |
| Frost/Freeze | 1,349 | 0 | 1,349 |

### Damage fields

`DAMAGE_PROPERTY` and `DAMAGE_CROPS` are text with K/M/B suffixes (e.g. `10.00K`); empty is not the same as `0.00K`.

| suffix | events |
|---|---|
| K | 164,849 |
|  | 49,267 |
| M | 1,155 |
| B | 11 |

### Location coding and resolution to EAGLE-I counties

- `CZ_TYPE = 'C'`: `CZ_FIPS` is the county FIPS within `STATE_FIPS`; county FIPS = `LPAD(STATE_FIPS, 2) || LPAD(CZ_FIPS, 3)`.
- `CZ_TYPE = 'Z'`: `CZ_FIPS` is an NWS forecast zone number. Zone key = state abbreviation (from `STATE_FIPS` via `data/reference/state_regions.csv`) + 3-digit zone, mapped to counties with the NWS correlation file in effect on the event's begin date. One zone can cover several counties, and one county several zones.
- No `M` (marine) rows appear in these three files.

| Measure | Value |
|---|---|
| County events (C) resolving to an EAGLE-I county | 111,807 of 115,161 (97.1%) |
| Zone events (Z) found in the zone file in effect | 91,085 of 100,121 (91.0%) |
| Zone events (Z) resolving to at least one EAGLE-I county | 88,330 of 100,121 (88.2%) |
| Same, using only the latest 2022-2024 zone file (bp05mr24) | 87,336 of 100,121 (87.2%) |
| Counties per resolved zone event | median 1, mean 1.27, max 9 |
| Events whose STATE_FIPS is not a state, DC or territory in the lookup | 10,146 |

Unresolved events by NOAA state (top 12):

| noaa_state | cz_type | events |
|---|---|---|
| GULF OF MEXICO | Z | 3,024 |
| ATLANTIC NORTH | Z | 2,411 |
| ATLANTIC SOUTH | Z | 1,892 |
| NEBRASKA | C | 1,321 |
| NEBRASKA | Z | 1,238 |
| PUERTO RICO | C | 1,056 |
| ALASKA | Z | 610 |
| LAKE MICHIGAN | Z | 370 |
| LAKE ERIE | Z | 351 |
| PUERTO RICO | Z | 314 |
| LAKE SUPERIOR | Z | 274 |
| KANSAS | C | 262 |

Most unresolved land events are not a join problem: EAGLE-I has no data for those counties. EAGLE-I county coverage against the counties in the NWS zone file (bp05mr24), states below 95%:

| state | nws_counties | eaglei_counties | coverage |
|---|---|---|---|
| PR | 78 | 7 | 0.09 |
| AK | 30 | 9 | 0.3 |
| NE | 93 | 56 | 0.602 |
| NV | 17 | 15 | 0.882 |
| UT | 29 | 27 | 0.931 |
| KS | 105 | 98 | 0.933 |
| TN | 95 | 89 | 0.937 |
| NM | 33 | 31 | 0.939 |
| WA | 39 | 37 | 0.949 |

### Event-level match to EAGLE-I outage events

NOAA to EAGLE-I: a resolved NOAA event (outage-relevant types only) matches when one of its counties has an EAGLE-I event overlapping [NOAA begin - 1 h, NOAA end + 12 h] in UTC. Overall: 93,119 of 175,631 (53.0%).

| event_type | resolved_events | with_eaglei_event | match_rate |
|---|---|---|---|
| Thunderstorm Wind | 57,789 | 42,113 | 72.9% |
| Hail | 26,988 | 11,636 | 43.1% |
| High Wind | 12,058 | 4,866 | 40.4% |
| Winter Weather | 11,012 | 3,034 | 27.6% |
| Flash Flood | 10,837 | 6,616 | 61.1% |
| Excessive Heat | 8,818 | 3,220 | 36.5% |
| Heat | 8,320 | 2,635 | 31.7% |
| Winter Storm | 7,800 | 3,088 | 39.6% |
| Heavy Snow | 6,827 | 2,553 | 37.4% |
| Flood | 6,744 | 3,485 | 51.7% |
| Tornado | 4,920 | 3,456 | 70.2% |
| Strong Wind | 3,451 | 2,068 | 59.9% |
| Extreme Cold/Wind Chill | 2,835 | 796 | 28.1% |
| Cold/Wind Chill | 1,829 | 596 | 32.6% |
| Blizzard | 1,400 | 244 | 17.4% |
| Wildfire | 1,033 | 579 | 56.1% |
| Tropical Storm | 966 | 910 | 94.2% |
| Lightning | 693 | 391 | 56.4% |
| Ice Storm | 650 | 423 | 65.1% |
| Debris Flow | 352 | 133 | 37.8% |
| Storm Surge/Tide | 132 | 116 | 87.9% |
| Hurricane (Typhoon) | 110 | 110 | 100.0% |
| Tropical Depression | 67 | 51 | 76.1% |

EAGLE-I to NOAA: an EAGLE-I event matches when a NOAA event (any type) in the same county was active between 24 h before and 2 h after the outage started.

| bucket | eaglei_events | with_noaa_event | match_rate |
|---|---|---|---|
| top 100 by customer-hours | 100 | 62 | 62.0% |
| top 1,000 by customer-hours | 1,000 | 740 | 74.0% |
| peak >= 10,000 customers out | 5,149 | 2,204 | 42.8% |
| all events | 442,362 | 95,927 | 21.7% |

## 2. NWS zone-county correlation

Files: `data/raw/nws_zone_county/<effective year>/bp<ddmmyy>.dbx`, pipe-delimited, no header, 11 fields: STATE, ZONE, CWA, NAME, STATE_ZONE, COUNTY, FIPS, TIME_ZONE, FE_AREA, LAT, LON. Each version is valid from its date until the next one.

| version | effective_from | effective_to | rows | zones | counties | eaglei_counties_covered | null_keys |
|---|---|---|---|---|---|---|---|
| bp08se21 | 2021-09-08 00:00:00 | 2022-03-22 00:00:00 | 4,623 | 3,790 | 3,231 | 3,061 | 0 |
| bp22mr22 | 2022-03-22 00:00:00 | 2022-09-13 00:00:00 | 4,707 | 3,882 | 3,268 | 3,061 | 0 |
| bp13se22 | 2022-09-13 00:00:00 | 2023-03-08 00:00:00 | 4,736 | 3,899 | 3,268 | 3,061 | 0 |
| bp08mr23 | 2023-03-08 00:00:00 | 2023-09-19 00:00:00 | 4,763 | 3,924 | 3,270 | 3,061 | 0 |
| bp19se23 | 2023-09-19 00:00:00 | 2024-03-05 00:00:00 | 4,769 | 3,958 | 3,270 | 3,061 | 0 |
| bp05mr24 | 2024-03-05 00:00:00 | 2025-03-18 00:00:00 | 4,793 | 3,978 | 3,269 | 3,061 | 0 |

| version | zones_with_several_counties | max_counties_per_zone | counties_in_several_zones |
|---|---|---|---|
| bp05mr24 | 409 | 10 | 666 |
| bp08mr23 | 423 | 10 | 661 |
| bp08se21 | 413 | 10 | 616 |
| bp13se22 | 421 | 10 | 649 |
| bp19se23 | 404 | 10 | 664 |
| bp22mr22 | 414 | 10 | 638 |

Changes between consecutive versions (zone keys added or removed):

| change | zones_added | zones_removed |
|---|---|---|
| bp08se21 -> bp22mr22 | 142 | 50 |
| bp22mr22 -> bp13se22 | 54 | 37 |
| bp13se22 -> bp08mr23 | 47 | 22 |
| bp08mr23 -> bp19se23 | 69 | 35 |
| bp19se23 -> bp05mr24 | 45 | 25 |

Time zone field: `TIME_ZONE` is a one- or two-letter NWS code per zone; it is not needed for the join because NOAA events carry their own offset.

## 3. EIA Form 861

Files: `data/raw/eia861/<year>/f861<year>.zip` with `Reliability_<year>.xlsx`, `Sales_Ult_Cust_<year>.xlsx` and `Service_Territory_<year>.xlsx` extracted. Each sheet has a multi-row header (3 rows for Reliability and Sales, 1 for Service Territory) and a footer row; only rows whose first cell is a 4-digit year are data. The unit of record is utility x state x year. There are no dates or times: everything is annual, so time zones do not apply.

### Reliability (SAIDI / SAIFI)

Two reporting standards side by side: IEEE 1366 and 'other'. Each has values with major event days (all events) and without; IEEE adds 'loss of supply removed'. Missing values are `.` (not reported) or empty.

| year | rows | utilities | states | ieee_saidi_with_med | ieee_saidi_without_med | other_saidi_with_med | neither | both |
|---|---|---|---|---|---|---|---|---|
| 2022 | 964 | 899 | 55 | 714 | 696 | 241 | 9 | 0 |
| 2023 | 970 | 905 | 54 | 734 | 709 | 231 | 5 | 0 |
| 2024 | 974 | 911 | 54 | 746 | 730 | 222 | 6 | 0 |

Placeholder values in the IEEE SAIDI-with-MED column (all years):

| value | rows |
|---|---|
| . | 714 |

Eversource and National Grid entities (analysis question 5), 2024, IEEE standard:

| utility_number | utility_name | state | ownership | customers | saidi_with_med | saidi_without_med | saifi_with_med | saifi_without_med |
|---|---|---|---|---|---|---|---|---|
| 4176 | Connecticut Light & Power Co | CT | Investor Owned | 1326461 | 158.8 | 76.9 | 0.891 | 0.649 |
| 11804 | Massachusetts Electric Co | MA | Investor Owned | 1345044 | 133.74 | 90.72 | 1.001 | 0.842 |
| 54913 | NSTAR Electric Company | MA | Investor Owned | 1462127 | 80.6 | 66.1 | 0.692 | 0.639 |
| 13206 | Nantucket Electric Co | MA | Investor Owned | 13995 | 138.16 | 50.4 | 0.719 | 0.328 |
| 13573 | Niagara Mohawk Power Corp. | NY | Investor Owned | 1690739 | 510.14 | 140.65 | 1.694 | 1.053 |
| 15472 | Public Service Co of NH | NH | Investor Owned | 551456 | 786.2 | 81.5 | 1.604 | 0.739 |
| 13214 | The Narragansett Electric Co | RI | Investor Owned | 509231 | 104.25 | 60.79 | 0.896 | 0.761 |

### Sales to ultimate customers (customers per utility and state)

`Part` matters: A = bundled service, B = energy-only, C = delivery-only, D = bundled by other providers. In retail-choice states one customer appears twice, once with its energy supplier (B) and once with its wires utility (C). Customer totals must use A + C + D, never B.

| year | part | service_type | rows | customers |
|---|---|---|---|---|
| 2022 | A | Bundled | 1,774 | 138,605,644.0 |
| 2022 | B | Energy | 907 | 15,423,554.0 |
| 2022 | C | Delivery | 76 | 15,423,554.0 |
| 2022 | D | Bundled | 85 | 7,769,695.0 |
| 2023 | A | Bundled | 1,825 | 139,412,113.0 |
| 2023 | B | Energy | 853 | 16,132,109.0 |
| 2023 | C | Delivery | 76 | 16,132,109.0 |
| 2023 | D | Bundled | 78 | 7,843,089.0 |
| 2024 | A | Bundled | 1,836 | 139,859,654.0 |
| 2024 | B | Energy | 834 | 17,481,113.0 |
| 2024 | C | Delivery | 73 | 17,481,113.0 |
| 2024 | D | Bundled | 85 | 8,050,525.0 |

State join to EAGLE-I, 2024: EIA customers (parts A + C + D) 165,391,292; EAGLE-I D13 denominators 177,246,426 (ratio 1.072). Per-state ratio EAGLE-I / EIA: median 1.012, 40 of 56 states within 10%.

States furthest from 1:

| state | eia_customers | eaglei_customers | ratio |
|---|---|---|---|
| MA | 3,372,904.0 | 6,799,970.0 | 2.02 |
| SC | 2,998,873.0 | 5,758,961.0 | 1.92 |
| HI | 506,988.0 | 668,078.0 | 1.32 |
| MO | 3,347,316.0 | 4,321,653.0 | 1.29 |
| SD | 516,156.0 | 658,178.0 | 1.27 |
| AK | 356,597.0 | 272,779.0 | 0.765 |
| NC | 5,827,720.0 | 7,115,460.0 | 1.22 |
| VA | 4,104,032.0 | 4,915,491.0 | 1.2 |

Where the gap comes from in MA and SC: the D13 denominator mostly comes from EAGLE-I's own 2024 `total_customers`, which is far above both MCC and EIA there (D12's larger-value rule keeps it).

| state | denominator_source | counties | d13_customers |
|---|---|---|---|
| MA | max_mcc_2024 | 9 | 3,220,014.0 |
| MA | total_customers_2024 | 5 | 3,579,956.0 |
| SC | max_mcc_2024 | 23 | 3,697,385.0 |
| SC | total_customers_2024 | 23 | 2,061,576.0 |

Largest MA counties by D13 denominator (for scale: Suffolk County has about 770,000 residents, so 1.67 M customers is not plausible):

| fips_code | county | d13_customers | denominator_source |
|---|---|---|---|
| 25025 | Suffolk | 1,666,496 | total_customers_2024 |
| 25017 | Middlesex | 807,605 | total_customers_2024 |
| 25021 | Norfolk | 646,684 | total_customers_2024 |
| 25023 | Plymouth | 608,164 | max_mcc_2024 |
| 25005 | Bristol | 581,443 | max_mcc_2024 |

### Service territory (utility to county)

The only county-level link in EIA-861: one row per utility, state and county **name**. There is no county FIPS. Matching to EAGLE-I therefore needs a one-off name-to-FIPS crosswalk (the project rule is to join on FIPS codes, never on names).

| year | rows | utilities | state_county_pairs | matched_to_eaglei | match_rate |
|---|---|---|---|---|---|
| 2022 | 11,872 | 2,914 | 3,232 | 3,016 | 93.3% |
| 2023 | 11,872 | 2,917 | 3,232 | 3,016 | 93.3% |
| 2024 | 11,866 | 2,912 | 3,232 | 3,016 | 93.3% |

Utilities per county (2024): median 3, mean 3.67, max 15; 2,876 of 3,232 counties have more than one utility. EAGLE-I (state, name) keys that are ambiguous after normalization: 6 (e.g. MD|baltimore, MO|saint louis, VA|fairfax, VA|franklin).

Unmatched (state, county) examples, 2024:

| state | county |
|---|---|
| NV | Lincoln |
| AK | Bethel |
| AK | Juneau |
| AK | Haines |
| AK | Prince of Wales Ketchikan |
| AK | Skagway Hoonah Angoon |
| AK | Dillingham |
| AK | Kodiak Island |
| AK | Kusilvak |
| AK | Nome |
| AK | Northwest Arctic |
| AK | Yakutat |

## 4. DOE OE-417 electric emergency incident and disturbance reports

Files: `data/raw/oe417/<year>/OE417_<year>.xls` (legacy Excel, read with xlrd). 2022 and 2023 come from Internet Archive copies of the official download URLs (`OE417_<year>.source.txt` records each). **2024 is missing:** the official host is IPv6-only and unreachable from this network, and no archived copy exists; `scripts/download_oe417.py` prints the manual steps.

### Columns, rows and nulls

| column | empty | unknown_or_ongoing |
|---|---|---|
| Month | 348 | 0 |
| Date Event Began | 32 | 0 |
| Time Event Began | 0 | 0 |
| Date of Restoration | 0 | 98 |
| Time of Restoration | 0 | 101 |
| Area Affected | 0 | 0 |
| NERC Region | 0 | 9 |
| Alert Criteria | 0 | 0 |
| Event Type | 0 | 0 |
| Demand Loss (MW) | 0 | 179 |
| Number of Customers Affected | 0 | 75 |
| Event Month | 390 | 0 |

| year | rows | first | last | restoration_missing |
|---|---|---|---|---|
| 2022 | 390 | 2022-01-01 | 2022-12-31 | 56 |
| 2023 | 348 | 2023-01-01 | 2023-12-30 | 48 |

`Number of Customers Affected` is numeric in 663 of 738 rows; 441 are 0. `Demand Loss (MW)` is numeric in 559 rows.

Event type text is not standardized (leading dashes, several types joined). Top values:

| event_type | rows |
|---|---|
| Vandalism | 139 |
| Severe Weather | 117 |
| System Operations | 105 |
| Suspicious Activity | 89 |
| Weather or natural disaster | 43 |
| Transmission Interruption | 38 |
| Suspicious activity | 28 |
| Other | 28 |
| Actual Physical Attack/Vandalism | 23 |
| Actual Physical Attack | 15 |

### Time zone handling

Dates are stored as text (`mm/dd/yyyy`) and times as Excel time cells. The file states no time zone. The estimate below compares OE-417 begin times, read as if UTC, with EAGLE-I event starts (UTC) in the same counties.

### Location coding

`Area Affected` is free text: `State: County, County;` repeated, often just `State:` with no county, sometimes several states. No FIPS codes. Parsed here with a regex and matched to EAGLE-I county names after normalization (lowercase, no 'County'/'Parish' suffix, 'St.' = 'Saint').

| Measure | Value |
|---|---|
| Rows with at least one state | 687 of 738 (93.1%) |
| Rows naming at least one county | 509 of 738 (69.0%) |
| State names recognized | 921 of 921 (100.0%) |
| County names matched to an EAGLE-I county | 1017 of 1030 (98.7%) |
| Rows with at least one matched county | 498 of 738 |

### Event-level match to EAGLE-I outage events

A row matches when an EAGLE-I event in its matched counties (or, with no county, anywhere in its states) overlaps [begin date - 1 day, restoration date + 1 day]. Day-level windows because the OE-417 time zone is not stated. State-only matches are weak: large states have EAGLE-I events almost every day.

| level | rows | with_eaglei_event | match_rate |
|---|---|---|---|
| county | 475 | 258 | 54.3% |
| no date | 32 | 0 | 0.0% |
| no location | 51 | 0 | 0.0% |
| state only | 180 | 178 | 98.9% |

County-level rows by customers affected (incidents with no customer impact, such as vandalism or suspicious activity, are not expected to appear in EAGLE-I):

| customers_affected | rows | with_eaglei_event | match_rate |
|---|---|---|---|
| 0 | 323 | 133 | 41.2% |
| 1,000-9,999 | 28 | 22 | 78.6% |
| 1-999 | 11 | 7 | 63.6% |
| 10,000+ | 75 | 69 | 92.0% |
| unknown | 38 | 27 | 71.1% |

EAGLE-I start minus OE-417 begin (read as UTC), county-level rows, events within 12 h: 725 pairs, median +4 h. Most common offsets:

| hours | pairs |
|---|---|
| 5 | 86 |
| 6 | 85 |
| 4 | 77 |
| 2 | 46 |
| 3 | 43 |
| 8 | 41 |

## 5. How each source joins to EAGLE-I

| Source | Grain | Location key | Time | Join to EAGLE-I | Measured |
|---|---|---|---|---|---|
| NOAA, CZ_TYPE C | event x county | county FIPS (STATE_FIPS + CZ_FIPS) | local standard, offset in CZ_TIMEZONE | county FIPS + UTC time overlap | 97.1% of C events resolve |
| NOAA, CZ_TYPE Z | event x zone | state + zone via NWS file in effect | same | zone -> counties (1:n), then as above | 88.2% of Z events resolve |
| NWS zone-county | zone x county x version | STATE + ZONE -> FIPS | effective dates per file | bridge only | see section 2 |
| EIA-861 reliability / sales | utility x state x year | state code; utility number | annual | state level only | EAGLE-I / EIA customers 1.072 |
| EIA-861 service territory | utility x county name x year | state + county name | annual | needs name -> FIPS crosswalk | 93.3% of 2024 pairs match |
| OE-417 | incident | free-text state and county names | local?, not stated | parsed names -> FIPS, day-level overlap | 98.7% of named counties match |
