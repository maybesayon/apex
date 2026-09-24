# ─────────────────────────────────────────────
#  indicators.py — Technical Analysis Engine
# ─────────────────────────────────────────────

import pandas as pd
import numpy as np
import ta


def calculate_all(df: pd.DataFrame) -> pd.DataFrame:
    """
    Calculate all technical indicators on an OHLCV dataframe.
    Adds RSI, MACD, Bollinger Bands, moving averages, ATR, volume signals.
    """
    if df.empty or len(df) < 20:
        return df

    df = df.copy()

    # ── Moving Averages ───────────────────────
    df["ma20"]  = df["close"].rolling(20).mean().round(2)
    df["ma50"]  = df["close"].rolling(50).mean().round(2)
    df["ma200"] = df["close"].rolling(200).mean().round(2)
    df["ema9"]  = df["close"].ewm(span=9).mean().round(2)
    df["ema21"] = df["close"].ewm(span=21).mean().round(2)

    # ── RSI ───────────────────────────────────
    df["rsi"] = ta.momentum.RSIIndicator(df["close"], window=14).rsi().round(2)

    # ── MACD ──────────────────────────────────
    macd_obj     = ta.trend.MACD(df["close"])
    df["macd"]   = macd_obj.macd().round(4)
    df["macd_signal"] = macd_obj.macd_signal().round(4)
    df["macd_hist"]   = macd_obj.macd_diff().round(4)

    # ── Bollinger Bands ───────────────────────
    bb           = ta.volatility.BollingerBands(df["close"])
    df["bb_upper"] = bb.bollinger_hband().round(2)
    df["bb_lower"] = bb.bollinger_lband().round(2)
    df["bb_mid"]   = bb.bollinger_mavg().round(2)

    # ── ATR (Average True Range) ──────────────
    # Deliberately NOT rounded to 2dp: for a sub-$0.20 stock every bar would
    # round to 0.00, and downstream code divides by ATR (atr_pct, move_vs_atr),
    # producing infinities that crash model training.
    df["atr"] = ta.volatility.AverageTrueRange(
        df["high"], df["low"], df["close"]
    ).average_true_range().round(6)

    # ── Volume Signal ─────────────────────────
    df["vol_ma20"]       = df["volume"].rolling(20).mean()
    df["vol_ratio"]      = (df["volume"] / df["vol_ma20"]).round(2)
    df["unusual_volume"] = df["vol_ratio"] > 2.0   # 2x average = unusual

    # ── Stochastic ────────────────────────────
    stoch        = ta.momentum.StochasticOscillator(df["high"], df["low"], df["close"])
    df["stoch_k"] = stoch.stoch().round(2)
    df["stoch_d"] = stoch.stoch_signal().round(2)

    return df


def get_signal_summary(df: pd.DataFrame) -> dict:
    """
    Analyze the latest row of indicators and return a signal summary.
    Returns dict with individual signal scores and overall score (0-100).
    """
    if df.empty:
        return {}

    latest = df.iloc[-1]
    prev   = df.iloc[-2] if len(df) > 1 else latest
    signals = {}

    def _num(row, col, default):
        """
        `.get(col, default)` only defaults when the COLUMN is missing, not
        when the value is NaN — and NaN fails every comparison, so a warm-up
        NaN silently fell through to the most bearish branch. A rising series
        with fewer than ~34 bars was being scored "Bearish but improving".
        """
        v = row.get(col, default)
        try:
            return default if v is None or pd.isna(v) else float(v)
        except (TypeError, ValueError):
            return default

    # ── RSI Signal ────────────────────────────
    rsi = _num(latest, "rsi", 50)
    if rsi < 30:
        signals["rsi"] = {"score": 5, "label": "Oversold — strong buy zone", "value": rsi}
    elif rsi < 45:
        signals["rsi"] = {"score": 4, "label": "Bullish territory", "value": rsi}
    elif rsi < 55:
        signals["rsi"] = {"score": 3, "label": "Neutral", "value": rsi}
    elif rsi < 70:
        signals["rsi"] = {"score": 2, "label": "Getting extended", "value": rsi}
    else:
        signals["rsi"] = {"score": 1, "label": "Overbought — caution", "value": rsi}

    # ── MACD Signal ───────────────────────────
    # An indicator still in its warm-up period is unknown, not bearish. It
    # scores a neutral 3 so a 25-bar series is not reported as "Bearish".
    _mh, _ph = latest.get("macd_hist"), prev.get("macd_hist")
    if _mh is None or pd.isna(_mh) or _ph is None or pd.isna(_ph):
        signals["macd"] = {"score": 3, "label": "Insufficient data", "value": None}
        macd_hist = prev_hist = None
    else:
        macd_hist, prev_hist = float(_mh), float(_ph)

    if macd_hist is None:
        pass
    elif macd_hist > 0 and macd_hist > prev_hist:
        signals["macd"] = {"score": 5, "label": "Bullish & strengthening", "value": round(macd_hist, 4)}
    elif macd_hist > 0:
        signals["macd"] = {"score": 3, "label": "Bullish but weakening", "value": round(macd_hist, 4)}
    elif macd_hist < 0 and macd_hist < prev_hist:
        signals["macd"] = {"score": 1, "label": "Bearish & strengthening", "value": round(macd_hist, 4)}
    else:
        signals["macd"] = {"score": 2, "label": "Bearish but improving", "value": round(macd_hist, 4)}

    # ── Moving Average Signal ─────────────────
    price = latest["close"]
    ma50  = latest.get("ma50")
    ma200 = latest.get("ma200")
    if pd.notna(ma50) and pd.notna(ma200):
        if price > ma50 > ma200:
            signals["ma"] = {"score": 5, "label": "Price above 50 & 200 MA — bullish", "value": f">${ma50:.2f}"}
        elif price > ma50:
            signals["ma"] = {"score": 4, "label": "Above 50MA", "value": f">${ma50:.2f}"}
        elif price > ma200:
            signals["ma"] = {"score": 3, "label": "Above 200MA only", "value": f">${ma200:.2f}"}
        else:
            signals["ma"] = {"score": 1, "label": "Below both MAs — bearish", "value": f"<${ma50:.2f}"}
    else:
        signals["ma"] = {"score": 3, "label": "Insufficient data", "value": "N/A"}

    # ── Volume Signal ─────────────────────────
    vol_ratio = _num(latest, "vol_ratio", 1)
    if vol_ratio > 3:
        signals["volume"] = {"score": 5, "label": f"Massive volume — {vol_ratio:.1f}x average", "value": vol_ratio}
    elif vol_ratio > 2:
        signals["volume"] = {"score": 4, "label": f"Unusual volume — {vol_ratio:.1f}x average", "value": vol_ratio}
    elif vol_ratio > 1.3:
        signals["volume"] = {"score": 3, "label": f"Above average volume", "value": vol_ratio}
    else:
        signals["volume"] = {"score": 2, "label": "Normal volume", "value": vol_ratio}

    # ── Bollinger Band Signal ─────────────────
    bb_upper = latest.get("bb_upper")
    bb_lower = latest.get("bb_lower")
    bb_mid   = latest.get("bb_mid")
    # A flat price series collapses the bands onto each other; dividing by
    # that zero width produced NaN and a bogus "Mid-range" reading.
    if pd.notna(bb_upper) and pd.notna(bb_lower) and (bb_upper - bb_lower) > 0:
        bb_pct = (price - bb_lower) / (bb_upper - bb_lower) * 100
        if bb_pct < 20:
            signals["bb"] = {"score": 5, "label": "Near lower band — bounce opportunity", "value": round(bb_pct, 1)}
        elif bb_pct > 80:
            signals["bb"] = {"score": 2, "label": "Near upper band — extended", "value": round(bb_pct, 1)}
        else:
            signals["bb"] = {"score": 3, "label": "Mid-range", "value": round(bb_pct, 1)}
    else:
        signals["bb"] = {"score": 3, "label": "N/A", "value": 50}

    # ── Overall Score ─────────────────────────
    scores = [s["score"] for s in signals.values()]
    avg_score = sum(scores) / len(scores) if scores else 0
    overall = round((avg_score / 5) * 100)

    return {
        "signals":      signals,
        "overall_score": overall,
        "signal_count":  len(signals),
    }


def get_support_resistance(df: pd.DataFrame, window: int = 20) -> dict:
    """Calculate recent support and resistance levels."""
    if df.empty:
        return {}
    recent = df.tail(window)
    return {
        "support":    round(recent["low"].min(), 2),
        "resistance": round(recent["high"].max(), 2),
        "avg_price":  round(recent["close"].mean(), 2),
    }


def estimate_hold_horizon(df: pd.DataFrame, price: float, target: float, atr: float = None) -> dict:
    """
    Estimate how long a trade needs for price to reach the target.
    Pace = recent 20-day trend drift ($/day) plus a fraction of ATR —
    price random-walks, so net daily progress is well below a full ATR.
    Returns trading-day range and a display label (e.g. "~3–6 weeks").
    """
    distance = target - price
    if distance <= 0:
        return {"days_low": 0, "days_high": 0, "label": "target reached"}

    drift = 0.0
    if len(df) >= 21:
        drift = float(df["close"].diff().tail(20).mean())
    drift = max(drift, 0.0)

    if not atr or atr <= 0:
        atr = float(df["close"].diff().abs().tail(20).mean() or 0)
    if atr <= 0:
        return {"days_low": None, "days_high": None, "label": "—"}

    fast_pace = drift + 0.35 * atr   # trend continues, good tape
    slow_pace = drift + 0.15 * atr   # choppy tape

    days_low  = max(2, round(distance / fast_pace))
    days_low  = min(days_low, 85)
    days_high = max(days_low + 1, round(distance / slow_pace))
    days_high = min(days_high, 90)

    if days_high <= 15:
        label = f"~{days_low}–{days_high} trading days"
    else:
        weeks_low  = max(1, round(days_low / 5))
        weeks_high = max(weeks_low + 1, round(days_high / 5))
        label = f"~{weeks_low}–{weeks_high} weeks"

    return {"days_low": days_low, "days_high": days_high, "label": label}


def calculate_stop_and_target(price: float, atr: float = None, stop_pct: float = 0.17, target_pct: float = 0.25) -> dict:
    """
    Recommended stop loss and price target.

    The ATR branch used to be `stop = p - 2*atr`, `target = p + 4*atr`, which
    made risk/reward exactly 2.0 for every stock with a non-zero ATR — the
    "R/R 2.0:1" tag was therefore meaningless — and silently discarded the
    configured stop_pct/target_pct. ATR now sizes the distance, while the
    configured percentages cap how far the stop may travel, so the ratio
    varies with actual volatility.
    """
    if not price or price <= 0 or pd.isna(price):
        return {"entry": price, "stop": None, "target": None,
                "risk": None, "reward": None, "risk_reward": 0}

    has_atr = atr is not None and not pd.isna(atr) and atr > 0
    if has_atr:
        # Cap ATR-derived risk at the configured max loss, and never below a
        # floor, so a violently volatile name cannot produce a negative stop.
        max_risk = price * stop_pct
        risk_amt = min(atr * 2, max_risk)
        risk_amt = max(risk_amt, price * 0.01)
        stop     = round(price - risk_amt, 2)
        target   = round(price + max(atr * 4, price * target_pct), 2)
    else:
        stop   = round(price * (1 - stop_pct), 2)
        target = round(price * (1 + target_pct), 2)

    risk   = round(price - stop, 2)
    reward = round(target - price, 2)
    rr     = round(reward / risk, 1) if risk > 0 else 0

    return {
        "entry":        price,
        "stop":         stop,
        "target":       target,
        "risk":         risk,
        "reward":       reward,
        "risk_reward":  rr,
    }
