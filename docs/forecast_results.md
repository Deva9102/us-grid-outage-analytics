# Restoration forecast: results

Written by `scripts/forecast_model.py evaluate` (`make forecast-evaluate`). Every number below is in `docs/forecast_results.json`. Design: `docs/decisions.md` D71 (features) and D72 (models). Model card: `docs/model_card_restoration.md`.

Model version `v1-5034668c`; config hash `5034668c5e370ef1`; feature data fingerprint `c9bc01537af4b4e4`.

## Protocol

- Tune on [2022, 2023] (108,033 events), validate on 2024 (56,440). Retrain on [2022, 2023, 2024] (164,473). Evaluate once on 2025 (57,235).
- Years each step saw (recorded by the run): {"baseline_tune": [2022, 2023], "tune": [2022, 2023], "calibration": [2024], "retrain": [2022, 2023, 2024], "baseline_retrain": [2022, 2023, 2024]}. 2025 never appears.
- Target: log(duration_hours); predictions converted back to hours. Errors are in hours.

Chosen settings (by validation pinball loss in hours):

| Model | Quantile | Settings | Validation pinball |
|---|---|---|---|
| Quantile linear | 0.5 | alpha=0.0 | 2.4216 |
| Quantile linear | 0.9 | alpha=0.0 | 2.3158 |
| Gradient boosting | 0.5 | learning_rate=0.1, max_leaf_nodes=15, min_samples_leaf=20, n_iter=518 | 2.3027 |
| Gradient boosting | 0.9 | learning_rate=0.05, max_leaf_nodes=31, min_samples_leaf=20, n_iter=182 | 2.3090 |
| Gradient boosting, no storm features | 0.5 | learning_rate=0.05, max_leaf_nodes=63, min_samples_leaf=100, n_iter=335 | 2.4103 |
| Gradient boosting, no storm features | 0.9 | learning_rate=0.1, max_leaf_nodes=15, min_samples_leaf=20, n_iter=194 | 2.4792 |

## p90 calibration on 2024

Applied when validation coverage is more than 3 percentage points from 90% (split-conformal offset on the log scale, from the validation residuals).

| Model | Validation coverage | Applied | Factor | Validation coverage after |
|---|---|---|---|---|
| Baseline (family x region) | 88.8% | no | 1.077 | 88.8% |
| Quantile linear | 88.3% | no | 1.078 | 88.3% |
| Gradient boosting | 87.5% | no | 1.106 | 87.5% |
| Gradient boosting, no storm features | 87.5% | no | 1.112 | 87.5% |

## 2025 test results

| Model | Events | p50 MAE (h) | p50 pinball | p90 pinball | p90 coverage |
|---|---|---|---|---|---|
| Baseline (family x region) | 57,235 | 4.215 | 2.107 | 2.102 | 90.8% |
| Quantile linear | 57,235 | 3.916 | 1.958 | 1.798 | 90.8% |
| Gradient boosting | 57,235 | 3.712 | 1.856 | 1.691 | 89.8% |
| Gradient boosting, no storm features | 57,235 | 3.834 | 1.917 | 1.807 | 90.0% |

p90 coverage before calibration: Baseline (family x region) 90.8%; Quantile linear 90.8%; Gradient boosting 89.8%; Gradient boosting, no storm features 90.0%.

### Against the baseline

Difference to the baseline on 2025 (negative is better), with a 95% paired bootstrap interval (200 resamples):

| Model | p50 MAE diff (h) | 95% interval | Relative | p90 pinball diff | 95% interval | Relative | Beats baseline |
|---|---|---|---|---|---|---|---|
| Quantile linear | -0.299 | [-0.319, -0.279] | -7.1% | -0.304 | [-0.335, -0.278] | -14.5% | yes, both |
| Gradient boosting | -0.503 | [-0.537, -0.470] | -11.9% | -0.411 | [-0.439, -0.385] | -19.6% | yes, both |
| Gradient boosting, no storm features | -0.381 | [-0.413, -0.347] | -9.0% | -0.296 | [-0.324, -0.268] | -14.1% | yes, both |

### Effect of the storm features (decision 1)

Removing the NOAA storm features changes p50 MAE by +0.122 h and p90 pinball loss by +0.115 (gradient boosting without minus with). Relative to the baseline: with storms -0.503 h, without -0.381 h p50 MAE.

### By storm family at the start

Cells: p50 MAE (h) / p90 coverage. Small groups are noisy: read the event counts.

| Group | Events | baseline MAE / p90 cov. | linear MAE / p90 cov. | hgb MAE / p90 cov. | hgb_no_storm MAE / p90 cov. |
|---|---|---|---|---|---|
| No storm matched | 48,396 | 3.02 / 91% | 2.92 / 91% | 2.85 / 90% | 2.90 / 91% |
| Thunderstorm wind | 3,787 | 9.75 / 90% | 7.97 / 91% | 6.74 / 90% | 6.98 / 86% |
| Winter weather | 1,636 | 16.20 / 90% | 15.28 / 89% | 14.09 / 88% | 15.27 / 73% |
| Other wind | 1,082 | 12.83 / 93% | 10.87 / 90% | 10.52 / 87% | 11.26 / 75% |
| Flood | 845 | 5.98 / 92% | 5.70 / 92% | 5.57 / 91% | 5.58 / 87% |
| Tornado | 536 | 17.51 / 91% | 14.99 / 92% | 12.84 / 88% | 14.29 / 76% |
| Heat | 355 | 2.54 / 94% | 2.39 / 92% | 2.39 / 90% | 2.42 / 92% |
| Wildfire | 323 | 3.57 / 92% | 3.67 / 91% | 3.42 / 89% | 3.45 / 90% |
| Other | 271 | 4.04 / 92% | 3.59 / 95% | 3.36 / 92% | 3.63 / 88% |
| Hurricane / tropical | 4 | 22.06 / 100% | 12.82 / 100% | 3.54 / 100% | 0.26 / 100% |

### By Census region

| Group | Events | baseline MAE / p90 cov. | linear MAE / p90 cov. | hgb MAE / p90 cov. | hgb_no_storm MAE / p90 cov. |
|---|---|---|---|---|---|
| South | 29,175 | 3.71 / 92% | 3.42 / 91% | 3.25 / 91% | 3.37 / 91% |
| Midwest | 11,637 | 5.45 / 90% | 5.07 / 90% | 4.76 / 89% | 4.98 / 89% |
| West | 7,362 | 4.13 / 90% | 3.97 / 90% | 3.88 / 89% | 3.94 / 89% |
| Northeast | 7,118 | 4.07 / 90% | 3.66 / 91% | 3.44 / 89% | 3.51 / 90% |
| Territory | 1,943 | 5.23 / 88% | 5.20 / 93% | 4.70 / 89% | 4.69 / 89% |

### By outage size at the prediction moment (customers out)

| Group | Events | baseline MAE / p90 cov. | linear MAE / p90 cov. | hgb MAE / p90 cov. | hgb_no_storm MAE / p90 cov. |
|---|---|---|---|---|---|
| < 1,000 | 44,743 | 3.25 / 93% | 3.11 / 91% | 3.03 / 90% | 3.08 / 90% |
| 1,000-9,999 | 11,974 | 6.97 / 84% | 6.30 / 91% | 5.82 / 89% | 6.17 / 90% |
| 10,000+ | 518 | 23.69 / 61% | 18.37 / 85% | 13.92 / 86% | 14.97 / 87% |

### Hurricane / tropical: indicative only

2025 has 4 hurricane / tropical events, too few to evaluate the category. The 2024 validation year has 304; its results are indicative only, because 2024 also chose the settings and the calibration:

| Model | Events | p50 MAE (h) | p50 pinball | p90 pinball | p90 coverage |
|---|---|---|---|---|---|
| Baseline (family x region) | 304 | 87.176 | 43.588 | 59.687 | 51.0% |
| Quantile linear | 304 | 78.529 | 39.264 | 36.603 | 61.2% |
| Gradient boosting | 304 | 73.222 | 36.611 | 52.418 | 52.0% |
| Gradient boosting, no storm features | 304 | 89.637 | 44.819 | 66.797 | 27.6% |

## 2024 validation results (tuning models, trained on [2022, 2023])

| Model | Events | p50 MAE (h) | p50 pinball | p90 pinball | p90 coverage |
|---|---|---|---|---|---|
| Baseline (family x region) | 56,440 | 5.228 | 2.614 | 2.788 | 88.8% |
| Quantile linear | 56,440 | 4.843 | 2.422 | 2.316 | 88.3% |
| Gradient boosting | 56,440 | 4.605 | 2.303 | 2.309 | 87.5% |
| Gradient boosting, no storm features | 56,440 | 4.821 | 2.410 | 2.479 | 87.5% |

By storm family (p50 MAE / p90 coverage):

| Group | Events | baseline MAE / p90 cov. | linear MAE / p90 cov. | hgb MAE / p90 cov. | hgb_no_storm MAE / p90 cov. |
|---|---|---|---|---|---|
| No storm matched | 47,241 | 3.54 / 89% | 3.42 / 89% | 3.36 / 88% | 3.37 / 90% |
| Thunderstorm wind | 3,682 | 10.34 / 88% | 8.41 / 88% | 7.08 / 87% | 7.73 / 81% |
| Winter weather | 1,523 | 12.10 / 90% | 11.09 / 91% | 10.23 / 87% | 11.02 / 72% |
| Other wind | 1,029 | 15.86 / 90% | 14.56 / 84% | 13.62 / 80% | 14.99 / 70% |
| Flood | 734 | 11.72 / 89% | 11.34 / 86% | 11.24 / 86% | 11.20 / 80% |
| Tornado | 645 | 21.18 / 84% | 16.43 / 84% | 14.08 / 82% | 17.03 / 64% |
| Heat | 570 | 3.33 / 91% | 3.32 / 88% | 3.16 / 89% | 3.14 / 90% |
| Wildfire | 449 | 6.47 / 86% | 6.34 / 90% | 6.32 / 90% | 6.22 / 87% |
| Hurricane / tropical | 304 | 87.18 / 51% | 78.53 / 61% | 73.22 / 52% | 89.64 / 28% |
| Other | 263 | 5.89 / 90% | 5.39 / 88% | 5.26 / 85% | 5.30 / 84% |

## Permutation importance (gradient boosting, 2025)

Increase in loss when one input is shuffled, mean of 5 shuffles on a seeded sample of 20,000 test events.

| Feature | p50 MAE increase (h) | sd | p90 pinball increase | sd |
|---|---|---|---|---|
| `growth_customers` | 0.3943 | 0.0064 | 0.3187 | 0.0038 |
| `storm_type_at_start` | 0.3539 | 0.0166 | 0.2646 | 0.0069 |
| `peak_share_so_far` | 0.1625 | 0.0026 | 0.1692 | 0.0027 |
| `state_abbr` | 0.1440 | 0.0083 | 0.0758 | 0.0050 |
| `customers_out_at_prediction` | 0.0863 | 0.0018 | 0.0203 | 0.0012 |
| `start_hour_local` | 0.0583 | 0.0032 | 0.0246 | 0.0034 |
| `growth_ratio` | 0.0318 | 0.0024 | 0.0065 | 0.0023 |
| `prior_eligible_events_per_year` | 0.0199 | 0.0030 | 0.0031 | 0.0018 |
| `customers_out_at_mid` | 0.0166 | 0.0015 | -0.0001 | 0.0003 |
| `prior_median_duration_hours` | 0.0130 | 0.0022 | 0.0037 | 0.0012 |
| `customers` | 0.0127 | 0.0025 | 0.0033 | 0.0006 |
| `prior_eligible_median_duration_hours` | 0.0102 | 0.0011 | 0.0092 | 0.0010 |
| `start_weekday_local` | 0.0101 | 0.0018 | 0.0057 | 0.0004 |
| `start_month_local` | 0.0081 | 0.0013 | 0.0061 | 0.0009 |
| `customers_out_at_start` | 0.0047 | 0.0012 | 0.0020 | 0.0003 |
| `dropout_so_far` | 0.0013 | 0.0010 | 0.0007 | 0.0007 |
| `prior_events_per_year` | 0.0010 | 0.0011 | -0.0004 | 0.0008 |
| `has_denominator` | 0.0000 | 0.0000 | 0.0000 | 0.0000 |
| `feed_gap_so_far` | 0.0000 | 0.0000 | 0.0000 | 0.0000 |
| `event_threshold` | -0.0000 | 0.0000 | 0.0000 | 0.0000 |
| `census_region` | -0.0004 | 0.0003 | -0.0003 | 0.0002 |
| `storm_family_at_start` | -0.0005 | 0.0003 | -0.0004 | 0.0004 |
| `peak_customers_out_so_far` | -0.0007 | 0.0009 | 0.0037 | 0.0003 |

Quantile crossings fixed on the test year (p90 raised to p50): baseline 0; linear 0; hgb 0; hgb_no_storm 1.
