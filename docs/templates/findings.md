<!-- Rendered by scripts/analysis.py from docs/templates/findings.md. Edit the template, not docs/findings.md. -->
# Findings: US power outages and storm impact, 2022-2025

Every number on this page comes from a query in `sql/analysis/` run on the dbt marts in
Databricks. `scripts/analysis.py check` reruns the queries and fails if any number here no longer
matches (D68). The full results are in `docs/analysis_results/`.

**Read this first**
- **Event year:** an outage event counts in the year it starts (UTC), even when it runs into the
  next year. Customer-hours are never split across years.
- **Customer-hours** are capped at the county's customer count (D4). Rates are outage hours per
  1,000 customers; divide by 1,000 for hours per customer.
- **Puerto Rico** results are for PREPA's seven operating regions, filed under the FIPS code of
  each region's namesake municipio. They are not municipios (D22).
- **D61 restatement:** a county has rows only from its first reported year. This changed some
  published 2022-2023 ranks; the before and after values are in `CHANGELOG.md`.
- **OE-417** disturbance reports are loaded for 2022-2023 only (D25, D59).

## Q1. The largest outage events and their causes

{{ table q1_top20_all_years | cols=event_rank:#,county:County,state_abbr:State,event_start:Start:date,duration_hours:Hours:f0,peak_customers_out:Peak out:int,customer_hours_lost:Customer-hours:m1,storm_type:Storm | rows=10 }}

- **Hurricane Beryl in Harris County TX is the largest event by far:**
  {{ q1_top20_all_years[0].customer_hours_lost | m1 }} customer-hours over
  {{ q1_top20_all_years[0].duration_hours | f0 }} hours, with
  {{ q1_top20_all_years[0].peak_customers_out | int }} customers out at the peak. NOAA places no
  Beryl event in Harris County, so the event shows as unmatched (D37). Hurricane Fiona in the
  Mayagüez and Arecibo regions is unmatched for the same reason: NOAA logs Fiona in Puerto Rico
  only as floods, debris flows and thunderstorm wind.
- **Tropical systems dominate the top 20:**
  {{ q1_top20_storm_mix[storm_group=Hurricane / tropical].events }} of the 20 are hurricanes or
  tropical storms, and {{ q1_top20_storm_mix[storm_group=No storm matched].events }} have no NOAA
  match, Beryl and Fiona among them. Across all events, hurricanes and tropical storms cause
  {{ q1_storm_share_all[storm_group=Hurricane / tropical].share_of_customer_hours | pct1 }} of
  customer-hours from only {{ q1_storm_share_all[storm_group=Hurricane / tropical].share_of_events | pct1 }}
  of events.
- **Most outages have no storm behind them:**
  {{ q1_storm_share_all[storm_group=No storm matched].share_of_events | pct1 }} of events and
  {{ q1_storm_share_all[storm_group=No storm matched].share_of_customer_hours | pct1 }} of
  customer-hours have no NOAA match.
- **Each year's largest event had a different cause:**
  - 2023: the {{ q1_top20_by_year[event_year=2023,year_rank=1].storm_type }} in
    {{ q1_top20_by_year[event_year=2023,year_rank=1].county }} County
    {{ q1_top20_by_year[event_year=2023,year_rank=1].state_abbr }}
    ({{ q1_top20_by_year[event_year=2023,year_rank=1].customer_hours_lost | m1 }}).
  - 2025: the January {{ q1_top20_by_year[event_year=2025,year_rank=1].storm_type }} in
    {{ q1_top20_by_year[event_year=2025,year_rank=1].county }} County
    {{ q1_top20_by_year[event_year=2025,year_rank=1].state_abbr }}
    ({{ q1_top20_by_year[event_year=2025,year_rank=1].customer_hours_lost | m1 }}, peak
    {{ q1_top20_by_year[event_year=2025,year_rank=1].peak_customers_out | int }} customers out).

![Top 10 events](images/chart_top10_events.png)

## Q2. States and counties with the most outage hours per customer

Rank 1 state each year:
- 2022: {{ q2_state_ranks[year=2022,national_rank=1].state_name }} ({{ q2_state_ranks[year=2022,national_rank=1].outage_hours_per_1000 | f0 }} hours per 1,000 customers)
- 2023: {{ q2_state_ranks[year=2023,national_rank=1].state_name }} ({{ q2_state_ranks[year=2023,national_rank=1].outage_hours_per_1000 | f0 }})
- 2024: {{ q2_state_ranks[year=2024,national_rank=1].state_name }} ({{ q2_state_ranks[year=2024,national_rank=1].outage_hours_per_1000 | f0 }})
- 2025: {{ q2_state_ranks[year=2025,national_rank=1].state_name }} ({{ q2_state_ranks[year=2025,national_rank=1].outage_hours_per_1000 | f0 }})

{{ table q2_state_ranks | cols=national_rank:Rank 2024,state_name:State,census_region:Region,outage_hours_per_1000:Hours per 1k:f0,customer_hours_lost:Customer-hours:m1,events:Events:int | where=year=2024 | rows=10 }}

Counties, top 3 per year:

{{ table q2_county_top10 | cols=year:Year,national_rank:Rank,county:County,state_abbr:State,outage_hours_per_1000:Hours per 1k:f0,customers:Customers:int | where=national_rank<=3 }}

- **Hurricane Helene put western North Carolina at the top of the 2024 county list:**
  {{ q2_county_top10[year=2024,national_rank=1].county }} County
  ({{ q2_county_top10[year=2024,national_rank=1].outage_hours_per_1000 | f0 }} hours per 1,000
  customers) and {{ q2_county_top10[year=2024,national_rank=2].county }} County are ranks 1 and 2.
  South Carolina is the top state that year.
- **Maine is at or near the top every year to 2024:** rank
  {{ q2_state_ranks[year=2022,state_abbr=ME].national_rank }} in 2022,
  {{ q2_state_ranks[year=2023,state_abbr=ME].national_rank }} in 2023 and
  {{ q2_state_ranks[year=2024,state_abbr=ME].national_rank }} in 2024. In 2025 it fell to
  {{ q2_state_ranks[year=2025,state_abbr=ME].national_rank }}.
- **Austin County TX:**
  - It is rank {{ q2_austin_tx[year=2023].national_rank }} in 2023
    ({{ q2_austin_tx[year=2023].outage_hours_per_1000 | f0 }} hours per 1,000 customers). It passed
    the D46 misattribution test and stays ranked: a small county
    ({{ q2_austin_tx[year=2023].customers | int }} customers) next to Houston, whose rate reflects
    Houston-area storms.
  - In 2024 it is footnoted by D45, because most of its customer-hours came from capped readings.
- **Possible misattributions:** {{ count(q2_possible_misattributions) }} counties outside the
  calibrated states have a 2022-2024 peak above 1.25x their customers. Their readings are flagged
  and capped (D4), not floored. When D36 was written the list had 30 counties; the same rule on
  today's marts finds the count above. The largest ratios:

{{ table q2_possible_misattributions | cols=county:County,state_abbr:State,customers:Customers:int,base_peak_customers_out:Peak out:int,peak_to_customers:Peak / customers:f2 | rows=8 }}

- **Connecticut 2025 is footnoted, not ranked:** from 2025-05-29 EAGLE-I reports it by planning
  region, and those regions have no customer denominator (D60). 2025 therefore ranks
  {{ q2_ranked_counts[year=2025].ranked_states }} states instead of
  {{ q2_ranked_counts[year=2024].ranked_states }}.
- **After the D61 restatement,** Mississippi is rank
  {{ q2_state_ranks[year=2022,state_abbr=MS].national_rank }} in 2022 and
  {{ q2_state_ranks[year=2023,state_abbr=MS].national_rank }} in 2023.

![State ranking 2024](images/chart_state_ranking_2024.png)

## Q3. Regions and the storms that cost them the most

The storm families with at least 10% of a region's customer-hours (50 states and DC):

{{ table q3_region_storm | cols=census_region:Region,storm_group:Storm family,events:Events:int,customer_hours_lost:Customer-hours:m1,share_of_region:Share of region:pct0,hours_per_1000_per_year:Hours per 1k per year:f0 | where=share_of_region>=0.1 }}

- **The South's outages are hurricane outages:** tropical systems account for
  {{ q3_region_storm[census_region=South,storm_group=Hurricane / tropical].share_of_region | pct0 }}
  of its customer-hours. That is
  {{ q3_region_storm[census_region=South,storm_group=Hurricane / tropical].hours_per_1000_per_year | f0 }}
  hours per 1,000 customers a year, more than any other region loses to any one storm family.
- **The Midwest is a thunderstorm region:** thunderstorm wind causes
  {{ q3_region_storm[census_region=Midwest,storm_group=Thunderstorm wind].share_of_region | pct0 }}
  of its customer-hours and tornadoes
  {{ q3_region_storm[census_region=Midwest,storm_group=Tornado].share_of_region | pct0 }}.
- **In the Northeast no single storm family dominates:**
  - winter weather {{ q3_region_storm[census_region=Northeast,storm_group=Winter weather].share_of_region | pct0 }};
  - thunderstorm wind {{ q3_region_storm[census_region=Northeast,storm_group=Thunderstorm wind].share_of_region | pct0 }};
  - other wind {{ q3_region_storm[census_region=Northeast,storm_group=Other wind].share_of_region | pct0 }}.
- **In the West, wind is the cause**
  ({{ q3_region_storm[census_region=West,storm_group=Other wind].share_of_region | pct0 }} of its
  customer-hours), and wildfire is not. Wildfire-matched outages in the West total
  {{ q3_named_comparisons[comparison=West wildfires,event_year=2024].customer_hours_lost | m1 }} in
  2024. Wildfire shutoffs happen in high wind, so NOAA most likely records those days as wind
  events.
- **Texas winter weather was a 2023 story:**
  {{ q3_named_comparisons[comparison=Texas winter weather and cold,event_year=2023].customer_hours_lost | m1 }}
  customer-hours that year, against
  {{ q3_named_comparisons[comparison=Texas winter weather and cold,event_year=2024].customer_hours_lost | m1 }}
  in 2024.
- **Gulf Coast hurricanes:**
  {{ q3_named_comparisons[comparison=Gulf Coast hurricanes,event_year=2022].customer_hours_lost | m1 }}
  in 2022 (Ian) and
  {{ q3_named_comparisons[comparison=Gulf Coast hurricanes,event_year=2024].customer_hours_lost | m1 }}
  in 2024. No 2025 event in the Gulf states matched a tropical storm.

## Q4. Which storms take longest to restore

{{ table q4_duration_by_storm | cols=storm_group:Storm family,events:Events:int,median_hours:Median h (all):f1,large_events:Events 10k+:int,large_median_hours:Median h (10k+):f1,large_p90_hours:P90 h (10k+):f0 }}

- **Most outages are short:** the median event lasts
  {{ q4_duration_by_storm[storm_group=No storm matched].median_hours | f1 }} hours when no storm is
  matched and {{ q4_duration_by_storm[storm_group=Thunderstorm wind].median_hours | f1 }} hours in
  thunderstorm wind. The large outages (10,000+ customers out) are the ones that last.
- **Large outages last longest after tropical systems:** median
  {{ q4_duration_by_storm[storm_group=Hurricane / tropical].large_median_hours | f0 }} hours, with
  one in ten lasting over {{ q4_duration_by_storm[storm_group=Hurricane / tropical].large_p90_hours | f0 }}
  hours. Next come winter weather
  ({{ q4_duration_by_storm[storm_group=Winter weather].large_median_hours | f0 }} h) and tornadoes
  ({{ q4_duration_by_storm[storm_group=Tornado].large_median_hours | f0 }} h). Large
  thunderstorm-wind outages restore in about a day
  ({{ q4_duration_by_storm[storm_group=Thunderstorm wind].large_median_hours | f0 }} h).
- **Large outages last longest in the Midwest and Northeast:**

{{ table q4_duration_by_region | cols=census_region:Region,events:Events:int,median_hours:Median h (all):f1,large_events:Events 10k+:int,large_median_hours:Median h (10k+):f1,large_p90_hours:P90 h (10k+):f0 }}

  The median large outage lasts
  {{ q4_duration_by_region[census_region=Midwest].large_median_hours | f0 }} hours in the Midwest
  and {{ q4_duration_by_region[census_region=Northeast].large_median_hours | f0 }} in the Northeast,
  against {{ q4_duration_by_region[census_region=West].large_median_hours | f0 }} in the West.

![Duration by storm type](images/chart_duration_by_storm.png)

## Q5. Utility reliability: Eversource and National Grid against their peers

SAIDI and SAIFI come from EIA-861, IEEE 1366 reporters only, ranked within size band (1 = most
reliable, D39). Figures exclude major event days.

{{ table q5_eversource_national_grid | cols=parent_company:Parent,utility_name:Utility,state_abbr:State,size_band:Band,saidi_without_med:SAIDI min:f1,rank_saidi_without_med:Rank,utilities_in_band:Of,saidi_vs_median:vs band median:f2,saifi_without_med:SAIFI:f2 | where=data_year=2025 }}

- **All three Eversource companies beat the very-large-band median in 2025**
  ({{ q5_band_summary[data_year=2025,size_band=very_large].saidi_median | f1 }} minutes).
  NSTAR Electric is best at rank
  {{ q5_eversource_national_grid[data_year=2025,utility_name=NSTAR Electric Company].rank_saidi_without_med }}
  of {{ q5_eversource_national_grid[data_year=2025,utility_name=NSTAR Electric Company].utilities_in_band }}
  ({{ q5_eversource_national_grid[data_year=2025,utility_name=NSTAR Electric Company].saidi_without_med | f1 }}
  minutes).
- **National Grid's Niagara Mohawk (NY) is the weak spot:** rank
  {{ q5_eversource_national_grid[data_year=2025,utility_name=Niagara Mohawk Power Corp.].rank_saidi_without_med }}
  of {{ q5_eversource_national_grid[data_year=2025,utility_name=Niagara Mohawk Power Corp.].utilities_in_band }},
  {{ q5_eversource_national_grid[data_year=2025,utility_name=Niagara Mohawk Power Corp.].saidi_vs_median | f2 }}x
  the band median. It ranks
  {{ q5_eversource_national_grid[data_year=2022,utility_name=Niagara Mohawk Power Corp.].rank_saidi_without_med }}
  in 2022, {{ q5_eversource_national_grid[data_year=2023,utility_name=Niagara Mohawk Power Corp.].rank_saidi_without_med }}
  in 2023 and {{ q5_eversource_national_grid[data_year=2024,utility_name=Niagara Mohawk Power Corp.].rank_saidi_without_med }}
  in 2024. National Grid's Massachusetts Electric is near the median
  ({{ q5_eversource_national_grid[data_year=2025,utility_name=Massachusetts Electric Co].saidi_vs_median | f2 }}x).
- **Two caveats:**
  - Narragansett Electric (RI) ranks
    {{ q5_eversource_national_grid[data_year=2025,utility_name=The Narragansett Electric Co].rank_saidi_without_med }},
    but National Grid sold it to PPL in May 2022.
  - NSTAR's 2023 row is unranked: "{{ q5_eversource_national_grid[data_year=2023,utility_name=NSTAR Electric Company].data_quality_flag }}"
    (D39). Its 2023 values repeat those of Connecticut Light & Power.

![Utility SAIDI benchmark](images/chart_utility_saidi_benchmark.png)

## Q6. The 2022-2025 trend, and why it is not a coverage effect

{{ table q6_national_trend | cols=year:Year,events:Events:int,customer_hours_lost:Customer-hours:m1,reporting_counties:Counties reporting:int,hours_per_1000_covered:Hours per 1k:f0,vs_first_year:vs 2022:f2 }}

Hours per 1k are per 1,000 customers of the reporting counties.

The same {{ q6_same_counties[year=2022].panel_counties | int }} counties, reported in every year:

{{ table q6_same_counties | cols=year:Year,events:Events:int,customer_hours_lost:Customer-hours:m1,hours_per_1000:Hours per 1k:f0,vs_first_year:vs 2022:f2 }}

- **2024 was the worst year, and not because of coverage:** customer-hours were
  {{ q6_national_trend[year=2024].vs_first_year | f2 }}x the 2022 level. On the same counties
  every year the ratio is {{ q6_same_counties[year=2024].vs_first_year | f2 }}x, so the increase
  happened in counties that were already reported. It came from storms: Beryl, Helene and Milton
  are all in the 2024 top 10 (Q1).
- **Coverage was flat over the period:**
  - EAGLE-I reports {{ q6_national_trend[year=2022].reporting_counties | int }} counties in 2022
    and {{ q6_national_trend[year=2025].reporting_counties | int }} in 2025.
  - Only {{ q6_first_reported[first_reported_year=2025].counties }} counties are first reported
    in 2025 ({{ q6_first_reported[first_reported_year=2025].customers | int }} customers).
  - 2025 is the lowest year: {{ q6_national_trend[year=2025].vs_first_year | f2 }}x 2022. No
    Gulf Coast event matched a tropical storm that year (Q3).
- **Coverage did grow before 2022, which is why the series starts there:** EAGLE-I's published
  coverage of customers in the 50 states and DC rose from
  {{ q6_published_coverage[year=2018].max_share_covered | pct1 }} in 2018 to
  {{ q6_published_coverage[year=2022].max_share_covered | pct1 }} in 2022. Its data quality index
  (mean of the ten FEMA regions) rose from {{ q6_published_coverage[year=2018].mean_dqi | f1 }} to
  {{ q6_published_coverage[year=2022].mean_dqi | f1 }}. The release publishes neither after 2022,
  so the same-county comparison above is the check for later years (D67).

![Yearly trend](images/chart_yearly_trend.png)
