# Restoration forecast: baseline

Written by `scripts/forecast_baseline.py` from `gold_restoration_features` (`sql/databricks/04_gold_forecast_features.sql`). Design and eligibility: `docs/decisions.md` D71.

**Task.** At 2 hours after an outage event starts, predict its total duration (p50 and p90). Eligible: the outage still meets its county's event threshold at that moment. Train 2022, 2023, 2024; test 2025 (time-based split).

## Eligible events

| Year | Split | Events |
|---|---|---|
| 2022 | train | 54,928 |
| 2023 | train | 53,105 |
| 2024 | train | 56,440 |
| 2025 | test | 57,235 |

## Target: duration_hours

All eligible events: p10 2.50 h, p25 2.75, median 4.00, p75 7.00, p90 13.50, p99 64.8, max 1,906 h. Mean 7.66 h: heavily right-skewed, so quantile losses are used rather than squared error.

Training median 4.00 h, p90 13.75 h; test median 4.00 h, p90 12.75 h.

## Feature null rates

Features with any NULL (all others are complete):

| Feature | Null share |
|---|---|
| `prior_eligible_median_duration_hours` | 25.1% |
| `prior_median_duration_hours` | 25.1% |
| `prior_eligible_event_count` | 25.1% |
| `prior_events_per_year` | 24.8% |
| `prior_event_count` | 24.8% |
| `customers_out_at_mid` | 1.0% |
| `customers` | 0.2% |
| `peak_share_so_far` | 0.2% |

History is NULL by design for 2022 events (no earlier year). After 2022, 0.4% of events have no earlier eligible event in their county.

## Training quantiles by storm family at the start

| Storm family | Training events | p50 (h) | p90 (h) |
|---|---|---|---|
| No storm matched | 136,630.0 | 3.75 | 10.25 |
| Thunderstorm wind | 11,587.0 | 8.00 | 32.35 |
| Winter weather | 5,328.0 | 6.50 | 46.08 |
| Other wind | 2,653.0 | 9.25 | 51.00 |
| Heat | 2,384.0 | 4.25 | 13.50 |
| Flood | 1,908.0 | 4.75 | 18.90 |
| Tornado | 1,543.0 | 15.25 | 64.70 |
| Wildfire | 995.0 | 4.00 | 12.75 |
| Other | 895.0 | 4.75 | 17.75 |
| Hurricane / tropical | 550.0 | 25.00 | 194.83 |

## Baseline scores on 2025 (57,235 events)

Family x region cells with fewer than 30 training events use the family's values.

| Baseline | p50 MAE (h) | p50 median abs. error (h) | p90 coverage | p90 pinball loss |
|---|---|---|---|---|
| global | 4.354 | 1.500 | 91.2% | 2.450 |
| family | 4.227 | 1.250 | 90.8% | 2.114 |
| family_region | 4.215 | 1.500 | 90.8% | 2.102 |

A model has to beat the `family_region` row on p50 MAE and p90 pinball loss, with p90 coverage close to 90%.
