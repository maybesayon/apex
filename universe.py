# ─────────────────────────────────────────────
#  universe.py — Broad Scan Universe
#  S&P 500 constituents + cheap pre-filter so the
#  full TA scan only runs on the liveliest names.
# ─────────────────────────────────────────────

import json
import os
import time
from io import StringIO

import pandas as pd
import requests
import yfinance as yf

from config import SCAN_UNIVERSE, SP500_CACHE_FILE

SP500_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
SP500_CACHE_SECS = 7 * 24 * 3600  # constituents rarely change; refresh weekly

# Pre-filter thresholds
MIN_PRICE = 3.0
MIN_DOLLAR_VOLUME = 5_000_000  # avg $ traded per day


def _load_cache() -> dict | None:
    if not os.path.exists(SP500_CACHE_FILE):
        return None
    try:
        with open(SP500_CACHE_FILE) as f:
            return json.load(f)
    except Exception:
        return None


def _fetch_sp500_table() -> dict | None:
    """
    Scrape the S&P 500 constituent table into {ticker: company name}.
    Returns None on any failure so callers can fall back.
    """
    try:
        # Fetch via requests (bundled CA certs) — urllib lacks them on
        # framework Python builds, so pd.read_html(url) fails on SSL.
        resp = requests.get(SP500_URL, headers={"User-Agent": "apex-scanner/1.0"}, timeout=15)
        resp.raise_for_status()
        table = pd.read_html(StringIO(resp.text))[0]
        names = {}
        for sym, sec in zip(table["Symbol"], table["Security"]):
            # yfinance wants BRK-B, not BRK.B
            t = str(sym).replace(".", "-").strip()
            if t and t != "nan":
                names[t] = str(sec).strip()
        return names or None
    except Exception as e:
        print(f"S&P 500 fetch failed: {e}")
        return None


def get_sp500_names() -> dict[str, str]:
    """
    {ticker: company name} for the S&P 500, cached locally for a week.
    Falls back to a stale cache, then to SCAN_UNIVERSE with bare tickers.
    """
    cached = _load_cache()
    if cached and time.time() - cached.get("fetched_at", 0) < SP500_CACHE_SECS:
        if cached.get("names"):
            return cached["names"]
        # Older cache format stored tickers only — refetch to pick up names
    names = _fetch_sp500_table()
    if names:
        try:
            with open(SP500_CACHE_FILE, "w") as f:
                json.dump({
                    "fetched_at": time.time(),
                    "tickers": sorted(names),
                    "names": names,
                }, f)
        except Exception:
            pass
        return names

    if cached:  # stale beats nothing
        if cached.get("names"):
            return cached["names"]
        return {t: t for t in cached.get("tickers", [])}
    return {t: t for t in SCAN_UNIVERSE}


def get_sp500_tickers() -> list[str]:
    """S&P 500 tickers, cached locally for a week."""
    return sorted(get_sp500_names())


def prefilter_universe(symbols: list[str], top_n: int = 40) -> list[str]:
    """
    Cheap first pass over a large universe: one batched download of a
    month of daily bars, then rank by momentum + unusual volume.
    Only the top_n names go on to the full (slow) TA scan.
    """
    data = yf.download(
        symbols, period="1mo", interval="1d",
        group_by="ticker", threads=True, progress=False,
    )
    if data is None or data.empty:
        return symbols[:top_n]

    rows = []
    for sym in symbols:
        try:
            df = data[sym].dropna() if isinstance(data.columns, pd.MultiIndex) else data.dropna()
            if len(df) < 10:
                continue
            close, volume = df["Close"], df["Volume"]
            price = float(close.iloc[-1])
            dollar_vol = float((close * volume).mean())
            if price < MIN_PRICE or dollar_vol < MIN_DOLLAR_VOLUME:
                continue

            ret_1d = float(close.iloc[-1] / close.iloc[-2] - 1) * 100
            ret_5d = float(close.iloc[-1] / close.iloc[-6] - 1) * 100 if len(close) > 5 else 0.0
            vol_ratio = float(volume.iloc[-1] / volume.mean()) if volume.mean() > 0 else 1.0

            # Heuristic ranking: reward recent jumps and unusual volume —
            # the "daily price jump" signal from the catalyst plan.
            heat = 2 * ret_1d + ret_5d + 3 * max(vol_ratio - 1, 0)
            rows.append((sym, heat))
        except Exception:
            continue

    rows.sort(key=lambda x: x[1], reverse=True)
    return [sym for sym, _ in rows[:top_n]]


def get_broad_universe(top_n: int = 40) -> list[str]:
    """S&P 500 + personal universe, pre-filtered to the hottest top_n."""
    combined = sorted(set(get_sp500_tickers()) | set(SCAN_UNIVERSE))
    return prefilter_universe(combined, top_n=top_n)
