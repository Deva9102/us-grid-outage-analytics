"""Restoration-time forecast: tune, train, calibrate and evaluate four models (D72).

Data: gold_restoration_features (sql/databricks/04_gold_forecast_features.sql, D71), read from a
DuckDB build or from Databricks. Settings: forecast in config/pipeline.yml.

Models, each with a separate p50 and p90 model:
    baseline      storm family x region training quantiles (scripts/forecast_baseline.py)
    linear        QuantileRegressor on log(duration_hours), one-hot categoricals
    hgb           HistGradientBoostingRegressor(loss="quantile") on log(duration_hours),
                  native categorical and missing-value support
    hgb_no_storm  hgb without the NOAA storm features (NOAA stands in for live NWS warnings)

Protocol (never tuned on the test year):
    1. tune      fit on the train years before validation_year, score each setting on validation_year
    2. calibrate when p90 coverage on validation_year is off by more than calibration_tolerance,
                 a split-conformal offset from the validation residuals (log scale) is added to p90
    3. retrain   on every train year with the chosen settings (hgb: the iterations early stopping chose)
    4. evaluate  once on test_years

Commands:
    train      steps 1-3; saves models/restoration/<version>/ (gitignored)
    evaluate   step 4; writes docs/forecast_results.md and .json and gold_restoration_predictions
               (in the DuckDB file, or on Databricks with --engine databricks)

Usage:
    uv run python scripts/forecast_model.py train --engine duckdb --duckdb-file build/duckdb/full.duckdb
    uv run python scripts/forecast_model.py evaluate --engine duckdb --duckdb-file build/duckdb/full.duckdb
"""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import math
import os
import time
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import QuantileRegressor
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

import forecast_baseline
import pipeline_config

REPO_ROOT = Path(__file__).resolve().parent.parent
TARGET = "duration_hours"
FAMILY, REGION = "storm_family_at_start", "census_region"
MODELS = ("baseline", "linear", "hgb", "hgb_no_storm")
LEARNED = ("linear", "hgb", "hgb_no_storm")
STORM = ["storm_type_at_start", "storm_family_at_start"]
CATEGORICAL = ["storm_type_at_start", "storm_family_at_start", "census_region", "state_abbr"]
BOOLEAN = ["has_denominator", "feed_gap_so_far", "dropout_so_far"]
NUMERIC = [
    "start_month_local", "start_hour_local", "start_weekday_local",
    "customers", "event_threshold",
    "customers_out_at_start", "customers_out_at_mid", "customers_out_at_prediction",
    "growth_customers", "growth_ratio", "peak_customers_out_so_far", "peak_share_so_far",
    "prior_events_per_year", "prior_eligible_events_per_year",
    "prior_median_duration_hours", "prior_eligible_median_duration_hours",
]
# Left out (D72): these grow with the number of history years, so the test year (3 years of
# history) would sit outside every training value. The per-year rates carry the same signal.
LEFT_OUT = ["history_years", "prior_event_count", "prior_eligible_event_count"]
# The linear model: calendar as one-hot, the storm type only as its family (types are too sparse).
LINEAR_CATEGORICAL = ["storm_family_at_start", "census_region", "state_abbr",
                      "start_month_local", "start_hour_local", "start_weekday_local"]
LINEAR_NUMERIC = [c for c in NUMERIC if c not in LINEAR_CATEGORICAL] + BOOLEAN
LOG_COLUMNS = ["customers", "event_threshold", "customers_out_at_start", "customers_out_at_mid",
               "customers_out_at_prediction", "growth_ratio", "peak_customers_out_so_far",
               "prior_events_per_year", "prior_eligible_events_per_year",
               "prior_median_duration_hours", "prior_eligible_median_duration_hours"]


class LeakageError(RuntimeError):
    """A test year reached a step that may only see training years."""


# -----------------------------------------------------------------------------
# Data
# -----------------------------------------------------------------------------

def load_features(engine: str, duckdb_file: Path | None = None) -> pd.DataFrame:
    if engine == "duckdb":
        import duckdb

        if not duckdb_file or not duckdb_file.exists():
            raise SystemExit(f"{duckdb_file} not found: run make forecast-features ENGINE=duckdb first")
        con = duckdb.connect(str(duckdb_file), read_only=True)
        df = con.execute("SELECT * FROM gold_restoration_features").df()
        con.close()
    else:
        from databricks import sql
        from dotenv import load_dotenv

        load_dotenv(REPO_ROOT / ".env")
        p = pipeline_config.get("project")
        with sql.connect(
            server_hostname=os.environ["DATABRICKS_SERVER_HOSTNAME"].strip().removeprefix("https://").rstrip("/"),
            http_path=os.environ["DATABRICKS_HTTP_PATH"].strip(),
            access_token=os.environ["DATABRICKS_TOKEN"].strip(),
        ) as conn, conn.cursor() as cur:
            cur.execute(f"SELECT * FROM {p['catalog']}.{p['schema']}.gold_restoration_features")
            df = cur.fetchall_arrow().to_pandas()
    return prepare(df)


def prepare(df: pd.DataFrame) -> pd.DataFrame:
    """Same types on both engines, rows in event_id order, and the derived per-year rate."""
    out = df.copy()
    for c in NUMERIC + BOOLEAN + LEFT_OUT + [TARGET]:
        if c in out.columns:
            out[c] = pd.to_numeric(out[c].astype(object), errors="raise").astype(float)
    for c in CATEGORICAL + ["event_id"]:
        out[c] = out[c].astype(object).where(out[c].notna(), None)
    out["event_year"] = out["event_year"].astype(int)
    out["prior_eligible_events_per_year"] = np.where(
        out["history_years"] > 0, out["prior_eligible_event_count"] / out["history_years"].where(out["history_years"] > 0), np.nan)
    return out.sort_values("event_id", kind="stable").reset_index(drop=True)


def fingerprint(df: pd.DataFrame) -> str:
    """Hash of every column the models read: equal when DuckDB and Databricks hold the same features."""
    cols = ["event_id", "event_year", TARGET] + CATEGORICAL + NUMERIC + BOOLEAN
    frame = df[cols].copy()
    for c in cols:
        frame[c] = frame[c].round(6) if frame[c].dtype.kind == "f" else frame[c].astype(str)
    return hashlib.sha256(pd.util.hash_pandas_object(frame, index=False).to_numpy().tobytes()).hexdigest()


def splits(df: pd.DataFrame, fc: dict) -> dict[str, pd.DataFrame]:
    val, test = fc["validation_year"], fc["test_years"]
    tune_years = [y for y in fc["train_years"] if y < val]
    return {
        "tune": df[df["event_year"].isin(tune_years)],
        "validation": df[df["event_year"] == val],
        "final": df[df["event_year"].isin(fc["train_years"])],
        "test": df[df["event_year"].isin(test)],
    }


def guard(frame: pd.DataFrame, fc: dict, step: str, audit: dict) -> None:
    """Every fit and the calibration pass through here: a test year stops the run."""
    years = sorted(int(y) for y in frame["event_year"].unique())
    if set(years) & set(fc["test_years"]):
        raise LeakageError(f"{step}: test years {fc['test_years']} must never be used, got {years}")
    audit[step] = sorted(set(audit.get(step, [])) | set(years))


# -----------------------------------------------------------------------------
# Models
# -----------------------------------------------------------------------------

def hgb_columns(storm: bool) -> list[str]:
    return [c for c in CATEGORICAL if storm or c not in STORM] + NUMERIC + BOOLEAN


def hgb_matrix(df: pd.DataFrame, categories: dict, storm: bool) -> pd.DataFrame:
    """Categoricals with the training categories fixed, so codes match and unseen values become missing."""
    cols = hgb_columns(storm)
    X = df[cols].copy()
    for c in cols:
        X[c] = pd.Categorical(X[c], categories=categories[c]) if c in CATEGORICAL else X[c].astype(float)
    return X


def linear_matrix(df: pd.DataFrame, storm: bool = True) -> pd.DataFrame:
    """Logs of the skewed counts, signed log of growth, calendar and categoricals as strings."""
    X = pd.DataFrame(index=df.index)
    for c in LINEAR_NUMERIC:
        v = df[c].astype(float)
        X[c] = np.log1p(v.clip(lower=0)) if c in LOG_COLUMNS else v
    X["growth_customers"] = np.sign(df["growth_customers"]) * np.log1p(df["growth_customers"].abs())
    for c in LINEAR_CATEGORICAL:
        if storm or c not in STORM:
            X[c] = df[c].map(lambda v: "missing" if v is None or (isinstance(v, float) and math.isnan(v)) else str(v))
    return X


def linear_pipeline(q: float, alpha: float) -> Pipeline:
    pre = ColumnTransformer([
        ("num", Pipeline([("impute", SimpleImputer(strategy="median", add_indicator=True, keep_empty_features=True)),
                          ("scale", StandardScaler())]), LINEAR_NUMERIC),
        ("cat", OneHotEncoder(handle_unknown="ignore", sparse_output=False),
         [c for c in LINEAR_CATEGORICAL]),
    ])
    return Pipeline([("pre", pre), ("model", QuantileRegressor(quantile=q, alpha=alpha, solver="highs"))])


def subsample(frame: pd.DataFrame, rows: int, seed: int) -> pd.DataFrame:
    if len(frame) <= rows:
        return frame
    idx = np.sort(np.random.default_rng(seed).choice(len(frame), size=rows, replace=False))
    return frame.iloc[idx]


def fit_learned(name: str, train: pd.DataFrame, q: float, params: dict, mc: dict, categories: dict,
                fc: dict, audit: dict, step: str):
    """One quantile model on log(duration_hours)."""
    guard(train, fc, step, audit)
    seed = mc["seed"]
    if name == "linear":
        train = subsample(train, mc["linear"]["max_train_rows"], seed)
        model = linear_pipeline(q, params["alpha"])
        model.fit(linear_matrix(train), np.log(train[TARGET].to_numpy()))
        return model
    h = mc["hgb"]
    model = HistGradientBoostingRegressor(
        loss="quantile", quantile=q, categorical_features="from_dtype",
        learning_rate=params["learning_rate"], max_leaf_nodes=int(params["max_leaf_nodes"]),
        min_samples_leaf=int(params["min_samples_leaf"]), max_iter=int(params.get("max_iter", h["max_iter"])),
        early_stopping=bool(params.get("early_stopping", h["early_stopping"])),
        validation_fraction=h["validation_fraction"], n_iter_no_change=h["n_iter_no_change"], random_state=seed,
    )
    X = hgb_matrix(train, categories, name == "hgb")
    # A numeric input that is empty in every training row cannot be binned; it carries no
    # information, so it is a constant for the fit. Only tiny samples hit this (the test fixture).
    for c in X.columns:
        if c not in CATEGORICAL and X[c].isna().all():
            X[c] = 0.0
    model.fit(X, np.log(train[TARGET].to_numpy()))
    return model


def predict_learned(name: str, model, df: pd.DataFrame, categories: dict) -> np.ndarray:
    X = linear_matrix(df) if name == "linear" else hgb_matrix(df, categories, name == "hgb")
    return np.exp(model.predict(X))


def predict_baseline(train: pd.DataFrame, df: pd.DataFrame, fc: dict) -> dict[float, np.ndarray]:
    pred = forecast_baseline.predict(train, df.reset_index(drop=True), [FAMILY, REGION], fc["quantiles"],
                                     fc["baseline_min_events"])
    return {q: pred[f"q{q}"].to_numpy(float) for q in fc["quantiles"]}


def grid(name: str, mc: dict) -> list[dict]:
    if name == "linear":
        return [{"alpha": a} for a in mc["linear"]["alpha"]]
    g = mc["hgb"]["grid"]
    keys = sorted(g)
    return [dict(zip(keys, combo, strict=True)) for combo in itertools.product(*(g[k] for k in keys))]


def categories_of(frame: pd.DataFrame) -> dict[str, list[str]]:
    return {c: sorted(v for v in frame[c].dropna().unique()) for c in CATEGORICAL}


# -----------------------------------------------------------------------------
# Metrics and calibration
# -----------------------------------------------------------------------------

def pinball(y: np.ndarray, pred: np.ndarray, q: float) -> float:
    return forecast_baseline.pinball(y, pred, q)


def metrics(y: np.ndarray, p50: np.ndarray, p90: np.ndarray) -> dict:
    if len(y) == 0:
        return {"n": 0}
    return {
        "n": int(len(y)),
        "mae_p50": float(np.mean(np.abs(y - p50))),
        "medae_p50": float(np.median(np.abs(y - p50))),
        "pinball_p50": pinball(y, p50, 0.5),
        "pinball_p90": pinball(y, p90, 0.9),
        "coverage_p90": float(np.mean(y <= p90)),
    }


def conformal_offset(y: np.ndarray, p90: np.ndarray, q: float) -> float:
    """Split-conformal offset on the log scale: the ceil((n+1)q)-th smallest log(y / p90)."""
    scores = np.sort(np.log(y) - np.log(p90))
    k = min(math.ceil((len(scores) + 1) * q), len(scores))
    return float(scores[k - 1])


def size_band(df: pd.DataFrame, edges: list[int]) -> pd.Series:
    lo, hi = edges
    v = df["customers_out_at_prediction"]
    return pd.Series(np.where(v < lo, f"< {lo:,}", np.where(v < hi, f"{lo:,}-{hi - 1:,}", f"{hi:,}+")), index=df.index)


# -----------------------------------------------------------------------------
# Train
# -----------------------------------------------------------------------------

def config_hash(fc: dict) -> str:
    payload = {"forecast": fc, "features": {"categorical": CATEGORICAL, "numeric": NUMERIC, "boolean": BOOLEAN,
                                            "left_out": LEFT_OUT}, "sklearn": sklearn.__version__}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()


def train(df: pd.DataFrame, fc: dict, log=print) -> dict:
    """Tune on the validation year, calibrate p90 on it, retrain on all train years. Never sees test years."""
    mc, qs = fc["model"], fc["quantiles"]
    q50, q90 = qs
    s = splits(df, fc)
    audit: dict[str, list[int]] = {}
    tune, val, final = s["tune"], s["validation"], s["final"]
    y_val = val[TARGET].to_numpy(float)
    tune_cats, final_cats = categories_of(tune), categories_of(final)

    # 1. Tune: every setting of every learned model, scored by pinball loss in hours on the validation year.
    tuning, chosen, val_pred = [], {}, {}
    guard(tune, fc, "baseline_tune", audit)
    val_pred["baseline"] = predict_baseline(tune, val, fc)
    for name in LEARNED:
        val_pred[name] = {}
        for q in qs:
            best = None
            for params in grid(name, mc):
                t0 = time.time()
                model = fit_learned(name, tune, q, params, mc, tune_cats, fc, audit, "tune")
                pred = predict_learned(name, model, val, tune_cats)
                loss = pinball(y_val, pred, q)
                row = {"model": name, "quantile": q, **params, "pinball_validation": loss,
                       "seconds": round(time.time() - t0, 1)}
                if name != "linear":
                    row["n_iter"] = int(model.n_iter_)
                tuning.append(row)
                if best is None or loss < best[0]:
                    best = (loss, row, pred)
            chosen[(name, q)] = {k: v for k, v in best[1].items() if k not in ("model", "quantile", "seconds")}
            val_pred[name][q] = best[2]
            log(f"  tuned {name:12s} q{q}: pinball {best[0]:.4f}  {chosen[(name, q)]}")

    # 2. Calibrate p90 on the validation year when its coverage is off by more than the tolerance.
    guard(val, fc, "calibration", audit)
    calibration = {}
    for name in MODELS:
        p50, p90 = val_pred[name][q50], val_pred[name][q90]
        coverage = float(np.mean(y_val <= p90))
        offset = conformal_offset(y_val, p90, q90)
        applied = abs(coverage - q90) > mc["calibration_tolerance"]
        cal_p90 = np.maximum(p90 * math.exp(offset) if applied else p90, p50)
        calibration[name] = {"coverage_validation_raw": coverage, "offset_log": offset, "factor": math.exp(offset),
                             "applied": bool(applied),
                             "coverage_validation_calibrated": float(np.mean(y_val <= cal_p90))}
        val_pred[name] = {q50: p50, q90: cal_p90, "p90_raw": p90}
        log(f"  calibration {name:12s} validation coverage {coverage:.3f} -> "
            f"{f'x{math.exp(offset):.3f}' if applied else 'unchanged'}")

    # 3. Retrain on all train years with the chosen settings; hgb keeps the iterations early stopping chose.
    models = {}
    for name in LEARNED:
        models[name] = {}
        for q in qs:
            params = dict(chosen[(name, q)])
            params.pop("pinball_validation", None)
            if name != "linear":
                params.update(max_iter=params.pop("n_iter"), early_stopping=False)
            models[name][q] = fit_learned(name, final, q, params, mc, final_cats, fc, audit, "retrain")
    guard(final, fc, "baseline_retrain", audit)

    chash = config_hash(fc)
    validation = pd.DataFrame({"event_id": val["event_id"].to_numpy()})
    for name in MODELS:
        validation[f"{name}_p50"] = val_pred[name][q50]
        validation[f"{name}_p90"] = val_pred[name][q90]
        validation[f"{name}_p90_raw"] = val_pred[name]["p90_raw"]
    return {
        "version": f"{mc['version']}-{chash[:8]}",
        "config_hash": chash,
        "sklearn_version": sklearn.__version__,
        "data_fingerprint": fingerprint(df),
        "categories": final_cats,
        "models": models,
        "baseline_train": final[[FAMILY, REGION, TARGET]].reset_index(drop=True),
        "chosen": {f"{n}|{q}": v for (n, q), v in chosen.items()},
        "tuning": tuning,
        "calibration": calibration,
        "validation": validation,
        "audit": audit,
        "rows": {k: int(len(v)) for k, v in s.items()},
    }


def predict_all(bundle: dict, df: pd.DataFrame, fc: dict) -> dict[str, dict]:
    """p50 and calibrated p90 of every model for df, from the retrained models."""
    q50, q90 = fc["quantiles"]
    out = {"baseline": predict_baseline(bundle["baseline_train"], df, fc)}
    for name in LEARNED:
        out[name] = {q: predict_learned(name, bundle["models"][name][q], df, bundle["categories"]) for q in (q50, q90)}
    for name in MODELS:
        cal = bundle["calibration"][name]
        raw = out[name][q90]
        out[name] = {q50: out[name][q50], "p90_raw": raw,
                     q90: np.maximum(raw * cal["factor"] if cal["applied"] else raw, out[name][q50])}
    return out


def model_dir(bundle_version: str, fc: dict) -> Path:
    return REPO_ROOT / fc["model"]["folder"] / bundle_version


def save(bundle: dict, fc: dict, engine: str) -> Path:
    folder = model_dir(bundle["version"], fc)
    folder.mkdir(parents=True, exist_ok=True)
    joblib.dump(bundle, folder / "bundle.joblib")
    meta = {k: bundle[k] for k in ("version", "config_hash", "sklearn_version", "data_fingerprint", "audit", "rows")}
    meta["engine"] = engine
    (folder / "metadata.json").write_text(json.dumps(meta, indent=2) + "\n")
    (folder.parent / "LATEST").write_text(bundle["version"] + "\n")
    return folder


def load_bundle(fc: dict) -> dict:
    latest = REPO_ROOT / fc["model"]["folder"] / "LATEST"
    if not latest.exists():
        raise SystemExit("No trained model: run make forecast-train first")
    bundle = joblib.load(model_dir(latest.read_text().strip(), fc) / "bundle.joblib")
    if bundle["config_hash"] != config_hash(fc):
        raise SystemExit("config/pipeline.yml forecast settings changed since training: run make forecast-train")
    return bundle


# -----------------------------------------------------------------------------
# Evaluate
# -----------------------------------------------------------------------------

def breakdowns(df: pd.DataFrame, preds: dict, fc: dict) -> dict:
    q50, q90 = fc["quantiles"]
    y = df[TARGET].to_numpy(float)
    groups = {"storm_family": df[FAMILY].to_numpy(), "census_region": df[REGION].to_numpy(),
              "outage_size": size_band(df, fc["size_band_edges"]).to_numpy()}
    out = {"overall": {m: metrics(y, preds[m][q50], preds[m][q90]) for m in MODELS}}
    out["overall_p90_uncalibrated"] = {m: metrics(y, preds[m][q50], preds[m]["p90_raw"]) for m in MODELS}
    for gname, g in groups.items():
        out[gname] = {}
        for level in sorted(set(g)):
            mask = g == level
            out[gname][str(level)] = {m: metrics(y[mask], preds[m][q50][mask], preds[m][q90][mask]) for m in MODELS}
    return out


def bootstrap(y: np.ndarray, preds: dict, fc: dict) -> dict:
    """Paired bootstrap over test events of (model - baseline) for p50 MAE and p90 pinball loss."""
    q50, q90 = fc["quantiles"]
    mc = fc["model"]
    rng = np.random.default_rng(mc["seed"])
    base_ae = np.abs(y - preds["baseline"][q50])
    base_pl = np.maximum(q90 * (y - preds["baseline"][q90]), (q90 - 1) * (y - preds["baseline"][q90]))
    out = {}
    idx = [rng.integers(0, len(y), len(y)) for _ in range(mc["bootstrap_samples"])]
    for m in LEARNED:
        ae = np.abs(y - preds[m][q50]) - base_ae
        pl = np.maximum(q90 * (y - preds[m][q90]), (q90 - 1) * (y - preds[m][q90])) - base_pl
        res = {}
        for key, d in (("mae_p50", ae), ("pinball_p90", pl)):
            draws = np.array([d[i].mean() for i in idx])
            res[key] = {"diff": float(d.mean()), "ci_low": float(np.quantile(draws, 0.025)),
                        "ci_high": float(np.quantile(draws, 0.975))}
        out[m] = res
    return out


def permutation_importance(bundle: dict, df: pd.DataFrame, fc: dict) -> list[dict]:
    """Increase in p50 MAE and p90 pinball loss (hours) when one hgb input is shuffled, on a seeded test sample."""
    q50, q90 = fc["quantiles"]
    mc = fc["model"]
    sample = subsample(df, mc["permutation_rows"], mc["seed"])
    y = sample[TARGET].to_numpy(float)
    cats, cal = bundle["categories"], bundle["calibration"]["hgb"]
    factor = cal["factor"] if cal["applied"] else 1.0
    X = hgb_matrix(sample, cats, storm=True)
    m50, m90 = bundle["models"]["hgb"][q50], bundle["models"]["hgb"][q90]

    def losses(frame):
        p50 = np.exp(m50.predict(frame))
        p90 = np.maximum(np.exp(m90.predict(frame)) * factor, p50)
        return float(np.mean(np.abs(y - p50))), pinball(y, p90, q90)

    base = losses(X)
    rng = np.random.default_rng(mc["seed"])
    rows = []
    for col in X.columns:
        inc = []
        for _ in range(mc["permutation_repeats"]):
            Xp = X.copy()
            Xp[col] = X[col].to_numpy()[rng.permutation(len(X))]
            if col in CATEGORICAL:
                Xp[col] = pd.Categorical(Xp[col], categories=cats[col])
            mae, pl = losses(Xp)
            inc.append((mae - base[0], pl - base[1]))
        inc = np.array(inc)
        rows.append({"feature": col, "mae_p50_increase": float(inc[:, 0].mean()), "mae_p50_sd": float(inc[:, 0].std()),
                     "pinball_p90_increase": float(inc[:, 1].mean()), "pinball_p90_sd": float(inc[:, 1].std())})
    return sorted(rows, key=lambda r: -r["mae_p50_increase"])


def evaluate(bundle: dict, df: pd.DataFrame, fc: dict) -> tuple[dict, pd.DataFrame]:
    q50, q90 = fc["quantiles"]
    s = splits(df, fc)
    val, test = s["validation"], s["test"]
    test_pred = predict_all(bundle, test, fc)
    v = bundle["validation"].set_index("event_id").loc[val["event_id"]]
    val_pred = {m: {q50: v[f"{m}_p50"].to_numpy(), q90: v[f"{m}_p90"].to_numpy(), "p90_raw": v[f"{m}_p90_raw"].to_numpy()}
                for m in MODELS}
    results = {
        "version": bundle["version"],
        "config_hash": bundle["config_hash"],
        "data_fingerprint": bundle["data_fingerprint"],
        "rows": bundle["rows"],
        "audit": bundle["audit"],
        "chosen": bundle["chosen"],
        "calibration": bundle["calibration"],
        "test": breakdowns(test, test_pred, fc),
        "validation": breakdowns(val, val_pred, fc),
        "bootstrap": bootstrap(test[TARGET].to_numpy(float), test_pred, fc),
        "importance": permutation_importance(bundle, test, fc),
        "crossing_fixed_test": {m: int(np.sum(test_pred[m]["p90_raw"] * (bundle["calibration"][m]["factor"]
                                                                           if bundle["calibration"][m]["applied"] else 1)
                                              < test_pred[m][q50])) for m in MODELS},
    }
    frames = []
    for split_name, frame, pred in (("validation", val, val_pred), ("test", test, test_pred)):
        for m in MODELS:
            frames.append(pd.DataFrame({
                "event_id": frame["event_id"].to_numpy(), "event_year": frame["event_year"].to_numpy(),
                "eval_split": split_name, "model": m,
                "p50_hours": pred[m][q50], "p90_hours": pred[m][q90], "model_version": bundle["version"],
            }))
    return results, pd.concat(frames, ignore_index=True)


# -----------------------------------------------------------------------------
# Report
# -----------------------------------------------------------------------------

LABEL = {"baseline": "Baseline (family x region)", "linear": "Quantile linear", "hgb": "Gradient boosting",
         "hgb_no_storm": "Gradient boosting, no storm features"}


def _metric_table(block: dict, models=MODELS) -> list[str]:
    lines = ["| Model | Events | p50 MAE (h) | p50 pinball | p90 pinball | p90 coverage |", "|---|---|---|---|---|---|"]
    for m in models:
        r = block[m]
        lines.append(f"| {LABEL[m]} | {r['n']:,} | {r['mae_p50']:.3f} | {r['pinball_p50']:.3f} | "
                     f"{r['pinball_p90']:.3f} | {r['coverage_p90']:.1%} |")
    return lines


def _group_table(groups: dict) -> list[str]:
    lines = ["| Group | Events | " + " | ".join(f"{m} MAE / p90 cov." for m in MODELS) + " |",
             "|---|---|" + "---|" * len(MODELS)]
    for level, block in sorted(groups.items(), key=lambda kv: -kv[1]["baseline"]["n"]):
        n = block["baseline"]["n"]
        cells = [f"{block[m]['mae_p50']:.2f} / {block[m]['coverage_p90']:.0%}" for m in MODELS]
        lines.append(f"| {level} | {n:,} | " + " | ".join(cells) + " |")
    return lines


def render(results: dict, fc: dict) -> str:
    t, v = results["test"], results["validation"]
    test_years = ", ".join(map(str, fc["test_years"]))
    val_year = fc["validation_year"]
    base = t["overall"]["baseline"]
    lines = [
        "# Restoration forecast: results",
        "",
        "Written by `scripts/forecast_model.py evaluate` (`make forecast-evaluate`). Every number below is in "
        "`docs/forecast_results.json`. Design: `docs/decisions.md` D71 (features) and D72 (models). "
        "Model card: `docs/model_card_restoration.md`.",
        "",
        f"Model version `{results['version']}`; config hash `{results['config_hash'][:16]}`; "
        f"feature data fingerprint `{results['data_fingerprint'][:16]}`.",
        "",
        "## Protocol",
        "",
        f"- Tune on {results['audit']['tune']} ({results['rows']['tune']:,} events), validate on {val_year} "
        f"({results['rows']['validation']:,}). Retrain on {results['audit']['retrain']} ({results['rows']['final']:,}). "
        f"Evaluate once on {test_years} ({results['rows']['test']:,}).",
        f"- Years each step saw (recorded by the run): {json.dumps(results['audit'])}. "
        f"{test_years} never appears.",
        "- Target: log(duration_hours); predictions converted back to hours. Errors are in hours.",
        "",
        "Chosen settings (by validation pinball loss in hours):",
        "",
        "| Model | Quantile | Settings | Validation pinball |",
        "|---|---|---|---|",
    ]
    for key, val in results["chosen"].items():
        name, q = key.split("|")
        settings = ", ".join(f"{k}={val[k]}" for k in sorted(val) if k != "pinball_validation")
        lines.append(f"| {LABEL[name]} | {q} | {settings} | {val['pinball_validation']:.4f} |")
    lines += ["", f"## p90 calibration on {val_year}", "",
              f"Applied when validation coverage is more than {fc['model']['calibration_tolerance'] * 100:g} percentage points from 90% "
              "(split-conformal offset on the log scale, from the validation residuals).", "",
              "| Model | Validation coverage | Applied | Factor | Validation coverage after |", "|---|---|---|---|---|"]
    for m in MODELS:
        c = results["calibration"][m]
        lines.append(f"| {LABEL[m]} | {c['coverage_validation_raw']:.1%} | {'yes' if c['applied'] else 'no'} | "
                     f"{c['factor']:.3f} | {c['coverage_validation_calibrated']:.1%} |")
    lines += ["", f"## {test_years} test results", "", *_metric_table(t["overall"]), "",
              "p90 coverage before calibration: " + "; ".join(
                  f"{LABEL[m]} {t['overall_p90_uncalibrated'][m]['coverage_p90']:.1%}" for m in MODELS) + ".", "",
              "### Against the baseline", "",
              f"Difference to the baseline on {test_years} (negative is better), with a 95% paired bootstrap interval "
              f"({fc['model']['bootstrap_samples']} resamples):", "",
              "| Model | p50 MAE diff (h) | 95% interval | Relative | p90 pinball diff | 95% interval | Relative | Beats baseline |",
              "|---|---|---|---|---|---|---|---|"]
    for m in LEARNED:
        b = results["bootstrap"][m]
        a, p = b["mae_p50"], b["pinball_p90"]
        beats = a["ci_high"] < 0 and p["ci_high"] < 0
        lines.append(f"| {LABEL[m]} | {a['diff']:+.3f} | [{a['ci_low']:+.3f}, {a['ci_high']:+.3f}] | "
                     f"{a['diff'] / base['mae_p50']:+.1%} | {p['diff']:+.3f} | [{p['ci_low']:+.3f}, {p['ci_high']:+.3f}] | "
                     f"{p['diff'] / base['pinball_p90']:+.1%} | {'yes, both' if beats else 'no'} |")
    nostorm = results["bootstrap"]
    lines += ["", "### Effect of the storm features (decision 1)", "",
              f"Removing the NOAA storm features changes p50 MAE by "
              f"{t['overall']['hgb_no_storm']['mae_p50'] - t['overall']['hgb']['mae_p50']:+.3f} h and p90 pinball loss by "
              f"{t['overall']['hgb_no_storm']['pinball_p90'] - t['overall']['hgb']['pinball_p90']:+.3f} "
              f"(gradient boosting without minus with). Relative to the baseline: with storms "
              f"{nostorm['hgb']['mae_p50']['diff']:+.3f} h, without {nostorm['hgb_no_storm']['mae_p50']['diff']:+.3f} h p50 MAE.",
              "", "### By storm family at the start", "",
              "Cells: p50 MAE (h) / p90 coverage. Small groups are noisy: read the event counts.", "",
              *_group_table(t["storm_family"]), "", "### By Census region", "", *_group_table(t["census_region"]), "",
              "### By outage size at the prediction moment (customers out)", "", *_group_table(t["outage_size"]), ""]
    hur = "Hurricane / tropical"
    th, vh = t["storm_family"].get(hur, {}).get("baseline", {"n": 0}), v["storm_family"].get(hur, {}).get("baseline", {"n": 0})
    lines += ["### Hurricane / tropical: indicative only", "",
              f"{test_years} has {th['n']:,} hurricane / tropical events, too few to evaluate the category. "
              f"The {val_year} validation year has {vh['n']:,}; its results are indicative only, because {val_year} "
              "also chose the settings and the calibration:", ""]
    if vh["n"]:
        lines += _metric_table(v["storm_family"][hur])
    lines += ["", f"## {val_year} validation results (tuning models, trained on {results['audit']['tune']})", "",
              *_metric_table(v["overall"]), "", "By storm family (p50 MAE / p90 coverage):", "",
              *_group_table(v["storm_family"]), "",
              f"## Permutation importance (gradient boosting, {test_years})", "",
              f"Increase in loss when one input is shuffled, mean of {fc['model']['permutation_repeats']} shuffles on a "
              f"seeded sample of {min(fc['model']['permutation_rows'], results['rows']['test']):,} test events.", "",
              "| Feature | p50 MAE increase (h) | sd | p90 pinball increase | sd |", "|---|---|---|---|---|"]
    for r in results["importance"]:
        lines.append(f"| `{r['feature']}` | {r['mae_p50_increase']:.4f} | {r['mae_p50_sd']:.4f} | "
                     f"{r['pinball_p90_increase']:.4f} | {r['pinball_p90_sd']:.4f} |")
    lines += ["", "Quantile crossings fixed on the test year (p90 raised to p50): "
              + "; ".join(f"{m} {n:,}" for m, n in results["crossing_fixed_test"].items()) + ".", ""]
    return "\n".join(lines)


# -----------------------------------------------------------------------------
# Predictions table
# -----------------------------------------------------------------------------

PREDICTIONS_TABLE = "gold_restoration_predictions"


def write_predictions(pred: pd.DataFrame, engine: str, duckdb_file: Path | None) -> None:
    if engine == "duckdb":
        import duckdb

        con = duckdb.connect(str(duckdb_file))
        con.register("pred_df", pred)
        con.execute(f"CREATE OR REPLACE TABLE {PREDICTIONS_TABLE} AS SELECT * FROM pred_df")
        n = con.execute(f"SELECT COUNT(*) FROM {PREDICTIONS_TABLE}").fetchone()[0]
        con.close()
    else:
        import run_databricks

        w, warehouse_id = run_databricks.connect()
        local = REPO_ROOT / "build" / "forecast" / f"{PREDICTIONS_TABLE}.parquet"
        local.parent.mkdir(parents=True, exist_ok=True)
        pred.to_parquet(local, index=False)
        remote = f"{run_databricks.VOLUME}/forecast/{PREDICTIONS_TABLE}.parquet"
        with local.open("rb") as f:
            w.files.upload(remote, f, overwrite=True)
        run_databricks.run_sql(w, warehouse_id, f"""
            CREATE OR REPLACE TABLE {PREDICTIONS_TABLE}
            COMMENT 'Restoration forecast p50 and p90 hours per eligible event and model, 2024 validation and 2025 test (D72)'
            AS SELECT event_id, CAST(event_year AS INT) AS event_year, eval_split, model,
                      p50_hours, p90_hours, model_version
            FROM read_files('{remote}', format => 'parquet')""")
        n = int(run_databricks.run_sql(w, warehouse_id, f"SELECT COUNT(*) FROM {PREDICTIONS_TABLE}")[0][0])
    if n != len(pred):
        raise SystemExit(f"{PREDICTIONS_TABLE}: wrote {n:,} rows, expected {len(pred):,}")
    print(f"{PREDICTIONS_TABLE} ({engine}): {n:,} rows")


# -----------------------------------------------------------------------------
# CLI
# -----------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["train", "evaluate"])
    parser.add_argument("--engine", choices=["duckdb", "databricks"], default="duckdb")
    parser.add_argument("--duckdb-file", default="build/duckdb/full.duckdb")
    args = parser.parse_args()
    fc = pipeline_config.load()["forecast"]
    duckdb_file = REPO_ROOT / args.duckdb_file
    df = load_features(args.engine, duckdb_file)
    print(f"gold_restoration_features ({args.engine}): {len(df):,} events, fingerprint {fingerprint(df)[:16]}")
    if args.command == "train":
        bundle = train(df, fc)
        folder = save(bundle, fc, args.engine)
        print(f"saved {folder.relative_to(REPO_ROOT)} (version {bundle['version']})")
        return
    bundle = load_bundle(fc)
    if bundle["data_fingerprint"] != fingerprint(df):
        raise SystemExit("The feature data differs from the data the model was trained on: run make forecast-train")
    results, pred = evaluate(bundle, df, fc)
    (REPO_ROOT / "docs" / "forecast_results.json").write_text(json.dumps(results, indent=1, sort_keys=True) + "\n")
    (REPO_ROOT / "docs" / "forecast_results.md").write_text(render(results, fc))
    print("docs/forecast_results.md and .json: written")
    write_predictions(pred, args.engine, duckdb_file)
    for m in MODELS:
        r = results["test"]["overall"][m]
        print(f"  {m:13s} MAE {r['mae_p50']:.3f}  pinball p50 {r['pinball_p50']:.3f}  p90 {r['pinball_p90']:.3f}  "
              f"coverage {r['coverage_p90']:.3f}")


if __name__ == "__main__":
    main()
