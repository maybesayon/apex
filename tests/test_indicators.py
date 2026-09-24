"""
Technical indicator correctness.

Golden snapshots pin the exact numbers the analysis engine produces today.
If the Next.js migration changes any of them, these fail — which is the
entire reason this file exists.
"""

import numpy as np
import pandas as pd
import pytest

from conftest import assert_golden
from indicators import (
    calculate_all,
    calculate_stop_and_target,
    estimate_hold_horizon,
    get_signal_summary,
    get_support_resistance,
)

EXPECTED_COLUMNS = [
    "ma20", "ma50", "ma200", "ema9", "ema21", "rsi", "macd", "macd_signal",
    "macd_hist", "bb_upper", "bb_lower", "bb_mid", "atr", "vol_ma20",
    "vol_ratio", "unusual_volume", "stoch_k", "stoch_d",
]


# ── Golden snapshots ──────────────────────────────────────────────────────────

def test_indicators_golden_aapl(aapl):
    d = calculate_all(aapl)
    tail = d[["rsi", "macd", "macd_signal", "macd_hist", "ma20", "ma50",
              "bb_upper", "bb_lower", "atr", "stoch_k"]].tail(5)
    assert_golden("indicators_aapl", tail.to_dict(orient="list"))


def test_signal_summary_golden_aapl(aapl):
    assert_golden("signals_aapl", get_signal_summary(calculate_all(aapl)))


def test_signal_summary_golden_nvda(nvda):
    assert_golden("signals_nvda", get_signal_summary(calculate_all(nvda)))


def test_support_resistance_golden(aapl):
    assert_golden("support_resistance_aapl", get_support_resistance(aapl))


def test_hold_horizon_golden(aapl):
    d = calculate_all(aapl)
    price = float(d["close"].iloc[-1])
    atr = float(d["atr"].iloc[-1])
    exits = calculate_stop_and_target(price, atr)
    assert_golden("hold_horizon_aapl",
                  estimate_hold_horizon(d, price, exits["target"], atr))


# ── Structural invariants ─────────────────────────────────────────────────────

def test_all_columns_present(aapl):
    d = calculate_all(aapl)
    missing = [c for c in EXPECTED_COLUMNS if c not in d.columns]
    assert not missing, f"missing indicator columns: {missing}"


def test_bounded_oscillators(aapl):
    d = calculate_all(aapl)
    assert d["rsi"].dropna().between(0, 100).all()
    assert d["stoch_k"].dropna().between(0, 100).all()
    assert d["stoch_d"].dropna().between(0, 100).all()


def test_bollinger_ordering(aapl):
    d = calculate_all(aapl).dropna(subset=["bb_upper", "bb_lower", "bb_mid"])
    assert (d["bb_upper"] >= d["bb_mid"]).all()
    assert (d["bb_mid"] >= d["bb_lower"]).all()


def test_atr_non_negative(aapl):
    assert (calculate_all(aapl)["atr"].dropna() >= 0).all()


def test_macd_histogram_identity(aapl):
    """hist == macd - signal, within the 4dp rounding each is stored at."""
    d = calculate_all(aapl)
    resid = (d["macd"] - d["macd_signal"] - d["macd_hist"]).dropna().abs().max()
    assert resid <= 2e-4, f"MACD identity broken (max residual {resid})"


def test_too_short_returns_input_unchanged():
    tiny = pd.DataFrame({"open": [1.0] * 5, "high": [1.0] * 5, "low": [1.0] * 5,
                         "close": [1.0] * 5, "volume": [1.0] * 5})
    assert list(calculate_all(tiny).columns) == list(tiny.columns)


# ── Regression tests for bugs found in QA ─────────────────────────────────────

def test_flat_series_produces_no_infinities(flat):
    """Regression: constant price divided by a zero-width Bollinger band."""
    d = calculate_all(flat)
    assert not np.isinf(d.select_dtypes("number").to_numpy()).any()
    sig = get_signal_summary(d)
    assert sig["signals"]["bb"]["value"] is not None
    assert not pd.isna(sig["signals"]["bb"]["value"])


def test_penny_stock_atr_is_not_zero(penny):
    """
    Regression: ATR rounded to 2dp made every sub-$0.20 bar 0.00, which
    produced inf downstream and crashed model training.

    The first ~13 bars are legitimately 0.0 — that is `ta`'s warm-up
    seeding, not the rounding bug — so this asserts on settled values only.
    """
    atr = calculate_all(penny)["atr"].dropna().iloc[20:]
    assert (atr > 0).all(), "zero ATR after warm-up will produce infinities"
    assert atr.min() < 0.01, "fixture is not actually a penny stock"


def test_warmup_indicator_is_not_scored_bearish(short_rising):
    """
    Regression: NaN fails every comparison and fell through to the most
    bearish branch, so a rising 25-bar series was 'Bearish but improving'.
    """
    sig = get_signal_summary(calculate_all(short_rising))
    macd = sig["signals"]["macd"]
    assert "Bearish" not in macd["label"], f"warm-up scored as {macd['label']}"
    assert macd["score"] == 3


@pytest.mark.parametrize("rsi_value,forbidden", [(63.0, "Oversold"), (25.0, "Overbought")])
def test_rsi_bands_are_not_inverted(aapl, rsi_value, forbidden):
    """Regression: RSI 60-70 was labelled 'Oversold', the exact opposite."""
    d = calculate_all(aapl)
    d.loc[d.index[-1], "rsi"] = rsi_value
    label = get_signal_summary(d)["signals"]["rsi"]["label"]
    assert forbidden.lower() not in label.lower(), f"RSI {rsi_value} -> '{label}'"


# ── Stop / target ─────────────────────────────────────────────────────────────

def test_risk_reward_varies_with_volatility():
    """
    Regression: the ATR branch hardcoded stop=p-2a, target=p+4a, so R/R was
    exactly 2.0 for every stock and the configured percentages were ignored.
    """
    ratios = {calculate_stop_and_target(100.0, a, 0.17, 0.25)["risk_reward"]
              for a in (0.1, 1, 5, 20, 49)}
    assert len(ratios) > 1, f"risk/reward is constant across volatility: {ratios}"


@pytest.mark.parametrize("atr", [0.5, 5, 20, 60, 200])
def test_stop_never_negative(atr):
    """Regression: 2*atr > price produced a negative stop price."""
    r = calculate_stop_and_target(100.0, atr)
    assert r["stop"] > 0, f"atr={atr} gave stop {r['stop']}"
    assert r["target"] > 100.0


def test_configured_percentages_bound_the_stop():
    r = calculate_stop_and_target(100.0, 50.0, stop_pct=0.10, target_pct=0.25)
    assert r["stop"] >= 90.0, "stop travelled past the configured 10% cap"


@pytest.mark.parametrize("price", [0, None, float("nan")])
def test_invalid_price_returns_empty_levels(price):
    r = calculate_stop_and_target(price, 1.0)
    assert r["risk_reward"] == 0 and r["stop"] is None


def test_stop_target_without_atr_uses_percentages():
    r = calculate_stop_and_target(100.0, None, stop_pct=0.20, target_pct=0.30)
    assert r["stop"] == 80.0 and r["target"] == 130.0
