"""Opportunity scanner and symbol search."""

import pandas as pd
import pytest

from conftest import assert_golden
import scanner
from scanner import score_opportunity
from symbols import format_symbol, get_symbol_index, resolve_symbol, search_symbols


# ── Scanner ───────────────────────────────────────────────────────────────────

def test_opportunity_golden_aapl(offline):
    r = score_opportunity("AAPL")
    assert r is not None
    assert_golden("opportunity_aapl", {
        k: r[k] for k in ("score", "confidence", "est_move", "entry", "target",
                          "stop", "risk_reward", "rsi", "macd_hist",
                          "vol_ratio", "atr", "tags")
    })


def test_score_is_bounded(offline):
    for sym in ("AAPL", "NVDA", "MSFT"):
        assert 0 <= score_opportunity(sym)["score"] <= 100


def test_exit_levels_are_ordered(offline):
    r = score_opportunity("AAPL")
    assert r["stop"] < r["entry"] < r["target"]


def test_unknown_symbol_returns_none(offline):
    assert score_opportunity("ZZZZQQ") is None


@pytest.mark.parametrize("price", [0, 0.0, None])
def test_zero_price_is_rejected(offline, monkeypatch, price):
    """
    Regression, major: a zero price produced a confident result with a
    negative stop and '+inf-inf%' move, which alerts.py would have emailed
    as a trade recommendation.
    """
    good = scanner.get_live_quote("AAPL")
    monkeypatch.setattr(scanner, "get_live_quote",
                        lambda s: {**good, "price": price})
    assert score_opportunity("AAPL") is None


def test_missing_quote_returns_none(offline, monkeypatch):
    monkeypatch.setattr(scanner, "get_live_quote", lambda s: None)
    assert score_opportunity("AAPL") is None


def test_empty_history_returns_none(offline, monkeypatch):
    monkeypatch.setattr(scanner, "get_historical_data", lambda *a, **k: pd.DataFrame())
    assert score_opportunity("AAPL") is None


def test_run_full_scan_filters_and_sorts(offline):
    results = scanner.run_full_scan(["AAPL", "NVDA", "MSFT"], min_score=0)
    scores = [r["score"] for r in results]
    assert scores == sorted(scores, reverse=True)
    assert all(r["score"] >= 0 for r in results)


def test_min_score_is_respected(offline):
    results = scanner.run_full_scan(["AAPL", "NVDA", "MSFT"], min_score=95)
    assert all(r["score"] >= 95 for r in results)


# ── Symbol search ─────────────────────────────────────────────────────────────

def test_index_is_populated():
    assert len(get_symbol_index()) > 480


@pytest.mark.parametrize("query,expected", [
    ("apple", "AAPL"),
    ("AAPL", "AAPL"),
    ("aapl", "AAPL"),
    ("nvidia", "NVDA"),
    ("tesla", "TSLA"),
    ("robinhood", "HOOD"),
    ("bank of america", "BAC"),
])
def test_search_finds_expected_top_hit(query, expected):
    hits = search_symbols(query, 5)
    assert hits, f"no results for {query!r}"
    assert hits[0][0] == expected, f"{query!r} -> {[t for t, _ in hits]}"


def test_exact_ticker_outranks_name_match():
    assert search_symbols("MU", 3)[0][0] == "MU"


@pytest.mark.parametrize("junk", ["zzzqqq", "!!!!", "1234567890"])
def test_junk_returns_nothing(junk):
    assert search_symbols(junk, 5) == []


@pytest.mark.parametrize("blank", ["", "   ", "\t", "\n", None])
def test_blank_input_resolves_to_none(blank):
    """Regression: whitespace fell through and returned 'A' (Agilent)."""
    assert resolve_symbol(blank) is None


@pytest.mark.parametrize("text,expected", [
    ("AAPL · Apple Inc.", "AAPL"),
    ("NVDA", "NVDA"),
    ("apple", "AAPL"),
])
def test_resolve_symbol(text, expected):
    assert resolve_symbol(text) == expected


@pytest.mark.parametrize("malformed", ["· ", "·", "·AAPL"])
def test_malformed_label_never_returns_empty_ticker(malformed):
    """Regression: these returned '' rather than None."""
    assert resolve_symbol(malformed) in (None, "AAPL")


def test_format_symbol_shape():
    assert format_symbol("AAPL").startswith("AAPL")
    assert "·" in format_symbol("AAPL")


def test_search_result_count_is_capped():
    assert len(search_symbols("a", limit=7)) <= 7
