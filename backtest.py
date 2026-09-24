# ─────────────────────────────────────────────
#  backtest.py — Strategy Backtesting Engine
# ─────────────────────────────────────────────

import pandas as pd
import numpy as np
from prices import get_historical_data
from indicators import calculate_all
from config import BACKTEST_START_DATE


# Columns the strategy actually reads. Dropping NaNs on only these keeps
# the early history that slow indicators (ma200) would otherwise discard.
REQUIRED_COLS = ["close", "open", "rsi", "macd_hist", "vol_ratio"]


def backtest_momentum_strategy(
    symbol: str,
    initial_capital: float = 1000.0,
    stop_loss_pct: float = 0.17,
    take_profit_pct: float = 0.25,
    rsi_entry: float = 65,
    rsi_exit: float = 70,
    vol_ratio_min: float = 1.2,
    vol_lookback: int = 3,
) -> dict:
    """
    Backtest a simple RSI + MACD momentum strategy.

    Entry:  MACD histogram crosses positive
            AND RSI < rsi_entry (not already overbought — guards against
            chasing a move that has run)
            AND volume ran hot (vol_ratio > vol_ratio_min) at some point
            in the last vol_lookback bars
    Exit:   RSI > rsi_exit OR MACD cross down OR stop loss OR take profit

    Note on rsi_entry: this is an overbought *guard*, not an oversold
    requirement. Demanding RSI < 45 on the bar MACD turns positive is
    self-contradictory (momentum turning up means RSI has already
    recovered), which is why a low value produces zero trades.
    """
    df = get_historical_data(symbol, period="2y")
    if df.empty or len(df) < 50:
        return {"error": "Insufficient historical data"}

    df = calculate_all(df)
    missing = [c for c in REQUIRED_COLS if c not in df.columns]
    if missing:
        return {"error": f"Missing indicator columns: {', '.join(missing)}"}
    df = df.dropna(subset=REQUIRED_COLS)
    if len(df) < 30:
        return {"error": "Not enough clean rows after indicator warm-up"}

    # Volume confirmation over a trailing window (rolling() looks backward,
    # so this never peeks at future bars).
    vol_hot = df["vol_ratio"].rolling(vol_lookback, min_periods=1).max() > vol_ratio_min

    # Diagnostics so a zero-trade run can explain itself
    cross_mask = (df["macd_hist"] > 0) & (df["macd_hist"].shift(1) <= 0)
    rsi_mask   = df["rsi"] < rsi_entry
    diagnostics = {
        "bars":            len(df),
        "macd_crosses":    int(cross_mask.sum()),
        "rsi_ok":          int(rsi_mask.sum()),
        "volume_ok":       int(vol_hot.sum()),
        "all_conditions":  int((cross_mask & rsi_mask & vol_hot).sum()),
    }

    trades      = []
    capital     = initial_capital
    position    = None   # Current open position
    equity_curve = [initial_capital]

    for i in range(1, len(df)):
        row  = df.iloc[i]
        prev = df.iloc[i - 1]
        price = row["close"]
        date  = df.index[i]

        if position is None:
            # ── Entry Logic ───────────────────
            rsi_ok   = row["rsi"] < rsi_entry
            macd_ok  = row["macd_hist"] > 0 and prev["macd_hist"] <= 0
            vol_ok   = bool(vol_hot.iloc[i])

            # Affordability is part of the entry test: opening a zero-share
            # position would otherwise block every later entry.
            can_afford = int(capital / price) >= 1

            if rsi_ok and macd_ok and vol_ok and can_afford:
                shares      = int(capital / price)
                cost        = shares * price
                stop        = round(price * (1 - stop_loss_pct), 2)
                target      = round(price * (1 + take_profit_pct), 2)
                position    = {
                    "entry_date":  date,
                    "entry_price": price,
                    "shares":      shares,
                    "cost":        cost,
                    "stop":        stop,
                    "target":      target,
                }
                capital -= cost

        else:
            # ── Exit Logic ────────────────────
            hit_stop   = price <= position["stop"]
            hit_target = price >= position["target"]
            rsi_exit_  = row["rsi"] > rsi_exit
            macd_exit  = row["macd_hist"] < 0 and prev["macd_hist"] >= 0

            if hit_stop or hit_target or rsi_exit_ or macd_exit:
                proceeds = position["shares"] * price
                pnl      = proceeds - position["cost"]
                pnl_pct  = (pnl / position["cost"]) * 100

                if hit_stop:
                    exit_reason = "Stop Loss"
                elif hit_target:
                    exit_reason = "Take Profit"
                elif rsi_exit_:
                    exit_reason = "RSI Overbought"
                else:
                    exit_reason = "MACD Cross"

                trades.append({
                    "symbol":       symbol,
                    "entry_date":   position["entry_date"].strftime("%Y-%m-%d"),
                    "exit_date":    date.strftime("%Y-%m-%d"),
                    "entry_price":  round(position["entry_price"], 2),
                    "exit_price":   round(price, 2),
                    "shares":       position["shares"],
                    "pnl":          round(pnl, 2),
                    "pnl_pct":      round(pnl_pct, 1),
                    "exit_reason":  exit_reason,
                    "win":          pnl > 0,
                })

                capital  += proceeds
                position  = None

        equity_curve.append(round(capital + (position["shares"] * price if position else 0), 2))

    # Close any position still open at the final bar, so total_pnl (closed
    # trades) and total_return_pct (mark-to-market equity) cannot disagree.
    open_at_end = position is not None
    if position is not None:
        last_price = df.iloc[-1]["close"]
        proceeds   = position["shares"] * last_price
        pnl        = proceeds - position["cost"]
        trades.append({
            "symbol":      symbol,
            "entry_date":  position["entry_date"].strftime("%Y-%m-%d"),
            "exit_date":   df.index[-1].strftime("%Y-%m-%d"),
            "entry_price": round(position["entry_price"], 2),
            "exit_price":  round(last_price, 2),
            "shares":      position["shares"],
            "pnl":         round(pnl, 2),
            "pnl_pct":     round(pnl / position["cost"] * 100, 1),
            "exit_reason": "Open at period end",
            "win":         pnl > 0,
        })
        capital += proceeds
        position = None

    # ── Summary Stats ─────────────────────────
    if not trades:
        d = diagnostics
        if d["macd_crosses"] == 0:
            why = "no MACD bullish crosses occurred in this period"
        elif d["all_conditions"] == 0:
            why = (
                f"{d['macd_crosses']} MACD crosses fired, but none passed the other "
                f"filters (RSI < {rsi_entry} on {d['rsi_ok']}/{d['bars']} bars, "
                f"volume > {vol_ratio_min}x on {d['volume_ok']}/{d['bars']} bars). "
                f"Try raising the RSI entry threshold or lowering the volume filter."
            )
        else:
            why = "entry signals fired but capital was too small to buy a share"
        return {"error": f"No trades executed — {why}", "diagnostics": d}

    wins        = [t for t in trades if t["win"]]
    losses      = [t for t in trades if not t["win"]]
    win_rate    = len(wins) / len(trades) * 100
    avg_win     = np.mean([t["pnl_pct"] for t in wins]) if wins else 0
    avg_loss    = np.mean([t["pnl_pct"] for t in losses]) if losses else 0
    total_pnl   = sum(t["pnl"] for t in trades)
    final_cap   = equity_curve[-1]
    total_return = ((final_cap - initial_capital) / initial_capital) * 100

    # Max drawdown
    peak = initial_capital
    max_dd = 0
    for val in equity_curve:
        if val > peak:
            peak = val
        dd = (peak - val) / peak * 100
        if dd > max_dd:
            max_dd = dd

    return {
        "symbol":           symbol,
        "initial_capital":  initial_capital,
        "final_capital":    round(final_cap, 2),
        "total_return_pct": round(total_return, 1),
        "total_pnl":        round(total_pnl, 2),
        "total_trades":     len(trades),
        "wins":             len(wins),
        "losses":           len(losses),
        "win_rate":         round(win_rate, 1),
        "avg_win_pct":      round(avg_win, 1),
        "avg_loss_pct":     round(avg_loss, 1),
        "max_drawdown_pct": round(max_dd, 1),
        "equity_curve":     equity_curve,
        "trades":           trades,
        "diagnostics":      diagnostics,
        "open_at_end":      open_at_end,
    }


def backtest_multiple(symbols: list, capital: float = 1000.0) -> list:
    """Run backtest on multiple symbols and return sorted results."""
    results = []
    for sym in symbols:
        r = backtest_momentum_strategy(sym, capital)
        if "error" not in r:
            results.append(r)
    results.sort(key=lambda x: x["total_return_pct"], reverse=True)
    return results
