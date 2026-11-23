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
   out last a median of 77
   hours after tropical systems and
   50 hours after winter
   weather. One in ten lasts over
   331 and
   137 hours. Large
   thunderstorm outages restore in about
   28 hours.
2. **The Northeast loses outage hours to three kinds of weather, not one:** winter weather
   (22%
   of its customer-hours), thunderstorm wind
   (22%)
   and other high wind
   (18%).
   The median large Northeast outage lasts
   26 hours, and one in ten
   lasts over 86.
3. **The worst-hit places repeat.** Maine is rank
   1,
   1 and
   2 nationally in outage hours per
   customer for 2022-2024. The Northeast's worst county each year:
   - 2022: Hamilton NY
   - 2023: Windham VT
   - 2024: Hamilton NY
   - 2025: Hamilton NY

   Hamilton County NY is small (2,566
   customers), and its peak reading is
   2.84x its customer count. It
   is on the possible-misattribution list, so it is a lead to check, not a conclusion. It lies in the
   Adirondacks, where many homes are seasonal, so its EAGLE-I customer count may be an undercount
   that inflates its per-1,000 rate and explains the high peak. It is in National Grid's Niagara
   Mohawk territory, so Niagara Mohawk's own customer and outage records can settle it.
4. **Eversource benchmarks well; Niagara Mohawk does not.** Among the
   62 very large IEEE 1366
   utilities in 2025:
   - NSTAR Electric, Public Service of NH and Connecticut Light & Power sit at
     0.62x,
     0.79x
     and 0.81x
     the band median SAIDI.
   - National Grid's Niagara Mohawk is
     1.32x
     the median and ranks
     43
     of 62.
     It ranked 45
     in 2022, 43
     in 2023 and 43
     in 2024.
5. **Bad years are storm years, and they are big.** 2024 had
   2.01x the customer-hours of 2022 in the same
   3,006 counties. 2025 had
   0.79x. A plan sized for an average year is
   short in a year like 2024.

## Recommendations

1. **Crew staging:** size mutual-assistance and contractor holds to the restoration tail, not the
   average.
   - Winter storms and tropical remnants: plan for multi-day restoration. Hold crews through the
     median (50 h for
     winter weather) and keep a release plan out to the 90th percentile
     (137 h).
   - Thunderstorm events: a one-day plan
     (28 h median)
     covers most of them.
2. **Investment prioritization:** rank the counties in the service territory by outage hours per
   1,000 customers over several years, not one, and harden where the same counties stay on top.
   Pair that with the storm family that drives each county's hours: vegetation and wind-hardening
   for wind, ice loading for winter weather. EAGLE-I is county-level and cannot be split by utility,
   so the overlay with the utility's own territory and circuit data has to be done internally.
3. **Peer benchmarking:** benchmark each operating company against its EIA-861 size band, not
   against sister companies.
   - Niagara Mohawk would need to cut
     34
     minutes of SAIDI (without major event days) to reach the 2025 very-large median of
     105.9 minutes.
   - Track SAIDI with major event days alongside; that is where storm restoration shows.

## Limitations

- **Outage detail:** EAGLE-I misses outages under 15 minutes, is weaker for small and rural
  utilities, and is county-level. Utility comparisons come only from EIA-861.
- **Storm attribution:**
  37% of
  customer-hours have no NOAA storm match. That includes Hurricane Beryl in Harris County, which
  NOAA does not place there.
- **Years:** events count in the year they start. EAGLE-I publishes its own coverage and data
  quality index only to 2022, so later years are compared on the same counties. Grid disturbance
  reports (OE-417) are loaded for 2022-2023 only.
- **Places:** Puerto Rico figures are PREPA operating regions, and Connecticut 2025 is footnoted
  because EAGLE-I switched it to planning regions without denominators.
