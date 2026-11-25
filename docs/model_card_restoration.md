# Model card: outage restoration-time forecast

Version `v1-5034668c` (`forecast.model.version` plus a hash of the forecast settings). Code:
`scripts/forecast_model.py`. Features: `sql/databricks/04_gold_forecast_features.sql`. Decisions:
`docs/decisions.md` D71-D74. Every number here is in `docs/forecast_results.md`, written by
`make forecast-evaluate`.

## Purpose

Two hours after a county outage starts, estimate how long it will last in total: a **p50** (the
typical case) and a **p90** (a planning upper bound that 9 in 10 outages should end by).

## Intended user

An analyst or operations planner looking at county-level outages across the US: someone who wants
a first estimate of restoration time, for example to set customer expectations, stage crews or
flag outages likely to run long. It is a portfolio model built on public data. It is not an
operational estimated time of restoration from a utility.

## Data

- DOE EAGLE-I county outages at 15-minute intervals, 2022-2025, turned into outage events
  (`gold_outage_events`, D17-D19, D64).
- NOAA Storm Events (storm type at the start), US Census regions, the county customer counts of
  D13, and earlier years' outage history in the same county.
- **Eligible events:** still at or above the county's event threshold 2 hours after the start, and
  not spanning an empty gap (D71). 221,708 events: 108,033 in 2022-2023, 56,440 in 2024, 57,235 in
  2025.

## Features

Everything known 2 hours after the start, and nothing later (leakage tests in
`tests/test_forecast_features.py`):

- customers out at the start, at 1 hour and at 2 hours; growth (difference and ratio); the peak so
  far, raw and as a share of the county's customers;
- whether the feed had a gap or a dropout so far;
- the NOAA storm type and storm family at the start;
- month, hour and weekday of the start in the state's time zone;
- state, Census region, county customers and event threshold;
- county history from earlier years: events per year, eligible events per year, median duration of
  all and of eligible events.

The most important inputs on 2025 (permutation importance, increase in p50 MAE when shuffled):
growth in customers out (0.39 h), storm type (0.35 h), peak share so far (0.16 h) and state
(0.14 h).

## Training and split

- Target `log(duration_hours)`, predictions converted back to hours.
- Tuned on 2022-2023 against 2024; retrained on 2022-2024 with the chosen settings; evaluated once
  on 2025. Never tuned on 2025, and a guard stops any step that would see it.
- Separate quantile models for p50 and p90. The p90 calibration rule (D74) was not triggered: 2024
  coverage was within 3 points of 90% for every model.

## Metrics (2025, 57,235 events)

| Model | p50 MAE (h) | p90 pinball loss | p90 coverage |
|---|---|---|---|
| Baseline: storm family x region quantiles | 4.215 | 2.102 | 90.8% |
| Quantile linear regression | 3.916 | 1.798 | 90.8% |
| **Gradient boosting (this model)** | **3.712** | **1.691** | **89.8%** |
| Gradient boosting without storm features | 3.834 | 1.807 | 90.0% |

Gradient boosting beats the baseline by 0.503 h p50 MAE (-11.9%, 95% bootstrap interval -0.537 to
-0.470) and by 0.411 in p90 pinball loss (-19.6%). The gain is largest where it matters most: for
outages with 10,000 or more customers out at 2 hours (518 events), p50 MAE is 13.92 h against
23.69 h for the baseline, and p90 coverage is 86% against 61%.

## Limitations

- **NOAA storm type is a stand-in.** NOAA Storm Events is published months later; in use, the
  storm type would come from live NWS warnings, which may differ. Without the storm features, p50
  MAE rises by 0.122 h overall, and p90 coverage falls to 73% for winter weather, 76% for
  tornadoes and 75% for other wind. Treat the storm-driven gains as an upper bound.
- **Hurricanes and tropical storms are not evaluated.** 2025 has only 4 such events. On 2024 (304
  events, indicative only, because 2024 chose the settings) the p90 covered just 52% of hurricane
  outages and p50 MAE was 73 hours: the model badly underestimates long hurricane restorations.
- **Large outages are under-covered.** For 10,000+ customers out, p90 coverage is 86%, not 90%.
- **EAGLE-I limits.** Outages under 15 minutes are missed, small and rural utilities are less
  reliable, and the data is county-level, so the forecast is per county, not per utility or
  per customer. Duration is the time above the county threshold, a proxy for restoration.
- **One test year.** 2025 is a single year; a year with an unusual storm season may score worse.
- **Calibration** was checked on 2024 and held on 2025, but the conformal rule would use residuals
  of the tuning models for the retrained ones (D74).

## When not to use it

- For hurricanes, tropical storms or any event far larger than those in 2022-2024.
- For outages shorter than 2 hours, or ones that have dropped below the county threshold by then:
  the model was never trained on them.
- As a promise to an individual customer, or in place of a utility's own restoration estimate.
- For years before 2022, where EAGLE-I coverage is lower.
- After the feature definitions or EAGLE-I coverage change, without retraining and re-evaluating.
