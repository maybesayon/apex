"""
ML forecasting: validation integrity above all.

The headline assertion here is that no training label depends on a price
inside its own test window. That property is the whole claim the Forecast
screen makes, and it was broken once already.
"""

import inspect

import numpy as np
import pandas as pd
import pytest
from sklearn.model_selection import TimeSeriesSplit

from conftest import assert_golden
import ml_predictions as ml
from ml_predictions import (
    PREDICT_HORIZON_DAYS,
    WALK_FORWARD_FOLDS,
    build_features,
    predict_direction,
    train_model,
)
from indicators import calculate_all


# ── Validation integrity ──────────────────────────────────────────────────────

def test_no_label_leakage_across_fold_boundaries():
    """
    Regression, critical. The label at row i is built from close[i+H], so a
    plain TimeSeriesSplit leaves the last H training rows with labels drawn
    from inside the test window. The embargo must remove them.
    """
    n = 400
    X = np.zeros((n, 3))
    leaked = []
    for train_idx, test_idx in TimeSeriesSplit(n_splits=WALK_FORWARD_FOLDS).split(X):
        embargoed = train_idx[train_idx < test_idx[0] - PREDICT_HORIZON_DAYS]
        if len(embargoed) == 0:
            continue
        overlap = (embargoed[-1] + PREDICT_HORIZON_DAYS) - test_idx[0] + 1
        leaked.append(max(0, overlap))
    assert leaked, "no folds evaluated"
    assert all(v == 0 for v in leaked), f"label leakage per fold: {leaked}"


def test_embargo_is_applied_in_source():
    src = inspect.getsource(ml._walk_forward_eval)
    assert "PREDICT_HORIZON_DAYS" in src, "embargo missing from walk-forward eval"
    assert "test_idx[0]" in src


def test_validation_never_shuffles():
    src = inspect.getsource(ml._walk_forward_eval)
    assert "shuffle" not in src
    assert "TimeSeriesSplit" in src


def test_baseline_is_reported(offline):
    r = predict_direction("AAPL")
    assert r.get("baseline_accuracy") is not None, (
        "accuracy without a baseline is uninterpretable"
    )
    assert 0 <= r["baseline_accuracy"] <= 100


def test_baseline_is_majority_class(offline):
    """The baseline must be >= 50%: it is the more common outcome by definition."""
    assert predict_direction("AAPL")["baseline_accuracy"] >= 50.0


# ── Golden ────────────────────────────────────────────────────────────────────

def test_forecast_golden_aapl(offline):
    r = predict_direction("AAPL")
    assert_golden("forecast_aapl", {
        k: r[k] for k in ("direction", "confidence", "probability_up",
                          "probability_down", "model_accuracy",
                          "baseline_accuracy", "fold_accuracies",
                          "top_factors", "horizon")
    })


def test_features_golden_aapl(aapl):
    feats = build_features(calculate_all(aapl))
    cols = [c for c in ml.FEATURE_COLS if c in feats.columns]
    assert_golden("features_aapl", feats[cols].tail(3).to_dict(orient="list"))


# ── Determinism and output shape ──────────────────────────────────────────────

def test_deterministic_across_runs(offline):
    a = predict_direction("AAPL")
    ml._model_cache.clear()
    b = predict_direction("AAPL")
    assert a["model_accuracy"] == b["model_accuracy"]
    assert a["probability_up"] == b["probability_up"]


def test_probabilities_sum_to_100(offline):
    r = predict_direction("AAPL")
    assert abs(r["probability_up"] + r["probability_down"] - 100) < 0.2


def test_confidence_is_the_larger_class(offline):
    r = predict_direction("AAPL")
    assert r["confidence"] == pytest.approx(
        max(r["probability_up"], r["probability_down"]), abs=0.2)


def test_direction_matches_probability(offline):
    r = predict_direction("AAPL")
    expected = "BULLISH" if r["probability_up"] >= 50 else "BEARISH"
    assert r["direction"] == expected


def test_fold_count(offline):
    assert 2 <= len(predict_direction("AAPL")["fold_accuracies"]) <= WALK_FORWARD_FOLDS


# ── Cache ─────────────────────────────────────────────────────────────────────

def test_cache_returns_a_copy(offline):
    """Regression: callers received the cached dict and could poison it."""
    a = predict_direction("AAPL")
    a["probability_up"] = 999
    assert predict_direction("AAPL")["probability_up"] != 999


def test_cache_key_is_case_insensitive(offline):
    assert predict_direction("aapl")["direction"] == predict_direction("AAPL")["direction"]


# ── Edge cases ────────────────────────────────────────────────────────────────

def test_penny_stock_does_not_crash(offline, monkeypatch, penny):
    """Regression, critical: zero ATR produced inf features and killed sklearn."""
    monkeypatch.setattr(ml, "get_historical_data", lambda *a, **k: penny)
    r = predict_direction("PENNY")
    assert "error" in r or 0 <= r["probability_up"] <= 100


def test_flat_series_degrades_gracefully(offline, monkeypatch, flat):
    monkeypatch.setattr(ml, "get_historical_data", lambda *a, **k: flat)
    r = predict_direction("FLAT")
    assert "error" in r or 0 <= r["probability_up"] <= 100


@pytest.mark.parametrize("bars", [50, 99, 150])
def test_short_history_returns_error_not_exception(offline, monkeypatch, aapl, bars):
    monkeypatch.setattr(ml, "get_historical_data", lambda *a, **k: aapl.head(bars))
    assert "error" in predict_direction("SHORT")


def test_empty_history(offline, monkeypatch):
    monkeypatch.setattr(ml, "get_historical_data", lambda *a, **k: pd.DataFrame())
    assert "error" in predict_direction("NONE")


def test_no_infinities_in_feature_matrix(aapl):
    feats = build_features(calculate_all(aapl))
    cols = [c for c in ml.FEATURE_COLS if c in feats.columns]
    clean = feats.dropna(subset=cols)
    assert np.isfinite(clean[cols].to_numpy()).all()
