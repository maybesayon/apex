"""Backtest engine: golden output, internal consistency, look-ahead safety."""

import pandas as pd
import pytest

from conftest import assert_golden, load_fixture
from backtest import backtest_momentum_strategy


def run(symbol="AAPL", **kw):
    return backtest_momentum_strategy(symbol, kw.pop("capital", 1000), **kw)


# ── Golden ────────────────────────────────────────────────────────────────────

def test_backtest_golden_aapl(offline):
    r = run("AAPL")
    assert "error" not in r
    assert_golden("backtest_aapl", {
        k: r[k] for k in ("total_return_pct", "final_capital", "total_pnl",
                          "total_trades", "wins", "losses", "win_rate",
                          "avg_win_pct", "avg_loss_pct", "max_drawdown_pct")
    })


def test_backtest_trades_golden_aapl(offline):
    assert_golden("backtest_trades_aapl", run("AAPL")["trades"])


# ── Consistency ───────────────────────────────────────────────────────────────

def test_summary_matches_trade_log(offline):
    r = run("AAPL")
    wins = [t for t in r["trades"] if t["pnl"] > 0]
    assert r["wins"] == len(wins)
    assert r["losses"] == len(r["trades"]) - len(wins)
    assert r["total_trades"] == len(r["trades"])
    assert abs(len(wins) / len(r["trades"]) * 100 - r["win_rate"]) < 0.11


def test_pnl_agrees_with_return(offline):
    """
    Regression: a position left open at the final bar was excluded from
    total_pnl but marked to market in final_capital, so the two headline
    numbers silently disagreed.
    """
    r = run("AAPL")
    assert abs(r["total_pnl"] - (r["final_capital"] - r["initial_capital"])) < 0.02


def test_each_trade_pnl_matches_prices(offline):
    for t in run("AAPL")["trades"]:
        expected = (t["exit_price"] - t["entry_price"]) * t["shares"]
        # entry_price and exit_price are stored rounded to 2dp while pnl is
        # computed from full precision, so tolerance scales with share count.
        tolerance = 0.02 * t["shares"] + 0.01
        assert abs(t["pnl"] - expected) < tolerance, t


def test_equity_curve_length_matches_bars(offline):
    r = run("AAPL")
    assert len(r["equity_curve"]) == r["diagnostics"]["bars"]


def test_drawdown_in_range(offline):
    assert 0 <= run("AAPL")["max_drawdown_pct"] <= 100


def test_exit_after_entry(offline):
    for t in run("AAPL")["trades"]:
        assert t["exit_date"] >= t["entry_date"]


# ── Look-ahead safety ─────────────────────────────────────────────────────────

def test_future_bars_cannot_change_past_trades(offline, monkeypatch):
    """
    Perturb every bar after a cut point. Trades that closed before the cut
    must be bit-identical, or the strategy is reading the future.
    """
    import backtest as bt
    full = load_fixture("AAPL_2y")
    cut = 300

    baseline = bt.backtest_momentum_strategy("AAPL", 1000)
    before = [t for t in baseline["trades"] if t["exit_date"] < str(full.index[cut].date())]

    tampered = full.copy()
    tampered.iloc[cut:, tampered.columns.get_indexer(["open", "high", "low", "close"])] *= 3.0
    tampered.iloc[cut:, tampered.columns.get_loc("volume")] *= 9.0
    monkeypatch.setattr(bt, "get_historical_data", lambda *a, **k: tampered)

    after = [t for t in bt.backtest_momentum_strategy("AAPL", 1000)["trades"]
             if t["exit_date"] < str(full.index[cut].date())]
    assert before == after, "trades before the cut changed — look-ahead bias"


# ── Parameters and edge cases ─────────────────────────────────────────────────

def test_contradictory_filters_report_why(offline):
    """
    Regression: RSI<45 and a bullish MACD cross never co-occur, so the
    original defaults produced zero trades with no explanation.
    """
    r = run("AAPL", rsi_entry=5)
    assert "error" in r and "MACD" in r["error"]
    assert r["diagnostics"]["macd_crosses"] > 0


def test_capital_too_small_opens_no_empty_position(offline):
    """Regression: int(capital/price)==0 opened a 0-share blocking position."""
    r = run("AAPL", capital=1)
    assert "error" in r or all(t["shares"] >= 1 for t in r.get("trades", []))


@pytest.mark.parametrize("stop,target", [(0.01, 0.05), (0.05, 0.10),
                                         (0.30, 0.50), (0.99, 2.0)])
def test_extreme_parameters_do_not_crash(offline, stop, target):
    r = run("AAPL", stop_loss_pct=stop, take_profit_pct=target)
    assert "error" in r or r["total_trades"] >= 0


def test_insufficient_history(offline, monkeypatch):
    import backtest as bt
    monkeypatch.setattr(bt, "get_historical_data", lambda *a, **k: pd.DataFrame())
    assert "error" in bt.backtest_momentum_strategy("AAPL", 1000)


def test_rsi_entry_changes_trade_count(offline):
    loose = run("AAPL", rsi_entry=85)
    tight = run("AAPL", rsi_entry=50)
    lo = loose.get("total_trades", 0)
    ti = tight.get("total_trades", 0)
    assert lo >= ti, "a looser RSI ceiling should not yield fewer trades"
