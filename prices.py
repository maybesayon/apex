# ─────────────────────────────────────────────
#  prices.py — Live price fetching via Finnhub
# ─────────────────────────────────────────────

import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta
from config import FINNHUB_API_KEY

_finnhub_client = None

# Symbols that need a different ticker on yfinance (indices use a ^ prefix)
_YF_ALIASES = {"VIX": "^VIX"}


def _get_finnhub():
    """Only create a Finnhub client when a key is configured."""
    global _finnhub_client
    if _finnhub_client is False:
        return None
    if not FINNHUB_API_KEY:
        return None
    if _finnhub_client is None:
        try:
            import finnhub  # type: ignore
        except Exception:
            _finnhub_client = False
            return None
        _finnhub_client = finnhub.Client(api_key=FINNHUB_API_KEY)
    return _finnhub_client


def get_live_quote(symbol: str) -> dict:
    """
    Fetch real-time quote for a symbol from Finnhub.
    Returns dict with price, change, % change, high, low, open, prev close.
    Falls back to yfinance if Finnhub fails.
    """
    fh = _get_finnhub()
    if fh:
        try:
            q = fh.quote(symbol)
            if q and q.get("c", 0) > 0:
                return {
                    "symbol":     symbol,
                    "price":      round(q["c"], 2),
                    "change":     round(q["d"], 2),
                    "pct_change": round(q["dp"], 2),
                    "high":       round(q["h"], 2),
                    "low":        round(q["l"], 2),
                    "open":       round(q["o"], 2),
                    "prev_close": round(q["pc"], 2),
                    "source":     "finnhub",
                }
        except Exception as e:
            print(f"Finnhub failed for {symbol}: {e}")

    # Fallback to yfinance
    try:
        ticker = yf.Ticker(_YF_ALIASES.get(symbol, symbol))
        info = ticker.fast_info
        price = round(float(info.last_price), 2)
        prev  = round(float(info.previous_close), 2)
        chg   = round(price - prev, 2)
        pct   = round((chg / prev) * 100, 2) if prev else 0
        return {
            "symbol":     symbol,
            "price":      price,
            "change":     chg,
            "pct_change": pct,
            "high":       round(float(info.day_high), 2),
            "low":        round(float(info.day_low), 2),
            "open":       round(float(info.open), 2),
            "prev_close": prev,
            "source":     "yfinance",
        }
    except Exception as e:
        print(f"yfinance also failed for {symbol}: {e}")
        return None


def get_multiple_quotes(symbols: list) -> dict:
    """Fetch quotes for a list of symbols. Returns dict keyed by symbol."""
    results = {}
    for sym in symbols:
        q = get_live_quote(sym)
        if q:
            results[sym] = q
    return results


def get_historical_data(symbol: str, period: str = "6mo", interval: str = "1d") -> pd.DataFrame:
    """
    Fetch historical OHLCV data using yfinance.
    period: 1mo, 3mo, 6mo, 1y, 2y
    interval: 1d, 1wk, 1mo
    """
    try:
        ticker = yf.Ticker(_YF_ALIASES.get(symbol, symbol))
        df = ticker.history(period=period, interval=interval)
        df.index = pd.to_datetime(df.index)
        df = df[["Open", "High", "Low", "Close", "Volume"]]
        df.columns = ["open", "high", "low", "close", "volume"]
        return df.dropna()
    except Exception as e:
        print(f"Historical data failed for {symbol}: {e}")
        return pd.DataFrame()


def get_company_profile(symbol: str) -> dict:
    """Fetch company name and basic info from Finnhub."""
    fh = _get_finnhub()
    if not fh:
        return {"name": symbol, "industry": "N/A", "market_cap": 0}
    try:
        profile = fh.company_profile2(symbol=symbol)
        return {
            "name":     profile.get("name", symbol),
            "industry": profile.get("finnhubIndustry", "N/A"),
            "market_cap": profile.get("marketCapitalization", 0),
            "logo":     profile.get("logo", ""),
            "web":      profile.get("weburl", ""),
        }
    except:
        return {"name": symbol, "industry": "N/A", "market_cap": 0}


def format_price(price: float) -> str:
    """Format price as string with $ sign."""
    if price is None:
        return "—"
    if price < 10:
        return f"${price:.2f}"
    elif price < 1000:
        return f"${price:.2f}"
    else:
        return f"${price:,.2f}"


def format_pct(pct: float) -> str:
    """Format percentage change with +/- sign."""
    if pct is None:
        return "—"
    sign = "+" if pct >= 0 else ""
    return f"{sign}{pct:.2f}%"
