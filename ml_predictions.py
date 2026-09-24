# ─────────────────────────────────────────────
#  ml_predictions.py — ML Price Predictions
#  Walk-forward validated, calibrated, cached.
# ─────────────────────────────────────────────

import time

import pandas as pd
import numpy as np
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import make_pipeline
from sklearn.calibration import CalibratedClassifierCV
from sklearn.model_selection import TimeSeriesSplit
from sklearn.metrics import accuracy_score
from prices import get_historical_data
from indicators import calculate_all

# Trained-model cache: {symbol: (fetched_at, result_dict)}.
# Daily bars only change once a day, so retraining more often than
# hourly buys nothing.
_model_cache: dict = {}
MODEL_CACHE_SECS = 3600

PREDICT_HORIZON_DAYS = 10   # target: >5% gain within this many trading days
TARGET_GAIN = 0.05
WALK_FORWARD_FOLDS = 5


def build_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Build feature matrix from technical indicators.
    Features: RSI, MACD, volume, MA spreads, momentum, volatility,
    gaps, distance from 52-week high, Bollinger position.
    """
    df = df.copy()

    # Price momentum features
    df["return_1d"]  = df["close"].pct_change(1)
    df["return_5d"]  = df["close"].pct_change(5)
    df["return_10d"] = df["close"].pct_change(10)
    df["return_20d"] = df["close"].pct_change(20)

    # MA spread features
    df["price_vs_ma20"]  = (df["close"] - df["ma20"]) / df["ma20"]
    df["price_vs_ma50"]  = (df["close"] - df["ma50"]) / df["ma50"]
    df["ma20_vs_ma50"]   = (df["ma20"] - df["ma50"]) / df["ma50"]

    # Volatility
    df["volatility_10d"] = df["return_1d"].rolling(10).std()
    df["atr_pct"]        = df["atr"] / df["close"]

    # ATR-normalized daily move (how unusual was today's move?)
    df["move_vs_atr"] = df["return_1d"] / df["atr_pct"]

    # Overnight gap (open vs prior close)
    df["gap_1d"] = df["open"] / df["close"].shift(1) - 1

    # Distance from 52-week high (0 = at the high)
    high_52w = df["close"].rolling(252, min_periods=60).max()
    df["dist_52w_high"] = df["close"] / high_52w - 1

    # Position inside the Bollinger channel (0 = lower band, 1 = upper)
    bb_span = df["bb_upper"] - df["bb_lower"]
    df["bb_pos"] = (df["close"] - df["bb_lower"]) / bb_span.where(bb_span > 0)

    # Volume z-score vs 20-day norm
    vol_std = df["volume"].rolling(20).std()
    df["vol_z"] = (df["volume"] - df["vol_ma20"]) / vol_std.where(vol_std > 0)

    # Target: will price be >5% higher in PREDICT_HORIZON_DAYS days?
    df["future_return"] = df["close"].shift(-PREDICT_HORIZON_DAYS) / df["close"] - 1
    df["target"] = (df["future_return"] > TARGET_GAIN).astype(int)

    return df


FEATURE_COLS = [
    "rsi", "macd_hist", "vol_ratio",
    "return_1d", "return_5d", "return_10d", "return_20d",
    "price_vs_ma20", "price_vs_ma50", "ma20_vs_ma50",
    "volatility_10d", "stoch_k",
    "atr_pct", "move_vs_atr", "gap_1d",
    "dist_52w_high", "bb_pos", "vol_z",
]


def _make_estimator():
    return make_pipeline(
        StandardScaler(),
        GradientBoostingClassifier(n_estimators=100, max_depth=3, random_state=42),
    )


def _walk_forward_eval(X: np.ndarray, y: np.ndarray) -> dict:
    """
    Expanding-window walk-forward validation with an embargo.

    TimeSeriesSplit alone is NOT sufficient here. The label at row i is built
    from close[i + PREDICT_HORIZON_DAYS], so the final PREDICT_HORIZON_DAYS
    rows of each training fold carry labels computed from prices that fall
    inside the test window. Splitting on row index alone leaked 10 rows at
    every fold boundary and biased the reported accuracy upward.

    Dropping the last PREDICT_HORIZON_DAYS training rows before each fold
    ("purging"/embargo) makes the claim honest: no training label depends on
    a price the test window has not yet reached.
    """
    tscv = TimeSeriesSplit(n_splits=WALK_FORWARD_FOLDS)
    fold_accs, test_labels = [], []
    for train_idx, test_idx in tscv.split(X):
        # Embargo: discard training rows whose outcome overlaps the test slice
        train_idx = train_idx[train_idx < test_idx[0] - PREDICT_HORIZON_DAYS]
        if len(train_idx) < 50 or len(np.unique(y[train_idx])) < 2:
            continue  # fold too short or too one-sided to train on
        model = _make_estimator()
        model.fit(X[train_idx], y[train_idx])
        preds = model.predict(X[test_idx])
        fold_accs.append(accuracy_score(y[test_idx], preds))
        test_labels.append(y[test_idx])

    if not fold_accs:
        return {"mean": None, "folds": [], "baseline": None}

    all_labels = np.concatenate(test_labels)
    majority_share = max(all_labels.mean(), 1 - all_labels.mean())
    return {
        "mean":     round(float(np.mean(fold_accs)) * 100, 1),
        "folds":    [round(a * 100, 1) for a in fold_accs],
        "baseline": round(float(majority_share) * 100, 1),
    }


def train_model(symbol: str) -> dict:
    """
    Train a calibrated gradient-boosting classifier on 2y of history.
    Accuracy is measured by walk-forward validation (train on past,
    test on future) rather than a single random split.
    """
    df = get_historical_data(symbol, period="2y")
    if df.empty or len(df) < 100:
        return {"error": "Not enough data to train model"}

    df = calculate_all(df)
    df = build_features(df)

    available_features = [c for c in FEATURE_COLS if c in df.columns]

    # Rows usable for training need features AND a known future outcome
    train_df = df.dropna(subset=available_features + ["target", "future_return"])
    if len(train_df) < 150:
        return {"error": "Not enough clean data after feature engineering"}

    X = train_df[available_features].values
    y = train_df["target"].values

    # Guard against infinities: a division by a near-zero ATR or volume
    # std can produce inf, which dropna() does not catch and sklearn rejects.
    finite = np.isfinite(X).all(axis=1)
    if finite.sum() < 150:
        return {"error": "Not enough finite feature rows (check for zero ATR or volume)"}
    X, y = X[finite], y[finite]
    if len(np.unique(y)) < 2:
        return {"error": "Target has a single class in this period (price moves were one-sided) — cannot train"}

    wf = _walk_forward_eval(X, y)
    if wf["mean"] is None:
        return {"error": "Walk-forward validation failed — target too imbalanced"}

    # Final model on all labeled data, with calibrated probabilities.
    # Sigmoid (Platt) calibration is the right choice at this sample size.
    calibrated = CalibratedClassifierCV(
        _make_estimator(), method="sigmoid", cv=TimeSeriesSplit(n_splits=3)
    )
    calibrated.fit(X, y)

    # Feature importances from an uncalibrated fit (calibration hides them)
    plain = _make_estimator()
    plain.fit(X, y)
    gbm = plain.named_steps["gradientboostingclassifier"]
    importances = dict(sorted(
        zip(available_features, gbm.feature_importances_),
        key=lambda x: x[1], reverse=True,
    ))

    # Latest feature row for prediction — features only, so the last
    # trading day is used (target columns are NaN there by construction)
    feat_df = df.dropna(subset=available_features)
    feat_df = feat_df[np.isfinite(feat_df[available_features].to_numpy()).all(axis=1)]
    if feat_df.empty:
        return {"error": "Latest bar has non-finite features — cannot predict"}
    latest_row  = feat_df[available_features].iloc[-1:].values
    latest_date = feat_df.index[-1].date()

    return {
        "model":            calibrated,
        "features":         available_features,
        "accuracy":         wf["mean"],
        "fold_accuracies":  wf["folds"],
        "baseline":         wf["baseline"],
        "importances":      importances,
        "train_size":       len(train_df),
        "latest_row":       latest_row,
        "latest_date":      latest_date,
    }


def predict_direction(symbol: str) -> dict:
    """
    Predict whether the stock will gain >5% in the next 10 trading days.
    Returns direction, calibrated probabilities, walk-forward accuracy,
    and key driving features. Trained models are cached for an hour.
    """
    symbol = (symbol or "").strip().upper()
    cached = _model_cache.get(symbol)
    if cached and time.time() - cached[0] < MODEL_CACHE_SECS:
        # Copy: callers used to receive the cached dict itself, so mutating a
        # result poisoned the cache for every later reader within the hour.
        return dict(cached[1])

    result = train_model(symbol)
    if "error" in result:
        return result

    model = result["model"]
    proba = model.predict_proba(result["latest_row"])[0]
    up_idx = list(model.classes_).index(1)
    prob_up = float(proba[up_idx])

    direction  = "BULLISH" if prob_up >= 0.5 else "BEARISH"
    confidence = round(max(prob_up, 1 - prob_up) * 100, 1)

    top_features = list(result["importances"].keys())[:3]

    output = {
        "symbol":           symbol,
        "direction":        direction,
        "confidence":       confidence,
        "probability_up":   round(prob_up * 100, 1),
        "probability_down": round((1 - prob_up) * 100, 1),
        "model_accuracy":   result["accuracy"],
        "baseline_accuracy": result["baseline"],
        "fold_accuracies":  result["fold_accuracies"],
        "top_factors":      top_features,
        "horizon":          f"{PREDICT_HORIZON_DAYS} days",
        "as_of":            str(result["latest_date"]),
        "note": (
            f"Walk-forward accuracy {result['accuracy']}% over "
            f"{len(result['fold_accuracies'])} folds (always-guess-majority baseline: "
            f"{result['baseline']}%) on {result['train_size']} days of history. "
            f"Probabilities are calibrated. Data as of {result['latest_date']}."
        ),
    }

    _model_cache[symbol] = (time.time(), output)
    # Copy on the way out too, not just on cache hits: returning `output`
    # itself hands the caller the cached object, so the very first caller
    # could poison the entry for everyone else within the TTL.
    return dict(output)


def predict_multiple(symbols: list) -> list:
    """Run ML predictions for multiple symbols."""
    results = []
    for sym in symbols:
        r = predict_direction(sym)
        if "error" not in r:
            results.append(r)
    results.sort(key=lambda x: x["probability_up"], reverse=True)
    return results
