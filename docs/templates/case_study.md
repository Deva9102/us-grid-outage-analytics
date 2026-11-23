<!-- Rendered by scripts/analysis.py from docs/templates/case_study.md. Edit the template, not docs/case_study.md. -->
# Case study: storm restoration and reliability in the Northeast

*For a storm operations or reliability manager at a Northeast utility such as Eversource or
National Grid. Every number comes from `sql/analysis/`; the full analysis is in
`docs/findings.md`.*

## The problem

A storm operations team has to decide three things before the weather arrives: how many crews to
stage and for how long, which parts of the territory to harden first, and whether its restoration
performance is good or bad compared with similar utilities. This project measures 2022-2025 outages
in every US county from DOE EAGLE-I's 15-minute outage feed, links each outage to the NOAA storm
that caused it, and benchmarks utilities with EIA-861 SAIDI and SAIFI.

## Key findings

1. **The large outages that need staffing last days, not hours.** Outages with 10,000+ customers
   out last a median of {{ q4_duration_by_storm[storm_group=Hurricane / tropical].large_median_hours | f0 }}
   hours after tropical systems and
   {{ q4_duration_by_storm[storm_group=Winter weather].large_median_hours | f0 }} hours after winter
   weather. One in ten lasts over
   {{ q4_duration_by_storm[storm_group=Hurricane / tropical].large_p90_hours | f0 }} and
   {{ q4_duration_by_storm[storm_group=Winter weather].large_p90_hours | f0 }} hours. Large
   thunderstorm outages restore in about
   {{ q4_duration_by_storm[storm_group=Thunderstorm wind].large_median_hours | f0 }} hours.
2. **The Northeast loses outage hours to three kinds of weather, not one:** winter weather
   ({{ q3_region_storm[census_region=Northeast,storm_group=Winter weather].share_of_region | pct0 }}
   of its customer-hours), thunderstorm wind
   ({{ q3_region_storm[census_region=Northeast,storm_group=Thunderstorm wind].share_of_region | pct0 }})
   and other high wind
   ({{ q3_region_storm[census_region=Northeast,storm_group=Other wind].share_of_region | pct0 }}).
   The median large Northeast outage lasts
   {{ q4_duration_by_region[census_region=Northeast].large_median_hours | f0 }} hours, and one in ten
   lasts over {{ q4_duration_by_region[census_region=Northeast].large_p90_hours | f0 }}.
3. **The worst-hit places repeat.** Maine is rank
   {{ q2_state_ranks[year=2022,state_abbr=ME].national_rank }},
   {{ q2_state_ranks[year=2023,state_abbr=ME].national_rank }} and
   {{ q2_state_ranks[year=2024,state_abbr=ME].national_rank }} nationally in outage hours per
   customer for 2022-2024. The Northeast's worst county each year:
   - 2022: {{ q2_northeast_counties[year=2022,region_rank=1].county }} {{ q2_northeast_counties[year=2022,region_rank=1].state_abbr }}
   - 2023: {{ q2_northeast_counties[year=2023,region_rank=1].county }} {{ q2_northeast_counties[year=2023,region_rank=1].state_abbr }}
   - 2024: {{ q2_northeast_counties[year=2024,region_rank=1].county }} {{ q2_northeast_counties[year=2024,region_rank=1].state_abbr }}
   - 2025: {{ q2_northeast_counties[year=2025,region_rank=1].county }} {{ q2_northeast_counties[year=2025,region_rank=1].state_abbr }}

   Hamilton County NY is small ({{ q2_northeast_counties[year=2024,region_rank=1].customers | int }}
   customers), and its peak reading is
   {{ q2_possible_misattributions[fips_code=36041].peak_to_customers | f2 }}x its customer count. It
   is on the possible-misattribution list, so it is a lead to check, not a conclusion. It lies in the
   Adirondacks, where many homes are seasonal, so its EAGLE-I customer count may be an undercount
   that inflates its per-1,000 rate and explains the high peak. It is in National Grid's Niagara
   Mohawk territory, so Niagara Mohawk's own customer and outage records can settle it.
4. **Eversource benchmarks well; Niagara Mohawk does not.** Among the
   {{ q5_band_summary[data_year=2025,size_band=very_large].ranked_utilities }} very large IEEE 1366
   utilities in 2025:
   - NSTAR Electric, Public Service of NH and Connecticut Light & Power sit at
     {{ q5_eversource_national_grid[data_year=2025,utility_name=NSTAR Electric Company].saidi_vs_median | f2 }}x,
     {{ q5_eversource_national_grid[data_year=2025,utility_name=Public Service Co of NH].saidi_vs_median | f2 }}x
     and {{ q5_eversource_national_grid[data_year=2025,utility_name=Connecticut Light & Power Co].saidi_vs_median | f2 }}x
     the band median SAIDI.
   - National Grid's Niagara Mohawk is
     {{ q5_eversource_national_grid[data_year=2025,utility_name=Niagara Mohawk Power Corp.].saidi_vs_median | f2 }}x
     the median and ranks
     {{ q5_eversource_national_grid[data_year=2025,utility_name=Niagara Mohawk Power Corp.].rank_saidi_without_med }}
     of {{ q5_eversource_national_grid[data_year=2025,utility_name=Niagara Mohawk Power Corp.].utilities_in_band }}.
     It ranked {{ q5_eversource_national_grid[data_year=2022,utility_name=Niagara Mohawk Power Corp.].rank_saidi_without_med }}
     in 2022, {{ q5_eversource_national_grid[data_year=2023,utility_name=Niagara Mohawk Power Corp.].rank_saidi_without_med }}
     in 2023 and {{ q5_eversource_national_grid[data_year=2024,utility_name=Niagara Mohawk Power Corp.].rank_saidi_without_med }}
     in 2024.
5. **Bad years are storm years, and they are big.** 2024 had
   {{ q6_same_counties[year=2024].vs_first_year | f2 }}x the customer-hours of 2022 in the same
   {{ q6_same_counties[year=2024].panel_counties | int }} counties. 2025 had
   {{ q6_same_counties[year=2025].vs_first_year | f2 }}x. A plan sized for an average year is
   short in a year like 2024.

## Recommendations

1. **Crew staging:** size mutual-assistance and contractor holds to the restoration tail, not the
   average.
   - Winter storms and tropical remnants: plan for multi-day restoration. Hold crews through the
     median ({{ q4_duration_by_storm[storm_group=Winter weather].large_median_hours | f0 }} h for
     winter weather) and keep a release plan out to the 90th percentile
     ({{ q4_duration_by_storm[storm_group=Winter weather].large_p90_hours | f0 }} h).
   - Thunderstorm events: a one-day plan
     ({{ q4_duration_by_storm[storm_group=Thunderstorm wind].large_median_hours | f0 }} h median)
     covers most of them.
2. **Investment prioritization:** rank the counties in the service territory by outage hours per
   1,000 customers over several years, not one, and harden where the same counties stay on top.
   Pair that with the storm family that drives each county's hours: vegetation and wind-hardening
   for wind, ice loading for winter weather. EAGLE-I is county-level and cannot be split by utility,
   so the overlay with the utility's own territory and circuit data has to be done internally.
3. **Peer benchmarking:** benchmark each operating company against its EIA-861 size band, not
   against sister companies.
   - Niagara Mohawk would need to cut
     {{ q5_eversource_national_grid[data_year=2025,utility_name=Niagara Mohawk Power Corp.].saidi_minutes_above_median | f0 }}
     minutes of SAIDI (without major event days) to reach the 2025 very-large median of
     {{ q5_band_summary[data_year=2025,size_band=very_large].saidi_median | f1 }} minutes.
   - Track SAIDI with major event days alongside; that is where storm restoration shows.

## Limitations

- **Outage detail:** EAGLE-I misses outages under 15 minutes, is weaker for small and rural
  utilities, and is county-level. Utility comparisons come only from EIA-861.
- **Storm attribution:**
  {{ q1_storm_share_all[storm_group=No storm matched].share_of_customer_hours | pct0 }} of
  customer-hours have no NOAA storm match. That includes Hurricane Beryl in Harris County, which
  NOAA does not place there.
- **Years:** events count in the year they start. EAGLE-I publishes its own coverage and data
  quality index only to 2022, so later years are compared on the same counties. Grid disturbance
  reports (OE-417) are loaded for 2022-2023 only.
- **Places:** Puerto Rico figures are PREPA operating regions, and Connecticut 2025 is footnoted
  because EAGLE-I switched it to planning regions without denominators.
