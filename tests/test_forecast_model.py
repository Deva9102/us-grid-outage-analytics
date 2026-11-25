"""Restoration-forecast models (D72): a deterministic smoke run on the fixture, and the test year
never reaching training, tuning or calibration.

The fixture has 14 eligible events (2022: 3, 2024: 9, 2025: 2), so the settings are shrunk to a
grid the fixture can fit. The same code path runs on the full data.
"""

from __future__ import annotations

import copy

import numpy as np
import pandas as pd
import pytest

import duckdb_pipeline
import forecast_model as fm
import pipeline_config
from conftest import FIXTURES


def small_config() -> dict:
    fc = copy.deepcopy(pipeline_config.load()["forecast"])
    fc["baseline_min_events"] = 2
    mc = fc["model"]
    mc["hgb"].update(grid={"learning_rate": [0.1], "max_leaf_nodes": [3], "min_samples_leaf": [1, 2]},
                     max_iter=5, early_stopping=False)
    mc["linear"].update(alpha=[0.0, 0.01], max_train_rows=1000)
    mc.update(permutation_rows=50, permutation_repeats=2, bootstrap_samples=10)
    return fc


@pytest.fixture(scope="module")
def features() -> pd.DataFrame:
    con = duckdb_pipeline.connect()
    duckdb_pipeline.run_all(con, FIXTURES)
    duckdb_pipeline.run_file(con, "04_gold_forecast_features.sql", FIXTURES)
    df = con.execute("SELECT * FROM gold_restoration_features").df()
    con.close()
    return fm.prepare(df)


@pytest.fixture(scope="module")
def fc() -> dict:
    return small_config()


@pytest.fixture(scope="module")
def bundle(features, fc):
    return fm.train(features, fc, log=lambda *_: None)


def test_fixture_has_every_split(features, fc):
    s = fm.splits(features, fc)
    assert {k: len(v) for k, v in s.items()} == {"tune": 3, "validation": 9, "final": 12, "test": 2}


def test_smoke_train_is_deterministic(features, fc, bundle):
    """Training twice on the fixture gives the same settings, calibration and predictions."""
    again = fm.train(features, fc, log=lambda *_: None)
    assert again["chosen"] == bundle["chosen"]
    assert again["calibration"] == bundle["calibration"]
    pd.testing.assert_frame_equal(again["validation"], bundle["validation"])
    test = fm.splits(features, fc)["test"]
    p1, p2 = fm.predict_all(bundle, test, fc), fm.predict_all(again, test, fc)
    for m in fm.MODELS:
        for q in fc["quantiles"]:
            np.testing.assert_array_equal(p1[m][q], p2[m][q])
            assert np.all(np.isfinite(p1[m][q])) and np.all(p1[m][q] > 0)
        assert np.all(p1[m][0.9] >= p1[m][0.5])


def test_smoke_evaluate_renders(features, fc, bundle):
    results, pred = fm.evaluate(bundle, features, fc)
    assert set(pred["eval_split"]) == {"validation", "test"}
    assert len(pred) == len(fm.MODELS) * (9 + 2)
    assert set(pred.columns) == {"event_id", "event_year", "eval_split", "model", "p50_hours", "p90_hours", "model_version"}
    assert results["test"]["overall"]["hgb"]["n"] == 2
    text = fm.render(results, fc)
    assert "## 2025 test results" in text and "Permutation importance" in text


def test_test_year_never_used_in_training_tuning_or_calibration(bundle, fc):
    """The years each fit and the calibration saw, as recorded by the run."""
    test_years = set(fc["test_years"])
    assert set(bundle["audit"]) == {"baseline_tune", "tune", "calibration", "retrain", "baseline_retrain"}
    for step, years in bundle["audit"].items():
        assert not set(years) & test_years, f"{step} used {years}"
    assert bundle["audit"]["tune"] == [2022]
    assert bundle["audit"]["calibration"] == [2024]
    assert bundle["audit"]["retrain"] == [2022, 2024]
    assert not set(bundle["baseline_train"].index) or len(bundle["baseline_train"]) == 12


def test_test_year_targets_change_nothing_learned(features, fc, bundle):
    """Scrambling every test-year target leaves settings, calibration, models and predictions unchanged."""
    changed = features.copy()
    test = changed["event_year"].isin(fc["test_years"])
    changed.loc[test, fm.TARGET] = changed.loc[test, fm.TARGET] * 1000 + 7
    other = fm.train(changed, fc, log=lambda *_: None)
    assert other["chosen"] == bundle["chosen"]
    assert other["calibration"] == bundle["calibration"]
    pd.testing.assert_frame_equal(other["validation"], bundle["validation"])
    rows = fm.splits(features, fc)["test"]
    p1, p2 = fm.predict_all(bundle, rows, fc), fm.predict_all(other, rows, fc)
    for m in fm.MODELS:
        np.testing.assert_array_equal(p1[m][0.5], p2[m][0.5])
        np.testing.assert_array_equal(p1[m][0.9], p2[m][0.9])


def test_guard_stops_a_test_year(features, fc):
    with pytest.raises(fm.LeakageError):
        fm.guard(features, fc, "tune", {})
    s = fm.splits(features, fc)
    with pytest.raises(fm.LeakageError):
        fm.fit_learned("hgb", pd.concat([s["final"], s["test"]]), 0.5,
                       {"learning_rate": 0.1, "max_leaf_nodes": 3, "min_samples_leaf": 1}, fc["model"],
                       fm.categories_of(s["final"]), fc, {}, "retrain")


def test_conformal_offset():
    """The ceil((n+1) x 0.9)-th smallest log ratio: with 9 residuals, the 9th (largest)."""
    y = np.exp(np.arange(1, 10, dtype=float))
    assert fm.conformal_offset(y, np.ones(9), 0.9) == pytest.approx(9.0)
    assert fm.conformal_offset(np.exp(np.arange(1, 20, dtype=float)), np.ones(19), 0.9) == pytest.approx(18.0)


def test_no_feature_grows_with_history_length():
    """Counts that grow with years of history are not model inputs (D72)."""
    assert not set(fm.LEFT_OUT) & set(fm.hgb_columns(True) + fm.LINEAR_NUMERIC + fm.LINEAR_CATEGORICAL)
    assert not set(fm.STORM) & set(fm.hgb_columns(False))
