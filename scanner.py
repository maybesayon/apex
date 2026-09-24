# ─────────────────────────────────────────────
#  scanner.py — Opportunity Scanner
# ─────────────────────────────────────────────

import pandas as pd
import numpy as np
from prices import get_live_quote, get_historical_data, get_company_profile
from indicators import calculate_all, get_signal_summary, calculate_stop_and_target, estimate_hold_horizon
from config import SCAN_UNIVERSE, DEFAULT_STOP_LOSS_PCT, DEFAULT_TARGET_PCT
from tradingview import get_tv_rating
import time


def score_opportunity(symbol: str) -> dict | None:
    """
    Analyze a single stock and return an opportunity score dict.
    Returns None if data unavailable or score too low.
    """
    try:
        # Get historical data
        df = get_historical_data(symbol, period="3mo")
        if df.empty or len(df) < 20:
            return None

        # Calculate indicators
        df = calculate_all(df)
        sig = get_signal_summary(df)
        if not sig:
            return None

        # Get live quote. A zero/missing price used to sail through and produce
        # a confident-looking result with a negative stop and "+inf–inf%"
        # estimated move — which alerts.py would then email as a trade idea.
        quote = get_live_quote(symbol)
        if not quote:
            return None
        price = quote.get("price")
        if price is None or pd.isna(price) or price <= 0:
            print(f"Scanner: {symbol} has no usable price ({price}) — skipping")
            return None

        # Get company info
        profile = get_company_profile(symbol)

        atr   = df["atr"].iloc[-1] if "atr" in df.columns else None
        exits = calculate_stop_and_target(price, atr, DEFAULT_STOP_LOSS_PCT, DEFAULT_TARGET_PCT)
        hold  = estimate_hold_horizon(df, price, exits["target"], atr)

        # Build signal tags
        tags = []
        signals = sig.get("signals", {})
        if signals.get("volume", {}).get("score", 0) >= 4:
            tags.append("Unusual Volume")
        if signals.get("rsi", {}).get("score", 0) >= 4:
            tags.append("Oversold Bounce")
        if signals.get("macd", {}).get("score", 0) >= 4:
            tags.append("MACD Bullish")
        if signals.get("ma", {}).get("score", 0) >= 4:
            tags.append("Above Key MAs")
        if quote["pct_change"] > 3:
            tags.append("Strong Momentum")
        if exits["risk_reward"] >= 2:
            tags.append(f"R/R {exits['risk_reward']}:1")

        # TradingView technical rating (display only — doesn't affect the score)
        tv = get_tv_rating(symbol)
        if tv and "BUY" in tv["recommendation"]:
            tags.append(f"TV {tv['recommendation'].replace('_', ' ').title()}")

        overall = sig["overall_score"]

        # Determine confidence level
        if overall >= 75:
            confidence = "HIGH"
        elif overall >= 55:
            confidence = "MEDIUM"
        else:
            confidence = "LOW"

        # Estimate move potential based on ATR
        if atr:
            est_move_low  = round((atr * 3 / price) * 100, 1)
            est_move_high = round((atr * 6 / price) * 100, 1)
            est_move = f"+{est_move_low}–{est_move_high}%"
        else:
            est_move = "+10–20%"

        return {
            "symbol":       symbol,
            "name":         profile.get("name", symbol),
            "industry":     profile.get("industry", "N/A"),
            "price":        price,
            "change":       quote["change"],
            "pct_change":   quote["pct_change"],
            "score":        overall,
            "confidence":   confidence,
            "est_move":     est_move,
            "horizon":      hold["label"],
            "hold_days_low":  hold["days_low"],
            "hold_days_high": hold["days_high"],
            "entry":        exits["entry"],
            "target":       exits["target"],
            "stop":         exits["stop"],
            "risk_reward":  exits["risk_reward"],
            "tags":         tags[:4],
            "signals":      signals,
            "rsi":          round(df["rsi"].iloc[-1], 1) if "rsi" in df.columns else None,
            "macd_hist":    round(df["macd_hist"].iloc[-1], 4) if "macd_hist" in df.columns else None,
            "vol_ratio":    round(df["vol_ratio"].iloc[-1], 2) if "vol_ratio" in df.columns else None,
            "atr":          round(atr, 2) if atr else None,
            "tv_rating":    tv["recommendation"] if tv else None,
        }

    except Exception as e:
        print(f"Scanner error for {symbol}: {e}")
        return None


def run_full_scan(symbols: list = None, min_score: int = 50) -> list:
    """
    Scan all symbols and return sorted list of opportunities.
    Filters to min_score and sorts by score descending.
    """
    if symbols is None:
        symbols = SCAN_UNIVERSE

    results = []
    for sym in symbols:
        print(f"  Scanning {sym}...")
        result = score_opportunity(sym)
        if result and result["score"] >= min_score:
            results.append(result)
        time.sleep(0.3)  # Rate limit protection

    # Sort by score descending
    results.sort(key=lambda x: x["score"], reverse=True)
    return results


def run_broad_scan(min_score: int = 50, top_n: int = None) -> list:
    """
    Scan the S&P 500 (plus the personal universe): a cheap batched
    pre-filter picks the top_n most active names, then each gets the
    full TA scoring pass.
    """
    from universe import get_broad_universe
    from config import BROAD_SCAN_TOP_N

    candidates = get_broad_universe(top_n=top_n or BROAD_SCAN_TOP_N)
    print(f"Broad scan: {len(candidates)} candidates after pre-filter")
    return run_full_scan(candidates, min_score=min_score)


def get_top_picks(n: int = 5) -> list:
    """Run scan and return top N picks."""
    all_results = run_full_scan()
    return all_results[:n]
