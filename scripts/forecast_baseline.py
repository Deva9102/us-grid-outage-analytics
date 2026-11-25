"""Restoration-forecast baseline: training-year quantiles by storm family (D71).

Reads gold_restoration_features from a DuckDB build (scripts/forecast_features.py) and scores
three lookup baselines on the test years (forecast.test_years in config/pipeline.yml):

    global         one p50 and one p90 from all training events
    family         p50 and p90 per storm family at the start
    family_region  per storm family x Census region; a cell with fewer than
                   forecast.baseline_min_events training events uses its family's values

Quantiles are linear-interpolated, the same as PERCENTILE_CONT. Scores on the test events:
    p50: MAE in hours (and median absolute error)
    p90: coverage (share of events at or under the p90) and pinball loss at 0.9

Writes docs/forecast_baseline.md: eligible events per year, feature null rates, the target
distribution and the scores.

Usage:
    uv run python scripts/forecast_baseline.py                          # build/duckdb/full.duckdb
    uv run python scripts/forecast_baseline.py --duckdb-file build/duckdb/fixture.duckdb --out -
"""

from __future__ import annotations

import argparse
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

import pipeline_config

REPO_ROOT = Path(__file__).resolve().parent.parent
TARGET = "duration_hours"
FAMILY, REGION = "storm_family_at_start", "census_region"
# Identifiers, the split and the target are not features.
NOT_FEATURES = {"event_id", "fips_code", "county", "event_year", "split", "event_start", "prediction_time", TARGET}


def pinball(y: np.ndarray, q_pred: np.ndarray, q: float) -> float:
    """Mean pinball (quantile) loss: q x under-prediction, (1 - q) x over-prediction."""
    diff = y - q_pred
    return float(np.mean(np.maximum(q * diff, (q - 1) * diff)))


def fit(train: pd.DataFrame, keys: list[str], quantiles: list[float]) -> pd.DataFrame:
    """Training quantiles of the target per group, with the group's event count."""
    if not keys:
        out = pd.DataFrame({f"q{q}": [train[TARGET].quantile(q)] for q in quantiles})
        out["n"] = len(train)
        return out
    g = train.groupby(keys)[TARGET]
    out = pd.concat({f"q{q}": g.quantile(q) for q in quantiles}, axis=1)
    out["n"] = g.size()
    return out.reset_index()


def predict(train: pd.DataFrame, test: pd.DataFrame, keys: list[str], quantiles: list[float],
            min_events: int) -> pd.DataFrame:
    """p50 / p90 for each test event from the finest level with at least min_events training events.

    Levels go from keys to shorter prefixes of keys and finally to all training events.
    """
    cols = [f"q{q}" for q in quantiles]
    pred = pd.DataFrame(index=test.index, columns=cols, dtype=float)
    for depth in range(len(keys), -1, -1):
        level = keys[:depth]
        table = fit(train, level, quantiles)
        table = table[table["n"] >= min_events] if depth else table
        todo = pred[cols[0]].isna()
        if not todo.any():
            break
        if level:
            merged = test.loc[todo, level].merge(table, on=level, how="left")
            merged.index = test.index[todo]
        else:
            merged = pd.DataFrame({c: table[c].iloc[0] for c in cols}, index=test.index[todo])
        pred.loc[todo, cols] = merged[cols].to_numpy()
    return pred


def score(y: np.ndarray, p50: np.ndarray, p90: np.ndarray) -> dict[str, float]:
    return {
        "mae_p50": float(np.mean(np.abs(y - p50))),
        "medae_p50": float(np.median(np.abs(y - p50))),
        "coverage_p90": float(np.mean(y <= p90)),
        "pinball_p90": pinball(y, p90, 0.9),
    }


def evaluate(df: pd.DataFrame, quantiles: list[float], min_events: int) -> dict[str, dict[str, float]]:
    train, test = df[df["split"] == "train"], df[df["split"] == "test"]
    y = test[TARGET].to_numpy(dtype=float)
    results = {}
    for name, keys in (("global", []), ("family", [FAMILY]), ("family_region", [FAMILY, REGION])):
        pred = predict(train, test, keys, quantiles, min_events)
        results[name] = score(y, pred[f"q{quantiles[0]}"].to_numpy(float), pred[f"q{quantiles[1]}"].to_numpy(float))
    return results


def null_rates(df: pd.DataFrame) -> pd.Series:
    feats = [c for c in df.columns if c not in NOT_FEATURES]
    return df[feats].isna().mean().sort_values(ascending=False)


def render(df: pd.DataFrame, results: dict, cfg: dict) -> str:
    fc = cfg["forecast"]
    train, test = df[df["split"] == "train"], df[df["split"] == "test"]
    per_year = df.groupby(["event_year", "split"]).size()
    q = df[TARGET].quantile([0.1, 0.25, 0.5, 0.75, 0.9, 0.99])
    nulls = null_rates(df)
    nulls = nulls[nulls > 0]
    hist = (df[df["event_year"] > cfg["years"]["first"]]["prior_eligible_median_duration_hours"].isna().mean())
    fam = train.groupby(FAMILY)[TARGET].agg(["size", "median", lambda s: s.quantile(0.9)])
    fam.columns = ["events", "p50", "p90"]
    fam["events"] = fam["events"].astype(int)
    fam = fam.sort_values("events", ascending=False)
    lines = [
        "# Restoration forecast: baseline",
        "",
        "Written by `scripts/forecast_baseline.py` from `gold_restoration_features` "
        "(`sql/databricks/04_gold_forecast_features.sql`). Design and eligibility: `docs/decisions.md` D71.",
        "",
        f"**Task.** At {fc['prediction_hours']:g} hours after an outage event starts, predict its total duration "
        "(p50 and p90). Eligible: the outage still meets its county's event threshold at that moment. "
        f"Train {', '.join(map(str, fc['train_years']))}; test {', '.join(map(str, fc['test_years']))} (time-based split).",
        "",
        "## Eligible events",
        "",
        "| Year | Split | Events |",
        "|---|---|---|",
        *[f"| {y} | {s} | {n:,} |" for (y, s), n in per_year.items()],
        "",
        "## Target: duration_hours",
        "",
        f"All eligible events: p10 {q[0.1]:.2f} h, p25 {q[0.25]:.2f}, median {q[0.5]:.2f}, p75 {q[0.75]:.2f}, "
        f"p90 {q[0.9]:.2f}, p99 {q[0.99]:.1f}, max {df[TARGET].max():,.0f} h. Mean {df[TARGET].mean():.2f} h: "
        "heavily right-skewed, so quantile losses are used rather than squared error.",
        "",
        f"Training median {train[TARGET].median():.2f} h, p90 {train[TARGET].quantile(0.9):.2f} h; "
        f"test median {test[TARGET].median():.2f} h, p90 {test[TARGET].quantile(0.9):.2f} h.",
        "",
        "## Feature null rates",
        "",
        "Features with any NULL (all others are complete):",
        "",
        "| Feature | Null share |",
        "|---|---|",
        *[f"| `{c}` | {v:.1%} |" for c, v in nulls.items()],
        "",
        f"History is NULL by design for {cfg['years']['first']} events (no earlier year). After "
        f"{cfg['years']['first']}, {hist:.1%} of events have no earlier eligible event in their county.",
        "",
        "## Training quantiles by storm family at the start",
        "",
        "| Storm family | Training events | p50 (h) | p90 (h) |",
        "|---|---|---|---|",
        *[f"| {f} | {r.events:,} | {r.p50:.2f} | {r.p90:.2f} |" for f, r in fam.iterrows()],
        "",
        f"## Baseline scores on {', '.join(map(str, fc['test_years']))} ({len(test):,} events)",
        "",
        f"Family x region cells with fewer than {fc['baseline_min_events']} training events use the family's values.",
        "",
        "| Baseline | p50 MAE (h) | p50 median abs. error (h) | p90 coverage | p90 pinball loss |",
        "|---|---|---|---|---|",
        *[f"| {name} | {r['mae_p50']:.3f} | {r['medae_p50']:.3f} | {r['coverage_p90']:.1%} | {r['pinball_p90']:.3f} |"
          for name, r in results.items()],
        "",
        "A model has to beat the `family_region` row on p50 MAE and p90 pinball loss, with p90 coverage "
        "close to 90%.",
        "",
    ]
    return "\n".join(lines)


def load(path: Path) -> pd.DataFrame:
    con = duckdb.connect(str(path), read_only=True)
    df = con.execute("SELECT * FROM gold_restoration_features").df()
    con.close()
    return df


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--duckdb-file", default="build/duckdb/full.duckdb")
    parser.add_argument("--out", default="docs/forecast_baseline.md", help="'-' prints instead")
    args = parser.parse_args()
    cfg = pipeline_config.load()
    fc = cfg["forecast"]
    df = load(REPO_ROOT / args.duckdb_file)
    results = evaluate(df, fc["quantiles"], fc["baseline_min_events"])
    text = render(df, results, cfg)
    if args.out == "-":
        print(text)
    else:
        (REPO_ROOT / args.out).write_text(text)
        print(f"{args.out}: written")
    for name, r in results.items():
        print(f"  {name:14s} MAE {r['mae_p50']:.3f}  p90 coverage {r['coverage_p90']:.3f}  pinball {r['pinball_p90']:.3f}")


if __name__ == "__main__":
    main()
